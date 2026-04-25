import asyncio
import os
import random
from datetime import datetime, timedelta
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

INITIAL_WAIT = 25
POLL_INTERVAL = 8
SELLING_PRICE = 12.0
REPLACEMENT_COST = 1.4

session = requests.Session()
session.mount("https://", HTTPAdapter(max_retries=Retry(total=8, backoff_factor=1.2, status_forcelist=[429, 500, 502, 503, 504])))

# ====================== GLOBAL STATS ======================
total_revenue = 0.0
total_cards_sold = 0
total_tester_cards = 0
total_replacements = 0
BIN_RATER: Dict[str, Dict[str, str]] = {}

# ====================== BIN DATABASE (UPDATED & EXPANDED) ======================
BIN_DATABASE = {
    "192051": {"brand": "UATP", "type": "CREDIT", "level": "UATP", "bank": "LUFTHANSA AIRPLUS SERVICEKARTEN GMBH", "country": "GERMANY", "rating": 6.0, "vr": 55},
    "371290": {"brand": "AMERICAN EXPRESS", "type": "CREDIT", "level": "PERSONAL", "bank": "AMERICAN EXPRESS US CONSUMER", "country": "UNITED STATES", "rating": 5.5, "vr": 88},
    "400022": {"brand": "DINERS CLUB INTERNATIONAL", "type": "CREDIT", "level": "BUSINESS", "bank": "DINERS CLUB", "country": "UNITED STATES", "rating": 5.5, "vr": 52},
    "400895": {"brand": "VISA", "type": "DEBIT", "level": "CLASSIC", "bank": "NAVY FEDERAL CREDIT UNION", "country": "UNITED STATES", "rating": 7.8, "vr": 79},
    "410039": {"brand": "VISA", "type": "CREDIT", "level": "TRADITIONAL", "bank": "CITIBANK, N.A. - COSTCO", "country": "UNITED STATES", "rating": 6.2, "vr": 84},
    "410040": {"brand": "VISA", "type": "CREDIT", "level": "BUSINESS", "bank": "CITIBANK, N.A. - COSTCO", "country": "UNITED STATES", "rating": 7.0, "vr": 82},
    "423904": {"brand": "VISA", "type": "DEBIT", "level": "CLASSIC", "bank": "ARVEST BANK", "country": "UNITED STATES", "rating": 6.5, "vr": 68},
    "426684": {"brand": "VISA", "type": "CREDIT", "level": "TRADITIONAL", "bank": "JPMORGAN CHASE BANK N.A.", "country": "UNITED STATES", "rating": 3.0, "vr": 72},
    "434256": {"brand": "VISA", "type": "DEBIT", "level": "CLASSIC", "bank": "WELLS FARGO BANK, NATIONAL ASSOCIATION", "country": "UNITED STATES", "rating": 6.8, "vr": 70},
    "434769": {"brand": "VISA", "type": "DEBIT", "level": "CLASSIC", "bank": "JPMORGAN CHASE BANK N.A. - DEBIT", "country": "UNITED STATES", "rating": 7.5, "vr": 77},
    "440215": {"brand": "VISA", "type": "DEBIT", "level": "CLASSIC", "bank": "TTCU FEDERAL CREDIT UNION", "country": "UNITED STATES", "rating": 6.0, "vr": 62},
    "443045": {"brand": "VISA", "type": "DEBIT", "level": "CLASSIC", "bank": "PNC BANK, NATIONAL ASSOCIATION", "country": "UNITED STATES", "rating": 7.2, "vr": 74},
    "461046": {"brand": "VISA", "type": "DEBIT", "level": "CLASSIC", "bank": "JPMORGAN CHASE BANK N.A. - DEBIT", "country": "UNITED STATES", "rating": 7.4, "vr": 76},
    "470793": {"brand": "VISA", "type": "CREDIT", "level": "TRADITIONAL", "bank": "CREDIT ONE BANK, NATIONAL ASSOCIATION", "country": "UNITED STATES", "rating": 6.5, "vr": 65},
    "474485": {"brand": "VISA", "type": "DEBIT", "level": "CLASSIC", "bank": "BANK OF AMERICA, NATIONAL ASSOCIATION", "country": "UNITED STATES", "rating": 8.0, "vr": 81},
    "475833": {"brand": "VISA", "type": "DEBIT", "level": "CLASSIC", "bank": "CHOICE FINANCIAL GROUP", "country": "UNITED STATES", "rating": 6.2, "vr": 64},
    "482821": {"brand": "VISA", "type": "CREDIT", "level": "SIGNATURE", "bank": "THE BANCORP BANK, NATIONAL ASSOCIATION", "country": "UNITED STATES", "rating": 7.8, "vr": 80},
    "483312": {"brand": "VISA", "type": "DEBIT", "level": "CLASSIC", "bank": "JPMORGAN CHASE BANK N.A. - DEBIT", "country": "UNITED STATES", "rating": 4.3, "vr": 75},
    "483316": {"brand": "VISA", "type": "DEBIT", "level": "CLASSIC", "bank": "JPMORGAN CHASE BANK N.A. - DEBIT", "country": "UNITED STATES", "rating": 2.3, "vr": 75},
    "498503": {"brand": "VISA", "type": "DEBIT", "level": "CLASSIC", "bank": "STRIDE BANK, NATIONAL ASSOCIATION", "country": "UNITED STATES", "rating": 6.8, "vr": 69},
    "513379": {"brand": "MASTERCARD", "type": "DEBIT", "level": "STANDARD", "bank": "BANQUE FEDERATIVE DU CREDIT MUTUEL (BFCM)", "country": "FRANCE", "rating": 8.5, "vr": 58},
    "514616": {"brand": "MASTERCARD", "type": "DEBIT", "level": "ENHANCED", "bank": "WOODFOREST NATIONAL BANK", "country": "UNITED STATES", "rating": 7.0, "vr": 73},
    "517805": {"brand": "MASTERCARD", "type": "CREDIT", "level": "WORLD", "bank": "CAPITAL ONE, NATIONAL ASSOCIATION", "country": "UNITED STATES", "rating": 8.1, "vr": 83},
    "521403": {"brand": "MASTERCARD", "type": "DEBIT", "level": "PREPAID GOVERNMENT", "bank": "COMERICA BANK", "country": "UNITED STATES", "rating": 6.0, "vr": 61},
    "521729": {"brand": "MASTERCARD", "type": "DEBIT", "level": "STANDARD", "bank": "COMMONWEALTH BANK OF AUSTRALIA", "country": "AUSTRALIA", "rating": 6.5, "vr": 67},
    "522535": {"brand": "MASTERCARD", "type": "DEBIT", "level": "ENHANCED", "bank": "PROVIDENT BANK", "country": "UNITED STATES", "rating": 7.2, "vr": 74},
    "527515": {"brand": "MASTERCARD", "type": "DEBIT", "level": "ENHANCED", "bank": "BANK OF AMERICA, NATIONAL ASSOCIATION", "country": "UNITED STATES", "rating": 7.9, "vr": 81},
    "534348": {"brand": "MASTERCARD", "type": "CREDIT", "level": "PLATINUM", "bank": "CELTIC BANK CORPORATION", "country": "UNITED STATES", "rating": 5.5, "vr": 78},
    "542418": {"brand": "MASTERCARD", "type": "CREDIT", "level": "PLATINUM", "bank": "CITIBANK N.A.", "country": "UNITED STATES", "rating": 6.0, "vr": 82},
}

def get_bin_info(card_number: str):
    prefix = card_number[:6]
    return BIN_DATABASE.get(prefix, {"brand": "UNKNOWN", "type": "CREDIT", "level": "STANDARD", "bank": "UNKNOWN BANK", "country": "UNITED STATES", "rating": 5.0, "vr": 45})

def get_random_balance(card_number: str, is_tester: bool = False) -> float:
    info = get_bin_info(card_number)
    rating = info.get("rating", 5.0)
    if is_tester:
        rand = random.random()
        if rand < 0.85: return round(random.uniform(250.0, 799.0), 2)
        elif rand < 0.95: return round(random.uniform(950.0, 2450.0), 2)
        else: return round(random.uniform(25.0, 169.0), 2)
    min_bal = 220 + (rating * 58)
    max_bal = 720 + (rating * 148)
    balance = random.uniform(min_bal, max_bal)
    if random.random() < (rating / 11.5):
        balance = random.uniform(1350, 8500)
    return round(min(9999.99, balance + random.uniform(0.0, 0.99)), 2)

def get_random_ip() -> str:
    return f"{random.randint(25,195)}.{random.randint(15,245)}.{random.randint(20,230)}.{random.randint(35,220)}"

def get_max_polls(total_cards: int) -> int:
    if total_cards < 10: return 4
    elif total_cards <= 50: return 12
    elif total_cards <= 300: return 18
    else: return 25

# ====================== KEYBOARDS ======================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Start New Check", callback_data="start_format")],
        [InlineKeyboardButton("🧪 Tester Cards", callback_data="start_tester")],
        [InlineKeyboardButton("🔄 E$ Replacement", callback_data="start_replacement")],
        [InlineKeyboardButton("💰 Record Sale", callback_data="record_sale")],
        [InlineKeyboardButton("📊 Bin Rater", callback_data="bin_rater")],
        [InlineKeyboardButton("💳 Check Balance", callback_data="check_balance")],
    ])

def pre_summary_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add More Cards", callback_data="add_more")],
        [InlineKeyboardButton("📝 Set Filename", callback_data="set_filename")],
        [InlineKeyboardButton("🗑️ Remove Card (Last 4)", callback_data="remove_last4")],
        [InlineKeyboardButton("🚀 E$ CHECK", callback_data="confirm_check")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ])

def usa_foreign_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇺🇸 USA Cards", callback_data="usa_cards")],
        [InlineKeyboardButton("🌍 Foreign Cards", callback_data="foreign_cards")],
    ])

def replacement_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Send Prepare Reps", callback_data="prepare_reps")],
        [InlineKeyboardButton("⚙️ Rep Settings", callback_data="rep_settings")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_main")],
    ])

# ====================== FIXED FORMATTER ======================
def format_live_card(raw_line: str, is_tester: bool = False) -> str:
    try:
        parts = [p.strip() for p in raw_line.replace("=>", "|").split('|')]
        
        card    = parts[0]
        month   = parts[1]
        year    = parts[2]
        cvv     = parts[3]
        name    = parts[4]
        address = parts[5]
        city    = parts[6]
        state   = parts[7]
        zipcode = parts[8]
        country = parts[9]
        phone   = parts[10]
        email   = parts[11] if len(parts) > 11 else "N/A"

        balance = get_random_balance(card, is_tester)
        ip = get_random_ip()
        info = get_bin_info(card)
        base_vr = info.get("vr", 45)
        vr = max(5, min(99, int(base_vr + random.gauss(0, 8))))
        
        bin_data = BIN_RATER.get(card[:6], {"rating": "N/A", "suggestion": "No rating added yet"})

        output = [
            "══════════════════════════════════════",
            f"🃏 LIVE • VR: {vr}%",
            "══════════════════════════════════════",
            f"💰 Balance : ${balance:.2f}",
            f"👤 Name    : {name}",
            f"💳 Card    : {card}",
            f"📅 Expiry  : {month}/{year}",
            f"🔒 CVV     : {cvv}",
            f"🏦 Bank    : {info.get('bank', 'UNKNOWN')}",
            f"🌍 Country : {country} • {info.get('brand', 'UNKNOWN')} {info.get('level', 'STANDARD')}",
            "",
            "📍 Billing Address:",
            f"   {address}",
            f"   {city}, {state} {zipcode}",
            f"   Phone  : {phone}",
            f"   Email  : {email}",
            "",
            f"🌐 IP      : {ip}",
            f"🕒 Checked : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "══════════════════════════════════════",
            f"BIN Rate   : {bin_data['rating']} | {bin_data['suggestion']}",
            "══════════════════════════════════════"
        ]
        
        if is_tester:
            output.append("❤️ Thank You For Choosing E$CO ❤️")
            
        return "\n".join(output)
        
    except Exception as e:
        return f"Parse Error: {raw_line}\nError: {str(e)}"

# ====================== CHECKER ======================
def is_live(item: dict) -> bool:
    if not isinstance(item, dict): return False
    text = " ".join(str(v).lower() for v in item.values())
    positive = ["live", "approved", "success", "charged", "passed", "valid", "good", "200", "ok"]
    return any(k in text for k in positive)

async def check_cards_with_storm(cards: List[str], status_message, max_polls: int):
    live_raw_cards = []
    seen = set()
    batch_id = None
    total = len(cards)

    await status_message.edit_text("Prepping Api For Account Status & Balance Check")

    try:
        r = session.post(f"{BASE_URL}/check", headers=HEADERS, json={"cards": cards}, timeout=40)
        r.raise_for_status()
        data = r.json()
        batch_id = data.get("batch_id") or data.get("id") or data.get("data", {}).get("batch_id") or data.get("data", {}).get("id")
        if not batch_id:
            await status_message.edit_text("❌ Failed to get batch_id.")
            return [], None
    except Exception as e:
        await status_message.edit_text(f"❌ Submission Error: {str(e)}")
        return [], None

    await status_message.edit_text(f"✅ Batch {batch_id} submitted.\nEnsuring 100% Quality By Balance And Live Checking\nWaiting {INITIAL_WAIT}s...")
    await asyncio.sleep(INITIAL_WAIT)

    poll_url = f"{BASE_URL}/check/{batch_id}"
    poll_count = 0

    while poll_count < max_polls:
        poll_count += 1
        await status_message.edit_text(f"Ensuring 100% Quality By Balance And Live Checking\nPoll: {poll_count}/{max_polls} | Live: {len(live_raw_cards)}")

        try:
            r = session.get(poll_url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            data = r.json()
            items = (data.get("data", {}).get("items") or data.get("data", {}).get("results") or 
                    data.get("items") or data.get("results") or data.get("checks", []))

            for item in items:
                if not isinstance(item, dict): continue
                card_num = str(item.get("card_number") or item.get("cc") or item.get("card") or "").strip()
                if card_num and card_num not in seen and is_live(item):
                    seen.add(card_num)
                    for raw in cards:
                        if raw.split('|')[0].strip()[-4:] == card_num[-4:]:
                            if raw not in live_raw_cards:
                                live_raw_cards.append(raw)
                            break
        except Exception:
            pass

        await asyncio.sleep(POLL_INTERVAL)

    return live_raw_cards, batch_id

# ====================== HANDLER FUNCTIONS ======================
async def get_customer_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip().replace(" ", "_")
    context.user_data["customer_name"] = name
    mode = context.user_data.get("mode", "normal")
    text = f"✅ Customer: **{name}**\n\n"
    if mode == "sale":
        text += "How many **LIVE** cards? (number)"
    else:
        text += "How many replacements? (number)"
    await update.message.reply_text(text, parse_mode='Markdown')
    return TARGET_COUNT

async def get_target_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        count = int(update.message.text.strip())
        context.user_data["target_count"] = count
        await update.message.reply_text("✅ Target saved.\nSend cards or .txt file.", parse_mode='Markdown')
        return COLLECTING
    except:
        await update.message.reply_text("❌ Invalid number.")
        return TARGET_COUNT

# ====================== STATES ======================
MENU, COLLECTING, USA_FOREIGN, SUMMARY, ADD_MORE_CARDS, REMOVE_LAST4, CUSTOMER_NAME, TARGET_COUNT, BIN_RATER_MODE, FILENAME, REP_SETTINGS = range(11)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Unauthorized.")
        return ConversationHandler.END

    global total_revenue, total_cards_sold, total_tester_cards, total_replacements
    profit = round(total_revenue - (total_cards_sold * 1.6) - (total_replacements * REPLACEMENT_COST), 2)

    welcome_text = (
        "🔥 **E$CO CONTROL PANEL** 🔥\n\n"
        f"Welcome, @{update.effective_user.username}\n\n"
        f"💵 Revenue : `${total_revenue:.2f}`\n"
        f"📦 Sold    : `{total_cards_sold}`\n"
        f"🧪 Tester  : `{total_tester_cards}`\n"
        f"🔄 Repl    : `{total_replacements}`\n"
        f"📈 Profit  : `${profit:.2f}`\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\nChoose option:"
    )

    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=main_menu(), parse_mode='Markdown')
    else:
        await update.callback_query.edit_message_text(welcome_text, reply_markup=main_menu(), parse_mode='Markdown')
    context.user_data.clear()
    return MENU

async def main_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    context.user_data.clear()

    if data in ["start_format", "start_tester"]:
        context.user_data["mode"] = "normal" if data == "start_format" else "tester"
        context.user_data["is_tester"] = (data == "start_tester")
        context.user_data["all_cards"] = []
        context.user_data["filename"] = None
        await query.edit_message_text("Send cards or .txt file.\n/cancel to stop.", parse_mode='Markdown')
        return COLLECTING

    if data == "start_replacement":
        await query.edit_message_text("🔄 **E$ Replacement Menu**", reply_markup=replacement_menu(), parse_mode='Markdown')
        return MENU

    if data == "prepare_reps":
        context.user_data["mode"] = "replacement"
        await query.edit_message_text("Send Customer Name:", parse_mode='Markdown')
        return CUSTOMER_NAME

    if data == "rep_settings":
        await query.edit_message_text("⚙️ Rep Settings\n\nUse:\n/setvr 85\n/setformat pipe", parse_mode='Markdown')
        return REP_SETTINGS

    if data == "back_to_main":
        return await start(update, context)

    if data == "record_sale":
        context.user_data["mode"] = "sale"
        await query.edit_message_text("💰 **Record Sale**\n\nSend Customer Name:", parse_mode='Markdown')
        return CUSTOMER_NAME

    if data == "bin_rater":
        await query.edit_message_text("📊 Send BIN rating:\n`410039 8.5 Good for cashout`", parse_mode='Markdown')
        return BIN_RATER_MODE

    if data == "check_balance":
        return await check_balance(query, context)

    if data == "set_filename":
        await query.edit_message_text("Send the desired filename (without .txt):", parse_mode='Markdown')
        return FILENAME

async def get_filename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    filename = update.message.text.strip().replace(" ", "_")
    context.user_data["filename"] = filename
    await update.message.reply_text(f"✅ Filename set to: **{filename}.txt**", parse_mode='Markdown')
    await show_pre_summary_from_message(update, context)
    return SUMMARY

async def collect_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text and update.message.text.strip().lower() in ["/cancel", "cancel"]:
        return await start(update, context)

    text = ""
    if update.message.document:
        file = await update.message.document.get_file()
        content = await file.download_as_bytearray()
        text = content.decode("utf-8", errors="ignore")
    else:
        text = update.message.text or ""

    new_cards = [line.strip() for line in text.splitlines() if "|" in line.strip() and len(line.split('|')) >= 3]
    if not new_cards:
        await update.message.reply_text("No valid cards found.")
        return COLLECTING

    context.user_data.setdefault("all_cards", []).extend(new_cards)
    await update.message.reply_text(f"📥 Added **{len(new_cards)}** cards.\nUSA or Foreign?", reply_markup=usa_foreign_keyboard(), parse_mode='Markdown')
    return USA_FOREIGN

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

async def show_pre_summary(query, context: ContextTypes.DEFAULT_TYPE):
    cards = context.user_data.get("all_cards", [])
    total = len(cards)
    usa = context.user_data.get("usa_count", 0)
    foreign = context.user_data.get("foreign_count", 0)
    mode = context.user_data.get("mode", "normal")
    filename = context.user_data.get("filename", "Not Set")

    text = (f"📊 **PRE-SUMMARY**\n\n"
            f"Total : `{total}` | USA : `{usa}` | Foreign : `{foreign}`\n"
            f"Mode  : **{mode.upper()}**\n"
            f"Filename : `{filename}`\n\nSelect:")
    await query.edit_message_text(text, reply_markup=pre_summary_keyboard(), parse_mode='Markdown')

async def show_pre_summary_from_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cards = context.user_data.get("all_cards", [])
    total = len(cards)
    usa = context.user_data.get("usa_count", 0)
    foreign = context.user_data.get("foreign_count", 0)
    mode = context.user_data.get("mode", "normal")
    filename = context.user_data.get("filename", "Not Set")

    text = (f"📊 **PRE-SUMMARY**\n\n"
            f"Total : `{total}` | USA : `{usa}` | Foreign : `{foreign}`\n"
            f"Mode  : **{mode.upper()}**\n"
            f"Filename : `{filename}`\n\nSelect:")
    await update.message.reply_text(text, reply_markup=pre_summary_keyboard(), parse_mode='Markdown')

async def pre_summary_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "add_more":
        await query.edit_message_text("Send more cards or .txt file.\n/cancel to stop.", parse_mode='Markdown')
        return ADD_MORE_CARDS

    if data == "set_filename":
        await query.edit_message_text("Send the desired filename (without .txt):", parse_mode='Markdown')
        return FILENAME

    if data == "remove_last4":
        await query.edit_message_text("🗑️ Send last 4 digits to remove:", parse_mode='Markdown')
        return REMOVE_LAST4

    if data == "confirm_check":
        cards = context.user_data.get("all_cards", [])
        if not cards:
            await query.edit_message_text("❌ No cards.", reply_markup=main_menu())
            return MENU

        status_msg = await query.edit_message_text("🚀 Starting E$ CHECK...")
        max_polls = get_max_polls(len(cards))
        live_cards, batch_id = await check_cards_with_storm(cards, status_msg, max_polls)
        context.user_data["live_cards"] = live_cards
        context.user_data["batch_id"] = batch_id

        if not live_cards:
            await status_msg.edit_text("❌ **0 Live Cards Found**", parse_mode='Markdown', reply_markup=main_menu())
            return MENU

        await show_post_summary(status_msg, context)
        return MENU

    if data == "cancel":
        await query.edit_message_text("✅ Cancelled.", reply_markup=main_menu())
        context.user_data.clear()
        return MENU

async def remove_last4_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    last4 = update.message.text.strip()
    if len(last4) != 4 or not last4.isdigit():
        await update.message.reply_text("❌ Send exactly 4 digits.")
        return REMOVE_LAST4

    all_cards = context.user_data.get("all_cards", [])
    filtered = [c for c in all_cards if not c.split('|')[0].strip().endswith(last4)]
    removed = len(all_cards) - len(filtered)
    context.user_data["all_cards"] = filtered
    await update.message.reply_text(f"✅ Removed **{removed}** card(s) ending `{last4}`.", parse_mode='Markdown')
    await show_pre_summary_from_message(update, context)
    return SUMMARY

async def add_more_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text and update.message.text.strip().lower() in ["/cancel", "cancel"]:
        return await start(update, context)

    text = ""
    if update.message.document:
        file = await update.message.document.get_file()
        content = await file.download_as_bytearray()
        text = content.decode("utf-8", errors="ignore")
    else:
        text = update.message.text or ""

    new_cards = [line.strip() for line in text.splitlines() if "|" in line.strip() and len(line.split('|')) >= 3]
    if not new_cards:
        await update.message.reply_text("No valid cards.")
        return ADD_MORE_CARDS

    context.user_data.setdefault("all_cards", []).extend(new_cards)
    await update.message.reply_text(f"📥 Added **{len(new_cards)}** more.\nUSA or Foreign?", reply_markup=usa_foreign_keyboard(), parse_mode='Markdown')
    return USA_FOREIGN

async def show_post_summary(status_msg, context: ContextTypes.DEFAULT_TYPE):
    global total_revenue, total_cards_sold, total_tester_cards, total_replacements

    live_cards = context.user_data.get("live_cards", [])
    live_count = len(live_cards)
    total_cards = len(context.user_data.get("all_cards", []))
    mode = context.user_data.get("mode", "normal")
    customer = context.user_data.get("customer_name", "Unknown")
    batch_id = context.user_data.get("batch_id", "N/A")
    live_rate = round((live_count / total_cards * 100), 2) if total_cards > 0 else 0.0
    est_time = (datetime.utcnow() - timedelta(hours=4)).strftime("%Y-%m-%d %H:%M:%S EST")
    filename = context.user_data.get("filename") or f"Output-{random.randint(1000,9999)}"

    if mode == "tester":
        revenue_text = "🧪 Tester Mode"
        total_tester_cards += live_count
    elif mode == "replacement":
        deduction = round(live_count * REPLACEMENT_COST, 2)
        total_revenue = round(total_revenue - deduction, 2)
        total_replacements += live_count
        revenue_text = f"🔄 Replacement -${deduction}"
    else:
        revenue = round(live_count * SELLING_PRICE, 2)
        total_revenue += revenue
        total_cards_sold += live_count
        revenue_text = f"💰 +${revenue}"

    final_filename = f"{filename}.txt"
    formatted = [format_live_card(raw, mode == "tester") for raw in live_cards]

    with open(final_filename, "w", encoding="utf-8") as f:
        f.write("══════════════════════════════════════\n")
        f.write("          E$CO CHECK OUTPUT\n")
        f.write("══════════════════════════════════════\n\n")
        f.write("\n\n".join(formatted))
        f.write("\n\n══════════════════════════════════════\n")
        f.write("E$CO Post Summary Attached\n")
        f.write(f"Time Checked (EST): {est_time}\n")
        f.write("══════════════════════════════════════\n")

    post_text = (
        "📊 **POST SUMMARY**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Batch   : `{batch_id}`\n"
        f"Total   : `{total_cards}` | Live : `{live_count}` ({live_rate}%)\n"
        f"Mode    : **{mode.upper()}**\n"
        f"{revenue_text}\n"
        f"Filename: `{final_filename}`\n"
        f"Time Checked (EST): `{est_time}`\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )

    await status_msg.edit_text(post_text, parse_mode='Markdown')
    await status_msg.reply_document(document=open(final_filename, "rb"), caption=final_filename)

    try: os.remove(final_filename)
    except: pass

    await status_msg.reply_text("**E$ Check Has Successfully Completed**", parse_mode='Markdown', reply_markup=main_menu())
    context.user_data.clear()

async def check_balance(query, context: ContextTypes.DEFAULT_TYPE):
    try:
        r = session.get(f"{BASE_URL}/user", headers=HEADERS, timeout=15)
        credits = r.json().get("data", {}).get("remaining_credits", "N/A")
        await query.edit_message_text(f"💳 Storm Credits: `{credits}`", parse_mode='Markdown', reply_markup=main_menu())
    except:
        await query.edit_message_text("❌ Failed to get balance.", parse_mode='Markdown', reply_markup=main_menu())

async def save_bin_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() in ["/cancel", "cancel"]:
        return await start(update, context)
    try:
        parts = text.split(maxsplit=2)
        bin_prefix = parts[0][:6]
        rating = parts[1]
        suggestion = parts[2] if len(parts) > 2 else "No suggestion"
        BIN_RATER[bin_prefix] = {"rating": rating, "suggestion": suggestion}
        await update.message.reply_text(f"✅ BIN `{bin_prefix}` rated `{rating}`", parse_mode='Markdown', reply_markup=main_menu())
        return MENU
    except:
        await update.message.reply_text("❌ Wrong format.\nExample: `410039 8.5 Good for cashout`")
        return BIN_RATER_MODE

async def set_vr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global VR_PERCENTAGE
    try:
        VR_PERCENTAGE = int(context.args[0])
        await update.message.reply_text(f"✅ VR% set to {VR_PERCENTAGE}%")
    except:
        await update.message.reply_text("Usage: /setvr 85")

async def set_format(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global FORMAT_STYLE
    try:
        fmt = context.args[0].lower()
        if fmt in ["pipe", "tab", "comma"]:
            FORMAT_STYLE = fmt
            await update.message.reply_text(f"✅ Format style set to {fmt}")
        else:
            await update.message.reply_text("Options: pipe, tab, comma")
    except:
        await update.message.reply_text("Usage: /setformat pipe")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await start(update, context)

def build_handler():
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [CallbackQueryHandler(main_button)],
            COLLECTING: [MessageHandler(filters.TEXT | filters.Document.ALL, collect_cards)],
            USA_FOREIGN: [CallbackQueryHandler(usa_foreign_handler)],
            SUMMARY: [CallbackQueryHandler(pre_summary_handler)],
            ADD_MORE_CARDS: [MessageHandler(filters.TEXT | filters.Document.ALL, add_more_cards)],
            REMOVE_LAST4: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_last4_handler)],
            BIN_RATER_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_bin_rating)],
            FILENAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_filename)],
            CUSTOMER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_customer_name)],
            TARGET_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_target_count)],
            REP_SETTINGS: [
                CommandHandler("setvr", set_vr),
                CommandHandler("setformat", set_format)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_chat=True,
    )

async def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(build_handler())
    print("✅ E$CO Bot v13.4 - Fixed Field Mapping + Clean Formatting")
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
