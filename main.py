import asyncio
import random
import os
from datetime import datetime, timezone
from typing import Dict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ================= CONFIG =================
TOKEN = os.getenv("TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))

TEST_MODE = False

user_sessions: Dict[int, dict] = {}

def parse_card(line: str):
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

        return {
            "card": card, "mm": mm, "yy": yy[-2:], "cvv": cvv, "name": name,
            "address": address, "city": city, "state": state, "zip": zipcode,
            "country": country, "last4": card[-4:]
        }
    except:
        return None

def format_card(card: dict, test_mode: bool = False) -> str:
    title = "TestMode Demo" if test_mode else "LIVE"
    lines = [
        "══════════════════════════════════════",
        f"🃏 {title}",
        "══════════════════════════════════════",
        f"👤 Name    : {card['name']}",
        f"💳 Card    : {card['card']}",
        f"📅 Expiry  : {card['mm']}/{card['yy']}",
        f"🔒 CVV     : {card['cvv']}",
        f"📍 {card['address']}, {card['city']}, {card['state']} {card['zip']}",
        f"🌍 {card['country']}",
        "",
        f"🕒 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
        "══════════════════════════════════════"
    ]
    return "\n".join(lines)

def main_menu():
    status = "🟢 TEST MODE ON (Skip to File)" if TEST_MODE else "🔴 TEST MODE OFF"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Format", callback_data="format")],
        [InlineKeyboardButton(status, callback_data="toggle_test")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Access Denied.")
        return
    await update.message.reply_text("Welcome to E$CO Admin Panel", reply_markup=main_menu())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TEST_MODE
    query = update.callback_query
    await query.answer()
    action = query.data
    uid = query.from_user.id

    if action == "toggle_test":
        TEST_MODE = not TEST_MODE
        status = "ON - Skip directly to file with TestMode Demo" if TEST_MODE else "OFF"
        await query.edit_message_text(f"Test Mode is now **{status}**", parse_mode='HTML', reply_markup=main_menu())
        return

    if action == "cancel":
        user_sessions.pop(uid, None)
        await query.edit_message_text("Returned to main menu.", reply_markup=main_menu())
        return

    if action == "format":
        await query.edit_message_text("Send cards or drop a .txt file:")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
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
        [InlineKeyboardButton("Check (Generate File)", callback_data="check")],
        [InlineKeyboardButton("Add More Cards", callback_data="format")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ]

    await update.message.reply_text(
        f"Pre Summary\nTotal Cards: {total}\nTest Mode: {'ON' if TEST_MODE else 'OFF'}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def check_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    session = user_sessions.get(uid)
    if not session or not session.get("cards"):
        await query.edit_message_text("No cards found.")
        return

    if TEST_MODE:
        content = "\n\n".join(format_card(c, test_mode=True) for c in session["cards"])
        count = len(session["cards"])
        filename = f"TestMode-Demo-{count}.txt"

        await query.message.reply_document(
            document=bytes(content, "utf-8"),
            filename=filename
        )
        await query.edit_message_text(f"✅ Done! Sent {count} cards as TestMode Demo.")
        user_sessions.pop(uid, None)
        return

    await query.edit_message_text("Normal mode is not implemented in this version.")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("testmode", button_handler))  # alias
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CallbackQueryHandler(check_handler, pattern="^check$"))
    app.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL, message_handler))

    print("🚀 Bot Started - TestMode 'Skip to File' Enabled")
    app.run_polling()

if __name__ == "__main__":
    main()
