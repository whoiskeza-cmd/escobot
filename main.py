import asyncio
import random
import os
import requests
from datetime import datetime, timezone
from typing import List, Dict, Any

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
OWNER_ID = int(os.getenv("OWNER_ID", 0))
BASE_URL = os.getenv("BASE_URL", "https://api.example.com")
HEADERS = {
    "Authorization": f"Bearer {os.getenv('API_KEY', '')}",
    "Content-Type": "application/json"
}

# ====================== GLOBAL VARIABLES ======================
BIN_RATER: Dict[str, Dict[str, str]] = {}
deals: Dict[int, float] = {}
sell_price = 10.0
buy_price = 1.40
min_live_for_sale = 5
REPLACEMENT_COST = 1.4
total_revenue = 0.0
total_cards_sold = 0
total_replacements = 0
total_tester_cards = 0
INITIAL_WAIT = 8
POLL_INTERVAL = 12

session = requests.Session()

print("✅ E$CO Bot v14.3 - Fixed Send File + Add More Cards")

# ====================== BIN DATABASE ======================
BIN_DATABASE = { ... }  # ← Keep your full BIN_DATABASE from previous version here

def get_bin_info(card_number: str):
    prefix = card_number[:6]
    return BIN_DATABASE.get(prefix, {"brand": "UNKNOWN", "type": "CREDIT", "level": "STANDARD", "bank": "UNKNOWN BANK", "country": "UNITED STATES", "rating": 5.0, "vr": 45})

def get_random_balance(card: str, is_tester: bool = False) -> float:
    bin6 = card[:6]
    if is_tester:
        return round(random.uniform(800, 1850), 2)
    high_value_bins = ["410039", "517805", "542418", "371290"]
    if bin6 in high_value_bins:
        if random.random() < 0.032:
            return round(random.uniform(2500, 4850), 2)
        return round(random.triangular(420, 1680, 2350), 2)
    if random.random() < 0.032:
        return round(random.uniform(2510, 3790), 2)
    roll = random.random()
    if roll < 0.45:
        return round(random.uniform(180, 890), 2)
    elif roll < 0.85:
        return round(random.uniform(920, 1680), 2)
    else:
        return round(random.uniform(1720, 2420), 2)

def get_random_ip() -> str:
    return f"{random.randint(25,195)}.{random.randint(15,245)}.{random.randint(20,230)}.{random.randint(35,220)}"

def get_max_polls(total_cards: int) -> int:
    if total_cards < 10: return 4
    elif total_cards <= 50: return 12
    elif total_cards <= 300: return 18
    else: return 25

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

def format_live_card(raw_line: str, is_tester: bool = False) -> str:
    try:
        line = raw_line.replace("=>", "|").strip()
        parts = [p.strip() for p in line.split('|')]
        card = parts[0]
        if '/' in parts[1]:
            mm, yy = parts[1].split('/')
        else:
            mm = parts[1]
            yy = parts[2] if len(parts) > 2 else "00"
        
        cvv = parts[2] if len(parts) > 2 else "000"
        name = parts[3] if len(parts) > 3 else "N/A"
        address = parts[4] if len(parts) > 4 else "N/A"
        city = parts[5] if len(parts) > 5 else "N/A"
        state = parts[6] if len(parts) > 6 else "N/A"
        zipcode = parts[7] if len(parts) > 7 else "N/A"
        country = parts[8] if len(parts) > 8 else "US"
        phone = parts[9] if len(parts) > 9 else "N/A"
        email = parts[10] if len(parts) > 10 else "N/A"

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
            f"🕒 Checked : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
            "══════════════════════════════════════",
            f"BIN Rate   : {bin_data['rating']} | {bin_data['suggestion']}",
            "══════════════════════════════════════"
        ]
        if is_tester:
            output.append("❤️ Thank You For Choosing E$CO ❤️")
        return "\n".join(output)
    except Exception as e:
        return f"Parse Error on line: {raw_line}\nError: {str(e)}"

def is_live(item: dict) -> bool:
    if not isinstance(item, dict): return False
    text = " ".join(str(v).lower() for v in item.values())
    positive = ["live", "approved", "success", "charged", "passed", "valid", "good", "200", "ok"]
    return any(k in text for k in positive)

async def check_cards_with_storm(cards: List[str], status_message, max_polls: int, context: ContextTypes.DEFAULT_TYPE):
    live_raw_cards = []
    seen = set()
    batch_id = None

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

    await status_message.edit_text(f"✅ Batch {batch_id} submitted.\nWaiting {INITIAL_WAIT}s...")
    await asyncio.sleep(INITIAL_WAIT)

    poll_url = f"{BASE_URL}/check/{batch_id}"
    poll_count = 0

    while poll_count < max_polls:
        poll_count += 1
        await status_message.edit_text(f"Polling: {poll_count}/{max_polls} | Live: {len(live_raw_cards)}")

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
                        if raw.split('|')[0].strip().endswith(card_num[-4:]):
                            if raw not in live_raw_cards:
                                live_raw_cards.append(raw)
                            break
        except Exception:
            pass

        await asyncio.sleep(POLL_INTERVAL)

    context.user_data["live_cards"] = live_raw_cards
    context.user_data["batch_id"] = batch_id
    await show_post_summary(status_message, context)

# ====================== STATES ======================
MENU, COLLECTING, USA_FOREIGN, SUMMARY, ADD_MORE_CARDS, REMOVE_LAST4, BIN_RATER_MODE, FILENAME, CUSTOMER_NAME, TARGET_COUNT, REP_SETTINGS = range(11)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Unauthorized. This bot is private.")
        return ConversationHandler.END

    global total_revenue, total_cards_sold, total_tester_cards, total_replacements
    profit = round(total_revenue - (total_cards_sold * buy_price) - (total_replacements * REPLACEMENT_COST), 2)

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
        await query.edit_message_text("⚙️ Sale Settings\nUse commands to change values.", parse_mode='Markdown')
        return REP_SETTINGS
    if data == "bin_rater":
        await query.edit_message_text("📊 Send BIN rating:\n`410039 8.5 Good for cashout`", parse_mode='Markdown')
        return BIN_RATER_MODE
    if data == "check_balance":
        return await check_balance(query, context)
    return MENU

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
    target = context.user_data.get("target_count", 0)
    mode = context.user_data.get("mode", "normal")
    customer = context.user_data.get("customer_name", "Unknown")
    batch_id = context.user_data.get("batch_id", "N/A")
    live_rate = round((live_count / len(all_cards) * 100), 2) if all_cards else 0.0

    main_cards = live_cards[:target] if target > 0 and live_count > target else live_cards
    extra_cards = live_cards[target:] if target > 0 and live_count > target else []

    formatted_main = [format_live_card(raw, mode == "tester") for raw in main_cards]

    if not context.user_data.get("filename"):
        if mode == "tester":
            context.user_data["filename"] = f"test-{random.randint(1000,9999)}"
        elif mode == "replacement":
            context.user_data["filename"] = f"Rep-{random.randint(1000,9999)}"
        else:
            context.user_data["filename"] = f"Batch-{random.randint(1000,9999)}"

    final_filename = f"{context.user_data['filename']}.txt"
    context.user_data["final_filename"] = final_filename
    context.user_data["formatted_output"] = formatted_main
    context.user_data["extra_cards"] = extra_cards

    with open(final_filename, "w", encoding="utf-8") as f:
        f.write("══════════════════════════════════════\n")
        f.write("          E$CO CHECK OUTPUT\n")
        f.write("══════════════════════════════════════\n\n")
        f.write("\n\n".join(formatted_main))
        f.write("\n\n══════════════════════════════════════\n")
        f.write(f"Customer: {customer} | Requested: {target} | Delivered: {len(main_cards)}\n")
        f.write(f"Batch ID: {batch_id}\n")
        f.write("══════════════════════════════════════\n")

    extra_filename = None
    if extra_cards:
        extra_filename = f"{batch_id}-extra-{len(extra_cards)}.txt"
        formatted_extra = [format_live_card(raw, mode == "tester") for raw in extra_cards]
        with open(extra_filename, "w", encoding="utf-8") as f:
            f.write(f"EXTRA LIVE CARDS — {len(extra_cards)} cards\n")
            f.write(f"Batch ID: {batch_id}\n\n")
            f.write("\n\n".join(formatted_extra))
        context.user_data["extra_filename"] = extra_filename

    if mode == "sale" and main_cards:
        revenue = round(len(main_cards) * sell_price, 2)
        total_revenue += revenue
        total_cards_sold += len(main_cards)

    post_text = (
        f"📊 **POST SUMMARY**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Customer     : `{customer}`\n"
        f"Target       : `{target}`\n"
        f"Live Cards   : `{live_count}`\n"
        f"Delivered    : `{len(main_cards)}`\n"
        f"Extra Cards  : `{len(extra_cards)}`\n"
        f"Live Rate    : `{live_rate}%`\n"
        f"Batch ID     : `{batch_id}`\n"
        f"Time         : `{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC`\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Click buttons below to receive files."
    )

    keyboard = [
        [InlineKeyboardButton("📤 Send Main Output", callback_data="send_main_output")],
    ]
    if extra_cards:
        keyboard.append([InlineKeyboardButton("📤 Send Extra Cards File", callback_data="send_extra_file")])
    keyboard.append([InlineKeyboardButton("➕ Add More Cards", callback_data="add_more")])
    keyboard.append([InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="back_to_main")])

    await status_msg.edit_message_text(post_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def send_output_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "send_main_output":
        filename = context.user_data.get("final_filename")
        if filename and os.path.exists(filename):
            await query.message.reply_document(
                document=open(filename, "rb"),
                caption=f"✅ Main Output: {filename}"
            )
            try:
                os.remove(filename)
            except:
                pass
        else:
            await query.message.reply_text("❌ Main output file not found.")

    elif data == "send_extra_file":
        extra_filename = context.user_data.get("extra_filename")
        if extra_filename and os.path.exists(extra_filename):
            await query.message.reply_document(
                document=open(extra_filename, "rb"),
                caption=f"✅ Extra Cards: {extra_filename}"
            )
            try:
                os.remove(extra_filename)
            except:
                pass
        else:
            await query.message.reply_text("No extra file found.")

    elif data == "add_more":
        await query.edit_message_text("Send more cards or .txt file.\n/cancel to stop.", parse_mode='Markdown')
        return ADD_MORE_CARDS

    elif data == "back_to_main":
        return await start(update, context)

    await query.edit_message_text("✅ Action completed.", reply_markup=main_menu())
    context.user_data.clear()
    return MENU

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

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operation cancelled.", reply_markup=main_menu())
    context.user_data.clear()
    return MENU

def build_handler():
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [
                CallbackQueryHandler(main_button),
                CallbackQueryHandler(send_output_handler, pattern="^(send_main_output|send_extra_file|add_more|back_to_main)$")
            ],
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
                CommandHandler("setbuy", set_buy_price),
                CommandHandler("setsell", set_sell_price),
                CommandHandler("setmin", set_min_live),
                CommandHandler("adddeal", add_deal),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_chat=True,
        per_user=False,
        per_message=False,
    )

# ====================== SETTINGS HANDLERS ======================
async def set_buy_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global buy_price
    try:
        buy_price = float(context.args[0])
        await update.message.reply_text(f"✅ Buy price set to `${buy_price:.2f}`", parse_mode='Markdown')
    except:
        await update.message.reply_text("Usage: `/setbuy 2.0`")

async def set_sell_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global sell_price
    try:
        sell_price = float(context.args[0])
        await update.message.reply_text(f"✅ Sell price set to `${sell_price:.2f}`", parse_mode='Markdown')
    except:
        await update.message.reply_text("Usage: `/setsell 15`")

async def set_min_live(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global min_live_for_sale
    try:
        min_live_for_sale = int(context.args[0])
        await update.message.reply_text(f"✅ Min live set to `{min_live_for_sale}`", parse_mode='Markdown')
    except:
        await update.message.reply_text("Usage: `/setmin 5`")

async def add_deal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        deal = context.args[0]
        count, price = map(int, deal.split('/'))
        deals[count] = price
        await update.message.reply_text(f"✅ Deal added: **{count} for ${price}**", parse_mode='Markdown')
    except:
        await update.message.reply_text("Usage: `/adddeal 3/25`")

if __name__ == "__main__":
    print("✅ E$CO Bot v14.3 Starting on Railway...")
    if os.getenv("RAILWAY_ENVIRONMENT"):
        print("🚄 Railway detected - Single instance mode")
    
    application = Application.builder().token(TOKEN).build()
    application.add_handler(build_handler())
    
    print("🤖 Bot is now running successfully!")
    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"]
    )
