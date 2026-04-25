import asyncio
import random
import os
import requests
from datetime import datetime, timezone
from typing import List, Dict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters,
)

# ====================== CONFIG ======================
TOKEN = os.getenv("TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", 0))
BASE_URL = os.getenv("BASE_URL", "https://api.example.com")
HEADERS = {
    "Authorization": f"Bearer {os.getenv('API_KEY', '')}",
    "Content-Type": "application/json"
}

# ====================== GLOBALS ======================
BIN_RATER: Dict[str, Dict[str, str]] = {}
sell_price = 10.0
buy_price = 1.40
total_revenue = 0.0
total_cards_sold = 0
INITIAL_WAIT = 8
POLL_INTERVAL = 12

session = requests.Session()
print("✅ E$CO Bot v14.5 - Buttons Fixed + Auto Filename")

# ====================== BIN DATABASE ======================
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
    return round(random.uniform(420, 2350), 2)

def get_random_ip() -> str:
    return f"{random.randint(25,195)}.{random.randint(15,245)}.{random.randint(20,230)}.{random.randint(35,220)}"

def is_live(item: dict) -> bool:
    text = " ".join(str(v).lower() for v in item.values())
    return any(word in text for word in ["live", "approved", "success", "charged", "valid", "good"])

def format_live_card(raw_line: str, is_tester: bool = False) -> str:
    try:
        parts = [p.strip() for p in raw_line.replace("=>", "|").split('|')]
        card = parts[0]
        exp = parts[1]
        cvv = parts[2] if len(parts) > 2 else "000"
        if '/' in exp:
            mm, yy = exp.split('/')
        else:
            mm, yy = exp[:2], exp[2:]
        name = parts[3] if len(parts) > 3 else "N/A"
        info = get_bin_info(card)
        vr = max(10, min(98, info.get("vr", 65) + random.randint(-8, 8)))
        balance = get_random_balance(card, is_tester)

        return "\n".join([
            "══════════════════════════════════════",
            f"🃏 LIVE • VR: {vr}%",
            "══════════════════════════════════════",
            f"💰 Balance : ${balance:.2f}",
            f"👤 Name    : {name}",
            f"💳 Card    : {card}",
            f"📅 Expiry  : {mm}/{yy}",
            f"🔒 CVV     : {cvv}",
            f"🏦 Bank    : {info.get('bank', 'UNKNOWN')}",
            f"🌍 Country : UNITED STATES",
            f"🌐 IP      : {get_random_ip()}",
            f"🕒 Checked : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
            "══════════════════════════════════════"
        ])
    except:
        return f"Parse Error: {raw_line}"

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Normal Check", callback_data="normal")],
        [InlineKeyboardButton("🧪 Tester Cards", callback_data="tester")],
        [InlineKeyboardButton("💰 Start Sale", callback_data="sale")],
        [InlineKeyboardButton("🔄 Replacement", callback_data="replacement")],
        [InlineKeyboardButton("📊 Bin Rater", callback_data="binrater")],
    ])

def post_check_keyboard(has_extra: bool = False):
    kb = [[InlineKeyboardButton("📤 Send Main Output", callback_data="send_main")]]
    if has_extra:
        kb.append([InlineKeyboardButton("📤 Send Extra Cards", callback_data="send_extra")])
    kb.append([InlineKeyboardButton("➕ Add More Cards", callback_data="add_more")])
    kb.append([InlineKeyboardButton("⬅️ Back to Menu", callback_data="back")])
    return InlineKeyboardMarkup(kb)

# ====================== CORE CHECK ======================
async def run_check(cards: List[str], status_msg, context: ContextTypes.DEFAULT_TYPE):
    live_cards = []
    seen = set()
    batch_id = f"BATCH-{random.randint(10000,99999)}"
    context.user_data["batch_id"] = batch_id
    mode = context.user_data.get("mode", "normal")

    await status_msg.edit_text(f"✅ Batch {batch_id} submitted. Checking...")

    for _ in range(12):  # Simplified polling
        await asyncio.sleep(3)
        for card in cards:
            if card.split('|')[0][-4:] not in seen and random.random() < 0.4:
                seen.add(card.split('|')[0][-4:])
                live_cards.append(card)

    context.user_data["live_cards"] = live_cards
    await show_post_summary(status_msg, context, mode)

async def show_post_summary(status_msg, context: ContextTypes.DEFAULT_TYPE, mode: str):
    live_cards = context.user_data.get("live_cards", [])
    target = context.user_data.get("target_count", len(live_cards))
    customer = context.user_data.get("customer_name", "Unknown")
    batch_id = context.user_data.get("batch_id", "N/A")

    main_cards = live_cards[:target] if target > 0 else live_cards
    extra_cards = live_cards[target:] if target > 0 and len(live_cards) > target else []

    # Auto filename logic
    if not context.user_data.get("filename"):
        if mode == "tester":
            context.user_data["filename"] = f"test-{random.randint(1000,9999)}"
        elif mode == "replacement":
            context.user_data["filename"] = f"Rep-{random.randint(1000,9999)}"
        else:
            context.user_data["filename"] = f"Batch-{random.randint(1000,9999)}"

    final_fn = f"{context.user_data['filename']}.txt"
    context.user_data["final_filename"] = final_fn
    context.user_data["formatted_output"] = [format_live_card(c, mode=="tester") for c in main_cards]
    context.user_data["extra_cards"] = extra_cards
    context.user_data["extra_filename"] = None

    # Write main file
    with open(final_fn, "w", encoding="utf-8") as f:
        f.write("\n\n".join(context.user_data["formatted_output"]))

    # Write extra file
    if extra_cards:
        extra_fn = f"{batch_id}-extra.txt"
        with open(extra_fn, "w", encoding="utf-8") as f:
            f.write("\n\n".join([format_live_card(c, mode=="tester") for c in extra_cards]))
        context.user_data["extra_filename"] = extra_fn

    text = (
        f"**POST SUMMARY**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Mode: {mode.upper()}\n"
        f"Live: {len(live_cards)}\n"
        f"Delivered: {len(main_cards)}\n"
        f"Extra: {len(extra_cards)}\n"
        f"Batch: `{batch_id}`\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Choose below:"
    )

    await status_msg.edit_text(text, reply_markup=post_check_keyboard(len(extra_cards)>0), parse_mode='Markdown')

# ====================== BUTTON HANDLER ======================
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data in ["normal", "tester", "sale", "replacement"]:
        context.user_data["mode"] = data
        if data in ["sale", "replacement"]:
            await query.edit_message_text("Send customer name:")
            return "CUSTOMER"
        context.user_data["all_cards"] = []
        await query.edit_message_text("Send cards or .txt file.\n/cancel to stop.")
        return "COLLECT"

    if data == "send_main":
        fn = context.user_data.get("final_filename")
        if fn and os.path.exists(fn):
            await query.message.reply_document(open(fn, "rb"), caption=f"✅ {fn}")
            try: os.remove(fn)
            except: pass
        else:
            await query.message.reply_text("❌ File not found.")

    elif data == "send_extra":
        fn = context.user_data.get("extra_filename")
        if fn and os.path.exists(fn):
            await query.message.reply_document(open(fn, "rb"), caption=f"✅ {fn}")
            try: os.remove(fn)
            except: pass

    elif data == "add_more":
        await query.edit_message_text("Send more cards or .txt file.")
        return "COLLECT"

    elif data == "back":
        await start(update, context)
        return ConversationHandler.END

    await query.edit_message_text("✅ Done.", reply_markup=main_menu())
    context.user_data.clear()
    return ConversationHandler.END

# ====================== OTHER HANDLERS ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Unauthorized.")
        return ConversationHandler.END

    await update.message.reply_text("🔥 **E$CO CONTROL PANEL**", reply_markup=main_menu(), parse_mode='Markdown')
    context.user_data.clear()
    return "MENU"

async def customer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def collect_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text and update.message.text.strip().lower() == "/cancel":
        return await start(update, context)

    text = ""
    if update.message.document:
        file = await update.message.document.get_file()
        content = await file.download_as_bytearray()
        text = content.decode("utf-8", errors="ignore")
    else:
        text = update.message.text or ""

    new_cards = [line.strip() for line in text.splitlines() if "|" in line.strip() and len(line.split('|')) >= 3]
    context.user_data.setdefault("all_cards", []).extend(new_cards)

    status = await update.message.reply_text("🚀 Starting check...")
    await run_check(context.user_data["all_cards"], status, context)
    return "SUMMARY"

# ====================== MAIN ======================
def main():
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            "MENU": [CallbackQueryHandler(button_callback)],
            "COLLECT": [MessageHandler(filters.TEXT | filters.Document.ALL, collect_handler)],
            "CUSTOMER": [MessageHandler(filters.TEXT & ~filters.COMMAND, customer_handler)],
            "TARGET": [MessageHandler(filters.TEXT & ~filters.COMMAND, target_handler)],
            "SUMMARY": [CallbackQueryHandler(button_callback)],
        },
        fallbacks=[CommandHandler("cancel", start)],
        per_chat=True,
        per_user=False,
        per_message=False,
    )

    app.add_handler(conv_handler)
    print("🤖 Bot started successfully!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
