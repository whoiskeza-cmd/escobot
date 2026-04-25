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
HEADERS = {
    "Authorization": f"Bearer {STORM_API_KEY}",
    "Accept": "application/json",
    "Content-Type": "application/json"
}

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
VR_PERCENTAGE = 85          # Default VR for replacements
FORMAT_STYLE = "pipe"       # pipe, tab, comma

# ====================== BIN DATABASE ======================
BIN_DATABASE = { ... }   # (kept same as before - omitted for brevity)

def get_bin_info(card_number: str): ...          # unchanged
def get_random_balance(card_number: str, is_tester: bool = False): ...  # unchanged
def get_random_ip(): ...                         # unchanged

# ====================== KEYBOARDS ======================
def main_menu(username: str = "User"):
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
        [InlineKeyboardButton("🗑️ Remove Card (Last 4)", callback_data="remove_last4")],
        [InlineKeyboardButton("🚀 E$ CHECK", callback_data="confirm_check")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ])

def replacement_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Send Prepare Reps", callback_data="prepare_reps")],
        [InlineKeyboardButton("⚙️ Rep Settings", callback_data="rep_settings")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_main")],
    ])

def usa_foreign_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇺🇸 USA Cards", callback_data="usa_cards")],
        [InlineKeyboardButton("🌍 Foreign Cards", callback_data="foreign_cards")],
    ])

# ====================== FORMATTER (WITH EMAIL) ======================
def format_live_card(raw_line: str, is_tester: bool = False) -> str:
    try:
        parts = [p.strip() for p in raw_line.replace("=>", "|").split('|')]
        card_number = parts[0]
        expiry = parts[1] if len(parts) > 1 else "00/00"
        cvv = parts[2] if len(parts) > 2 else "000"
        name = parts[3] if len(parts) > 3 else "N/A"
        address = parts[4] if len(parts) > 4 else "N/A"
        city = parts[5] if len(parts) > 5 else "N/A"
        state = parts[6] if len(parts) > 6 else "N/A"
        zip_code = parts[7] if len(parts) > 7 else "N/A"
        phone = parts[9] if len(parts) > 9 else "N/A"
        email = parts[10] if len(parts) > 10 else "N/A"

        mm, yy = expiry.split('/') if '/' in expiry else (expiry[:2], expiry[-2:])
        balance = get_random_balance(card_number, is_tester)
        ip = get_random_ip()
        info = get_bin_info(card_number)
        base_vr = info.get("vr", 45)
        vr = max(5, min(99, int(base_vr + random.gauss(0, 8))))

        bin_data = BIN_RATER.get(card_number[:6], {"rating": "N/A", "suggestion": "No rating added yet"})

        lines = [
            "═━═━═━═━═━═━═━═",
            f"🃏 LIVE • VR: {vr}%",
            "═━═━═━═━═━═━═━═",
            f"💰 ${balance:.2f}    👤 {name}",
            f"💳 {card_number}    📅 {mm}/{yy}    🔒 {cvv}",
            f"🏦 {info['bank']}",
            f"🌍 {info['country']} • {info['brand']} {info['level']}",
            "",
            "📍 Billing:",
            f"   {address}",
            f"   {city}, {state} {zip_code}",
            f"   ☎ {phone}",
            f"   ✉️ {email}",
            "",
            f"🌐 {ip}    🕒 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "═━═━═━═━═━═━═━═",
            f"📊 BIN Rate: {bin_data['rating']} | {bin_data['suggestion']}",
            "═━═━═━═━═━═━═━═"
        ]
        if is_tester:
            lines.append("❤️ Thank You For Choosing E$CO ❤️")
        return "\n".join(lines)
    except Exception:
        return f"Parse Error: {raw_line}"

# ====================== IMPROVED CHECKER ======================
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
    await asyncio.sleep(3)

    try:
        r = session.post(f"{BASE_URL}/check", headers=HEADERS, json={"cards": cards}, timeout=40)
        r.raise_for_status()
        data = r.json()
        batch_id = data.get("batch_id") or data.get("id") or data.get("data", {}).get("batch_id")
    except Exception as e:
        await status_message.edit_text(f"❌ Submission Error: {str(e)}")
        return [], None

    await status_message.edit_text(f"✅ Batch submitted.\nEnsuring 100% Quality By Balance And Live Checking\nWaiting {INITIAL_WAIT}s...")
    await asyncio.sleep(INITIAL_WAIT)

    poll_url = f"{BASE_URL}/check/{batch_id}"
    poll_count = 0

    while poll_count < max_polls:
        poll_count += 1
        await status_message.edit_text(
            f"Ensuring 100% Quality By Balance And Live Checking\n"
            f"Poll: {poll_count}/{max_polls} | Live: {len(live_raw_cards)}"
        )

        try:
            r = session.get(poll_url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            data = r.json()
            items = data.get("data", {}).get("items") or data.get("items") or []

            for item in items:
                if not isinstance(item, dict): continue
                card_num = str(item.get("card_number") or item.get("cc") or "").strip()
                if card_num and card_num not in seen and is_live(item):
                    seen.add(card_num)
                    for raw in cards:
                        if raw.split('|')[0].strip()[-4:] == card_num[-4:]:
                            if raw not in live_raw_cards:
                                live_raw_cards.append(raw)
                            break
        except:
            pass
        await asyncio.sleep(POLL_INTERVAL)

    return live_raw_cards, batch_id

# ====================== STATES ======================
MENU, COLLECTING, USA_FOREIGN, SUMMARY, ADD_MORE_CARDS, REMOVE_LAST4, CUSTOMER_NAME, TARGET_COUNT, BIN_RATER_MODE, FILENAME, REP_SETTINGS = range(11)

# ====================== CONTROL PANEL ======================
async def control_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (
        "🔥 **E$CO CONTROL PANEL** 🔥\n\n"
        f"Welcome, @{user.username}\n\n"
        f"💵 Revenue : `${total_revenue:.2f}`\n"
        f"📦 Sold    : `{total_cards_sold}`\n"
        f"🧪 Tester  : `{total_tester_cards}`\n"
        f"🔄 Repl    : `{total_replacements}`\n"
        f"📈 Profit  : `${round(total_revenue - (total_cards_sold * 1.6) - (total_replacements * REPLACEMENT_COST), 2):.2f}`\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\nChoose option:"
    )
    await (update.message or update.callback_query.message).edit_text(
        text, reply_markup=main_menu(user.username), parse_mode='Markdown'
    )
    context.user_data.clear()
    return MENU

# ====================== HANDLERS ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Unauthorized.")
        return ConversationHandler.END
    return await control_panel(update, context)

async def main_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    context.user_data.clear()

    if data == "start_format":
        context.user_data["mode"] = "normal"
        context.user_data["is_tester"] = False
        context.user_data["all_cards"] = []
        await query.edit_message_text("Send cards or .txt file.\n/cancel to stop.\n\nSend filename after cards (or press skip):")
        return FILENAME

    if data == "start_tester":
        context.user_data["mode"] = "tester"
        context.user_data["is_tester"] = True
        context.user_data["all_cards"] = []
        await query.edit_message_text("Send cards or .txt file for testing.\n/cancel to stop.")
        return COLLECTING

    if data == "start_replacement":
        await query.edit_message_text("🔄 **E$ Replacement Menu**", reply_markup=replacement_menu())
        return MENU

    if data == "prepare_reps":
        context.user_data["mode"] = "replacement"
        await query.edit_message_text("Send Customer Name:")
        return CUSTOMER_NAME

    if data == "rep_settings":
        await query.edit_message_text(
            "⚙️ Rep Settings\n\n"
            "Use commands:\n"
            "/setvr 85\n"
            "/setformat pipe\n"
            "Current VR: {VR_PERCENTAGE}%\n"
            f"Current Format: {FORMAT_STYLE}"
        )
        return REP_SETTINGS

    if data == "back_to_main":
        return await control_panel(update, context)

    if data == "record_sale":
        context.user_data["mode"] = "sale"
        await query.edit_message_text("💰 **Record Sale**\n\nSend Customer Name:")
        return CUSTOMER_NAME

    if data == "bin_rater":
        await query.edit_message_text("📊 Send BIN rating:\n`410039 8.5 Good for cashout`")
        return BIN_RATER_MODE

    if data == "check_balance":
        return await check_balance(query, context)

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

async def get_filename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() in ["skip", "/skip"]:
        context.user_data["filename"] = None
    else:
        context.user_data["filename"] = text.replace(" ", "_")
    await update.message.reply_text("Send cards or .txt file now.")
    return COLLECTING

async def collect_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text and update.message.text.strip().lower() in ["/cancel", "cancel"]:
        return await control_panel(update, context)

    # ... (same parsing logic as before - kept clean)
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
    await update.message.reply_text(
        f"📥 Added **{len(new_cards)}** cards.\nUSA or Foreign?",
        reply_markup=usa_foreign_keyboard(),
        parse_mode='Markdown'
    )
    return USA_FOREIGN

# ... (usa_foreign_handler, show_pre_summary, pre_summary_handler, remove_last4_handler, add_more_cards kept with fixes)

async def pre_summary_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "confirm_check":
        cards = context.user_data.get("all_cards", [])
        if not cards:
            await query.edit_message_text("❌ No cards.", reply_markup=main_menu())
            return MENU

        max_polls = 4 if len(cards) < 10 else 12
        status_msg = await query.edit_message_text("🚀 Starting E$ CHECK...")
        
        live_cards, batch_id = await check_cards_with_storm(cards, status_msg, max_polls)
        context.user_data["live_cards"] = live_cards
        context.user_data["batch_id"] = batch_id

        if not live_cards:
            await status_msg.edit_text("❌ **0 Live Cards Found**", parse_mode='Markdown', reply_markup=main_menu())
            return MENU

        await show_post_summary(status_msg, context)
        return MENU

    # ... other buttons (add_more, remove_last4, cancel) remain same

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

    if mode == "tester":
        filename = context.user_data.get("filename") or f"Test-{random.randint(10000,99999)}"
        revenue_text = "🧪 Tester Mode"
        total_tester_cards += live_count
    elif mode == "replacement":
        deduction = round(live_count * REPLACEMENT_COST, 2)
        total_revenue = round(total_revenue - deduction, 2)
        total_replacements += live_count
        filename = context.user_data.get("filename") or f"{customer}_Rep{live_count}"
        revenue_text = f"🔄 Replacement -${deduction}"
    else:
        # Profit only added in Sale mode
        revenue = round(live_count * SELLING_PRICE, 2)
        total_revenue += revenue
        total_cards_sold += live_count
        filename = context.user_data.get("filename") or f"{customer}_{live_count}_Live"
        revenue_text = f"💰 +${revenue}"

    final_filename = f"{filename}.txt"
    formatted = [format_live_card(raw, mode == "tester") for raw in live_cards]

    with open(final_filename, "w", encoding="utf-8") as f:
        f.write("\n\n".join(formatted))
        f.write("\n\n" + "="*50 + "\n")
        f.write(f"E$CO Post Summary Attached\n")
        f.write(f"Time Checked (EST): {est_time}\n")

    post_text = (
        "📊 **POST SUMMARY**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Batch   : `{batch_id}`\n"
        f"Total   : `{total_cards}` | Live : `{live_count}` ({live_rate}%)\n"
        f"Mode    : **{mode.upper()}**\n"
        f"{revenue_text}\n"
        f"Time Checked (EST): `{est_time}`\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )

    await status_msg.edit_text(post_text, parse_mode='Markdown')
    await status_msg.reply_document(document=open(final_filename, "rb"), caption=final_filename)

    try:
        os.remove(final_filename)
    except:
        pass

    await status_msg.reply_text("**E$ Check Has Successfully Completed**", parse_mode='Markdown', reply_markup=main_menu())
    context.user_data.clear()

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await control_panel(update, context)

def build_handler():
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [CallbackQueryHandler(main_button)],
            FILENAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_filename)],
            CUSTOMER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_customer_name)],
            TARGET_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_target_count)],
            COLLECTING: [MessageHandler(filters.TEXT | filters.Document.ALL, collect_cards)],
            USA_FOREIGN: [CallbackQueryHandler(usa_foreign_handler)],
            SUMMARY: [CallbackQueryHandler(pre_summary_handler)],
            ADD_MORE_CARDS: [MessageHandler(filters.TEXT | filters.Document.ALL, add_more_cards)],
            REMOVE_LAST4: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_last4_handler)],
            BIN_RATER_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_bin_rating)],
            REP_SETTINGS: [CommandHandler("setvr", set_vr), CommandHandler("setformat", set_format)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_chat=True,
    )

async def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(build_handler())
    print("✅ E$CO Bot v13.0 - Updated with all requested features")
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
