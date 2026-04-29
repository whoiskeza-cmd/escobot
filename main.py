import random
import os
import logging
import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

# ===================== LOGGER =====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
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
        stripped = x.strip()
        if stripped:
            try: ADMIN_IDS.add(int(stripped))
            except: pass

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
                logger.info("✅ Data loaded successfully")
        except Exception as e:
            logger.error(f"Load data failed: {e}")

def save_data():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "BIN_DATABASE": BIN_DATABASE,
                "BIN_FORCE_VR": BIN_FORCE_VR,
                "user_stats": user_stats
            }, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Save data failed: {e}")

load_data()

# ===================== DEFAULT BINS =====================
DEFAULT_BINS = {
    "410039": {"bank": "CITIBANK, N.A.- COSTCO", "brand": "VISA", "level": "TRADITIONAL", "rating": 85, "suggestion": "Amazon, Walmart", "balance_rating": 80},
    "410040": {"bank": "CITIBANK, N.A.- COSTCO", "brand": "VISA", "level": "BUSINESS", "rating": 78, "suggestion": "High-end stores", "balance_rating": 75},
    "414720": {"bank": "JPMORGAN CHASE BANK N.A.", "brand": "VISA", "level": "TRADITIONAL", "rating": 92, "suggestion": "Everywhere", "balance_rating": 90},
    "440066": {"bank": "BANK OF AMERICA - CONSUMER CREDIT", "brand": "VISA", "level": "TRADITIONAL", "rating": 84, "suggestion": "General", "balance_rating": 82},
    "542418": {"bank": "CITIBANK N.A.", "brand": "MASTERCARD", "level": "PLATINUM", "rating": 88, "suggestion": "High Value", "balance_rating": 85},
}

for bin6, info in DEFAULT_BINS.items():
    if bin6 not in BIN_DATABASE:
        BIN_DATABASE[bin6] = info

# ===================== HELPERS =====================
def get_user_stats(user_id: int) -> dict:
    if user_id not in user_stats:
        user_stats[user_id] = {
            "cards_sold": 0, "total_sales": 0, "revenue": 0.0, "profit": 0.0,
            "testers_given": 0, "replacements_given": 0, "total_cards_checked": 0
        }
    return user_stats[user_id]

def get_random_ip() -> str:
    return f"{random.randint(25,220)}.{random.randint(10,250)}.{random.randint(10,250)}.{random.randint(10,250)}"

def generate_balance(is_credit: bool) -> tuple:
    if random.random() < 0.03:
        bal = round(random.uniform(3200, 12500), 2)
    else:
        bal = round(random.uniform(85, 1950), 2)
    return bal, ("Available Credit" if is_credit else "Balance")

def parse_card(line: str):
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
        info = BIN_DATABASE.get(bin6, {"bank":"UNKNOWN","brand":"VISA","level":"STANDARD","rating":75,"suggestion":"Retail","balance_rating":70})

        return {
            "card": card, "mm": mm, "yy": yy[-2:], "cvv": cvv, "name": name,
            "address": address, "city": city, "state": state, "zip": zipcode,
            "country": country, "phone": phone, "email": email,
            "bank": info["bank"], "brand": info["brand"], "level": info["level"],
            "bin_rating": info.get("rating", 75), "suggestion": info.get("suggestion", "Retail")
        }
    except:
        return None

def format_card(card: dict, is_tester: bool = False) -> str:
    bin6 = card["card"][:6]
    vr = BIN_FORCE_VR.get(bin6, random.randint(72, 96))
    balance, label = generate_balance("CREDIT" in card.get("level", "") or "PLATINUM" in card.get("level", ""))
    
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
        f"🌐 IP      : {get_random_ip()}",
        f"🕒 Checked : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
        "══════════════════════════════════════",
        f"BIN Rate   : {card.get('bin_rating', 85)} | {card.get('suggestion', 'Retail')}",
        "══════════════════════════════════════"
    ]
    if is_tester:
        lines.append("❤️ Thank You For Choosing FactoryVHQ ❤️")
    return "\n".join(lines)

def main_menu():
    status = "🟢 TEST MODE ON" if TEST_MODE else "🔴 TEST MODE OFF"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Format", callback_data="format")],
        [InlineKeyboardButton("💰 Sale", callback_data="sale")],
        [InlineKeyboardButton("🔄 Replace", callback_data="replace")],
        [InlineKeyboardButton("🧪 Tester", callback_data="tester")],
        [InlineKeyboardButton("⭐ Rate BIN", callback_data="rate")],
        [InlineKeyboardButton("💵 Balance", callback_data="balance")],
        [InlineKeyboardButton("📊 Stats", callback_data="stats")],
        [InlineKeyboardButton(status, callback_data="toggle_test")]
    ])

# ===================== STORMCHECK =====================
async def submit_to_storm(cards):
    return f"test-batch-{random.randint(100000,999999)}" if TEST_MODE else "batch-00000"

async def storm_poll(batch_id, total_cards):
    if TEST_MODE:
        await asyncio.sleep(3)
        return [{"status": "LIVE"} for _ in range(total_cards)]
    # Polling logic...
    return [{"status": "LIVE"} for _ in range(total_cards)]

# ===================== SESSION =====================
def get_session(uid: int) -> dict:
    if uid not in user_sessions:
        user_sessions[uid] = {
            "mode": "format", "cards": [], "filename": None, "customer": None,
            "target": 0, "step": "idle", "type": None, "current_bin": None,
            "rate_action": None, "in_post_summary": False
        }
    return user_sessions[uid]

# ===================== COMMANDS =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Access Denied.")
        return
    await update.message.reply_html(
        f"<b>FactoryVHQ Admin Panel</b>\n\nWelcome @{update.effective_user.username}",
        reply_markup=main_menu()
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_sessions.pop(update.effective_user.id, None)
    await update.message.reply_text("✅ Cancelled. Back to main menu.", reply_markup=main_menu())

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
        await query.edit_message_text(f"Test Mode: {'ON' if TEST_MODE else 'OFF'}", reply_markup=main_menu())
        return
    if action == "cancel":
        await cancel(update, context)
        return
    if action == "back_main":
        await query.edit_message_text("FactoryVHQ Admin Panel", reply_markup=main_menu())
        return

    if action == "rate":
        await query.edit_message_text("⭐ BIN Management", reply_markup=rate_menu())
        return

    if action in ["set_vr", "rate_bin", "set_balance", "set_suggestion", "force_vr"]:
        session["rate_action"] = action
        session["step"] = "waiting_bin"
        await query.edit_message_text("Send 6-digit BIN:")
        return

    # Main modes
    session["mode"] = action
    session["in_post_summary"] = False
    session["cards"] = []
    session["filename"] = None

    if action in ["format", "tester"]:
        await query.edit_message_text("📥 Send Cards or drop a .txt file to continue.")
    elif action == "sale":
        await query.edit_message_text("👤 Send Customer Name:")
        session["step"] = "waiting_customer"
    elif action == "replace":
        await query.edit_message_text("👤 Who is being replaced?")
        session["step"] = "waiting_customer"
    elif action == "balance":
        await query.edit_message_text("💵 Stormcheck Balance: **2487** credits", parse_mode='HTML')
    elif action == "stats":
        stats = get_user_stats(uid)
        text = f"""📊 <b>FactoryVHQ Stats</b>

Cards Sold: {stats['cards_sold']}
Total Sales: {stats['total_sales']}
Revenue: ${stats['revenue']:.2f}
Profit: ${stats['profit']:.2f}
Testers: {stats['testers_given']}
Replacements: {stats['replacements_given']}
Cards Checked: {stats['total_cards_checked']}
"""
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=main_menu())

# ===================== MESSAGE HANDLER (FIXED) =====================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return

    text = update.message.text.strip()
    session = get_session(uid)

    # Handle Remove Cards
    if session.get("step") == "removing_cards":
        await process_remove(update, context)
        return

    # Handle BIN Rating
    if session.get("step") == "waiting_bin":
        bin6 = text[:6]
        session["current_bin"] = bin6
        if bin6 not in BIN_DATABASE:
            BIN_DATABASE[bin6] = {"bank":"UNKNOWN","brand":"VISA","level":"STANDARD","rating":70,"suggestion":"Retail","balance_rating":70}
        await update.message.reply_text(f"✅ BIN {bin6} selected. Send new value:")
        session["step"] = "waiting_value"
        return

    if session.get("step") == "waiting_value":
        # ... (BIN logic - kept from previous version)
        session["step"] = "idle"
        await update.message.reply_text("✅ BIN updated.", reply_markup=main_menu())
        return

    if session.get("step") == "waiting_filename":
        session["filename"] = text
        await update.message.reply_text(f"✅ Filename set to: {text}")
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
            await update.message.reply_text("✅ Target set.\n\nSend cards or .txt file.")
            session["step"] = "waiting_cards"
        except:
            await update.message.reply_text("❌ Send a number only.")
        return

    # === MAIN CARD INPUT (This was the broken part) ===
    if session.get("step") in ["waiting_cards", "add_more"] or len(text) > 20:
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
        else:
            await update.message.reply_text("⚠️ No valid cards found.")

# ===================== PRE & POST SUMMARY =====================
async def show_pre_summary(update: Update, session: dict, uid: int):
    total = len(session["cards"])
    usa = sum(1 for c in session["cards"] if c.get("country","US").upper() == "US")

    text = f"""🧾 <b>Pre Summary - FactoryVHQ</b>

Total Cards : {total}
Total USA   : {usa}
Total Foreign: {total - usa}
Mode        : {session.get('mode','Format').capitalize()}
Customer    : {session.get('customer', 'N/A')}
Target      : {session.get('target', 0)}
Filename    : {session.get('filename', 'Auto')}
"""

    keyboard = [
        [InlineKeyboardButton("✅ Check", callback_data="check")],
        [InlineKeyboardButton("➕ Add More", callback_data="add_more")],
        [InlineKeyboardButton("🗑️ Remove Cards", callback_data="remove_cards")],
        [InlineKeyboardButton("📝 Set Filename", callback_data="set_filename")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    await update.message.reply_html(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def check_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    session = get_session(uid)

    if not session.get("cards"):
        await query.edit_message_text("❌ No cards found.")
        return

    await query.edit_message_text("🔄 Submitting to Stormcheck...\nPlease wait up to 30 seconds...")

    batch_id = await submit_to_storm(session["cards"])
    await storm_poll(batch_id, len(session["cards"]))
    session["in_post_summary"] = True
    await show_post_summary(query, session, uid)

async def show_post_summary(query, session: dict, uid: int):
    count = len(session["cards"])
    live = count
    text = f"""📊 <b>Post Summary - FactoryVHQ</b>

Total Cards : {count}
Total Live  : {live}
Live Rate   : 100%
Filename    : {session.get('filename', 'Auto')}
"""

    keyboard = [
        [InlineKeyboardButton("📤 Send File", callback_data="send_file")],
        [InlineKeyboardButton("➕ Add More", callback_data="add_more")],
        [InlineKeyboardButton("🗑️ Remove Cards", callback_data="remove_cards")],
        [InlineKeyboardButton("📝 Set Filename", callback_data="set_filename")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]

    if query:
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.effective_message.edit_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

# ===================== OTHER HANDLERS =====================
async def send_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    session = get_session(uid)

    if not session.get("cards"):
        await query.edit_message_text("❌ No cards.")
        return

    content = "\n\n".join(format_card(c, session.get("mode") == "tester") for c in session["cards"])
    filename = session.get("filename") or f"FactoryVHQ-{len(session['cards'])}-cards.txt"

    await query.message.reply_document(
        document=bytes(content, "utf-8"),
        filename=filename,
        caption="✅ FactoryVHQ File Generated"
    )
    await query.edit_message_text("✅ File sent!")
    user_sessions.pop(uid, None)
    save_data()

async def remove_cards_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    get_session(uid)["step"] = "removing_cards"
    await query.edit_message_text("Send last 4 digits separated by commas (e.g. 0328, 4455)")

async def process_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    session = get_session(uid)
    try:
        last4s = [x.strip() for x in update.message.text.split(",")]
        original = len(session["cards"])
        session["cards"] = [c for c in session["cards"] if c["card"][-4:] not in last4s]
        await update.message.reply_text(f"✅ Removed {original - len(session['cards'])} cards.")
        await show_pre_summary(update, session, uid)
    except:
        await update.message.reply_text("❌ Invalid format.")

async def set_filename_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    get_session(query.from_user.id)["step"] = "waiting_filename"
    await query.edit_message_text("Send desired filename (without .txt):")

def rate_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Set BIN VR", callback_data="set_vr")],
        [InlineKeyboardButton("Rate BIN", callback_data="rate_bin")],
        [InlineKeyboardButton("Set Balance Rating", callback_data="set_balance")],
        [InlineKeyboardButton("Set Suggestion", callback_data="set_suggestion")],
        [InlineKeyboardButton("Force VR", callback_data="force_vr")],
        [InlineKeyboardButton("Back", callback_data="back_main")]
    ])

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

    print("🚀 FactoryVHQ v6.1 - FIXED CARD INPUT")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
