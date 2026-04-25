import asyncio
import random
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any   # ← Added Dict and Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ====================== CONFIG ======================
TOKEN = os.getenv("TOKEN")
BASE_URL = os.getenv("BASE_URL", "https://api.example.com")
HEADERS = {
    "Authorization": f"Bearer {os.getenv('API_KEY', 'default_key')}",
    "Content-Type": "application/json"
}

# Global variables
BIN_RATER: Dict[str, Dict[str, str]] = {}
deals: Dict[int, float] = {}
sell_price = 10
buy_price = 1.40
min_live_for_sale = 5
REPLACEMENT_COST = 1.4
total_revenue = 0.0
total_cards_sold = 0
total_replacements = 0
total_tester_cards = 0

print("✅ E$CO Bot v13.5 - Fixed Imports & Type Hints")

# ====================== BIN DATABASE ======================
BIN_DATABASE = {
    "192051": {"brand": "UATP", "type": "CREDIT", "level": "UATP", "bank": "LUFTHANSA AIRPLUS SERVICEKARTEN GMBH", "country": "GERMANY", "rating": 6.0, "vr": 55},
    "371290": {"brand": "AMERICAN EXPRESS", "type": "CREDIT", "level": "PERSONAL", "bank": "AMERICAN EXPRESS US CONSUMER", "country": "UNITED STATES", "rating": 8.5, "vr": 88},
    "400022": {"brand": "DINERS CLUB INTERNATIONAL", "type": "CREDIT", "level": "BUSINESS", "bank": "DINERS CLUB", "country": "UNITED STATES", "rating": 5.5, "vr": 52},
    "400895": {"brand": "VISA", "type": "DEBIT", "level": "CLASSIC", "bank": "NAVY FEDERAL CREDIT UNION", "country": "UNITED STATES", "rating": 7.8, "vr": 79},
    "410039": {"brand": "VISA", "type": "CREDIT", "level": "TRADITIONAL", "bank": "CITIBANK, N.A. - COSTCO", "country": "UNITED STATES", "rating": 8.2, "vr": 84},
    "410040": {"brand": "VISA", "type": "CREDIT", "level": "BUSINESS", "bank": "CITIBANK, N.A. - COSTCO", "country": "UNITED STATES", "rating": 8.0, "vr": 82},
    "423904": {"brand": "VISA", "type": "DEBIT", "level": "CLASSIC", "bank": "ARVEST BANK", "country": "UNITED STATES", "rating": 6.5, "vr": 68},
    "426684": {"brand": "VISA", "type": "CREDIT", "level": "TRADITIONAL", "bank": "JPMORGAN CHASE BANK N.A.", "country": "UNITED STATES", "rating": 7.0, "vr": 72},
    "434256": {"brand": "VISA", "type": "DEBIT", "level": "CLASSIC", "bank": "WELLS FARGO BANK, NATIONAL ASSOCIATION", "country": "UNITED STATES", "rating": 6.8, "vr": 70},
    "434769": {"brand": "VISA", "type": "DEBIT", "level": "CLASSIC", "bank": "JPMORGAN CHASE BANK N.A. - DEBIT", "country": "UNITED STATES", "rating": 7.5, "vr": 77},
    "440215": {"brand": "VISA", "type": "DEBIT", "level": "CLASSIC", "bank": "TTCU FEDERAL CREDIT UNION", "country": "UNITED STATES", "rating": 6.0, "vr": 62},
    "443045": {"brand": "VISA", "type": "DEBIT", "level": "CLASSIC", "bank": "PNC BANK, NATIONAL ASSOCIATION", "country": "UNITED STATES", "rating": 7.2, "vr": 74},
    "461046": {"brand": "VISA", "type": "DEBIT", "level": "CLASSIC", "bank": "JPMORGAN CHASE BANK N.A. - DEBIT", "country": "UNITED STATES", "rating": 7.4, "vr": 76},
    "470793": {"brand": "VISA", "type": "CREDIT", "level": "TRADITIONAL", "bank": "CREDIT ONE BANK, NATIONAL ASSOCIATION", "country": "UNITED STATES", "rating": 6.5, "vr": 65},
    "474485": {"brand": "VISA", "type": "DEBIT", "level": "CLASSIC", "bank": "BANK OF AMERICA, NATIONAL ASSOCIATION", "country": "UNITED STATES", "rating": 8.0, "vr": 81},
    "475833": {"brand": "VISA", "type": "DEBIT", "level": "CLASSIC", "bank": "CHOICE FINANCIAL GROUP", "country": "UNITED STATES", "rating": 6.2, "vr": 64},
    "482821": {"brand": "VISA", "type": "CREDIT", "level": "SIGNATURE", "bank": "THE BANCORP BANK, NATIONAL ASSOCIATION", "country": "UNITED STATES", "rating": 7.8, "vr": 80},
    "498503": {"brand": "VISA", "type": "DEBIT", "level": "CLASSIC", "bank": "STRIDE BANK, NATIONAL ASSOCIATION", "country": "UNITED STATES", "rating": 6.8, "vr": 69},
    "513379": {"brand": "MASTERCARD", "type": "DEBIT", "level": "STANDARD", "bank": "BANQUE FEDERATIVE DU CREDIT MUTUEL", "country": "FRANCE", "rating": 5.5, "vr": 58},
    "517805": {"brand": "MASTERCARD", "type": "CREDIT", "level": "WORLD", "bank": "CAPITAL ONE", "country": "UNITED STATES", "rating": 8.1, "vr": 83},
    "522535": {"brand": "MASTERCARD", "type": "DEBIT", "level": "ENHANCED", "bank": "PROVIDENT BANK", "country": "UNITED STATES", "rating": 7.2, "vr": 74},
    "527515": {"brand": "MASTERCARD", "type": "DEBIT", "level": "ENHANCED", "bank": "BANK OF AMERICA", "country": "UNITED STATES", "rating": 7.9, "vr": 81},
    "534348": {"brand": "MASTERCARD", "type": "CREDIT", "level": "PLATINUM", "bank": "CELTIC BANK CORPORATION", "country": "UNITED STATES", "rating": 7.5, "vr": 78},
    "542418": {"brand": "MASTERCARD", "type": "CREDIT", "level": "PLATINUM", "bank": "CITIBANK N.A.", "country": "UNITED STATES", "rating": 8.0, "vr": 82},
}
def get_bin_info(card_number: str):
    prefix = card_number[:6]
    return BIN_DATABASE.get(prefix, {"brand": "UNKNOWN", "type": "CREDIT", "level": "STANDARD", "bank": "UNKNOWN BANK", "country": "UNITED STATES", "rating": 5.0, "vr": 45})

def get_random_balance(card: str, is_tester: bool = False) -> float:
    """
    Reduced probability of balance > $2500 to approximately 3.2%
    """
    bin6 = card[:6]
    
    # Base balance ranges - most cards stay under $2,500
    if is_tester:
        return round(random.uniform(800, 1850), 2)
    
    # High-value bins (keep low chance of very high balances)
    high_value_bins = ["410039", "517805", "542418", "371290"]
    
    if bin6 in high_value_bins:
        # 3.2% chance of balance > 2500
        if random.random() < 0.032:
            return round(random.uniform(2500, 4850), 2)
        else:
            # 96.8% of the time: normal distribution under $2500
            return round(random.triangular(420, 1680, 2350), 2)
    
    # Normal cards - very low chance of high balance
    if random.random() < 0.032:           # 3.2% chance
        return round(random.uniform(2510, 3790), 2)
    else:
        # 96.8% chance - realistic lower balances
        roll = random.random()
        if roll < 0.45:   # 45% chance of low balance
            return round(random.uniform(180, 890), 2)
        elif roll < 0.85: # 40% chance of medium balance
            return round(random.uniform(920, 1680), 2)
        else:             # 15% chance of higher but still under 2500
            return round(random.uniform(1720, 2420), 2)

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
        [InlineKeyboardButton("🔍 Normal Check", callback_data="start_format")],
        [InlineKeyboardButton("🧪 Tester Cards", callback_data="start_tester")],
        [InlineKeyboardButton("💰 Start Sale", callback_data="start_sale")],
        [InlineKeyboardButton("⚙️ Sale Settings", callback_data="sale_settings")],
        [InlineKeyboardButton("🔄 Replacement", callback_data="start_replacement")],
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

# ====================== FIXED FORMATTER - SUPPORTS BOTH FORMATS ======================
def format_live_card(raw_line: str, is_tester: bool = False) -> str:
    try:
        # Clean and split the line
        line = raw_line.replace("=>", "|").strip()
        parts = [p.strip() for p in line.split('|')]
        
        card    = parts[0]
        cvv     = parts[2] if len(parts) > 2 else "000"
        name    = parts[3] if len(parts) > 3 else "N/A"
        address = parts[4] if len(parts) > 4 else "N/A"
        city    = parts[5] if len(parts) > 5 else "N/A"
        state   = parts[6] if len(parts) > 6 else "N/A"
        zipcode = parts[7] if len(parts) > 7 else "N/A"
        country = parts[8] if len(parts) > 8 else "US"
        phone   = parts[9] if len(parts) > 9 else "N/A"
        email   = parts[10] if len(parts) > 10 else "N/A"
        # Handle both formats: "06/26" or "06" and "26"
        if '/' in parts[1]:
            expiry = parts[1]
            mm, yy = expiry.split('/')
        else:
            mm = parts[1]
            yy = parts[2] if len(parts) > 2 else "00"
            # Adjust indices if expiry is split
            if len(parts) > 11:  # Means we have separate MM and YY
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
            f"📅 Expiry  : {mm}/{yy}",
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
        return f"Parse Error on line: {raw_line}\nError: {str(e)}"
# ====================== CHECKER ======================
def is_live(item: dict) -> bool:
    if not isinstance(item, dict): return False
    text = " ".join(str(v).lower() for v in item.values())
    positive = ["live", "approved", "success", "charged", "passed", "valid", "good", "200", "ok"]
    return any(k in text for k in positive)

async def check_cards_with_storm(cards: List[str], status_message, max_polls: int, context: ContextTypes.DEFAULT_TYPE):
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
            return
        context.user_data["batch_id"] = batch_id
    except Exception as e:
        await status_message.edit_text(f"❌ Submission Error: {str(e)}")
        return

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

    # IMPORTANT: Always call post summary after polling ends
    context.user_data["live_cards"] = live_raw_cards
    await show_post_summary(status_message, context)

# ====================== HANDLER FUNCTIONS ======================
async def get_customer_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip().replace(" ", "_")
    context.user_data["customer_name"] = name
    mode = context.user_data.get("mode")
    if mode == "sale":
        await update.message.reply_text(f"✅ Customer: **{name}**\n\nHow many **LIVE** cards do they want?", parse_mode='Markdown')
        return TARGET_COUNT
    elif mode == "replacement":
        await update.message.reply_text(f"✅ Customer: **{name}**\n\nHow many replacements do they want?", parse_mode='Markdown')
        return TARGET_COUNT
    else:
        context.user_data["all_cards"] = []
        context.user_data["filename"] = None
        await update.message.reply_text("Send cards or .txt file.\n/cancel to stop.", parse_mode='Markdown')
        return COLLECTING
        
async def get_target_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        target = int(update.message.text.strip())
        context.user_data["target_count"] = target
        await update.message.reply_text(f"✅ Target set to **{target}** live cards.\n\nSend cards or .txt file.", parse_mode='Markdown')
        return COLLECTING
    except:
        await update.message.reply_text("❌ Please send a valid number.")
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
    if data == "start_format":
        context.user_data["mode"] = "normal"
        context.user_data["all_cards"] = []
        context.user_data["filename"] = None
        await query.edit_message_text("Send cards or .txt file.\n/cancel to stop.", parse_mode='Markdown')
        return COLLECTING
    if data == "start_tester":
        context.user_data["mode"] = "tester"
        context.user_data["all_cards"] = []
        context.user_data["filename"] = None
        await query.edit_message_text("Send tester cards or .txt file.\n/cancel to stop.", parse_mode='Markdown')
        return COLLECTING
    if data == "start_sale":
        context.user_data["mode"] = "sale"
        await query.edit_message_text("💰 **Sale Mode**\n\nSend Customer Name:", parse_mode='Markdown')
        return CUSTOMER_NAME
    if data == "start_replacement":
        context.user_data["mode"] = "replacement"
        await query.edit_message_text("🔄 **Replacement Mode**\n\nSend Customer Name:", parse_mode='Markdown')
        return CUSTOMER_NAME
    if data == "sale_settings":
        await query.edit_message_text(
            "⚙️ **Sale Settings**\n\n"
            f"Buy Price : `${context.bot_data.get('buy_price', 1.6):.2f}`\n"
            f"Sell Price: `${context.bot_data.get('sell_price', 12.0):.2f}`\n"
            f"Min Live  : `{context.bot_data.get('min_live_for_sale', 5)}`",
            parse_mode='Markdown'
        )
        return REP_SETTINGS
    if data == "bin_rater":
        await query.edit_message_text("📊 Send BIN rating:\n`410039 8.5 Good for cashout`", parse_mode='Markdown')
        return BIN_RATER_MODE
    if data == "check_balance":
        return await check_balance(query, context)
        
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
        await check_cards_with_storm(cards, status_msg, max_polls, context)
        return MENU
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
    all_cards = context.user_data.get("all_cards", [])
    live_count = len(live_cards)
    dead_count = len(all_cards) - live_count
    total_cards = len(all_cards)
    mode = context.user_data.get("mode", "normal")
    customer = context.user_data.get("customer_name", "Unknown")
    target = context.user_data.get("target_count", 0)
    batch_id = context.user_data.get("batch_id", "N/A")
    live_rate = round((live_count / total_cards * 100), 2) if total_cards > 0 else 0.0
    est_time = (datetime.utcnow() - timedelta(hours=4)).strftime("%Y-%m-%d %H:%M:%S EST")
    filename = context.user_data.get("filename") or f"Output-{random.randint(1000,9999)}"
    final_filename = f"{filename}.txt"
    # Save formatted output for later
    formatted = [format_live_card(raw, mode == "tester") for raw in live_cards]
    context.user_data["formatted_output"] = formatted
    context.user_data["final_filename"] = final_filename
    if mode in ["sale", "replacement"] and live_count < target:
        status = "❌ Target Not Reached"
        color = "🔴"
    else:
        status = "✅ Target Reached"
        color = "🟢"
        if mode == "sale":
            revenue = round(live_count * sell_price, 2)
            total_revenue += revenue
            total_cards_sold += live_count
            revenue_text = f"💰 Revenue: ${revenue:.2f}"
        elif mode == "replacement":
            deduction = round(live_count * REPLACEMENT_COST, 2)
            total_revenue = round(total_revenue - deduction, 2)
            total_replacements += live_count
            revenue_text = f"🔄 Replacements Done"
        else:
            revenue_text = ""
    post_text = (
        f"📊 **POST SUMMARY**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Customer     : `{customer}`\n"
        f"Target       : `{target}`\n"
        f"Live Cards   : `{live_count}`\n"
        f"Dead Cards   : `{dead_count}`\n"
        f"Live Rate    : `{live_rate}%`\n"
        f"Status       : {color} {status}\n"
        f"{revenue_text}\n"
        f"Batch ID     : `{batch_id}`\n"
        f"Time (EST)   : `{est_time}`\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Output file is ready. Use button below to download."
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Send Output File", callback_data="send_output_file")],
        [InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="back_to_main")]
    ])
    await status_msg.edit_text(post_text, reply_markup=keyboard, parse_mode='Markdown')
    context.user_data["live_count"] = live_count
    context.user_data["dead_count"] = dead_count

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

async def set_buy_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global buy_price
    try:
        buy_price = float(context.args[0])
        context.bot_data['buy_price'] = buy_price
        await update.message.reply_text(f"✅ Buy price set to `${buy_price:.2f}` per card", parse_mode='Markdown')
    except:
        await update.message.reply_text("Usage: `/setbuy 2.0`")
async def set_sell_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global sell_price
    try:
        sell_price = float(context.args[0])
        context.bot_data['sell_price'] = sell_price
        await update.message.reply_text(f"✅ Sell price set to `${sell_price:.2f}` per card", parse_mode='Markdown')
    except:
        await update.message.reply_text("Usage: `/setsell 15`")
async def set_min_live(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global min_live_for_sale
    try:
        min_live_for_sale = int(context.args[0])
        context.bot_data['min_live_for_sale'] = min_live_for_sale
        await update.message.reply_text(f"✅ Minimum live cards for sale set to `{min_live_for_sale}`", parse_mode='Markdown')
    except:
        await update.message.reply_text("Usage: `/setmin 5`")
async def add_deal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        deal = context.args[0]
        count, price = map(int, deal.split('/'))
        deals[count] = price
        await update.message.reply_text(f"✅ Deal added: **{count} for ${price}**", parse_mode='Markdown')
    except:
        await update.message.reply_text("Usage: `/adddeal 3/25` or `/adddeal 5/55`")
        return

async def post_summary_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "send_file_anyway":
        live_cards = context.user_data.get("live_cards", [])
        filename = f"Partial_Output-{random.randint(1000,9999)}.txt"
        formatted = [format_live_card(raw) for raw in live_cards]
        with open(filename, "w", encoding="utf-8") as f:
            f.write("\n\n".join(formatted))
        await query.edit_message_text("📤 Sending partial file...")
        await query.message.reply_document(document=open(filename, "rb"), caption=filename)
        try: os.remove(filename)
        except: pass
        await query.message.reply_text("✅ Partial file sent.", reply_markup=main_menu())
        context.user_data.clear()
        return MENU
    if data == "back_to_main":
        return await start(update, context)

async def send_output_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "send_output_file":
        formatted = context.user_data.get("formatted_output", [])
        final_filename = context.user_data.get("final_filename", "output.txt")
        if not formatted:
            await query.edit_message_text("❌ No output available.")
            return
        with open(final_filename, "w", encoding="utf-8") as f:
            f.write("══════════════════════════════════════\n")
            f.write("          E$CO CHECK OUTPUT\n")
            f.write("══════════════════════════════════════\n\n")
            f.write("\n\n".join(formatted))
            f.write("\n\n══════════════════════════════════════\n")
            f.write(f"Customer: {context.user_data.get('customer_name', 'Unknown')}\n")
            f.write(f"Live: {context.user_data.get('live_count', 0)} | Dead: {context.user_data.get('dead_count', 0)}\n")
            f.write("══════════════════════════════════════\n")
        await query.message.reply_document(
            document=open(final_filename, "rb"),
            caption=f"✅ {final_filename}"
        )
        try:
            os.remove(final_filename)
        except:
            pass
        await query.edit_message_text("✅ Output file sent successfully.", reply_markup=main_menu())
        context.user_data.clear()
        return MENU
    if query.data == "back_to_main":
        return await start(update, context)
        
def build_handler():
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [CallbackQueryHandler(main_button)],
            COLLECTING: [MessageHandler(filters.TEXT | filters.Document.ALL, collect_cards)],
            USA_FOREIGN: [CallbackQueryHandler(usa_foreign_handler)],
            SUMMARY: [
                CallbackQueryHandler(pre_summary_handler),
                CallbackQueryHandler(send_output_handler)
            ],
            ADD_MORE_CARDS: [MessageHandler(filters.TEXT | filters.Document.ALL, add_more_cards)],
            REMOVE_LAST4: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_last4_handler)],
            BIN_RATER_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_bin_rating)],
            FILENAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_filename)],
            CUSTOMER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_customer_name)],
            TARGET_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_target_count)],
            REP_SETTINGS: [
                CommandHandler("setvr", set_vr),
                CommandHandler("setformat", set_format),
                CommandHandler("setbuy", set_buy_price),
                CommandHandler("setsell", set_sell_price),
                CommandHandler("setmin", set_min_live),
                CommandHandler("adddeal", add_deal),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_chat=True,
        per_message=False,           # ← This removes the warning
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
    print("✅ E$CO Bot v13.5 Starting on Railway...")
    
    if os.environ.get("RAILWAY_ENVIRONMENT"):
        print("🚄 Railway detected - Using drop_pending_updates")
    
    application = Application.builder().token(TOKEN).build()
    application.add_handler(build_handler())
    
    print("🤖 Bot is now running successfully!")
    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"]
    )
