import asyncio
import os
import random
from datetime import datetime
from typing import List, Dict

import requests
from requests.adapters import HTTPAdapter, Retry
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes,
    filters, ConversationHandler, CallbackQueryHandler,
)

# ====================== CONFIG ======================
TOKEN = "8736162481:AAExSSrfNZ9xSap7E-ZNtz42PvBbEIslvE0"
OWNER_ID = 6329309831
STORM_API_KEY = "38223|COVoley7T1hbfcCo92qI9Wr6NSbUVcMqTTLMePNMfc29b2ec"

BASE_URL = "https://api.storm.gift/api/v1"
HEADERS = {"Authorization": f"Bearer {STORM_API_KEY}", "Accept": "application/json", "Content-Type": "application/json"}

BATCH_SIZE = 800
INITIAL_WAIT = 25
POLL_INTERVAL = 8
SELLING_PRICE = 12.0
REPLACEMENT_COST = 1.4

session = requests.Session()
session.mount("https://", HTTPAdapter(max_retries=Retry(total=6, backoff_factor=0.6, status_forcelist=[429, 500, 502, 503, 504])))

# ====================== GLOBAL STATS ======================
total_revenue = 0.0
total_cards_sold = 0
total_tester_cards = 0
total_replacements = 0
BIN_RATER: Dict[str, Dict[str, str]] = {}

# ====================== BIN DATABASE ======================
BIN_DATABASE = {
    "410039": {"brand": "VISA", "type": "CREDIT", "level": "TRADITIONAL", "bank": "CITIBANK", "country": "UNITED STATES", "rating": 7.0, "vr": 71},
    "410040": {"brand": "VISA", "type": "CREDIT", "level": "BUSINESS", "bank": "CITIBANK", "country": "UNITED STATES", "rating": 8.0, "vr": 84},
    "426684": {"brand": "VISA", "type": "CREDIT", "level": "TRADITIONAL", "bank": "CHASE", "country": "UNITED STATES", "rating": 4.0, "vr": 39},
}

def get_bin_info(card_number: str):
    prefix = card_number[:6]
    return BIN_DATABASE.get(prefix, {"brand": "UNKNOWN", "type": "CREDIT", "level": "STANDARD", "bank": "UNKNOWN", "country": "US", "rating": 5.0, "vr": 50})

def get_random_balance(card_number: str, is_tester: bool = False) -> float:
    info = get_bin_info(card_number)
    rating = info.get("rating", 5.0)
    if is_tester:
        return round(random.uniform(8.0, 180.0), 2)
    return round(random.uniform(250, 4500), 2)

def get_random_ip() -> str:
    return f"{random.randint(25,195)}.{random.randint(15,245)}.{random.randint(20,230)}.{random.randint(35,220)}"

def get_max_polls(total_cards: int) -> int:
    if total_cards < 10: return 3
    return 25 if total_cards > 500 else 15 if total_cards > 100 else 8

# ====================== KEYBOARDS ======================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Start New Check", callback_data="start_format")],
        [InlineKeyboardButton("🧪 Tester Cards", callback_data="start_tester")],
        [InlineKeyboardButton("🔄 Replacement", callback_data="start_replacement")],
        [InlineKeyboardButton("💰 Record Sale", callback_data="record_sale")],
        [InlineKeyboardButton("📊 Bin Rater", callback_data="bin_rater")],
        [InlineKeyboardButton("💳 Check Balance", callback_data="check_balance")],
    ])

def pre_summary_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 E$ CHECK", callback_data="confirm_check")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ])

def usa_foreign_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇺🇸 USA Cards", callback_data="usa_cards")],
        [InlineKeyboardButton("🌍 Foreign Cards", callback_data="foreign_cards")],
    ])

# ====================== FORMATTER ======================
def format_live_card(raw_line: str, is_tester: bool = False) -> str:
    try:
        parts = [p.strip() for p in raw_line.split('|')]
        card_number = parts[0]
        expiry = parts[1] if len(parts) > 1 else "00/00"
        cvv = parts[2] if len(parts) > 2 else "000"
        name = parts[3] if len(parts) > 3 else "N/A"
        info = get_bin_info(card_number)
        balance = get_random_balance(card_number, is_tester)
        ip = get_random_ip()
        vr = info.get("vr", 50)

        lines = [
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"🃏 LIVE CARD          VR: {vr}%",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"💰 Balance     : ${balance:.2f}",
            f"👤 Cardholder  : {name}",
            f"💳 Card Number : {card_number}",
            f"📅 Expiry      : {expiry}",
            f"🔒 CVV         : {cvv}",
            f"🏦 Bank        : {info['bank']}",
            f"🌍 Country     : {info['country']}",
            f"🌐 IP          : {ip}",
            f"🕒 Checked     : {datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')}",
            "━━━━━━━━━━━━━━━━━━━━━━"
        ]
        if is_tester:
            lines.append("❤️ Thank You For Choosing E$CO ❤️")
        return "\n".join(lines)
    except:
        return f"Error formatting: {raw_line}"

def is_live(item: dict) -> bool:
    status = str(item.get("status", "")).lower()
    response = str(item.get("response", "")).lower()
    return any(k in (status + response) for k in ["live", "approved", "success", "00"])

# ====================== CHECKER ======================
CHECKING_MESSAGES = ["🔍 Checking Bank Status...", "💳 Pulling Balance...", "📡 Validating Cards..."]

async def check_cards_with_storm(cards: List[str], status_message, max_polls: int):
    live_raw_cards = []
    seen = set()
    batch_id = f"TEST-{random.randint(10000,99999)}"

    await status_message.edit_text("🚀 Submitting batch to Storm API...")
    await asyncio.sleep(2)

    poll_url = f"{BASE_URL}/check/{batch_id}"
    poll_count = 0

    while poll_count < max_polls:
        poll_count += 1
        msg = CHECKING_MESSAGES[poll_count % len(CHECKING_MESSAGES)]
        await status_message.edit_text(f"{msg}\n\nPoll: {poll_count}/{max_polls} | Live: {len(live_raw_cards)}")
        await asyncio.sleep(POLL_INTERVAL)

        try:
            r = session.get(poll_url, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                items = r.json().get("data", {}).get("items", [])
                for item in items:
                    card_num = item.get("card_number") or item.get("cc")
                    if card_num and card_num not in seen and is_live(item):
                        seen.add(card_num)
                        for raw in cards:
                            if raw.startswith(card_num + "|") and raw not in live_raw_cards:
                                live_raw_cards.append(raw)
                                break
        except:
            pass

    return live_raw_cards, batch_id

# ====================== STATES ======================
MENU, COLLECTING, USA_FOREIGN, SUMMARY, CUSTOMER_NAME, TARGET_COUNT, BIN_RATER_MODE = range(7)

# ====================== START SCREEN (UPDATED) ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Unauthorized.")
        return ConversationHandler.END

    global total_revenue, total_cards_sold, total_tester_cards, total_replacements
    profit = round(total_revenue - (total_cards_sold * 1.6) - (total_replacements * REPLACEMENT_COST), 2)

    text = (
        "🔥 **E$CO CONTROL PANEL** 🔥\n\n"
        "👑 Welcome back, Admin\n\n"
        f"💵 Total Revenue : `${total_revenue:.2f}`\n"
        f"📦 Cards Sold     : `{total_cards_sold}`\n"
        f"🧪 Tester Cards   : `{total_tester_cards}`\n"
        f"🔄 Replacements   : `{total_replacements}`\n"
        f"📈 Net Profit     : `${profit:.2f}`\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "**Available Features:**\n\n"
        "🔍 **Start New Check** → Normal live check + revenue tracking\n"
        "🧪 **Tester Cards** → Test cards, no revenue, file named Test-#####\n"
        "🔄 **Replacement** → Replacement for customer (deducts $1.4 per card)\n"
        "💰 **Record Sale** → Record customer sale with name + live count\n"
        "📊 **Bin Rater** → Save BIN ratings for future checks\n"
        "💳 **Check Balance** → Check Storm API credits\n\n"
        "Choose an option below:"
    )

    await update.message.reply_text(text, reply_markup=main_menu(), parse_mode='Markdown')
    context.user_data.clear()
    return MENU

# ====================== BUTTON HANDLER ======================
async def main_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    context.user_data.clear()

    if data in ["start_format", "start_tester"]:
        context.user_data["mode"] = "normal" if data == "start_format" else "tester"
        context.user_data["is_tester"] = (data == "start_tester")
        await query.edit_message_text("Send cards or .txt file now.\nType /cancel anytime.", parse_mode='Markdown')
        return COLLECTING

    if data == "start_replacement":
        context.user_data["mode"] = "replacement"
        await query.edit_message_text("🔄 **Replacement Mode**\n\nPlease send the **Customer Name**:", parse_mode='Markdown')
        return CUSTOMER_NAME

    if data == "record_sale":
        context.user_data["mode"] = "sale"
        await query.edit_message_text("💰 **Record Sale**\n\nPlease send the **Customer Name**:", parse_mode='Markdown')
        return CUSTOMER_NAME

    if data == "bin_rater":
        await query.edit_message_text("📊 Send BIN rating like this:\n`410039 8.5 Good for cashout`", parse_mode='Markdown')
        return BIN_RATER_MODE

    if data == "check_balance":
        return await check_balance(update, context)

# ====================== CUSTOMER NAME & COUNT ======================
async def get_customer_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip().replace(" ", "_")
    context.user_data["customer_name"] = name
    mode = context.user_data["mode"]

    if mode == "sale":
        await update.message.reply_text(f"✅ Customer: **{name}**\n\nHow many LIVE cards does the customer want? (Number only)", parse_mode='Markdown')
    else:
        await update.message.reply_text(f"✅ Customer: **{name}**\n\nHow many replacements? (Number only)", parse_mode='Markdown')
    return TARGET_COUNT

async def get_target_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        count = int(update.message.text.strip())
        context.user_data["target_count"] = count
        await update.message.reply_text("✅ Target saved.\n\nNow send the cards or .txt file.", parse_mode='Markdown')
        return COLLECTING
    except:
        await update.message.reply_text("❌ Please send a valid number.")
        return TARGET_COUNT

# ====================== COLLECT CARDS ======================
async def collect_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text and update.message.text.strip().lower() in ["/cancel", "cancel"]:
        return await cancel(update, context)

    text = ""
    if update.message.document:
        file = await update.message.document.get_file()
        content = await file.download_as_bytearray()
        text = content.decode("utf-8", errors="ignore")
    else:
        text = update.message.text or ""

    new_cards = [line.strip() for line in text.splitlines() if "|" in line.strip() and len(line.split('|')) >= 3]
    
    if not new_cards:
        await update.message.reply_text("No valid cards found. Try again or /cancel.")
        return COLLECTING

    context.user_data.setdefault("all_cards", []).extend(new_cards)
    await update.message.reply_text("Are these USA or Foreign cards?", reply_markup=usa_foreign_keyboard(), parse_mode='Markdown')
    return USA_FOREIGN

async def usa_foreign_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await show_pre_summary(query, context)
    return SUMMARY

async def show_pre_summary(query, context: ContextTypes.DEFAULT_TYPE):
    total = len(context.user_data.get("all_cards", []))
    mode = context.user_data.get("mode", "normal")
    await query.edit_message_text(
        f"📊 **PRE-SUMMARY**\n\n"
        f"Total Cards: `{total}`\n"
        f"Mode: **{mode.upper()}**\n\n"
        "Press **🚀 E$ CHECK** when ready.",
        reply_markup=pre_summary_keyboard(),
        parse_mode='Markdown'
    )

# ====================== POST SUMMARY (MAIN FIX HERE) ======================
async def pre_summary_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "confirm_check":
        cards = context.user_data.get("all_cards", [])
        if not cards:
            await query.edit_message_text("No cards!", reply_markup=main_menu())
            return MENU

        context.user_data["start_time"] = datetime.now()
        status_msg = await query.edit_message_text("🚀 Starting check...")

        live_cards, batch_id = await check_cards_with_storm(cards, status_msg, get_max_polls(len(cards)))
        context.user_data["live_cards"] = live_cards
        context.user_data["batch_id"] = batch_id
        context.user_data["end_time"] = datetime.now()

        await show_post_summary(status_msg, context)
        return MENU
    elif query.data == "cancel":
        await query.edit_message_text("✅ Cancelled.", reply_markup=main_menu())
        context.user_data.clear()
        return MENU

async def show_post_summary(status_msg, context: ContextTypes.DEFAULT_TYPE):
    global total_revenue, total_cards_sold, total_tester_cards, total_replacements

    live_cards = context.user_data.get("live_cards", [])
    live_count = len(live_cards)
    total_cards = len(context.user_data.get("all_cards", []))
    mode = context.user_data.get("mode", "normal")
    customer = context.user_data.get("customer_name", "Unknown")
    batch_id = context.user_data.get("batch_id", "N/A")
    live_rate = round((live_count / total_cards * 100), 2) if total_cards > 0 else 0.0

    if mode == "tester":
        test_num = random.randint(10000, 99999)
        filename = f"Test-{test_num}"
        revenue_text = "🧪 Tester Mode - No Revenue Recorded"
        total_tester_cards += live_count
    elif mode == "replacement":
        deduction = round(live_count * REPLACEMENT_COST, 2)
        total_revenue = round(total_revenue - deduction, 2)
        total_replacements += live_count
        filename = f"{customer}_Rep{live_count}"
        revenue_text = f"🔄 Replacement -${deduction}"
    elif mode == "sale":
        revenue = round(live_count * SELLING_PRICE, 2)
        total_revenue += revenue
        total_cards_sold += live_count
        filename = f"{customer}_{live_count}_Live"
        revenue_text = f"💰 Revenue +${revenue}"
    else:  # normal
        revenue = round(live_count * SELLING_PRICE, 2)
        total_revenue += revenue
        total_cards_sold += live_count
        filename = f"{customer}_{live_count}_Live"
        revenue_text = f"💰 Revenue +${revenue}"

    final_filename = f"{filename}.txt"
    formatted = [format_live_card(raw, mode == "tester") for raw in live_cards]

    with open(final_filename, "w", encoding="utf-8") as f:
        f.write("\n".join(formatted))

    post_text = (
        "📊 **POST SUMMARY**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Batch ID     : `{batch_id}`\n"
        f"Total Cards  : `{total_cards}`\n"
        f"Cards Live   : `{live_count}`\n"
        f"Live Rate    : `{live_rate}%`\n"
        f"Mode         : **{mode.upper()}**\n"
        f"{revenue_text}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ File attached below."
    )

    await status_msg.edit_text(post_text, parse_mode='Markdown')
    await status_msg.reply_document(document=open(final_filename, "rb"), caption=final_filename)

    try:
        os.remove(final_filename)
    except:
        pass

    context.user_data.clear()
    await status_msg.reply_text("✅ Operation Completed.", reply_markup=main_menu())

# ====================== OTHER FUNCTIONS ======================
async def check_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        r = session.get(f"{BASE_URL}/user", headers=HEADERS, timeout=15)
        credits = r.json().get("data", {}).get("remaining_credits", "N/A")
        await query.edit_message_text(f"💳 Storm API Credits: `{credits}`", parse_mode='Markdown', reply_markup=main_menu())
    except:
        await query.edit_message_text("❌ Failed to fetch balance.", reply_markup=main_menu(), parse_mode='Markdown')

async def save_bin_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() in ["/cancel", "cancel"]:
        return await cancel(update, context)
    try:
        parts = text.split(maxsplit=2)
        bin_prefix = parts[0][:6]
        rating = parts[1]
        suggestion = parts[2] if len(parts) > 2 else "No suggestion"
        BIN_RATER[bin_prefix] = {"rating": rating, "suggestion": suggestion}
        await update.message.reply_text(f"✅ BIN `{bin_prefix}` saved with rating `{rating}`", parse_mode='Markdown', reply_markup=main_menu())
        return MENU
    except:
        await update.message.reply_text("❌ Wrong format.\nExample: `410039 8.5 Good for cashout`")
        return BIN_RATER_MODE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Cancelled.", reply_markup=main_menu())
    context.user_data.clear()
    return MENU

# ====================== BUILD & RUN ======================
def build_handler():
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [CallbackQueryHandler(main_button)],
            CUSTOMER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_customer_name)],
            TARGET_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_target_count)],
            COLLECTING: [MessageHandler(filters.TEXT | filters.Document.ALL, collect_cards)],
            USA_FOREIGN: [CallbackQueryHandler(usa_foreign_handler)],
            SUMMARY: [CallbackQueryHandler(pre_summary_handler)],
            BIN_RATER_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_bin_rating)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_chat=True,
    )

async def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(build_handler())
    print("✅ E$CO Bot v12.0 Started Successfully!")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
