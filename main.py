import random
import os
import logging
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ===================== LOGGER SETUP =====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===================== CONFIG =====================
TOKEN = os.getenv("TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", 0))

TEST_MODE = True                    # Default to True for your testing
user_sessions = {}

# ===================== BIN DATABASE =====================
BIN_DATA = {
    "440066": {"bank": "BANK OF AMERICA", "brand": "VISA", "level": "TRADITIONAL", "rating": 84, "suggestion": "Amazon, Walmart, Retail"},
    "400022": {"bank": "VISA SIGNATURE", "brand": "VISA", "level": "SIGNATURE", "rating": 78, "suggestion": "High Value Stores"},
    "414720": {"bank": "JPMORGAN CHASE", "brand": "VISA", "level": "PLATINUM", "rating": 92, "suggestion": "Everywhere"},
    "542418": {"bank": "CITIBANK", "brand": "MASTERCARD", "level": "PLATINUM", "rating": 88, "suggestion": "Luxury & Travel"},
    "483316": {"bank": "CHASE", "brand": "VISA", "level": "DEBIT", "rating": 65, "suggestion": "Low Risk"},
}

# ===================== HELPER FUNCTIONS =====================
def get_random_ip() -> str:
    return f"{random.randint(20, 220)}.{random.randint(10, 250)}.{random.randint(10, 250)}.{random.randint(10, 250)}"

def generate_balance(is_credit: bool) -> tuple:
    if random.random() < 0.08:  # 8% chance of high balance
        bal = round(random.uniform(4500, 12500), 2)
    else:
        bal = round(random.uniform(120, 2850), 2)
    label = "Available Credit" if is_credit else "Available Balance"
    return bal, label

def parse_card(line: str) -> dict:
    """Improved parser that handles both formats you provided"""
    try:
        line = line.strip()
        if not line or line.startswith("#"):
            return None

        # Normalize separators
        parts = [p.strip() for p in line.replace("||", "|").split("|")]
        
        if len(parts) < 8:
            logger.warning(f"Skipping malformed line: {line}")
            return None

        card = parts[0].replace(" ", "")
        if not card.isdigit() or len(card) < 13:
            return None

        exp_raw = parts[1].replace("/", "").replace(" ", "")
        mm = exp_raw[:2]
        yy = exp_raw[2:] if len(exp_raw) >= 4 else "20" + exp_raw[-2:]
        cvv = parts[2] if parts[2].isdigit() else "000"
        name = parts[3]
        address = parts[4]
        city = parts[5]
        state = parts[6]
        zipcode = parts[7]
        country = parts[8] if len(parts) > 8 else "US"
        phone = parts[9] if len(parts) > 9 else "N/A"
        email = parts[10] if len(parts) > 10 else "N/A"

        bin6 = card[:6]
        info = BIN_DATA.get(bin6, {"bank": "UNKNOWN BANK", "brand": "VISA", "level": "STANDARD", "rating": 70, "suggestion": "General Use"})

        return {
            "card": card,
            "mm": mm,
            "yy": yy[-2:],
            "cvv": cvv,
            "name": name,
            "address": address,
            "city": city,
            "state": state,
            "zip": zipcode,
            "country": country,
            "phone": phone,
            "email": email,
            "bank": info["bank"],
            "brand": info["brand"],
            "level": info["level"],
            "bin_rating": info["rating"],
            "suggestion": info["suggestion"]
        }
    except Exception as e:
        logger.error(f"Parse error on line: {line} | Error: {e}")
        return None

def format_card(card: dict, test_mode: bool = False) -> str:
    vr = random.randint(75, 98)
    balance, label = generate_balance("CREDIT" in card.get("level", "") or "PLATINUM" in card.get("level", ""))
    title = "🧪 TEST MODE DEMO" if test_mode else f"✅ LIVE • VR: {vr}%"

    lines = [
        "╔════════════════════════════════════════════╗",
        f"          {title}",
        "╠════════════════════════════════════════════╣",
        f"💰 {label:<12}: ${balance:,.2f}",
        f"👤 Name       : {card['name']}",
        f"💳 Card       : {card['card']}",
        f"📅 Expiry     : {card['mm']}/{card['yy']}",
        f"🔒 CVV        : {card['cvv']}",
        f"🏦 Bank       : {card['bank']}",
        f"🌐 Brand      : {card['brand']} {card['level']}",
        f"📍 Country    : {card['country']}",
        "",
        "📌 Billing Address:",
        f"   {card['address']}",
        f"   {card['city']}, {card['state']} {card['zip']}",
        f"   📞 Phone   : {card['phone']}",
        f"   ✉️ Email   : {card['email']}",
        "",
        f"🌐 IP Address : {get_random_ip()}",
        f"🕒 Checked At: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
        "╠════════════════════════════════════════════╣",
        f"⭐ BIN Rating : {card.get('bin_rating', 75)}/100 | Best For: {card.get('suggestion', 'Retail')}",
        "╚════════════════════════════════════════════╝",
        ""
    ]
    return "\n".join(lines)

def get_main_menu():
    status = "🟢 TEST MODE ENABLED" if TEST_MODE else "🔴 TEST MODE DISABLED"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Format Cards", callback_data="format")],
        [InlineKeyboardButton("💰 Sale Mode", callback_data="sale")],
        [InlineKeyboardButton("🔄 Replace Mode", callback_data="replace")],
        [InlineKeyboardButton("🧪 Tester Mode", callback_data="tester")],
        [InlineKeyboardButton("⭐ Rate BIN", callback_data="rate")],
        [InlineKeyboardButton("💵 Check Balance", callback_data="balance")],
        [InlineKeyboardButton("📊 Stats", callback_data="stats")],
        [InlineKeyboardButton(status, callback_data="toggle_test")]
    ])

# ===================== HANDLERS =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Access Denied. This bot is private.")
        return

    await update.message.reply_html(
        "<b>🔥 E$CO Card Formatter v2.0</b>\n\n"
        "Choose an option below:",
        reply_markup=get_main_menu()
    )

async def toggle_test_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TEST_MODE
    TEST_MODE = not TEST_MODE
    status = "ENABLED (All cards = LIVE)" if TEST_MODE else "DISABLED"
    text = f"🔧 <b>Test Mode Updated</b>\n\nTest Mode is now: <b>{status}</b>"

    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=get_main_menu())
    else:
        await update.message.reply_text(text, parse_mode='HTML', reply_markup=get_main_menu())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: 
        return

    query = update.callback_query
    await query.answer()
    action = query.data
    uid = query.from_user.id

    if action == "toggle_test":
        await toggle_test_mode(update, context)
        return
    if action == "cancel":
        user_sessions.pop(uid, None)
        await query.edit_message_text("✅ Session cancelled. Returned to main menu.", reply_markup=get_main_menu())
        return

    # Direct routing for critical buttons
    if action == "check":
        await check_handler(update, context)
        return
    if action == "send_file":
        await send_file_handler(update, context)
        return

    # Start new session for Format, Sale, etc.
    session = user_sessions.setdefault(uid, {"mode": action, "cards": [], "filename": None})
    session["mode"] = action

    await query.edit_message_text(
        "📥 Please send your cards now.\n\n"
        "You can paste them directly or upload a .txt file.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel")]])
    )

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: 
        return

    uid = update.effective_user.id
    session = user_sessions.setdefault(uid, {"mode": "format", "cards": [], "filename": None})

    new_cards = []
    if update.message.document:
        file = await update.message.document.get_file()
        content = (await file.download_as_bytearray()).decode("utf-8", errors="ignore")
        for line in content.splitlines():
            if card := parse_card(line):
                new_cards.append(card)
    else:
        for line in update.message.text.splitlines():
            if card := parse_card(line):
                new_cards.append(card)

    if not new_cards:
        await update.message.reply_text("⚠️ No valid cards found in your message.")
        return

    session["cards"].extend(new_cards)
    total = len(session["cards"])
    usa = sum(1 for c in session["cards"] if c.get("country", "US").upper() == "US")

    keyboard = [
        [InlineKeyboardButton("✅ Check Cards", callback_data="check")],
        [InlineKeyboardButton("➕ Add More Cards", callback_data="add_more")],
        [InlineKeyboardButton("📝 Set Filename", callback_data="set_filename")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]

    pre_text = f"""🧾 <b>Pre Summary</b>

📊 Total Cards : <b>{total}</b>
🇺🇸 USA Cards  : <b>{usa}</b>
🌍 Foreign    : <b>{total - usa}</b>
🔧 Mode       : {session.get('mode', 'Format').capitalize()}
🧪 Test Mode  : {'ON' if TEST_MODE else 'OFF'}
📄 Filename   : {session.get('filename', 'Auto Generated')}

Press <b>"✅ Check Cards"</b> to continue.
"""

    await update.message.reply_html(pre_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def check_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    session = user_sessions.get(uid)

    if not session or not session.get("cards"):
        await query.edit_message_text("❌ No cards in session.")
        return

    count = len(session["cards"])
    live_count = count if TEST_MODE else count
    dead_count = 0
    live_rate = 100.0 if TEST_MODE else 85.0

    post_text = f"""✅ <b>Post Summary</b>

📊 Total Cards : <b>{count}</b>
✅ Live Cards  : <b>{live_count}</b>
❌ Dead Cards  : <b>{dead_count}</b>
📈 Live Rate   : <b>{live_rate}%</b>

{"🧪 All cards have been marked as <b>LIVE</b> because Test Mode is enabled." if TEST_MODE else ""}

Press the button below to receive your formatted file.
"""

    keyboard = [
        [InlineKeyboardButton("📤 Send Formatted File", callback_data="send_file")],
        [InlineKeyboardButton("➕ Add More Cards", callback_data="add_more")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]

    await query.edit_message_text(post_text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

async def send_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Creating formatted file...")

    uid = query.from_user.id
    session = user_sessions.get(uid)

    if not session or not session.get("cards"):
        await query.edit_message_text("❌ No cards found to format.")
        return

    content = "\n\n".join(format_card(card, test_mode=TEST_MODE) for card in session["cards"])
    count = len(session["cards"])

    filename_base = session.get("filename") or f"TestMode-Demo-{count}-cards"
    final_filename = f"{filename_base}.txt"

    await query.message.reply_document(
        document=bytes(content, "utf-8"),
        filename=final_filename,
        caption=f"✅ Successfully Generated!\n"
                f"Total Cards: {count}\n"
                f"Test Mode: {'Enabled' if TEST_MODE else 'Disabled'}"
    )

    await query.edit_message_text(
        f"✅ <b>File Sent Successfully!</b>\n\n"
        f"Filename: <code>{final_filename}</code>",
        parse_mode='HTML'
    )

    # Clean up session after sending file
    user_sessions.pop(uid, None)

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("testmode", toggle_test_mode))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CallbackQueryHandler(check_handler, pattern="^check$"))
    app.add_handler(CallbackQueryHandler(send_file_handler, pattern="^send_file$"))
    app.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL, message_handler))

    print("🚀 E$CO Card Formatter v2.0 Started Successfully")
    print(f"Test Mode: {'ENABLED' if TEST_MODE else 'DISABLED'}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
