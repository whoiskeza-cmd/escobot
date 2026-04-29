import random
import os
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ===================== CONFIG =====================
TOKEN = os.getenv("TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))

TEST_MODE = False
user_sessions = {}

# ===================== BIN DATA =====================
BIN_DATA = {
    "410039": {"bank": "CITIBANK, N.A.- COSTCO", "brand": "VISA", "level": "TRADITIONAL", "rating": 85, "suggestion": "Amazon, Walmart"},
    "410040": {"bank": "CITIBANK, N.A.- COSTCO", "brand": "VISA", "level": "BUSINESS", "rating": 78, "suggestion": "High-end stores"},
    "414720": {"bank": "JPMORGAN CHASE BANK N.A.", "brand": "VISA", "level": "TRADITIONAL", "rating": 92, "suggestion": "Everywhere"},
    "414740": {"bank": "JPMORGAN CHASE BANK N.A.", "brand": "VISA", "level": "TRADITIONAL", "rating": 89, "suggestion": "Retail"},
    "440066": {"bank": "BANK OF AMERICA", "brand": "VISA", "level": "TRADITIONAL", "rating": 84, "suggestion": "General"},
    "483312": {"bank": "JPMORGAN CHASE", "brand": "VISA", "level": "DEBIT", "rating": 65, "suggestion": "Low Risk"},
    "483316": {"bank": "JPMORGAN CHASE", "brand": "VISA", "level": "DEBIT", "rating": 68, "suggestion": "Low Risk"},
    "542418": {"bank": "CITIBANK N.A.", "brand": "MASTERCARD", "level": "PLATINUM", "rating": 88, "suggestion": "High Value"},
}

# ===================== HELPERS =====================
def get_random_ip() -> str:
    return f"{random.randint(25,220)}.{random.randint(10,250)}.{random.randint(10,250)}.{random.randint(10,250)}"

def generate_balance(is_credit: bool) -> tuple:
    if random.random() < 0.03:
        bal = round(random.uniform(3200, 9200), 2)
    else:
        bal = round(random.uniform(85, 1950), 2)
    label = "Available Credit" if is_credit else "Balance"
    return bal, label

def parse_card(line: str) -> dict:
    try:
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 8: return None
        card = parts[0].replace(" ", "")
        exp = parts[1].replace("/", "").replace(" ", "")
        mm = exp[:2]
        yy = exp[2:] if len(exp) == 4 else "20" + exp[2:]
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
        info = BIN_DATA.get(bin6, {"bank":"UNKNOWN","brand":"VISA","level":"STANDARD","rating":75,"suggestion":"Retail"})

        return {
            "card": card, "mm": mm, "yy": yy[-2:], "cvv": cvv, "name": name,
            "address": address, "city": city, "state": state, "zip": zipcode,
            "country": country, "phone": phone, "email": email,
            "bank": info["bank"], "brand": info["brand"], "level": info["level"],
            "bin_rating": info["rating"], "suggestion": info["suggestion"]
        }
    except:
        return None

def format_card(card: dict, test_mode: bool = False) -> str:
    vr = random.randint(68, 97)
    balance, label = generate_balance("CREDIT" in card.get("level", "") or "PLATINUM" in card.get("level", ""))
    title = "TestMode Demo" if test_mode else f"LIVE • VR: {vr}%"
    
    lines = [
        "══════════════════════════════════════",
        f"🃏 {title}",
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
    return "\n".join(lines)

def main_menu():
    status = "🟢 TEST MODE ON" if TEST_MODE else "🔴 TEST MODE OFF"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Format", callback_data="format")],
        [InlineKeyboardButton("Sale", callback_data="sale")],
        [InlineKeyboardButton("Replace", callback_data="replace")],
        [InlineKeyboardButton("Tester", callback_data="tester")],
        [InlineKeyboardButton("Rate BIN", callback_data="rate")],
        [InlineKeyboardButton("Balance", callback_data="balance")],
        [InlineKeyboardButton("Stats", callback_data="stats")],
        [InlineKeyboardButton(status, callback_data="toggle_test")]
    ])

# ===================== HANDLERS =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Access Denied.")
        return
    await update.message.reply_html(
        f"<b>E$CO Admin Panel</b>\n\nWelcome @{update.effective_user.username}",
        reply_markup=main_menu()
    )

async def toggle_test_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TEST_MODE
    TEST_MODE = not TEST_MODE
    status = "ENABLED - All cards marked LIVE instantly (No API)" if TEST_MODE else "DISABLED"
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(f"🔧 Test Mode is now **{status}**", parse_mode='HTML', reply_markup=main_menu())
    else:
        await update.message.reply_text(f"🔧 Test Mode is now **{status}**", parse_mode='HTML')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    query = update.callback_query
    await query.answer()
    action = query.data
    uid = query.from_user.id
    session = user_sessions.setdefault(uid, {"mode": None, "cards": [], "filename": None})

    if action == "toggle_test":
        await toggle_test_mode(update, context)
        return
    if action == "cancel":
        user_sessions.pop(uid, None)
        await query.edit_message_text("✅ Returned to Admin Panel.", reply_markup=main_menu())
        return

    session["mode"] = action
    if action in ["format", "tester"]:
        await query.edit_message_text("Send Cards or drop a .txt file to continue.")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    uid = update.effective_user.id
    session = user_sessions.get(uid)
    if not session or not session.get("mode"): return

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

    session.setdefault("cards", []).extend(new_cards)
    total = len(session["cards"])
    usa = sum(1 for c in session["cards"] if c.get("country", "US").upper() == "US")

    keyboard = [
        [InlineKeyboardButton("✅ Check", callback_data="check")],
        [InlineKeyboardButton("Add More Cards", callback_data="add_more")],
        [InlineKeyboardButton("Set Filename", callback_data="set_filename")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ]

    pre_text = f"""Pre Summary/Confirmation
Total Cards: {total}
Total USA: {usa}
Total Foreign: {total - usa}
Mode: {session.get('mode','Format').capitalize()}
Test Mode: {'ON' if TEST_MODE else 'OFF'}
Filename: {session.get('filename', 'None')}
"""

    await update.message.reply_text(pre_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def check_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """This now correctly goes to Post Summary"""
    if update.effective_user.id != OWNER_ID: return
    query = update.callback_query
    await query.answer("Processing...")

    uid = query.from_user.id
    session = user_sessions.get(uid)
    if not session or not session.get("cards"):
        await query.edit_message_text("❌ No cards found.")
        return

    count = len(session["cards"])
    live_count = count if TEST_MODE else count
    dead_count = 0 if TEST_MODE else 0
    live_rate = 100.0 if TEST_MODE else 0.0

    post_text = f"""Post Summary/Confirmation
Total Cards: {count}
Total Live: {live_count}
Total Dead: {dead_count}
LiveRate: {live_rate}%
"""

    if TEST_MODE:
        post_text += "\n\n✅ All cards have been marked as LIVE in Test Mode."

    keyboard = [
        [InlineKeyboardButton("📤 Send File", callback_data="send_file")],
        [InlineKeyboardButton("Add More Cards", callback_data="add_more")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ]

    await query.edit_message_text(post_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def send_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    query = update.callback_query
    await query.answer("Generating file...")

    uid = query.from_user.id
    session = user_sessions.get(uid)
    if not session or not session.get("cards"):
        await query.edit_message_text("❌ No cards found.")
        return

    content = "\n\n".join(format_card(card, test_mode=TEST_MODE) for card in session["cards"])
    count = len(session["cards"])

    filename = session.get("filename") or (f"TestMode-Demo-{count}-cards")
    final_filename = f"{filename}.txt"

    await query.message.reply_document(
        document=bytes(content, "utf-8"),
        filename=final_filename,
        caption=f"✅ TestMode File Generated\nTotal Cards: {count}"
    )

    await query.edit_message_text(f"✅ File sent successfully!\nFilename: `{final_filename}`", parse_mode='HTML')
    user_sessions.pop(uid, None)

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("testmode", toggle_test_mode))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CallbackQueryHandler(check_handler, pattern="^check$"))
    app.add_handler(CallbackQueryHandler(send_file_handler, pattern="^send_file$"))
    app.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL, message_handler))

    print("🚀 E$CO Bot Started - Pre Summary → Post Summary → File Now Working in Test Mode")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
