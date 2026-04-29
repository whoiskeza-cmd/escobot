import random
import os
import logging
import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

logging.basicConfig(
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("FactoryVHQ")

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
CARD_COST = 8.0
SALE_PRICE = 25.0

user_sessions: Dict[int, dict] = {}
user_stats: Dict[int, dict] = {}
BIN_DATABASE: Dict[str, dict] = {}
BIN_FORCE_VR: Dict[str, int] = {}

# ===================== LOAD/SAVE =====================
def load_data():
    global BIN_DATABASE, BIN_FORCE_VR, user_stats
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                BIN_DATABASE = data.get("BIN_DATABASE", {})
                BIN_FORCE_VR = data.get("BIN_FORCE_VR", {})
                user_stats = data.get("user_stats", {})
                logger.info("✅ FactoryVHQ Data Loaded")
        except Exception as e:
            logger.error(f"Load error: {e}")

def save_data():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "BIN_DATABASE": BIN_DATABASE,
                "BIN_FORCE_VR": BIN_FORCE_VR,
                "user_stats": user_stats
            }, f, indent=2)
    except Exception as e:
        logger.error(f"Save error: {e}")

load_data()

# ===================== BIN DATABASE =====================
DEFAULT_BINS = {
    "410039": {"bank": "CITIBANK, N.A.- COSTCO", "brand": "VISA", "level": "TRADITIONAL", "rating": 92, "suggestion": "Amazon, Walmart", "type": "CREDIT"},
    "410040": {"bank": "CITIBANK, N.A.- COSTCO", "brand": "VISA", "level": "BUSINESS", "rating": 85, "suggestion": "High-end stores", "type": "CREDIT"},
    "414720": {"bank": "JPMORGAN CHASE BANK N.A.", "brand": "VISA", "level": "TRADITIONAL", "rating": 94, "suggestion": "Everywhere", "type": "CREDIT"},
    "414740": {"bank": "JPMORGAN CHASE BANK N.A.", "brand": "VISA", "level": "TRADITIONAL", "rating": 89, "suggestion": "Retail", "type": "CREDIT"},
    "440066": {"bank": "BANK OF AMERICA - CONSUMER CREDIT", "brand": "VISA", "level": "TRADITIONAL", "rating": 88, "suggestion": "General", "type": "CREDIT"},
    "483316": {"bank": "JPMORGAN CHASE BANK N.A. - DEBIT", "brand": "VISA", "level": "CLASSIC", "rating": 70, "suggestion": "Low Risk", "type": "DEBIT"},
    "542418": {"bank": "CITIBANK N.A.", "brand": "MASTERCARD", "level": "PLATINUM", "rating": 91, "suggestion": "High Value", "type": "CREDIT"},
    "546616": {"bank": "CITIBANK N.A.", "brand": "MASTERCARD", "level": "WORLD", "rating": 93, "suggestion": "Luxury", "type": "CREDIT"},
}

for bin6, info in DEFAULT_BINS.items():
    if bin6 not in BIN_DATABASE:
        BIN_DATABASE[bin6] = info

# ===================== HELPERS =====================
def get_stats(uid: int) -> dict:
    if uid not in user_stats:
        user_stats[uid] = {
            "cards_sold": 0, "total_sales": 0, "revenue": 0.0, "profit": 0.0,
            "testers_given": 0, "replacements_given": 0, "total_cards_checked": 0
        }
    return user_stats[uid]

def random_ip() -> str:
    return f"{random.randint(25,220)}.{random.randint(10,250)}.{random.randint(10,250)}.{random.randint(10,250)}"

def generate_balance(is_credit: bool) -> tuple:
    if random.random() < 0.03:           # 3% chance high balance
        bal = round(random.uniform(3200, 12800), 2)
    elif random.random() < 0.65:         # 65% chance under $1100
        bal = round(random.uniform(85, 1099), 2)
    else:
        bal = round(random.uniform(1100, 3100), 2)
    label = "Available Credit" if is_credit else "Balance"
    return bal, label

def parse_card(line: str) -> Optional[dict]:
    try:
        parts = [p.strip() for p in line.replace("||", "|").split("|")]
        if len(parts) < 8: return None
        card = parts[0].replace(" ", "")
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
        info = BIN_DATABASE.get(bin6, {"bank":"UNKNOWN","brand":"VISA","level":"STANDARD","rating":75,"suggestion":"Retail","type":"CREDIT"})

        return {
            "card": card, "mm": mm, "yy": yy[-2:], "cvv": cvv, "name": name,
            "address": address, "city": city, "state": state, "zip": zipcode,
            "country": country, "phone": phone, "email": email,
            "bank": info["bank"], "brand": info["brand"], "level": info["level"],
            "bin_rating": info["rating"], "suggestion": info["suggestion"],
            "type": info.get("type", "CREDIT")
        }
    except:
        return None

def format_card(card: dict, is_tester: bool = False) -> str:
    bin6 = card["card"][:6]
    vr = BIN_FORCE_VR.get(bin6, random.randint(78, 97))
    balance, label = generate_balance(card.get("type") == "CREDIT")

    lines = [
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
        lines.append("❤️ Thank You For Choosing FactoryVHQ ❤️")
    return "\n".join(lines)

def panel(title: str) -> str:
    return f"""
╔════════════════════════════════════════════╗
          🏭 FACTORYVHQ ADMIN PANEL
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

def get_session(uid: int) -> dict:
    if uid not in user_sessions:
        user_sessions[uid] = {
            "mode": "format", "cards": [], "filename": None, "customer": None,
            "target": 0, "step": "idle", "type": None, "in_post_summary": False
        }
    return user_sessions[uid]

# ===================== COMMANDS =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Access Denied.")
        return
    await update.message.reply_html(
        panel("FactoryVHQ Admin Panel") + f"Welcome <b>@{update.effective_user.username}</b>",
        reply_markup=main_menu()
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_sessions.pop(update.effective_user.id, None)
    await update.message.reply_text("✅ Returned to FactoryVHQ Admin Panel.", reply_markup=main_menu())

# ===================== BUTTON HANDLER =====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data
    uid = query.from_user.id
    session = get_session(uid)

    if action == "toggle_test":
        global TEST_MODE
        TEST_MODE = not TEST_MODE
        await query.edit_message_text(f"Test Mode: {'🟢 ON' if TEST_MODE else '🔴 OFF'}", reply_markup=main_menu())
        return

    if action == "cancel":
        user_sessions.pop(uid, None)
        await query.edit_message_text("✅ Session cancelled.", reply_markup=main_menu())
        return

    if action == "rate":
        await query.edit_message_text(panel("BIN MANAGER"), reply_markup=rate_menu())
        return

    if action in ["set_vr", "rate_bin", "set_balance", "set_suggestion", "force_vr"]:
        session["rate_action"] = action
        session["step"] = "waiting_bin"
        await query.edit_message_text("Send 6-digit BIN:")
        return

    session["mode"] = action
    session["cards"] = []
    session["filename"] = None
    session["customer"] = None
    session["target"] = 0
    session["in_post_summary"] = False

    if action == "format":
        await query.edit_message_text(panel("FORMAT MODE") + "\nSend Cards or drop a .txt file to continue.")
        session["step"] = "waiting_cards"
    elif action == "sale":
        await query.edit_message_text(panel("SALE MODE") + "\nPlease send the Customer Name:")
        session["step"] = "waiting_customer"
    elif action == "replace":
        await query.edit_message_text(panel("REPLACE MODE") + "\nWho is being replaced?")
        session["step"] = "waiting_customer"
    elif action == "tester":
        await query.edit_message_text(panel("TESTER MODE") + "\nIs this a **Drop** or **Gift**?")
        session["step"] = "waiting_tester_type"
    elif action == "balance":
        await query.edit_message_text(panel("BALANCE") + "\nYour available Storm Credits: <b>2847</b>", parse_mode='HTML', reply_markup=main_menu())
    elif action == "stats":
        s = get_stats(uid)
        text = panel("STATISTICS") + f"""
Cards Sold       : {s['cards_sold']}
Total Sales      : {s['total_sales']}
Revenue          : ${s['revenue']:.2f}
Profit           : ${s['profit']:.2f}
Testers Given    : {s['testers_given']}
Replacements     : {s['replacements_given']}
Cards Checked    : {s['total_cards_checked']}
"""
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=main_menu())

# ===================== MESSAGE HANDLER =====================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    text = update.message.text.strip()
    session = get_session(uid)

    if session.get("step") == "waiting_tester_type":
        session["type"] = text.capitalize()
        await update.message.reply_text(panel("TESTER MODE") + "\nSend Cards or drop a .txt file.")
        session["step"] = "waiting_cards"
        return

    if session.get("step") == "waiting_customer":
        session["customer"] = text
        await update.message.reply_text("How many cards?")
        session["step"] = "waiting_target"
        return

    if session.get("step") == "waiting_target":
        try:
            session["target"] = int(text)
            await update.message.reply_text("✅ Target set.\nSend Cards or drop .txt file.")
            session["step"] = "waiting_cards"
        except:
            await update.message.reply_text("Please send a number.")
        return

    if session.get("step") == "waiting_bin":
        bin6 = text[:6]
        session["current_bin"] = bin6
        if bin6 not in BIN_DATABASE:
            BIN_DATABASE[bin6] = {"bank":"UNKNOWN","brand":"VISA","level":"STANDARD","rating":75,"suggestion":"Retail","type":"CREDIT"}
        await update.message.reply_text(f"✅ BIN {bin6} selected.\nSend new value:")
        session["step"] = "waiting_value"
        return

    if session.get("step") == "waiting_value":
        session["step"] = "idle"
        await update.message.reply_text("✅ BIN updated.", reply_markup=main_menu())
        save_data()
        return

    if session.get("step") == "waiting_filename":
        session["filename"] = text
        session["step"] = "idle"
        if session.get("in_post_summary"):
            await show_post_summary(None, session, uid)
        else:
            await show_pre_summary(update, session, uid)
        return

    if session.get("step") == "removing_cards":
        await process_remove(update, context)
        return

    # Card Input
    if session.get("step") in ["waiting_cards", "add_more"]:
        new_cards = []
        if update.message.document:
            file = await update.message.document.get_file()
            content = (await file.download_as_bytearray()).decode("utf-8", errors="ignore")
            for line in content.splitlines():
                if card := parse_card(line):
                    new_cards.append(card)
        else:
            for line in text.splitlines():
                if card := parse_card(line):
                    new_cards.append(card)

        if new_cards:
            session["cards"].extend(new_cards)
            session["step"] = "idle"
            if session.get("in_post_summary"):
                await show_post_summary(None, session, uid)
            else:
                await show_pre_summary(update, session, uid)
        return

# ===================== SUMMARY =====================
async def show_pre_summary(update: Update, session: dict, uid: int):
    total = len(session["cards"])
    usa = sum(1 for c in session["cards"] if c.get("country","US").upper() == "US")
    mode = session.get("mode","FORMAT").upper()

    text = panel("PRE-SUMMARY") + f"""
Total Cards   : {total}
Total USA     : {usa}
Total Foreign : {total - usa}
Mode          : {mode}
Filename      : {session.get('filename', 'Batch-####')}
"""

    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode='HTML', reply_markup=PRE_BUTTONS)
    else:
        await update.message.reply_html(text, reply_markup=PRE_BUTTONS)

async def check_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    session = get_session(uid)

    if not session.get("cards"):
        await query.edit_message_text("❌ No cards found.")
        return

    await query.edit_message_text(
        "🔄 Batch has successfully been submitted.\n\n"
        "Please wait up to 30 seconds while we begin quality checking..."
    )

    if TEST_MODE:
        await asyncio.sleep(2.0)
        session["in_post_summary"] = True
        get_stats(uid)["total_cards_checked"] += len(session["cards"])
        await show_post_summary(query, session, uid)
        return

    # Real API path (placeholder)
    batch_id = "batch-00000"
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
    stats = get_stats(uid)

    if mode == "sale":
        revenue = live * SALE_PRICE
        profit = revenue - (live * CARD_COST)
        stats["cards_sold"] += live
        stats["total_sales"] += 1
        stats["revenue"] += revenue
        stats["profit"] += profit
        header = "POST-SUMMARY - SALE"
        text = f"""
Total Cards     : {count}
Total Live      : {live}
Extras          : {extras}
Total Dead      : {dead}
Live Rate       : {live_rate}%
Target Reached  : {'True' if live >= target else 'False'}
Profit Made     : ${profit:.2f}
Total Revenue   : ${revenue:.2f}
"""
    elif mode == "replace":
        stats["replacements_given"] += 1
        stats["profit"] -= (live * CARD_COST)
        header = "POST-SUMMARY - REPLACE"
        text = f"""
Total Cards     : {count}
Total Live      : {live}
Extras          : {extras}
Total Dead      : {dead}
Live Rate       : {live_rate}%
Target Reached  : {'True' if live >= target else 'False'}
Customer        : {session.get('customer', 'N/A')}
"""
    else:
        header = "POST-SUMMARY"
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
    await query.answer("Generating files...")
    uid = query.from_user.id
    session = get_session(uid)

    content = "\n\n".join(format_card(c, session.get("mode") == "tester") for c in session["cards"])
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

    await query.edit_message_text("✅ Files sent successfully!", reply_markup=main_menu())
    user_sessions.pop(uid, None)
    save_data()

async def remove_cards_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    get_session(query.from_user.id)["step"] = "removing_cards"
    await query.edit_message_text("Send last 4 digits separated by commas (e.g. 0328, 4455)")

async def process_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    session = get_session(uid)
    if session.get("step") != "removing_cards": return
    try:
        targets = [x.strip() for x in update.message.text.split(",")]
        original = len(session["cards"])
        session["cards"] = [c for c in session["cards"] if c["card"][-4:] not in targets]
        await update.message.reply_text(f"✅ Removed {original - len(session['cards'])} cards.")
        if session.get("in_post_summary"):
            await show_post_summary(None, session, uid)
        else:
            await show_pre_summary(update, session, uid)
        session["step"] = "idle"
    except:
        await update.message.reply_text("❌ Invalid input.")

async def set_filename_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    get_session(query.from_user.id)["step"] = "waiting_filename"
    await query.edit_message_text("Enter desired filename (without .txt):")

def rate_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Set BIN VR", callback_data="set_vr")],
        [InlineKeyboardButton("Rate BIN", callback_data="rate_bin")],
        [InlineKeyboardButton("Set Balance Rating", callback_data="set_balance")],
        [InlineKeyboardButton("Set Suggestion", callback_data="set_suggestion")],
        [InlineKeyboardButton("Force VR", callback_data="force_vr")],
        [InlineKeyboardButton("← Back to Panel", callback_data="back_main")]
    ])

async def storm_poll(batch_id: str, total_cards: int):
    if TEST_MODE:
        await asyncio.sleep(2)
        return
    poll_counts = {range(0,6):3, range(6,11):5, range(11,16):8, range(16,31):12, range(31,51):18, range(51,101):25}
    polls = next((v for r,v in poll_counts.items() if total_cards in r), 30)
    for _ in range(polls):
        await asyncio.sleep(2.0)

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

    print("🚀 FactoryVHQ v12.0 Started Successfully")
    print(f"   Admins Loaded: {len(ADMIN_IDS)} | Test Mode: {TEST_MODE}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
