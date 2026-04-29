import random
import os
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

TOKEN = os.getenv("TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))

TEST_MODE = False
user_sessions = {}

def parse_card(line: str):
    try:
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 8:
            return None
        return {
            "card": parts[0].replace(" ", ""),
            "mm": parts[1].split("/")[0],
            "yy": parts[1].split("/")[-1][-2:],
            "cvv": parts[2],
            "name": parts[3],
            "address": parts[4],
            "city": parts[5],
            "state": parts[6],
            "zip": parts[7],
            "country": parts[8] if len(parts) > 8 else "US",
        }
    except:
        return None

def format_card(card: dict) -> str:
    lines = [
        "══════════════════════════════════════",
        "🃏 TestMode Demo",
        "══════════════════════════════════════",
        f"💰 Balance : ${random.uniform(85, 1850):.2f}",
        f"👤 Name    : {card['name']}",
        f"💳 Card    : {card['card']}",
        f"📅 Expiry  : {card['mm']}/{card['yy']}",
        f"🔒 CVV     : {card['cvv']}",
        f"🏦 Bank    : UNKNOWN BANK",
        f"🌍 Country : {card['country']}",
        "",
        "📍 Billing:",
        f"   {card['address']}",
        f"   {card['city']}, {card['state']} {card['zip']}",
        "",
        f"🌐 IP      : {random.randint(25,220)}.{random.randint(10,250)}.{random.randint(10,250)}.{random.randint(10,250)}",
        f"🕒 Checked : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
        "══════════════════════════════════════"
    ]
    return "\n".join(lines)

def main_menu():
    status = "🟢 TEST MODE ON" if TEST_MODE else "🔴 TEST MODE OFF"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Format", callback_data="format")],
        [InlineKeyboardButton(status, callback_data="toggle_test")],
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Access Denied.")
        return
    await update.message.reply_text("E$CO Admin Panel", reply_markup=main_menu())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TEST_MODE
    query = update.callback_query
    await query.answer()
    action = query.data
    uid = query.from_user.id

    if action == "toggle_test":
        TEST_MODE = not TEST_MODE
        text = "🟢 Test Mode ENABLED\nPress 'Format' and send cards → Check will now skip directly to file."
        await query.edit_message_text(text, reply_markup=main_menu())
        return

    if action == "format":
        await query.edit_message_text("Send your fullz (cards) or upload a .txt file:")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    uid = update.effective_user.id
    session = user_sessions.setdefault(uid, {"cards": []})

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

    session["cards"].extend(new_cards)
    total = len(session["cards"])

    keyboard = [
        [InlineKeyboardButton("✅ Check & Generate File", callback_data="check")],
        [InlineKeyboardButton("Add More Cards", callback_data="format")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ]

    await update.message.reply_text(
        f"✅ Cards Received\nTotal Cards: {total}\nTest Mode: {'ON (Will auto generate file)' if TEST_MODE else 'OFF'}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def check_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    query = update.callback_query
    await query.answer("Generating file...")
    
    uid = query.from_user.id
    session = user_sessions.get(uid)
    if not session or not session.get("cards"):
        await query.edit_message_text("❌ No cards found.")
        return

    count = len(session["cards"])
    content = "\n\n".join(format_card(card) for card in session["cards"])
    filename = f"TestMode-Demo-{count}-cards.txt"

    await query.message.reply_document(
        document=bytes(content, "utf-8"),
        filename=filename
    )
    
    await query.edit_message_text(f"✅ Success!\nSent {count} cards with 'TestMode Demo' header.")
    user_sessions.pop(uid, None)

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CallbackQueryHandler(check_handler, pattern="^check$"))
    app.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL, message_handler))

    print("🚀 E$CO Bot Started - TestMode 'Skip to File' Active")
    app.run_polling()

if __name__ == "__main__":
    main()
