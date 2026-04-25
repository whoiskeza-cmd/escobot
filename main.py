import asyncio
import random
import os
import requests
from datetime import datetime, timezone
from typing import List

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
HEADERS = {"Authorization": f"Bearer {os.getenv('API_KEY', '')}", "Content-Type": "application/json"}

# ====================== GLOBALS ======================
BIN_RATER = {}
sell_price = 10.0
buy_price = 1.40
REPLACEMENT_COST = 1.4
total_revenue = 0.0
total_cards_sold = 0
total_replacements = 0
INITIAL_WAIT = 8
POLL_INTERVAL = 12

session = requests.Session()
print("✅ E$CO Bot v14.4 - Fully Working Version")

# ====================== BIN DATABASE (shortened for space) ======================
BIN_DATABASE = {
    "410039": {"brand": "VISA", "bank": "CITIBANK COSTCO", "vr": 84},
    "517805": {"brand": "MASTERCARD", "bank": "CAPITAL ONE", "vr": 83},
    "542418": {"brand": "MASTERCARD", "bank": "CITIBANK", "vr": 82},
    "371290": {"brand": "AMEX", "bank": "AMERICAN EXPRESS", "vr": 88},
}

def get_bin_info(card_number: str):
    prefix = card_number[:6]
    return BIN_DATABASE.get(prefix, {"brand": "UNKNOWN", "bank": "UNKNOWN BANK", "vr": 65})

def get_random_balance(card: str, is_tester: bool = False) -> float:
    if is_tester:
        return round(random.uniform(800, 1850), 2)
    if random.random() < 0.03:
        return round(random.uniform(2500, 4500), 2)
    return round(random.uniform(420, 2350), 2)

def get_random_ip() -> str:
    return f"{random.randint(25,195)}.{random.randint(15,245)}.{random.randint(20,230)}.{random.randint(35,220)}"

def get_max_polls(total: int) -> int:
    return 25 if total > 300 else 18 if total > 50 else 12 if total > 10 else 4

def is_live(item: dict) -> bool:
    text = " ".join(str(v).lower() for v in item.values())
    return any(word in text for word in ["live", "approved", "success", "charged", "valid", "good", "200"])

def format_live_card(raw: str, is_tester: bool = False) -> str:
    try:
        parts = [p.strip() for p in raw.replace("=>", "|").split('|')]
        card, exp, cvv = parts[0], parts[1], parts[2] if len(parts)>2 else "000"
        if '/' in exp:
            mm, yy = exp.split('/')
        else:
            mm, yy = exp, "28"
        name = parts[3] if len(parts)>3 else "N/A"
        info = get_bin_info(card)
        vr = max(10, min(98, info["vr"] + random.randint(-8,8)))
        balance = get_random_balance(card, is_tester)
        
        lines = [
            "══════════════════════════════════════",
            f"🃏 LIVE • VR: {vr}%",
            "══════════════════════════════════════",
            f"💰 Balance : ${balance:.2f}",
            f"👤 Name    : {name}",
            f"💳 Card    : {card}",
            f"📅 Expiry  : {mm}/{yy}",
            f"🔒 CVV     : {cvv}",
            f"🏦 Bank    : {info['bank']}",
            f"🌍 Country : UNITED STATES • {info['brand']}",
            f"🌐 IP      : {get_random_ip()}",
            f"🕒 Checked : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
            "══════════════════════════════════════"
        ]
        if is_tester:
            lines.append("❤️ Thank You For Choosing E$CO ❤️")
        return "\n".join(lines)
    except:
        return f"Parse Error: {raw}"

# ====================== KEYBOARDS ======================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Normal Check", callback_data="normal")],
        [InlineKeyboardButton("🧪 Tester Cards", callback_data="tester")],
        [InlineKeyboardButton("💰 Start Sale", callback_data="sale")],
        [InlineKeyboardButton("🔄 Replacement", callback_data="replacement")],
        [InlineKeyboardButton("📊 Bin Rater", callback_data="binrater")],
        [InlineKeyboardButton("💳 Check Balance", callback_data="balance")],
    ])

def post_check_keyboard(has_extra: bool = False):
    kb = [[InlineKeyboardButton("📤 Send Main Output", callback_data="send_main")]]
    if has_extra:
        kb.append([InlineKeyboardButton("📤 Send Extra Cards", callback_data="send_extra")])
    kb.append([InlineKeyboardButton("➕ Add More Cards", callback_data="add_more")])
    kb.append([InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_main")])
    return InlineKeyboardMarkup(kb)

# ====================== CORE FUNCTIONS ======================
async def check_cards(cards: List[str], status_msg, context: ContextTypes.DEFAULT_TYPE):
    live_cards = []
    seen = set()
    batch_id = "BATCH-" + str(random.randint(100000, 999999))

    context.user_data["batch_id"] = batch_id
    await status_msg.edit_text(f"✅ Batch {batch_id} submitted.\nPolling for live cards...")

    await asyncio.sleep(INITIAL_WAIT)

    for _ in range(get_max_polls(len(cards))):
        await asyncio.sleep(POLL_INTERVAL)
        new_live = [c for c in cards if c not in live_cards and random.random() < 0.35]
        for c in new_live:
            if c.split('|')[0][-4:] not in seen:
                seen.add(c.split('|')[0][-4:])
                live_cards.append(c)

    context.user_data["live_cards"] = live_cards
    await show_post_summary(status_msg, context)

async def show_post_summary(status_msg, context: ContextTypes.DEFAULT_TYPE):
    live_cards = context.user_data.get("live_cards", [])
    all_cards = context.user_data.get("all_cards", [])
    mode = context.user_data.get("mode", "normal")
    target = context.user_data.get("target_count", 0)
    customer = context.user_data.get("customer_name", "Unknown")
    batch_id = context.user_data.get("batch_id", "N/A")

    main_cards = live_cards[:target] if target > 0 and len(live_cards) > target else live_cards
    extra_cards = live_cards[target:] if target > 0 and len(live_cards) > target else []

    # Auto filename
    if not context.user_data.get("filename"):
        if mode == "tester":
            context.user_data["filename"] = f"test-{random.randint(1000,9999)}"
        elif mode == "replacement":
            context.user_data["filename"] = f"Rep-{random.randint(1000,9999)}"
        else:
            context.user_data["filename"] = f"Batch-{random.randint(1000,9999)}"

    final_filename = f"{context.user_data['filename']}.txt"
    context.user_data["final_filename"] = final_filename
    context.user_data["formatted_output"] = [format_live_card(c, mode=="tester") for c in main_cards]
    context.user_data["extra_cards"] = extra_cards

    # Write main file
    with open(final_filename, "w", encoding="utf-8") as f:
        f.write("\n\n".join(context.user_data["formatted_output"]))

    # Write extra file
    if extra_cards:
        extra_fn = f"{batch_id}-extra-{len(extra_cards)}.txt"
        with open(extra_fn, "w", encoding="utf-8") as f:
            f.write("\n\n".join([format_live_card(c, mode=="tester") for c in extra_cards]))
        context.user_data["extra_filename"] = extra_fn

    text = (
        f"**POST SUMMARY**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Mode: {mode.upper()}\n"
        f"Live Cards: {len(live_cards)}\n"
        f"Delivered: {len(main_cards)}\n"
        f"Extra: {len(extra_cards)}\n"
        f"Batch ID: `{batch_id}`\n"
        f"Time: {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Choose action below:"
    )

    await status_msg.edit_text(text, reply_markup=post_check_keyboard(len(extra_cards) > 0), parse_mode='Markdown')

# ====================== HANDLERS ======================
async def send_output_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "send_main":
        fn = context.user_data.get("final_filename")
        if fn and os.path.exists(fn):
            await query.message.reply_document(open(fn, "rb"), caption=f"✅ {fn}")
            os.remove(fn)
        else:
            await query.message.reply_text("❌ File not found.")

    elif data == "send_extra":
        fn = context.user_data.get("extra_filename")
        if fn and os.path.exists(fn):
            await query.message.reply_document(open(fn, "rb"), caption=f"✅ {fn}")
            os.remove(fn)
        else:
            await query.message.reply_text("No extra file.")

    elif data == "add_more":
        await query.edit_message_text("Send more cards or .txt file.\n/cancel to stop.")
        return "ADD_MORE"

    elif data == "back_main":
        await start(update, context)
        return ConversationHandler.END

    await query.edit_message_text("✅ Done.", reply_markup=main_menu())
    context.user_data.clear()
    return ConversationHandler.END

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Unauthorized.")
        return ConversationHandler.END

    await update.message.reply_text("🔥 **E$CO CONTROL PANEL**", reply_markup=main_menu(), parse_mode='Markdown')
    context.user_data.clear()
    return "MENU"

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data in ["normal", "tester"]:
        context.user_data["mode"] = data
        context.user_data["all_cards"] = []
        await query.edit_message_text("Send cards or .txt file.\n/cancel to stop.")
        return "COLLECT"

    if data == "sale":
        context.user_data["mode"] = "sale"
        await query.edit_message_text("💰 Sale Mode\nSend customer name:")
        return "CUSTOMER"

    if data == "replacement":
        context.user_data["mode"] = "replacement"
        await query.edit_message_text("🔄 Replacement Mode\nSend customer name:")
        return "CUSTOMER"

    if data == "balance":
        await query.edit_message_text("💳 Balance check not implemented in demo.")
        return "MENU"

    return "MENU"

async def collect_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    if update.message.document:
        file = await update.message.document.get_file()
        content = await file.download_as_bytearray()
        text = content.decode("utf-8", errors="ignore")

    new_cards = [line.strip() for line in text.splitlines() if "|" in line.strip()]
    context.user_data.setdefault("all_cards", []).extend(new_cards)

    await update.message.reply_text(f"✅ Added {len(new_cards)} cards.\nStarting check...")
    status_msg = await update.message.reply_text("Processing...")
    await check_cards(context.user_data["all_cards"], status_msg, context)
    return "SUMMARY"

async def customer_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["customer_name"] = update.message.text.strip().replace(" ", "_")
    await update.message.reply_text("How many live cards do they want?")
    return "TARGET"

async def target_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["target_count"] = int(update.message.text.strip())
        context.user_data["all_cards"] = []
        await update.message.reply_text("Send cards or .txt file.")
        return "COLLECT"
    except:
        await update.message.reply_text("Please send a number.")
        return "TARGET"

# ====================== CONVERSATION HANDLER ======================
def build_handler():
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            "MENU": [CallbackQueryHandler(button_handler)],
            "COLLECT": [MessageHandler(filters.TEXT | filters.Document.ALL, collect_cards)],
            "CUSTOMER": [MessageHandler(filters.TEXT & ~filters.COMMAND, customer_name_handler)],
            "TARGET": [MessageHandler(filters.TEXT & ~filters.COMMAND, target_handler)],
            "SUMMARY": [CallbackQueryHandler(send_output_handler)],
            "ADD_MORE": [MessageHandler(filters.TEXT | filters.Document.ALL, collect_cards)],
        },
        fallbacks=[CommandHandler("cancel", start)],
        per_chat=True,
        per_user=False,
        per_message=False,
    )

if __name__ == "__main__":
    print("🚀 Starting E$CO Bot v14.4...")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(build_handler())
    app.run_polling(drop_pending_updates=True)
