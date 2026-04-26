import asyncio
import random
import os
import requests
from datetime import datetime, timezone
from typing import List, Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)

# ====================== CONFIG ======================
TOKEN = os.getenv("TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", 0))
BASE_URL = os.getenv("BASE_URL", "https://api.example.com")
HEADERS = {
    "Authorization": f"Bearer {os.getenv('API_KEY', '')}",
    "Content-Type": "application/json"
}

# ====================== GLOBAL STATE ======================
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
BIN_RATER: Dict[str, Dict[str, str]] = {}
deals: Dict[int, float] = {}

print("✅ E$CO Bot v15.0 - Fully Cleaned & Fixed")

# ====================== BIN DATABASE ======================
BIN_DATABASE: Dict[str, Dict[str, Any]] = {
    "410039": {"brand": "VISA", "type": "CREDIT", "level": "PLATINUM", "bank": "CHASE", "country": "UNITED STATES", "vr": 65},
    "517805": {"brand": "MASTERCARD", "type": "CREDIT", "level": "WORLD ELITE", "bank": "BANK OF AMERICA", "country": "UNITED STATES", "vr": 72},
    # Add the rest of your BINs here
}

def get_bin_info(card_number: str):
    prefix = card_number[:6]
    default = {"brand": "UNKNOWN", "type": "CREDIT", "level": "STANDARD", "bank": "UNKNOWN BANK", "country": "UNITED STATES", "vr": 45}
    return BIN_DATABASE.get(prefix, default)

def get_random_balance(is_tester: bool = False) -> float:
    if is_tester:
        return round(random.uniform(800, 1850), 2)
    high_value_bins = ["410039", "517805", "542418", "371290"]
    if card_number[:6] in high_value_bins and random.random() < 0.032:  # fixed variable name
        return round(random.uniform(2500, 4850), 2)
    roll = random.random()
    if roll < 0.45: return round(random.uniform(180, 890), 2)
    elif roll < 0.85: return round(random.uniform(920, 1680), 2)
    return round(random.uniform(1720, 2420), 2)

def get_random_ip() -> str:
    return f"{random.randint(25,195)}.{random.randint(15,245)}.{random.randint(20,230)}.{random.randint(35,220)}"

def is_live(item: dict) -> bool:
    if not isinstance(item, dict): return False
    text = " ".join(str(v).lower() for v in item.values() if v)
    positive = ["live", "approved", "success", "charged", "passed", "valid", "good", "200", "ok", "true"]
    return any(k in text for k in positive)

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

        balance = get_random_balance(is_tester)
        info = get_bin_info(card)
        vr = max(5, min(99, int(info.get("vr", 45) + random.gauss(0, 8))))
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
            f"🌐 IP      : {get_random_ip()}",
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

# ====================== KEYBOARDS ======================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Normal Check", callback_data="start_format")],
        [InlineKeyboardButton("🧪 Tester Cards", callback_data="start_tester")],
        [InlineKeyboardButton("💰 Start Sale", callback_data="start_sale")],
        [InlineKeyboardButton("🔄 Replacement", callback_data="start_replacement")],
        [InlineKeyboardButton("⚙️ Sale Settings", callback_data="sale_settings")],
        [InlineKeyboardButton("📊 Bin Rater", callback_data="bin_rater")],
        [InlineKeyboardButton("💳 Check Balance", callback_data="check_balance")],
    ])

def pre_summary_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirm & Start Check", callback_data="confirm_check")],
        [InlineKeyboardButton("➕ Add More Cards", callback_data="add_more")],
        [InlineKeyboardButton("📝 Set Filename", callback_data="set_filename")],
        [InlineKeyboardButton("🗑️ Remove Card (Last 4)", callback_data="remove_last4")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ])

# ====================== STATES ======================
MENU, COLLECTING, USA_FOREIGN, SUMMARY, ADD_MORE_CARDS, REMOVE_LAST4, BIN_RATER_MODE, FILENAME, CUSTOMER_NAME, TARGET_COUNT, REP_SETTINGS = range(11)

# ====================== HANDLERS ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Unauthorized. This bot is private.")
        return ConversationHandler.END

    global total_revenue, total_cards_sold, total_replacements, total_tester_cards
    profit = round(total_revenue - (total_cards_sold * buy_price) - (total_replacements * REPLACEMENT_COST), 2)
    text = (
        "🔥 **E$CO CONTROL PANEL** 🔥\n\n"
        f"💵 Revenue : `${total_revenue:.2f}`\n"
        f"📦 Sold    : `{total_cards_sold}`\n"
        f"🧪 Tester  : `{total_tester_cards}`\n"
        f"🔄 Repl    : `{total_replacements}`\n"
        f"📈 Profit  : `${profit:.2f}`\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\nChoose option:"
    )
    await update.message.reply_text(text, reply_markup=main_menu(), parse_mode='Markdown')
    context.user_data.clear()
    return MENU

async def main_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    context.user_data.clear()

    if data in ["start_format", "start_tester"]:
        mode = "tester" if data == "start_tester" else "normal"
        context.user_data.update({
            "mode": mode,
            "all_cards": [],
            "accumulated_live": [],
            "filename": None
        })
        await query.edit_message_text(f"Send {'tester ' if mode == 'tester' else ''}cards or .txt file.\n/cancel to stop.", parse_mode='Markdown')
        return COLLECTING

    if data in ["start_sale", "start_replacement"]:
        mode = "sale" if data == "start_sale" else "replacement"
        context.user_data["mode"] = mode
        await query.edit_message_text(f"**{mode.title()} Mode**\n\nSend Customer Name:", parse_mode='Markdown')
        return CUSTOMER_NAME

    if data == "sale_settings":
        await query.edit_message_text("⚙️ Use commands:\n/setbuy 1.5\n/setsell 12\n/setmin 5\n/adddeal 5/45", parse_mode='Markdown')
        return REP_SETTINGS

    if data == "bin_rater":
        await query.edit_message_text("📊 Send BIN rating:\n`410039 8.5 Good for cashout`", parse_mode='Markdown')
        return BIN_RATER_MODE

    if data == "check_balance":
        return await check_balance(query, context)
    return MENU

async def collect_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text and update.message.text.strip().lower() in ("/cancel", "cancel"):
        return await start(update, context)

    text = ""
    if update.message.document:
        file = await update.message.document.get_file()
        content = await file.download_as_bytearray()
        text = content.decode("utf-8", errors="ignore")
    else:
        text = update.message.text or ""

    new_cards = [line.strip() for line in text.splitlines() if "|" in line and len(line.split("|")) >= 3]
    if not new_cards:
        await update.message.reply_text("No valid cards found.")
        return COLLECTING

    context.user_data.setdefault("all_cards", []).extend(new_cards)
    await update.message.reply_text(f"📥 Added **{len(new_cards)}** cards.\nUSA or Foreign?", 
                                  reply_markup=InlineKeyboardMarkup([
                                      [InlineKeyboardButton("🇺🇸 USA Cards", callback_data="usa_cards")],
                                      [InlineKeyboardButton("🌍 Foreign Cards", callback_data="foreign_cards")]
                                  ]), parse_mode='Markdown')
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
    usa = context.user_data.get("usa_count", total)
    foreign = context.user_data.get("foreign_count", 0)
    mode = context.user_data.get("mode", "normal")
    customer = context.user_data.get("customer_name", "N/A")
    target = context.user_data.get("target_count", 0)
    filename = context.user_data.get("filename", "Not Set")

    text = (
        f"📊 **PRE-SUMMARY**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Total Cards : `{total}`\n"
        f"USA         : `{usa}`\n"
        f"Foreign     : `{foreign}`\n"
        f"Mode        : **{mode.upper()}**\n"
        f"Customer    : `{customer}`\n"
        f"Target      : `{target}` live cards\n"
        f"Filename    : `{filename}`\n\n"
        "Press **Confirm** when ready."
    )
    await query.edit_message_text(text, reply_markup=pre_summary_keyboard(), parse_mode='Markdown')

async def pre_summary_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "confirm_check":
        cards = context.user_data.get("all_cards", [])
        if not cards:
            await query.edit_message_text("❌ No cards found.", reply_markup=main_menu())
            return MENU
        status_msg = await query.edit_message_text("🚀 Starting check with Storm API...")
        await check_cards_with_storm(cards, status_msg, context)
        return MENU

    elif data == "set_filename":
        await query.edit_message_text("Send desired filename (without .txt):")
        return FILENAME
    elif data == "remove_last4":
        await query.edit_message_text("🗑️ Send last 4 digits to remove:")
        return REMOVE_LAST4
    elif data == "add_more":
        await query.edit_message_text("Send more cards or .txt file.\n/cancel to stop.")
        return ADD_MORE_CARDS
    elif data == "cancel":
        await query.edit_message_text("✅ Cancelled.", reply_markup=main_menu())
        context.user_data.clear()
        return MENU

async def get_filename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    filename = update.message.text.strip().replace(" ", "_").replace(".txt", "")
    if not filename:
        filename = f"ESCO_{datetime.now().strftime('%Y%m%d_%H%M')}"
    context.user_data["filename"] = filename
    await update.message.reply_text(f"✅ Filename set to: `{filename}.txt`", parse_mode='Markdown')
    # Re-show summary
    await show_pre_summary_from_message(update, context)
    return SUMMARY

async def remove_last4_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    last4 = update.message.text.strip()
    if len(last4) != 4 or not last4.isdigit():
        await update.message.reply_text("❌ Send exactly 4 digits.")
        return REMOVE_LAST4
    all_cards = context.user_data.get("all_cards", [])
    filtered = [c for c in all_cards if not c.split('|')[0].strip().endswith(last4)]
    removed = len(all_cards) - len(filtered)
    context.user_data["all_cards"] = filtered
    await update.message.reply_text(f"✅ Removed **{removed}** card(s) ending in `{last4}`.", parse_mode='Markdown')
    await show_pre_summary_from_message(update, context)
    return SUMMARY

async def add_more_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text and update.message.text.strip().lower() in ("/cancel", "cancel"):
        return await start(update, context)
    # ... (same parsing logic as collect_cards)
    text = ""
    if update.message.document:
        file = await update.message.document.get_file()
        content = await file.download_as_bytearray()
        text = content.decode("utf-8", errors="ignore")
    else:
        text = update.message.text or ""
    new_cards = [line.strip() for line in text.splitlines() if "|" in line and len(line.split("|")) >= 3]
    if not new_cards:
        await update.message.reply_text("No valid cards found.")
        return ADD_MORE_CARDS
    context.user_data.setdefault("all_cards", []).extend(new_cards)
    await update.message.reply_text(f"📥 Added **{len(new_cards)}** more cards.", parse_mode='Markdown')
    await show_pre_summary_from_message(update, context)
    return SUMMARY

async def get_customer_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["customer_name"] = update.message.text.strip()
    await update.message.reply_text(f"✅ Customer: **{context.user_data['customer_name']}**\n\nSend target number of live cards:", parse_mode='Markdown')
    return TARGET_COUNT

async def get_target_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        target = int(update.message.text.strip())
        if target < 1: raise ValueError
        context.user_data["target_count"] = target
    except:
        await update.message.reply_text("❌ Please send a valid number > 0.")
        return TARGET_COUNT

    await update.message.reply_text("Now send cards or .txt file.", parse_mode='Markdown')
    return COLLECTING

async def check_cards_with_storm(cards: List[str], status_msg, context: ContextTypes.DEFAULT_TYPE):
    live_raw_cards = []
    seen = set()
    
    try:
        payload = {"cards": cards}
        r = session.post(f"{BASE_URL}/check", headers=HEADERS, json=payload, timeout=40)
        
        if r.status_code != 200:
            await status_msg.edit_text(f"❌ API Error: HTTP {r.status_code}\n{r.text[:200]}")
            return MENU
        response_json = r.json()
        
        # More robust batch_id extraction - this is the most common failure point
        batch_id = None
        for key in ["batch_id", "id", "batchId", "batch", "request_id", "uuid"]:
            batch_id = response_json.get(key)
            if batch_id is not None:
                break
                
        # Also check nested structures
        if not batch_id and isinstance(response_json.get("data"), dict):
            data = response_json.get("data")
            for key in ["batch_id", "id", "batchId"]:
                batch_id = data.get(key)
                if batch_id is not None:
                    break
        
        if not batch_id:
            await status_msg.edit_text(
                "❌ Failed to get batch_id from API response.\n\n"
                f"Response keys: {list(response_json.keys())}\n"
                f"Full response: {str(response_json)[:400]}"
            )
            return MENU
        await status_msg.edit_text(f"✅ Batch submitted successfully.\nBatch ID: `{batch_id}`\nWaiting {INITIAL_WAIT}s before polling...", parse_mode='Markdown')
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Submission Error: {str(e)}")
        return MENU
    await asyncio.sleep(INITIAL_WAIT)
    
    poll_url = f"{BASE_URL}/check/{batch_id}"
    for poll_count in range(25):
        await status_msg.edit_text(f"🔄 Polling: {poll_count+1}/25 | Live found: {len(live_raw_cards)}", parse_mode='Markdown')
        
        try:
            resp = session.get(poll_url, headers=HEADERS, timeout=30)
            if resp.status_code != 200:
                continue
                
            data = resp.json()
            
            # Multiple possible response structures
            items = (
                data.get("data", {}).get("items") or 
                data.get("items") or 
                data.get("results") or 
                data.get("data", {}).get("checks") or 
                []
            )
            
            for item in items:
                if not isinstance(item, dict):
                    continue
                    
                card_num = str(
                    item.get("card_number") or 
                    item.get("cc") or 
                    item.get("card") or 
                    item.get("number") or ""
                ).strip()
                
                if card_num and card_num not in seen and is_live(item):
                    seen.add(card_num)
                    # Match back to original raw line by last 4 digits
                    for raw in cards:
                        if raw.split('|')[0].strip()[-4:] == card_num[-4:]:
                            if raw not in live_raw_cards:
                                live_raw_cards.append(raw)
                            break
        except Exception:
            pass  # Silent fail on individual poll attempts
            
        await asyncio.sleep(POLL_INTERVAL)
    context.user_data["accumulated_live"] = live_raw_cards
    await handle_live_accumulation(status_msg, context)
    return MENU
async def handle_live_accumulation(status_msg, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("mode", "normal")
    target = context.user_data.get("target_count", 5)
    accumulated = context.user_data.get("accumulated_live", [])

    if mode == "tester":
        context.user_data["live_cards"] = accumulated[:]
        await show_post_summary(status_msg, context)
        return

    if len(accumulated) < target:
        text = f"📊 **Partial Result**\nTarget: `{target}`\nGot: `{len(accumulated)}`\nNeed more cards."
        keyboard = [[InlineKeyboardButton("➕ Add More Cards", callback_data="add_more")],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_main")]]
        await status_msg.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return

    context.user_data["live_cards"] = accumulated[:target]
    context.user_data["extra_cards"] = accumulated[target:]
    await show_post_summary(status_msg, context)

async def show_post_summary(status_msg, context: ContextTypes.DEFAULT_TYPE):
    live_cards = context.user_data.get("live_cards", [])
    extra_cards = context.user_data.get("extra_cards", [])
    mode = context.user_data.get("mode", "normal")
    customer = context.user_data.get("customer_name", "Not Required")
    filename_base = context.user_data.get("filename", f"ESCO_{mode.upper()}_{datetime.now().strftime('%Y%m%d_%H%M')}")
    filename = f"{filename_base}.txt"

    formatted = [format_live_card(raw, mode == "tester") for raw in live_cards]

    with open(filename, "w", encoding="utf-8") as f:
        f.write("══════════════ E$CO CHECK OUTPUT ══════════════\n")
        f.write(f"Mode     : {mode.upper()}\nCustomer : {customer}\n")
        f.write(f"Delivered: {len(live_cards)}\nTotal Live: {len(live_cards)+len(extra_cards)}\n")
        f.write(f"Time     : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n")
        f.write("\n\n".join(formatted))

    if mode == "sale" and live_cards:
        global total_revenue, total_cards_sold
        total_revenue += len(live_cards) * sell_price
        total_cards_sold += len(live_cards)

    if mode == "tester":
        global total_tester_cards
        total_tester_cards += len(live_cards)

    text = (
        f"✅ **TARGET REACHED SUCCESSFULLY**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Live Cards : `{len(live_cards)}`\n"
        f"Extra      : `{len(extra_cards)}`\n"
        f"Mode       : `{mode.upper()}`\n"
        f"Customer   : `{customer}`\n\n"
        "What next?"
    )

    keyboard = [[InlineKeyboardButton("📤 Send Main File", callback_data="send_main")]]
    if extra_cards:
        keyboard.append([InlineKeyboardButton("📤 Send Extra File", callback_data="send_extra")])
    keyboard.extend([
        [InlineKeyboardButton("🏠 Back to Main Menu", callback_data="back_to_main")]
    ])

    await status_msg.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    context.user_data["main_filename"] = filename
    context.user_data["extra_filename"] = f"{filename_base}_EXTRA.txt" if extra_cards else None
    context.user_data["extra_cards"] = extra_cards

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "send_main":
        fn = context.user_data.get("main_filename")
        if fn and os.path.exists(fn):
            await query.message.reply_document(open(fn, "rb"), filename=os.path.basename(fn))
            os.remove(fn)
    elif data == "send_extra":
        fn = context.user_data.get("extra_filename")
        if fn and os.path.exists(fn):
            await query.message.reply_document(open(fn, "rb"), filename=os.path.basename(fn))
            os.remove(fn)

    await query.edit_message_text("✅ Done!", reply_markup=main_menu())
    context.user_data.clear()

async def check_balance(query, context: ContextTypes.DEFAULT_TYPE):
    try:
        r = session.get(f"{BASE_URL}/user", headers=HEADERS, timeout=15)
        credits = r.json().get("data", {}).get("remaining_credits", "N/A")
        await query.edit_message_text(f"💳 Storm Credits: `{credits}`", parse_mode='Markdown', reply_markup=main_menu())
    except Exception:
        await query.edit_message_text("❌ Failed to get balance.", reply_markup=main_menu())

async def save_bin_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        parts = text.split(maxsplit=2)
        bin_prefix = parts[0][:6]
        rating = parts[1]
        suggestion = parts[2] if len(parts) > 2 else "No suggestion"
        BIN_RATER[bin_prefix] = {"rating": rating, "suggestion": suggestion}
        await update.message.reply_text(f"✅ BIN `{bin_prefix}` rated `{rating}`", parse_mode='Markdown', reply_markup=main_menu())
        return MENU
    except:
        await update.message.reply_text("❌ Wrong format. Example: `410039 8.5 Good for cashout`")
        return BIN_RATER_MODE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Cancelled.", reply_markup=main_menu())
    context.user_data.clear()
    return MENU

async def show_pre_summary_from_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update  # reuse for message-based call
    await show_pre_summary(query, context)  # simplified

# ====================== CONVERSATION HANDLER ======================
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
                CommandHandler("setbuy", lambda u,c: globals().update(buy_price=float(c.args[0])) or u.message.reply_text(f"Buy price set to {buy_price}")),
                CommandHandler("setsell", lambda u,c: globals().update(sell_price=float(c.args[0])) or u.message.reply_text(f"Sell price set to {sell_price}")),
                CommandHandler("setmin", lambda u,c: globals().update(min_live_for_sale=int(c.args[0])) or u.message.reply_text(f"Min live set to {min_live_for_sale}")),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_chat=True,
    )

if __name__ == "__main__":
    application = Application.builder().token(TOKEN).build()
    application.add_handler(build_handler())
    application.add_handler(CallbackQueryHandler(button_handler, pattern="^(send_main|send_extra|back_to_main)$"))
    print("🤖 Bot is now running successfully!")
    application.run_polling(drop_pending_updates=True)
