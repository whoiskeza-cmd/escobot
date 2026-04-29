import asyncio
import random
import os
from datetime import datetime, timezone
from typing import Dict, List

import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ================= CONFIG =================
TOKEN = os.getenv("TOKEN")
API_KEY = os.getenv("API_KEY")
OWNER_ID = int(os.getenv("OWNER_ID"))
BASE_URL = os.getenv("BASE_URL", "https://api.storm.gift/api/v1")

print(f"✅ Bot starting for OWNER_ID: {OWNER_ID}")
print(f"🌐 Using BASE_URL: {BASE_URL}")

TEST_MODE = False

stats = {
    "cards_sold": 0, "total_sales": 0, "revenue": 0.0,
    "testers_given": 0, "replacements_given": 0, "profit": 0.0,
    "card_cost": 2.50, "sale_price": 15.00
}

BIN_DATA: Dict[str, dict] = {}  # You can keep adding BINs later

user_sessions: Dict[int, dict] = {}

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
        info = BIN_DATA.get(bin6, {"bank":"UNKNOWN","brand":"VISA","level":"STANDARD","vr":75,"balance":80,"suggestion":"Retail"})

        return {
            "card": card, "mm": mm, "yy": yy[-2:], "cvv": cvv, "name": name,
            "address": address, "city": city, "state": state, "zip": zipcode,
            "country": country, "phone": phone, "email": email,
            "bank": info["bank"], "brand": info["brand"], "level": info["level"],
            "bin_rating": info.get("vr", 75), "suggestion": info.get("suggestion", "Retail"),
            "last4": card[-4:]
        }
    except Exception:
        return None

def format_live_card(card: dict, test_mode: bool = False) -> str:
    vr = random.randint(68, 97)
    balance, label = generate_balance("CREDIT" in card.get("level", ""))
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

def main_menu() -> InlineKeyboardMarkup:
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

# ===================== MAIN HANDLERS =====================
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
    status = "ENABLED (Skip to File - TestMode Demo)" if TEST_MODE else "DISABLED (Real API)"
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(f"🔧 Test Mode is now **{status}**", parse_mode='HTML')
        await query.edit_message_reply_markup(reply_markup=main_menu())
    else:
        await update.message.reply_text(f"🔧 Test Mode is now **{status}**", parse_mode='HTML')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        if update.callback_query:
            await update.callback_query.answer("Access Denied.", show_alert=True)
        return

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
    if action == "add_more":
        session["mode"] = "format"
        await query.edit_message_text("Send more cards or drop another .txt file:")
        return

    session["mode"] = action
    if action == "format":
        await query.edit_message_text("Send Cards or drop a .txt file to continue.")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    uid = update.effective_user.id
    session = user_sessions.get(uid)
    if not session: return

    new_cards = []
    if update.message.document:
        file = await update.message.document.get_file()
        content = (await file.download_as_bytearray()).decode("utf-8")
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
        [InlineKeyboardButton("Check", callback_data="check")],
        [InlineKeyboardButton("Add More Cards", callback_data="add_more")],
        [InlineKeyboardButton("Remove Cards", callback_data="remove")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ]

    pre_text = f"""Pre Summary/Confirmation
Total Cards: {total}
Total USA: {usa}
Mode: {session.get('mode', 'Format').capitalize()}
Test Mode: {'ON - Will skip to file' if TEST_MODE else 'OFF'}
"""
    await update.message.reply_text(pre_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def check_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    session = user_sessions.get(uid)
    if not session or not session.get("cards"):
        await query.edit_message_text("❌ No cards found.")
        return

    if TEST_MODE:
        content = "\n\n".join(format_live_card(c, test_mode=True) for c in session["cards"])
        count = len(session["cards"])
        filename = f"TestMode-Demo-{count}-{random.randint(1000,9999)}.txt"

        await query.message.reply_document(
            document=bytes(content, "utf-8"),
            filename=filename
        )
        await query.edit_message_text(f"✅ TestMode Complete!\nSent {count} cards with 'TestMode Demo' header.")
        user_sessions.pop(uid, None)
        return

    # Normal mode (kept minimal)
    await query.edit_message_text("Normal mode not fully implemented in this simplified version.")

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("testmode", toggle_test_mode))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CallbackQueryHandler(check_handler, pattern="^check$"))
    app.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL, message_handler))

    print("🚀 E$CO Bot Started - Test Mode: Skip directly to file")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
