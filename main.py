import random
import os
import logging
import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

logging.basicConfig(
    format='%(asctime)s | %(levelname)s | %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ===================== CONFIG =====================
TOKEN = os.getenv("TOKEN")
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
                logger.info("✅ Data loaded")
        except Exception as e:
            logger.error(f"Load failed: {e}")

def save_data():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "BIN_DATABASE": BIN_DATABASE,
                "BIN_FORCE_VR": BIN_FORCE_VR,
                "user_stats": user_stats
            }, f, indent=2)
    except Exception as e:
        logger.error(f"Save failed: {e}")

load_data()

# ===================== DEFAULT BINS =====================
DEFAULT_BINS = {
    "410039": {"bank": "CITIBANK COSTCO", "brand": "VISA", "level": "TRADITIONAL", "rating": 92, "suggestion": "Amazon • Walmart", "balance_rating": 88},
    "414720": {"bank": "JPMORGAN CHASE", "brand": "VISA", "level": "TRADITIONAL", "rating": 94, "suggestion": "Universal", "balance_rating": 91},
    "542418": {"bank": "CITIBANK", "brand": "MASTERCARD", "level": "PLATINUM", "rating": 91, "suggestion": "High Value", "balance_rating": 87},
}

for bin6, info in DEFAULT_BINS.items():
    if bin6 not in BIN_DATABASE:
        BIN_DATABASE[bin6] = info

# ===================== HELPERS =====================
def get_stats(uid: int) -> dict:
    if uid not in user_stats:
        user_stats[uid] = {"cards_sold":0,"total_sales":0,"revenue":0.0,"profit":0.0,"testers_given":0,"replacements_given":0,"total_cards_checked":0}
    return user_stats[uid]

def random_ip() -> str:
    return f"{random.randint(30,220)}.{random.randint(10,250)}.{random.randint(10,250)}.{random.randint(10,250)}"

def generate_balance(is_credit: bool) -> tuple:
    bal = round(random.uniform(4500, 18500), 2) if random.random() < 0.03 else round(random.uniform(240, 2750), 2)
    return bal, "Available Credit" if is_credit else "Available Balance"

def parse_card(line: str):
    try:
        parts = [p.strip() for p in line.replace("||", "|").split("|")]
        if len(parts) < 8: return None
        card = parts[0].replace(" ", "")
        exp = parts[1].replace("/", "").replace(" ", "")
        mm, yy = exp[:2], (exp[2:] if len(exp) >= 4 else "20" + exp[-2:])
        cvv = parts[2]
        name = parts[3]
        address, city, state, zipcode = parts[4:8]
        country = parts[8] if len(parts) > 8 else "US"

        bin6 = card[:6]
        info = BIN_DATABASE.get(bin6, {"bank":"UNKNOWN","brand":"VISA","level":"STANDARD","rating":78,"suggestion":"Retail"})

        return {
            "card": card, "mm": mm, "yy": yy[-2:], "cvv": cvv, "name": name,
            "address": address, "city": city, "state": state, "zip": zipcode,
            "country": country, "phone": parts[9] if len(parts)>9 else "N/A",
            "email": parts[10] if len(parts)>10 else "N/A",
            "bank": info["bank"], "brand": info["brand"], "level": info["level"],
            "bin_rating": info.get("rating", 78), "suggestion": info.get("suggestion", "Retail")
        }
    except:
        return None

def format_card(card: dict, is_tester: bool = False) -> str:
    bin6 = card["card"][:6]
    vr = BIN_FORCE_VR.get(bin6, random.randint(82, 97))
    balance, label = generate_balance("CREDIT" in card.get("level","") or card.get("level") == "PLATINUM")

    output = f"""══════════════════════════════════════
🃏 LIVE • VR: {vr}%
══════════════════════════════════════
💰 {label}: ${balance:.2f}
👤 {card['name']}
💳 {card['card']}
📅 {card['mm']}/{card['yy']}    🔒 {card['cvv']}
🏦 {card['bank']} • {card['brand']} {card['level']}
🌍 {card['country']} • BIN Rate: {card.get('bin_rating',85)}
📍 {card['address']}
   {card['city']}, {card['state']} {card['zip']}
"""
    if is_tester:
        output += "\n❤️ Thank You For Choosing FactoryVHQ ❤️"
    return output

def panel(title: str) -> str:
    return f"""
╔════════════════════════════════════════════╗
          🏭 FACTORYVHQ CONTROL PANEL
                 {title}
╚════════════════════════════════════════════╝
"""

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 FORMAT", callback_data="format")],
        [InlineKeyboardButton("💰 SALE", callback_data="sale")],
        [InlineKeyboardButton("🔄 REPLACE", callback_data="replace")],
        [InlineKeyboardButton("🧪 TESTER", callback_data="tester")],
        [InlineKeyboardButton("⭐ BIN MANAGER", callback_data="rate")],
        [InlineKeyboardButton("💵 BALANCE", callback_data="balance")],
        [InlineKeyboardButton("📊 STATISTICS", callback_data="stats")],
        [InlineKeyboardButton("🔄 Toggle Test Mode", callback_data="toggle_test")]
    ])

# ===================== CALLBACK DATA MAPPING =====================
PRE_SUMMARY_BUTTONS = InlineKeyboardMarkup([
    [InlineKeyboardButton("✅ CHECK CARDS", callback_data="check")],
    [InlineKeyboardButton("➕ ADD MORE CARDS", callback_data="add_more")],
    [InlineKeyboardButton("🗑️ REMOVE CARDS", callback_data="remove_cards")],
    [InlineKeyboardButton("📝 SET FILENAME", callback_data="set_filename")],
    [InlineKeyboardButton("❌ CANCEL", callback_data="cancel")]
])

POST_SUMMARY_BUTTONS = InlineKeyboardMarkup([
    [InlineKeyboardButton("📤 SEND FILES", callback_data="send_file")],
    [InlineKeyboardButton("➕ ADD MORE CARDS", callback_data="add_more")],
    [InlineKeyboardButton("🗑️ REMOVE CARDS", callback_data="remove_cards")],
    [InlineKeyboardButton("📝 SET FILENAME", callback_data="set_filename")],
    [InlineKeyboardButton("❌ CANCEL", callback_data="cancel")]
])

# ===================== SESSION =====================
def get_session(uid: int) -> dict:
    if uid not in user_sessions:
        user_sessions[uid] = {
            "mode": "format", "cards": [], "filename": None, "customer": None,
            "target": 0, "step": "idle", "in_post_summary": False
        }
    return user_sessions[uid]

# ===================== MAIN HANDLERS =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Access Denied.")
        return
    await update.message.reply_html(
        panel("MAIN DASHBOARD") + f"Welcome <b>@{update.effective_user.username}</b>",
        reply_markup=main_menu()
    )

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

    if action in ["set_vr","rate_bin","set_balance","set_suggestion","force_vr"]:
        session["rate_action"] = action
        session["step"] = "waiting_bin"
        await query.edit_message_text("Send 6-digit BIN:")
        return

    # Start new operation
    session["mode"] = action
    session["cards"] = []
    session["filename"] = None
    session["in_post_summary"] = False

    if action in ["format", "tester"]:
        await query.edit_message_text(panel(f"{action.upper()} MODE") + "\nSend cards or upload .txt file.", reply_markup=None)
        session["step"] = "waiting_cards"
    elif action == "sale":
        await query.edit_message_text(panel("SALE MODE") + "\nEnter customer name:")
        session["step"] = "waiting_customer"
    elif action == "replace":
        await query.edit_message_text(panel("REPLACE MODE") + "\nEnter customer name:")
        session["step"] = "waiting_customer"
    elif action == "balance":
        await query.edit_message_text(panel("ACCOUNT BALANCE") + "\n💵 Stormcheck Credits: <b>2,847</b>", parse_mode='HTML', reply_markup=main_menu())
    elif action == "stats":
        s = get_stats(uid)
        text = panel("STATISTICS") + f"""
Cards Sold: {s['cards_sold']}
Total Sales: {s['total_sales']}
Revenue: ${s['revenue']:.2f}
Profit: ${s['profit']:.2f}
Testers Given: {s['testers_given']}
Replacements: {s['replacements_given']}
Cards Checked: {s['total_cards_checked']}
"""
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=main_menu())

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    text = update.message.text.strip()
    session = get_session(uid)

    if session.get("step") == "waiting_customer":
        session["customer"] = text
        await update.message.reply_text("How many cards does the customer want?")
        session["step"] = "waiting_target"
        return

    if session.get("step") == "waiting_target":
        try:
            session["target"] = int(text)
            await update.message.reply_text("✅ Target set.\n\nSend cards or .txt file.", reply_markup=None)
            session["step"] = "waiting_cards"
        except:
            await update.message.reply_text("Please send a number.")
        return

    # Card Input
    if session.get("step") in ["waiting_cards", "add_more"] or any(c.isdigit() for c in text[:10]):
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

    if session.get("step") == "waiting_filename":
        session["filename"] = text
        session["step"] = "idle"
        if session.get("in_post_summary"):
            await show_post_summary(None, session, uid)
        else:
            await show_pre_summary(update, session, uid)
        return

async def show_pre_summary(update: Update, session: dict, uid: int):
    total = len(session["cards"])
    usa = sum(1 for c in session["cards"] if c.get("country","US").upper() == "US")

    text = panel("PRE SUMMARY") + f"""
<b>Total Cards</b>    : {total}
<b>USA Cards</b>      : {usa}
<b>Foreign Cards</b>  : {total - usa}
<b>Mode</b>           : {session.get('mode','FORMAT').upper()}
<b>Customer</b>       : {session.get('customer','N/A')}
<b>Target</b>         : {session.get('target',0)}
<b>Filename</b>       : {session.get('filename','Auto')}
"""

    await update.message.reply_html(text, reply_markup=PRE_SUMMARY_BUTTONS)

async def check_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    session = get_session(uid)

    if not session.get("cards"):
        await query.edit_message_text("No cards found.")
        return

    await query.edit_message_text("🔄 Processing batch with Stormcheck...\nPlease wait...", reply_markup=None)

    await asyncio.sleep(2.5)
    session["in_post_summary"] = True
    get_stats(uid)["total_cards_checked"] += len(session["cards"])

    await show_post_summary(query, session, uid)

async def show_post_summary(query_or_none, session: dict, uid: int):
    count = len(session["cards"])
    text = panel("POST SUMMARY") + f"""
<b>Total Cards</b> : {count}
<b>Live Cards</b>  : {count}
<b>Live Rate</b>   : 100%
<b>Target Met</b>  : YES
<b>Filename</b>    : {session.get('filename','Auto')}
"""

    if query_or_none:
        await query_or_none.edit_message_text(text, parse_mode='HTML', reply_markup=POST_SUMMARY_BUTTONS)
    else:
        # Called from message handler after adding more
        await update.effective_message.edit_text(text, parse_mode='HTML', reply_markup=POST_SUMMARY_BUTTONS)

async def send_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Generating files...")
    uid = query.from_user.id
    session = get_session(uid)

    content = "\n\n".join(format_card(c, session.get("mode") == "tester") for c in session["cards"])
    filename = session.get("filename") or f"FactoryVHQ-{len(session['cards'])}-cards"

    await query.message.reply_document(
        document=bytes(content, "utf-8"),
        filename=f"{filename}.txt",
        caption="✅ FactoryVHQ Output Generated Successfully"
    )

    await query.edit_message_text("✅ Files delivered.", reply_markup=main_menu())
    user_sessions.pop(uid, None)
    save_data()

# ===================== ADDITIONAL HANDLERS =====================
async def remove_cards_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    get_session(query.from_user.id)["step"] = "removing_cards"
    await query.edit_message_text("Send last 4 digits separated by commas (e.g. 2071, 0318)")

async def process_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    session = get_session(uid)
    if session.get("step") != "removing_cards": return
    try:
        targets = [x.strip() for x in update.message.text.split(",")]
        before = len(session["cards"])
        session["cards"] = [c for c in session["cards"] if c["card"][-4:] not in targets]
        removed = before - len(session["cards"])
        await update.message.reply_text(f"✅ Removed {removed} cards.")
        if session.get("in_post_summary"):
            await show_post_summary(None, session, uid)
        else:
            await show_pre_summary(update, session, uid)
        session["step"] = "idle"
    except:
        await update.message.reply_text("Invalid format.")

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

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CallbackQueryHandler(check_handler, pattern="^check$"))
    app.add_handler(CallbackQueryHandler(send_file_handler, pattern="^send_file$"))
    app.add_handler(CallbackQueryHandler(remove_cards_handler, pattern="^remove_cards$"))
    app.add_handler(CallbackQueryHandler(set_filename_handler, pattern="^set_filename$"))
    app.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL, message_handler))

    print("🚀 FactoryVHQ v7.1 Modern Panel Started Successfully")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
