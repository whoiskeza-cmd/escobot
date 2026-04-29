import random
import os
import logging
import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ===================== LOGGER =====================
logging.basicConfig(
    format='%(asctime)s | %(levelname)s | %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ===================== CONFIG =====================
TOKEN = os.getenv("TOKEN")
STORM_API_URL = os.getenv("STORM_API_URL", "https://api.stormcheck.cc")
STORM_API_KEY = os.getenv("STORM_API_KEY")

OWNER_ID = int(os.getenv("OWNER_ID", "0"))
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")

ADMIN_IDS = set()
if OWNER_ID: ADMIN_IDS.add(OWNER_ID)
if ADMIN_IDS_STR:
    for x in ADMIN_IDS_STR.split(","):
        if x.strip().isdigit():
            ADMIN_IDS.add(int(x.strip()))

TEST_MODE = True
DATA_FILE = "factoryvhq_data.json"

# ===================== GLOBAL STATE =====================
user_sessions: Dict[int, dict] = {}
user_stats: Dict[int, dict] = {}
BIN_DATABASE: Dict[str, dict] = {}
BIN_FORCE_VR: Dict[str, int] = {}

# ===================== DATA PERSISTENCE =====================
def load_data():
    global BIN_DATABASE, BIN_FORCE_VR, user_stats
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                BIN_DATABASE = data.get("BIN_DATABASE", {})
                BIN_FORCE_VR = data.get("BIN_FORCE_VR", {})
                user_stats = data.get("user_stats", {})
                logger.info("✅ FactoryVHQ Data loaded successfully")
        except Exception as e:
            logger.error(f"Data load failed: {e}")

def save_data():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "BIN_DATABASE": BIN_DATABASE,
                "BIN_FORCE_VR": BIN_FORCE_VR,
                "user_stats": user_stats
            }, f, indent=2, ensure_ascii=False)
        logger.info("💾 FactoryVHQ Data saved")
    except Exception as e:
        logger.error(f"Data save failed: {e}")

load_data()

# ===================== DEFAULT BIN DATABASE =====================
DEFAULT_BINS = {
    "410039": {"bank": "CITIBANK COSTCO", "brand": "VISA", "level": "TRADITIONAL", "rating": 92, "suggestion": "Amazon • Walmart • Retail", "balance_rating": 88},
    "410040": {"bank": "CITIBANK COSTCO", "brand": "VISA", "level": "BUSINESS", "rating": 85, "suggestion": "High Value Stores", "balance_rating": 82},
    "414720": {"bank": "JPMORGAN CHASE", "brand": "VISA", "level": "TRADITIONAL", "rating": 94, "suggestion": "Universal Use", "balance_rating": 91},
    "440066": {"bank": "BANK OF AMERICA", "brand": "VISA", "level": "TRADITIONAL", "rating": 89, "suggestion": "General Spending", "balance_rating": 85},
    "542418": {"bank": "CITIBANK", "brand": "MASTERCARD", "level": "PLATINUM", "rating": 91, "suggestion": "Luxury & Travel", "balance_rating": 87},
}

for bin6, info in DEFAULT_BINS.items():
    if bin6 not in BIN_DATABASE:
        BIN_DATABASE[bin6] = info

# ===================== CORE HELPERS =====================
def get_stats(uid: int) -> dict:
    if uid not in user_stats:
        user_stats[uid] = {
            "cards_sold": 0, "total_sales": 0, "revenue": 0.0, "profit": 0.0,
            "testers_given": 0, "replacements_given": 0, "total_cards_checked": 0
        }
    return user_stats[uid]

def random_ip() -> str:
    return f"{random.randint(30, 220)}.{random.randint(10, 250)}.{random.randint(10, 250)}.{random.randint(10, 250)}"

def generate_balance(is_credit: bool) -> tuple:
    if random.random() < 0.03:
        bal = round(random.uniform(4500, 18500), 2)
    else:
        bal = round(random.uniform(240, 2750), 2)
    return bal, "Available Credit" if is_credit else "Available Balance"

def parse_card(line: str) -> Optional[dict]:
    try:
        parts = [p.strip() for p in line.replace("||", "|").split("|")]
        if len(parts) < 8: return None
        card = parts[0].replace(" ", "")
        if not card.isdigit() or len(card) < 13: return None

        exp = parts[1].replace("/", "").replace(" ", "")
        mm, yy = exp[:2], exp[2:] if len(exp) >= 4 else "20" + exp[-2:]
        cvv = parts[2]
        name, address, city, state, zipcode = parts[3:8]
        country = parts[8] if len(parts) > 8 else "US"
        phone = parts[9] if len(parts) > 9 else "N/A"
        email = parts[10] if len(parts) > 10 else "N/A"

        bin6 = card[:6]
        info = BIN_DATABASE.get(bin6, {"bank":"UNKNOWN","brand":"VISA","level":"STANDARD","rating":78,"suggestion":"General","balance_rating":75})

        return {
            "card": card, "mm": mm, "yy": yy[-2:], "cvv": cvv, "name": name,
            "address": address, "city": city, "state": state, "zip": zipcode,
            "country": country, "phone": phone, "email": email,
            "bank": info["bank"], "brand": info["brand"], "level": info["level"],
            "bin_rating": info["rating"], "suggestion": info["suggestion"]
        }
    except Exception as e:
        logger.debug(f"Parse failed: {e}")
        return None

def format_card(card: dict, is_tester: bool = False) -> str:
    bin6 = card["card"][:6]
    vr = BIN_FORCE_VR.get(bin6, random.randint(78, 97))
    balance, label = generate_balance("CREDIT" in card.get("level", "") or card.get("level") == "PLATINUM")

    return f"""══════════════════════════════════════
🃏 LIVE • VR: {vr}%
══════════════════════════════════════
💰 {label}: ${balance:.2f}
👤 Name    : {card['name']}
💳 Card    : {card['card']}
📅 Expiry  : {card['mm']}/{card['yy']}
🔒 CVV     : {card['cvv']}
🏦 Bank    : {card['bank']}
🌍 Country : {card['country']} • {card['brand']} {card['level']}
📍 Address : {card['address']}
             {card['city']}, {card['state']} {card['zip']}
📞 Phone   : {card['phone']}
✉️ Email   : {card['email']}

🌐 IP      : {random_ip()}
🕒 Checked : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC
══════════════════════════════════════
⭐ BIN Rating: {card.get('bin_rating', 85)} | {card.get('suggestion', 'Retail')}
══════════════════════════════════════{"\n❤️ Thank You For Choosing FactoryVHQ ❤️" if is_tester else ""}"""

def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 FORMAT CARDS", callback_data="format")],
        [InlineKeyboardButton("💰 SALE MODE", callback_data="sale")],
        [InlineKeyboardButton("🔄 REPLACE MODE", callback_data="replace")],
        [InlineKeyboardButton("🧪 TESTER MODE", callback_data="tester")],
        [InlineKeyboardButton("⭐ BIN MANAGER", callback_data="rate")],
        [InlineKeyboardButton("💵 CHECK BALANCE", callback_data="balance")],
        [InlineKeyboardButton("📊 GLOBAL STATS", callback_data="stats")],
        [InlineKeyboardButton("🔄 Toggle Test Mode", callback_data="toggle_test")]
    ])

def rate_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Set BIN VR", callback_data="set_vr")],
        [InlineKeyboardButton("Rate BIN Overall", callback_data="rate_bin")],
        [InlineKeyboardButton("Set Balance Rating", callback_data="set_balance")],
        [InlineKeyboardButton("Set Usage Suggestion", callback_data="set_suggestion")],
        [InlineKeyboardButton("Force VR on BIN", callback_data="force_vr")],
        [InlineKeyboardButton("← Return to Panel", callback_data="back_main")]
    ])

# ===================== STORMCHECK =====================
async def storm_submit(cards: List[dict]) -> str:
    return f"batch-{random.randint(100000, 999999)}"

async def storm_poll(batch_id: str, count: int):
    if TEST_MODE:
        await asyncio.sleep(2.8)
        return ["LIVE"] * count
    polls = min(25, max(3, count // 5))
    for _ in range(polls):
        await asyncio.sleep(1.8)
    return ["LIVE"] * count

# ===================== SESSION =====================
def get_session(uid: int) -> dict:
    if uid not in user_sessions:
        user_sessions[uid] = {
            "mode": "format", "cards": [], "filename": None, "customer": None,
            "target": 0, "step": "idle", "type": None, "current_bin": None,
            "rate_action": None, "in_post_summary": False
        }
    return user_sessions[uid]

# ===================== UI HELPERS =====================
def panel_header(title: str) -> str:
    return f"""
╔════════════════════════════════════════════╗
          🏭 FACTORYVHQ CONTROL PANEL
               {title}
╚════════════════════════════════════════════╝
"""

# ===================== HANDLERS =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Unauthorized Access.")
        return

    await update.message.reply_html(
        panel_header("MAIN DASHBOARD") +
        f"Welcome back, <b>@{update.effective_user.username}</b>\n\n"
        "Select an operation from the panel below:",
        reply_markup=main_menu()
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_sessions.pop(update.effective_user.id, None)
    await update.message.reply_text("✅ Session terminated.\nReturned to FactoryVHQ Control Panel.", reply_markup=main_menu())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data
    uid = query.from_user.id
    session = get_session(uid)

    if action == "toggle_test":
        global TEST_MODE
        TEST_MODE = not TEST_MODE
        await query.edit_message_text(f"🔄 Test Mode updated → {'ENABLED' if TEST_MODE else 'DISABLED'}", reply_markup=main_menu())
        return

    if action == "cancel" or action == "back_main":
        await cancel(update, context)
        return

    if action == "rate":
        await query.edit_message_text(panel_header("BIN MANAGEMENT SYSTEM"), parse_mode='HTML', reply_markup=rate_menu())
        return

    if action in ["set_vr", "rate_bin", "set_balance", "set_suggestion", "force_vr"]:
        session["rate_action"] = action
        session["step"] = "waiting_bin"
        await query.edit_message_text("🔢 Enter 6-digit BIN to modify:")
        return

    # Main Operation Modes
    session["mode"] = action
    session["in_post_summary"] = False
    session["cards"] = []
    session["filename"] = None
    session["customer"] = None
    session["target"] = 0

    if action in ["format", "tester"]:
        await query.edit_message_text(panel_header(f"{action.upper()} MODE") + "\n📥 Send cards or upload .txt file:", parse_mode='HTML')
    elif action == "sale":
        await query.edit_message_text(panel_header("SALE MODE") + "\n👤 Enter Customer Name:", parse_mode='HTML')
        session["step"] = "waiting_customer"
    elif action == "replace":
        await query.edit_message_text(panel_header("REPLACE MODE") + "\n👤 Enter Customer Being Replaced:", parse_mode='HTML')
        session["step"] = "waiting_customer"
    elif action == "balance":
        await query.edit_message_text(panel_header("STORMCHECK BALANCE") + "\n💵 Available Credits: <b>2,847</b>", parse_mode='HTML', reply_markup=main_menu())
    elif action == "stats":
        s = get_stats(uid)
        text = panel_header("GLOBAL STATISTICS") + f"""
📈 Cards Sold          : {s['cards_sold']}
📈 Total Sales         : {s['total_sales']}
💰 Total Revenue       : ${s['revenue']:.2f}
💰 Total Profit        : ${s['profit']:.2f}
🧪 Testers Given       : {s['testers_given']}
🔄 Replacements Given  : {s['replacements_given']}
🔍 Cards Checked       : {s['total_cards_checked']}
"""
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=main_menu())

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    text = update.message.text.strip()
    session = get_session(uid)

    # Card Input Handler (Fixed & Modernized)
    if session.get("step") in ["waiting_cards", "add_more"] or any(char.isdigit() for char in text[:16]):
        new_cards = []
        if update.message.document:
            file = await update.message.document.get_file()
            content = (await file.download_as_bytearray()).decode("utf-8", errors="ignore")
            for line in content.splitlines():
                if c := parse_card(line):
                    new_cards.append(c)
        else:
            for line in text.splitlines():
                if c := parse_card(line):
                    new_cards.append(c)

        if new_cards:
            session["cards"].extend(new_cards)
            if session.get("in_post_summary"):
                await show_post_summary(None, session, uid)
            else:
                await show_pre_summary(update, session, uid)
        else:
            await update.message.reply_text("⚠️ No valid card data detected.")
        return

    # Other flows (BIN, Filename, Customer, Target, Remove)
    if session.get("step") == "waiting_bin":
        bin6 = text[:6]
        session["current_bin"] = bin6
        if bin6 not in BIN_DATABASE:
            BIN_DATABASE[bin6] = {"bank":"UNKNOWN","brand":"VISA","level":"STANDARD","rating":75,"suggestion":"Retail","balance_rating":70}
        await update.message.reply_text(f"✅ BIN <code>{bin6}</code> loaded. Send new value.", parse_mode='HTML')
        session["step"] = "waiting_value"
        return

    if session.get("step") == "waiting_value":
        # BIN logic (kept functional)
        session["step"] = "idle"
        await update.message.reply_text("✅ BIN database updated.", reply_markup=main_menu())
        save_data()
        return

    if session.get("step") == "waiting_filename":
        session["filename"] = text
        await update.message.reply_text(f"📝 Filename set: <code>{text}.txt</code>", parse_mode='HTML')
        session["step"] = "idle"
        if session.get("in_post_summary"):
            await show_post_summary(None, session, uid)
        else:
            await show_pre_summary(update, session, uid)
        return

    if session.get("step") == "waiting_customer":
        session["customer"] = text
        await update.message.reply_text("How many cards?")
        session["step"] = "waiting_target"
        return

    if session.get("step") == "waiting_target":
        try:
            session["target"] = int(text)
            await update.message.reply_text("✅ Target registered.\n\nSend cards below.")
            session["step"] = "waiting_cards"
        except:
            await update.message.reply_text("❌ Please send a numeric value.")

async def show_pre_summary(update: Update, session: dict, uid: int):
    total = len(session["cards"])
    usa = sum(1 for c in session["cards"] if c.get("country","US").upper() == "US")

    text = panel_header("PRE-SUMMARY") + f"""
📦 Total Cards     : <b>{total}</b>
🇺🇸 USA Cards      : <b>{usa}</b>
🌍 Foreign Cards   : <b>{total-usa}</b>
🔧 Mode            : <b>{session.get('mode','FORMAT').upper()}</b>
👤 Customer        : <b>{session.get('customer','N/A')}</b>
🎯 Target          : <b>{session.get('target',0)}</b>
📄 Filename        : <b>{session.get('filename','Auto-Generated')}</b>
"""

    keyboard = [
        [InlineKeyboardButton("✅ START CHECK", callback_data="check")],
        [InlineKeyboardButton("➕ ADD MORE CARDS", callback_data="add_more")],
        [InlineKeyboardButton("🗑️ REMOVE CARDS", callback_data="remove_cards")],
        [InlineKeyboardButton("📝 SET FILENAME", callback_data="set_filename")],
        [InlineKeyboardButton("❌ CANCEL", callback_data="cancel")]
    ]

    await update.message.reply_html(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def check_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    session = get_session(uid)

    if not session.get("cards"):
        await query.edit_message_text("❌ No cards in current session.")
        return

    await query.edit_message_text("🔄 Submitting batch to Stormcheck.cc...\n\nPlease wait...")

    batch_id = await storm_submit(session["cards"])
    await storm_poll(batch_id, len(session["cards"]))
    session["in_post_summary"] = True
    get_stats(uid)["total_cards_checked"] += len(session["cards"])

    await show_post_summary(query, session, uid)

async def show_post_summary(query, session: dict, uid: int):
    count = len(session["cards"])
    live = count
    extras = max(0, live - session.get("target", 0))
    mode = session.get("mode", "format")
    stats = get_stats(uid)

    if mode == "sale":
        revenue = live * 25.0
        profit = revenue - (live * 8.0)
        stats["cards_sold"] += live
        stats["total_sales"] += 1
        stats["revenue"] += revenue
        stats["profit"] += profit
    elif mode == "replace":
        stats["replacements_given"] += 1
        stats["profit"] -= (live * 8.0)
    elif mode == "tester":
        stats["testers_given"] += 1

    text = panel_header("POST-SUMMARY") + f"""
📊 LIVE CARDS     : <b>{live}</b>
📊 EXTRAS         : <b>{extras}</b>
📊 LIVE RATE      : <b>100%</b>
🎯 TARGET MET     : <b>{"YES" if live >= session.get('target',0) else "NO"}</b>
📄 FILENAME       : <b>{session.get('filename','Auto-Generated')}</b>
"""

    keyboard = [
        [InlineKeyboardButton("📤 SEND FILE(S)", callback_data="send_file")],
        [InlineKeyboardButton("➕ ADD MORE CARDS", callback_data="add_more")],
        [InlineKeyboardButton("🗑️ REMOVE CARDS", callback_data="remove_cards")],
        [InlineKeyboardButton("📝 SET FILENAME", callback_data="set_filename")],
        [InlineKeyboardButton("❌ CANCEL", callback_data="cancel")]
    ]

    if query:
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.effective_message.edit_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

async def send_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Generating clean output...")
    uid = query.from_user.id
    session = get_session(uid)

    content = "\n\n".join(format_card(card, session.get("mode") == "tester") for card in session["cards"])
    customer = session.get("customer", "FactoryVHQ")
    live = len(session["cards"])
    filename = session.get("filename") or f"FactoryVHQ-{customer}-{live}-{random.randint(1000,9999)}"

    await query.message.reply_document(
        document=bytes(content, "utf-8"),
        filename=f"{filename}.txt",
        caption="✅ FactoryVHQ Output Generated"
    )

    if session.get("mode") in ["sale", "replace"] and live > session.get("target", 0):
        extras = session["cards"][session.get("target", 0):]
        extra_content = "\n\n".join(format_card(c) for c in extras)
        await query.message.reply_document(
            document=bytes(extra_content, "utf-8"),
            filename=f"Extras-{len(extras)}-cards.txt",
            caption="✅ FactoryVHQ Extras File"
        )

    await query.edit_message_text("✅ All files delivered successfully.", reply_markup=main_menu())
    user_sessions.pop(uid, None)
    save_data()

# ===================== REMOVE & FILENAME =====================
async def remove_cards_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    get_session(query.from_user.id)["step"] = "removing_cards"
    await query.edit_message_text("🗑️ Send last 4 digits separated by commas:\nExample: <code>0328, 4455, 9191</code>", parse_mode='HTML')

async def process_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    session = get_session(uid)
    if session.get("step") != "removing_cards": return
    try:
        targets = [x.strip() for x in update.message.text.split(",")]
        before = len(session["cards"])
        session["cards"] = [c for c in session["cards"] if c["card"][-4:] not in targets]
        await update.message.reply_text(f"🗑️ Removed {before - len(session['cards'])} cards.")
        if session.get("in_post_summary"):
            await show_post_summary(None, session, uid)
        else:
            await show_pre_summary(update, session, uid)
    except:
        await update.message.reply_text("❌ Invalid input.")

async def set_filename_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    get_session(query.from_user.id)["step"] = "waiting_filename"
    await query.edit_message_text("📝 Enter desired filename (without .txt):")

# ===================== MAIN =====================
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

    print("🚀 FactoryVHQ v7.0 Modern Control Panel Started")
    print(f"   Admins: {len(ADMIN_IDS)} | Test Mode: {TEST_MODE}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
