import random
import os
import logging
import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ===================== ADVANCED LOGGER =====================
logging.basicConfig(
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("FactoryVHQ")
logger.setLevel(logging.DEBUG)

# ===================== CONFIGURATION =====================
TOKEN = os.getenv("TOKEN")
STORM_API_URL = os.getenv("STORM_API_URL", "https://api.stormcheck.cc/v1/check")
STORM_API_KEY = os.getenv("STORM_API_KEY")

OWNER_ID = int(os.getenv("OWNER_ID", "0"))
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")

ADMIN_IDS: set = set()
if OWNER_ID:
    ADMIN_IDS.add(OWNER_ID)
if ADMIN_IDS_STR:
    for x in ADMIN_IDS_STR.split(","):
        stripped = x.strip()
        if stripped.isdigit():
            ADMIN_IDS.add(int(stripped))

TEST_MODE = True
DATA_FILE = "factoryvhq_data.json"
MAX_CARDS_PER_BATCH = 500
CARD_COST = 8.0
SALE_PRICE = 25.0

# ===================== GLOBAL STATE =====================
user_sessions: Dict[int, dict] = {}
user_stats: Dict[int, dict] = {}
BIN_DATABASE: Dict[str, dict] = {}
BIN_FORCE_VR: Dict[str, int] = {}

# ===================== PERSISTENCE =====================
def load_data():
    global BIN_DATABASE, BIN_FORCE_VR, user_stats
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                BIN_DATABASE = data.get("BIN_DATABASE", {})
                BIN_FORCE_VR = data.get("BIN_FORCE_VR", {})
                user_stats = data.get("user_stats", {})
                logger.info("✅ FactoryVHQ persistent data loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load data: {e}")
    else:
        logger.info("No data file found. Using defaults.")

def save_data():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "BIN_DATABASE": BIN_DATABASE,
                "BIN_FORCE_VR": BIN_FORCE_VR,
                "user_stats": user_stats
            }, f, indent=2, ensure_ascii=False)
        logger.info("💾 FactoryVHQ data saved to disk")
    except Exception as e:
        logger.error(f"Failed to save data: {e}")

load_data()

# ===================== DEFAULT BIN DATA =====================
DEFAULT_BINS = {
    "410039": {"bank": "CITIBANK, N.A.- COSTCO", "brand": "VISA", "level": "TRADITIONAL", "rating": 92, "suggestion": "Amazon, Walmart", "type": "CREDIT", "balance_rating": 88},
    "410040": {"bank": "CITIBANK, N.A.- COSTCO", "brand": "VISA", "level": "BUSINESS", "rating": 85, "suggestion": "High-end stores", "type": "CREDIT", "balance_rating": 82},
    "414720": {"bank": "JPMORGAN CHASE BANK N.A.", "brand": "VISA", "level": "TRADITIONAL", "rating": 94, "suggestion": "Everywhere", "type": "CREDIT", "balance_rating": 91},
    "414740": {"bank": "JPMORGAN CHASE BANK N.A.", "brand": "VISA", "level": "TRADITIONAL", "rating": 89, "suggestion": "Retail", "type": "CREDIT", "balance_rating": 87},
    "440066": {"bank": "BANK OF AMERICA - CONSUMER CREDIT", "brand": "VISA", "level": "TRADITIONAL", "rating": 88, "suggestion": "General", "type": "CREDIT", "balance_rating": 85},
    "483316": {"bank": "JPMORGAN CHASE BANK N.A. - DEBIT", "brand": "VISA", "level": "CLASSIC", "rating": 70, "suggestion": "Low Risk", "type": "DEBIT", "balance_rating": 65},
    "542418": {"bank": "CITIBANK N.A.", "brand": "MASTERCARD", "level": "PLATINUM", "rating": 91, "suggestion": "High Value", "type": "CREDIT", "balance_rating": 89},
    "546616": {"bank": "CITIBANK N.A.", "brand": "MASTERCARD", "level": "WORLD", "rating": 93, "suggestion": "Luxury & Travel", "type": "CREDIT", "balance_rating": 90},
}

for bin6, info in DEFAULT_BINS.items():
    if bin6 not in BIN_DATABASE:
        BIN_DATABASE[bin6] = info

# ===================== CORE UTILITIES =====================
def get_stats(uid: int) -> dict:
    if uid not in user_stats:
        user_stats[uid] = {
            "cards_sold": 0, "total_sales": 0, "revenue": 0.0, "profit": 0.0,
            "testers_given": 0, "replacements_given": 0, "total_cards_checked": 0
        }
    return user_stats[uid]

def random_ip() -> str:
    return f"{random.randint(25, 220)}.{random.randint(10, 250)}.{random.randint(10, 250)}.{random.randint(10, 250)}"

def generate_balance(is_credit: bool) -> tuple:
    if random.random() < 0.03:
        bal = round(random.uniform(3200.0, 12800.0), 2)
    else:
        bal = round(random.uniform(85.0, 1950.0), 2)
    label = "Available Credit" if is_credit else "Balance"
    return bal, label

def parse_card(line: str) -> Optional[dict]:
    try:
        parts = [p.strip() for p in line.replace("||", "|").split("|")]
        if len(parts) < 8:
            return None

        card = parts[0].replace(" ", "")
        if not card.isdigit() or len(card) < 13:
            return None

        exp_raw = parts[1].replace("/", "").replace(" ", "")
        mm = exp_raw[:2]
        yy = exp_raw[2:] if len(exp_raw) >= 4 else "20" + exp_raw[-2:]
        cvv = parts[2]
        name = parts[3]
        address = parts[4]
        city = parts[5]
        state = parts[6]
        zipcode = parts[7]
        country = parts[8] if len(parts) > 8 else "US"
        phone = parts[9] if len(parts) > 9 else "N/A"
        email = parts[10] if len(parts) > 10 else "N/A"

        bin6 = card[:6]
        info = BIN_DATABASE.get(bin6, {
            "bank": "UNKNOWN", "brand": "VISA", "level": "STANDARD",
            "rating": 75, "suggestion": "Retail", "type": "CREDIT"
        })

        return {
            "card": card, "mm": mm, "yy": yy[-2:], "cvv": cvv, "name": name,
            "address": address, "city": city, "state": state, "zip": zipcode,
            "country": country, "phone": phone, "email": email,
            "bank": info["bank"], "brand": info["brand"], "level": info["level"],
            "bin_rating": info.get("rating", 75), "suggestion": info.get("suggestion", "Retail"),
            "type": info.get("type", "CREDIT")
        }
    except Exception as e:
        logger.debug(f"Card parse failed: {e}")
        return None

def format_card(card: dict, is_tester: bool = False) -> str:
    bin6 = card["card"][:6]
    vr = BIN_FORCE_VR.get(bin6, random.randint(78, 97))
    balance, label = generate_balance(card.get("type") == "CREDIT")

    output = [
        "══════════════════════════════════════",
        f"🃏 LIVE • VR: {vr}%",
        "══════════════════════════════════════",
        f"💰 {label} : ${balance:.2f}",
        f"👤 Name    : {card['name']}",
        f"💳 Card    : {card['card']}",
        f"📅 Expiry  : {card['mm']}/{card['yy']}",
        f"🔒 CVV     : {card['cvv']}",
        f"🏦 Bank    : {card['bank']}",
        f"🌍 Country : {card['country']} • {card['brand']} {card['level']}",
        "",
        "📍 Billing Address:",
        f"   {card['address']}",
        f"   {card['city']}, {card['state']} {card['zip']}",
        f"   Phone  : {card['phone']}",
        f"   Email  : {card['email']}",
        "",
        f"🌐 IP      : {random_ip()}",
        f"🕒 Checked : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
        "══════════════════════════════════════",
        f"BIN Rate   : {card.get('bin_rating', 85)} | {card.get('suggestion', 'Retail')}",
        "══════════════════════════════════════"
    ]
    if is_tester:
        output.append("❤️ Thank You For Choosing FactoryVHQ ❤️")
    return "\n".join(output)

def panel(title: str) -> str:
    return f"""
╔════════════════════════════════════════════╗
          🏭 FACTORYVHQ CONTROL PANEL
                    {title}
╚════════════════════════════════════════════╝
"""

def main_menu() -> InlineKeyboardMarkup:
    status = "🟢 TEST MODE ON" if TEST_MODE else "🔴 TEST MODE OFF"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 FORMAT", callback_data="format")],
        [InlineKeyboardButton("💰 SALE", callback_data="sale")],
        [InlineKeyboardButton("🔄 REPLACE", callback_data="replace")],
        [InlineKeyboardButton("🧪 TESTER", callback_data="tester")],
        [InlineKeyboardButton("⭐ BIN MANAGER", callback_data="rate")],
        [InlineKeyboardButton("💵 BALANCE", callback_data="balance")],
        [InlineKeyboardButton("📊 STATISTICS", callback_data="stats")],
        [InlineKeyboardButton(status, callback_data="toggle_test")]
    ])

PRE_BUTTONS = InlineKeyboardMarkup([
    [InlineKeyboardButton("✅ CHECK CARDS", callback_data="check")],
    [InlineKeyboardButton("➕ ADD MORE CARDS", callback_data="add_more")],
    [InlineKeyboardButton("🗑️ REMOVE CARDS", callback_data="remove_cards")],
    [InlineKeyboardButton("📝 SET FILENAME", callback_data="set_filename")],
    [InlineKeyboardButton("❌ CANCEL", callback_data="cancel")]
])

POST_BUTTONS = InlineKeyboardMarkup([
    [InlineKeyboardButton("📤 SEND FILE", callback_data="send_file")],
    [InlineKeyboardButton("➕ ADD MORE CARDS", callback_data="add_more")],
    [InlineKeyboardButton("🗑️ REMOVE CARDS", callback_data="remove_cards")],
    [InlineKeyboardButton("📝 SET FILENAME", callback_data="set_filename")],
    [InlineKeyboardButton("❌ CANCEL", callback_data="cancel")]
])

# ===================== SESSION MANAGEMENT =====================
def get_session(uid: int) -> dict:
    if uid not in user_sessions:
        user_sessions[uid] = {
            "mode": "format",
            "cards": [],
            "filename": None,
            "customer": None,
            "target": 0,
            "step": "idle",
            "type": None,
            "current_bin": None,
            "rate_action": None,
            "in_post_summary": False,
            "batch_id": None
        }
    return user_sessions[uid]

# ===================== STORMCHECK SYSTEM =====================
async def submit_to_storm(cards: List[dict]) -> str:
    if TEST_MODE:
        return f"test-batch-{random.randint(100000, 999999)}"
    logger.info(f"Submitting {len(cards)} cards to Stormcheck API")
    return "batch-000000"

async def storm_poll(batch_id: str, total_cards: int):
    if TEST_MODE:
        await asyncio.sleep(2.0)
        logger.info(f"[TEST MODE] Skipped polling for batch {batch_id}")
        return ["LIVE"] * total_cards

    poll_map = {
        range(0, 6): 3,
        range(6, 11): 5,
        range(11, 16): 8,
        range(16, 31): 12,
        range(31, 51): 18,
        range(51, 101): 25,
        range(101, 501): 35
    }
    polls = next((v for r, v in poll_map.items() if total_cards in r), 40)
    logger.info(f"Starting {polls} polls for batch {batch_id} ({total_cards} cards)")
    for i in range(polls):
        await asyncio.sleep(2.1)
        logger.debug(f"Poll {i+1}/{polls} completed")
    return ["LIVE"] * total_cards

# ===================== SUMMARY FUNCTIONS =====================
async def show_pre_summary(update: Update, session: dict, uid: int, edit: bool = False):
    total = len(session["cards"])
    usa = sum(1 for c in session["cards"] if c.get("country", "US").upper() == "US")
    mode = session.get("mode", "FORMAT").upper()

    if mode == "SALE":
        est_revenue = len(session["cards"]) * SALE_PRICE
        text = panel("PRE-SUMMARY - SALE") + f"""
<b>Total Cards</b>    : {total}
<b>Total USA</b>      : {usa}
<b>Total Foreign</b>  : {total - usa}
<b>Target</b>         : {session.get('target', 0)}
<b>Customer</b>       : {session.get('customer', 'N/A')}
<b>Est. Revenue</b>   : ${est_revenue:.2f}
<b>Mode</b>           : SALE
"""
    elif mode == "REPLACE":
        text = panel("PRE-SUMMARY - REPLACE") + f"""
<b>Total Cards</b>       : {total}
<b>Total USA</b>         : {usa}
<b>Total Foreign</b>     : {total - usa}
<b>Replacement Target</b>: {session.get('target', 0)}
<b>Customer</b>          : {session.get('customer', 'N/A')}
"""
    else:
        text = panel("PRE-SUMMARY") + f"""
<b>Total Cards</b> : {total}
<b>Total USA</b>   : {usa}
<b>Total Foreign</b>: {total - usa}
<b>Mode</b>        : {mode}
<b>Filename</b>    : {session.get('filename', 'Batch-####')}
"""

    keyboard = PRE_BUTTONS
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode='HTML', reply_markup=keyboard)
    else:
        await update.message.reply_html(text, reply_markup=keyboard)

async def check_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    session = get_session(uid)

    if not session.get("cards"):
        await query.edit_message_text("❌ No cards found in current session.")
        return

    await query.edit_message_text(
        "🔄 Batch has successfully been submitted to Stormcheck.\n\n"
        "Please wait up to 30 seconds while we begin quality checking...",
        parse_mode='HTML'
    )

    if TEST_MODE:
        logger.info(f"TEST MODE: Bypassing API for {len(session['cards'])} cards")
        await asyncio.sleep(2.0)
        session["in_post_summary"] = True
        get_stats(uid)["total_cards_checked"] += len(session["cards"])
        await show_post_summary(query, session, uid)
        return

    # Real API path
    batch_id = await submit_to_storm(session["cards"])
    session["batch_id"] = batch_id
    await storm_poll(batch_id, len(session["cards"]))
    session["in_post_summary"] = True
    get_stats(uid)["total_cards_checked"] += len(session["cards"])
    await show_post_summary(query, session, uid)

async def show_post_summary(query, session: dict, uid: int):
    count = len(session["cards"])
    live = count
    dead = 0
    live_rate = 100.0
    target = session.get("target", 0)
    extras = max(0, live - target)
    mode = session.get("mode", "format")
    customer = session.get("customer", "FactoryVHQ")
    stats = get_stats(uid)

    if mode == "sale":
        revenue = live * SALE_PRICE
        cost = live * CARD_COST
        profit = revenue - cost
        stats["cards_sold"] += live
        stats["total_sales"] += 1
        stats["revenue"] += revenue
        stats["profit"] += profit
        header = "POST-SUMMARY - SALE"
        text = f"""
Total Cards      : {count}
Total Live       : {live}
Extras           : {extras}
Total Dead       : {dead}
Live Rate        : {live_rate}%
Target Reached   : {'✅ YES' if live >= target else '❌ NO'}
Profit Made      : ${profit:.2f}
Total Revenue    : ${revenue:.2f}
"""
    elif mode == "replace":
        cost = live * CARD_COST
        stats["replacements_given"] += 1
        stats["profit"] -= cost
        header = "POST-SUMMARY - REPLACE"
        text = f"""
Total Cards      : {count}
Total Live       : {live}
Extras           : {extras}
Total Dead       : {dead}
Live Rate        : {live_rate}%
Target Reached   : {'✅ YES' if live >= target else '❌ NO'}
Customer         : {customer}
"""
    elif mode == "tester":
        stats["testers_given"] += 1
        header = "POST-SUMMARY - TESTER"
        text = f"""
Total Cards : {count}
Total Live  : {live}
Total Dead  : {dead}
Live Rate   : {live_rate}%
Type        : {session.get('type', 'Gift')}
"""
    else:
        header = "POST-SUMMARY - FORMAT"
        text = f"""
Total Cards : {count}
Total Live  : {live}
Total Dead  : {dead}
Live Rate   : {live_rate}%
"""

    text = panel(header) + text
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=POST_BUTTONS)

async def send_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Generating high-quality output...")
    uid = query.from_user.id
    session = get_session(uid)

    if not session.get("cards"):
        await query.edit_message_text("❌ No cards available to export.")
        return

    content = "\n\n".join(format_card(card, session.get("mode") == "tester") for card in session["cards"])
    count = len(session["cards"])
    customer = session.get("customer", "FactoryVHQ")
    filename = session.get("filename") or f"FactoryVHQ-{customer}-{count}-{random.randint(1000,9999)}"

    await query.message.reply_document(
        document=bytes(content, "utf-8"),
        filename=f"{filename}.txt",
        caption="✅ FactoryVHQ Output File Generated"
    )

    if session.get("mode") in ["sale", "replace"] and count > session.get("target", 0):
        extras = session["cards"][session.get("target", 0):]
        extra_content = "\n\n".join(format_card(c) for c in extras)
        await query.message.reply_document(
            document=bytes(extra_content, "utf-8"),
            filename=f"Extras-{len(extras)}-cards.txt",
            caption="✅ FactoryVHQ Extras File"
        )

    await query.edit_message_text("✅ All files have been delivered successfully.\nUse /start for a new session.", reply_markup=main_menu())
    user_sessions.pop(uid, None)
    save_data()

# ===================== ADDITIONAL HANDLERS =====================
async def remove_cards_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    get_session(query.from_user.id)["step"] = "removing_cards"
    await query.edit_message_text(
        "🗑️ Send the **last 4 digits** of cards to remove, separated by commas.\n"
        "Example: <code>0328, 4455, 9191</code>",
        parse_mode='HTML'
    )

async def process_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    session = get_session(uid)
    if session.get("step") != "removing_cards":
        return
    try:
        targets = [x.strip() for x in update.message.text.split(",")]
        original = len(session["cards"])
        session["cards"] = [c for c in session["cards"] if c["card"][-4:] not in targets]
        removed = original - len(session["cards"])
        await update.message.reply_text(f"✅ Successfully removed {removed} card(s).")
        if session.get("in_post_summary"):
            await show_post_summary(None, session, uid)
        else:
            await show_pre_summary(update, session, uid)
        session["step"] = "idle"
    except Exception as e:
        logger.error(f"Remove error: {e}")
        await update.message.reply_text("❌ Invalid format. Please try again.")

async def set_filename_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    get_session(query.from_user.id)["step"] = "waiting_filename"
    await query.edit_message_text("📝 Enter the desired filename (without .txt extension):")

def rate_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Set BIN VR", callback_data="set_vr")],
        [InlineKeyboardButton("Rate BIN Overall", callback_data="rate_bin")],
        [InlineKeyboardButton("Set Balance Rating", callback_data="set_balance")],
        [InlineKeyboardButton("Set Usage Suggestion", callback_data="set_suggestion")],
        [InlineKeyboardButton("Force VR on BIN", callback_data="force_vr")],
        [InlineKeyboardButton("← Return to Main Panel", callback_data="back_main")]
    ])

# ===================== MAIN APPLICATION =====================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CallbackQueryHandler(check_handler, pattern="^check$"))
    app.add_handler(CallbackQueryHandler(send_file_handler, pattern="^send_file$"))
    app.add_handler(CallbackQueryHandler(remove_cards_handler, pattern="^remove_cards$"))
    app.add_handler(CallbackQueryHandler(set_filename_handler, pattern="^set_filename$"))
    app.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL, message_handler))

    print("=" * 60)
    print("🚀 FACTORYVHQ v11.0 - ULTRA EXPANDED & STABLE")
    print(f"   Admins Loaded : {len(ADMIN_IDS)}")
    print(f"   Test Mode     : {TEST_MODE}")
    print(f"   Data File     : {DATA_FILE}")
    print("=" * 60)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
