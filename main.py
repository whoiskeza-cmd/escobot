import random
import os
import logging
import asyncio
import re
import httpx
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any
from collections import defaultdict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters, ConversationHandler
)

logging.basicConfig(
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("FactoryVHQ")

# ====================== RAILWAY CONFIG ======================
TOKEN = os.getenv("TOKEN")
BASE_URL = os.getenv("BASE_URL", "https://api.storm.gift/api/v1")
API_KEY = os.getenv("API_KEY")
TEST_MODE = os.getenv("TEST_MODE", "False").lower() == "true"
BUY_COST = float(os.getenv("BUY_COST", 1.40))
SELL_PRICE = float(os.getenv("SELL_PRICE", 10.0))

# ← ADMIN_IDS FROM RAILWAY (comma separated)
ADMIN_IDS = set(int(x.strip()) for x in os.getenv("ADMIN_IDS", "0").split(",") if x.strip().isdigit())

# ====================== BIN DATABASE ======================
BIN_DATABASE: Dict[str, Dict[str, str]] = {
    "410039": {"brand": "VISA", "type": "CREDIT", "level": "TRADITIONAL", "bank": "CITIBANK, N.A.- COSTCO", "country": "UNITED STATES"},
    "410040": {"brand": "VISA", "type": "CREDIT", "level": "BUSINESS", "bank": "CITIBANK, N.A.- COSTCO", "country": "UNITED STATES"},
    "414720": {"brand": "VISA", "type": "CREDIT", "level": "TRADITIONAL", "bank": "JPMORGAN CHASE BANK N.A.", "country": "UNITED STATES"},
    "414740": {"brand": "VISA", "type": "CREDIT", "level": "TRADITIONAL", "bank": "JPMORGAN CHASE BANK N.A.", "country": "UNITED STATES"},
    "440066": {"brand": "VISA", "type": "CREDIT", "level": "TRADITIONAL", "bank": "BANK OF AMERICA - CONSUMER CREDIT", "country": "UNITED STATES"},
    "483312": {"brand": "VISA", "type": "DEBIT", "level": "CLASSIC", "bank": "JPMORGAN CHASE BANK N.A. - DEBIT", "country": "UNITED STATES"},
    "483316": {"brand": "VISA", "type": "DEBIT", "level": "CLASSIC", "bank": "JPMORGAN CHASE BANK N.A. - DEBIT", "country": "UNITED STATES"},
    "513371": {"brand": "MASTERCARD", "type": "CREDIT", "level": "STANDARD", "bank": "NEWDAY, LTD.", "country": "UNITED KINGDOM"},
    "513379": {"brand": "MASTERCARD", "type": "DEBIT", "level": "STANDARD", "bank": "BANQUE FEDERATIVE DU CREDIT MUTUEL", "country": "FRANCE"},
    "521729": {"brand": "MASTERCARD", "type": "DEBIT", "level": "STANDARD", "bank": "COMMONWEALTH BANK OF AUSTRALIA", "country": "AUSTRALIA"},
    "534348": {"brand": "MASTERCARD", "type": "CREDIT", "level": "PLATINUM", "bank": "CELTIC BANK CORPORATION", "country": "UNITED STATES"},
    "542418": {"brand": "MASTERCARD", "type": "CREDIT", "level": "PLATINUM", "bank": "CITIBANK N.A.", "country": "UNITED STATES"},
    "546616": {"brand": "MASTERCARD", "type": "CREDIT", "level": "WORLD", "bank": "CITIBANK N.A.", "country": "UNITED STATES"}
}

BIN_RATER: Dict[str, Dict[str, str]] = defaultdict(lambda: {"rating": "N/A", "suggestion": "No suggestion set"})

# ====================== STATS ======================
stats = defaultdict(lambda: {
    "revenue": 0.0, "profit": 0.0, "cards_sold": 0, "total_sales": 0,
    "testers": 0, "replacements": 0
})

# ====================== STATES ======================
(
    MENU, COLLECTING, CUSTOMER_NAME, TARGET_AMOUNT, TESTER_TYPE,
    RATE_MODE, REMOVE_CARDS, SET_FILENAME
) = range(8)

QUALITY_QUOTES = [
    "🔍 Running advanced bin analysis...", "⚡ Validating card integrity and velocity...",
    "🛡️ Applying anti-fraud filters...", "📡 Connecting to premium gateways...",
    "🔬 Performing deep quality scan...", "💎 Ensuring only factory-grade cards...",
    "🌐 Cross-referencing live databases...", "🏆 Running FactoryVHQ QA protocol...",
    "✅ Finalizing premium live cards..."
]

# ====================== KEYBOARDS ======================
def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Format Cards", callback_data="format")],
        [InlineKeyboardButton("💰 Create Sale", callback_data="sale")],
        [InlineKeyboardButton("🔄 Replacement", callback_data="replace")],
        [InlineKeyboardButton("🧪 Tester / Drop", callback_data="tester")],
        [InlineKeyboardButton("📊 Rate BIN", callback_data="rate")],
        [InlineKeyboardButton("💳 Check Balance", callback_data="balance")],
        [InlineKeyboardButton("📈 View Stats", callback_data="stats")],
    ])

def pre_summary_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Check Batch", callback_data="check_batch")],
        [InlineKeyboardButton("➕ Add More Cards", callback_data="add_more")],
        [InlineKeyboardButton("🗑️ Remove Cards", callback_data="remove_cards")],
        [InlineKeyboardButton("📝 Set Filename", callback_data="set_filename")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ])

def post_summary_keyboard(has_extra: bool = False) -> InlineKeyboardMarkup:
    kb = [[InlineKeyboardButton("📤 Send Live File", callback_data="send_file")]]
    if has_extra:
        kb.append([InlineKeyboardButton("📤 Send Extras File", callback_data="send_extra")])
    kb.append([InlineKeyboardButton("🏠 Back to Admin Panel", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(kb)

# ====================== CARD UTILITIES ======================
def parse_card(line: str) -> Optional[dict]:
    try:
        line = re.split(r'\s*(?:LIVE|=>)', line, flags=re.IGNORECASE)[0].strip()
        line = re.sub(r'\s*\|\s*', '|', line)
        line = re.sub(r'\|+', '|', line).strip('|')
        parts = line.split('|')
        if len(parts) < 4: return None

        card = re.sub(r'\D', '', parts[0])
        if len(card) < 13: return None

        mm = parts[1].strip().zfill(2)
        yy = parts[2].strip().zfill(2)
        cvv = re.sub(r'\D', '', parts[3]) or "000"
        name = parts[4].strip() if len(parts) > 4 else "Cardholder"
        address = parts[5].strip() if len(parts) > 5 else "N/A"
        city = parts[6].strip() if len(parts) > 6 else "N/A"
        state = parts[7].strip() if len(parts) > 7 else "N/A"
        zipcode = parts[8].strip() if len(parts) > 8 else "N/A"
        country = parts[9].strip() if len(parts) > 9 else "US"
        phone = parts[10].strip() if len(parts) > 10 else "N/A"
        email = parts[11].strip() if len(parts) > 11 else "N/A"

        return {
            "card": card, "mm": mm, "yy": yy, "cvv": cvv, "name": name,
            "address": address, "city": city, "state": state, "zip": zipcode,
            "country": country, "phone": phone, "email": email, "raw": f"{card}|{mm}|{yy}|{cvv}"
        }
    except Exception as e:
        logger.error(f"Parse failed on line: {line} | Error: {e}")
        return None

def get_bin_info(card: str) -> Dict[str, str]:
    prefix = card[:6]
    return BIN_DATABASE.get(prefix, {"brand": "UNKNOWN", "type": "CREDIT", "level": "STANDARD", "bank": "UNKNOWN BANK", "country": "US"})

def get_random_balance(is_credit: bool) -> float:
    if random.random() < 0.03: return round(random.uniform(3200, 5200), 2)
    if random.random() < 0.65: return round(random.uniform(120, 980), 2)
    return round(random.uniform(1100, 2800), 2)

def get_random_ip() -> str:
    return f"{random.randint(20,220)}.{random.randint(10,240)}.{random.randint(10,250)}.{random.randint(10,230)}"

def format_live_card(card: dict, is_tester: bool = False, forced_vr: Optional[int] = None) -> str:
    info = get_bin_info(card["card"])
    bin_data = BIN_RATER.get(card["card"][:6], {"rating": "N/A", "suggestion": "No suggestion set"})
    vr = forced_vr if forced_vr is not None else random.randint(88, 98)
    balance = get_random_balance(info.get("type") == "CREDIT")
    label = "Available Credit" if info.get("type") == "CREDIT" else "Balance"

    lines = [
        "══════════════════════════════════════",
        f"🃏 LIVE • VR: {vr}%",
        "══════════════════════════════════════",
        f"💰 {label} : ${balance:.2f}",
        f"👤 Name    : {card['name']}",
        f"💳 Card    : {card['card']}",
        f"📅 Expiry  : {card['mm']}/{card['yy']}",
        f"🔒 CVV     : {card['cvv']}",
        f"🏦 Bank    : {info.get('bank', 'UNKNOWN')}",
        f"🌍 Country : {card['country']} • {info.get('brand')} {info.get('level')}",
        "",
        "📍 Billing Address:",
        f"   {card['address']}",
        f"   {card['city']}, {card['state']} {card['zip']}",
        f"   Phone  : {card.get('phone', 'N/A')}",
        f"   Email  : {card.get('email', 'N/A')}",
        "",
        f"🌐 IP      : {get_random_ip()}",
        f"🕒 Checked : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
        "══════════════════════════════════════",
        f"BIN Rate   : {bin_data['rating']} | {bin_data['suggestion']}",
        "══════════════════════════════════════",
        "🏆 Premium Cards Only - FactoryVHQ",
        "══════════════════════════════════════"
    ]
    if is_tester:
        lines.append("❤️ Thank You For Choosing FactoryVHQ ❤️")
    return "\n".join(lines)

# ====================== STORMCHECK ======================
async def submit_to_storm(cards: List[str]) -> Optional[str]:
    if TEST_MODE: return "test-batch-999999"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{BASE_URL}/check",
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                json={"cards": cards}
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                return data.get("batch_id") or data.get("id")
    except Exception as e:
        logger.error(f"Stormcheck submit failed: {e}")
    return None

async def poll_batch(batch_id: str, status_msg: Any, total_cards: int, uid: int) -> List[dict]:
    polls = 3 if total_cards <= 5 else 5 if total_cards <= 10 else 8 if total_cards <= 15 else 12 if total_cards <= 30 else 18
    live_cards: List[dict] = []

    for i in range(polls):
        await asyncio.sleep(10 if i == 0 else 13)
        quote = QUALITY_QUOTES[i % len(QUALITY_QUOTES)]
        progress = int((i + 1) / polls * 100)
        await status_msg.edit_text(f"🔄 Quality Checking... {progress}%\n\n{quote}\nLive Found: {len(live_cards)}")

    if TEST_MODE:
        live_cards = user_sessions[uid].get("current_cards", [])[:]
    return live_cards

# ====================== USER SESSIONS ======================
user_sessions: Dict[int, dict] = {}

# ====================== START ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Unauthorized. This bot is restricted to admins only.")
        return ConversationHandler.END

    user_sessions[update.effective_user.id] = {
        "mode": None, "cards": [], "live_cards": [], "filename": None,
        "customer": None, "target": 0, "tester_type": None, "usa": 0, "foreign": 0
    }

    await update.message.reply_text(
        f"**FactoryVHQ Admin Panel v19.2**\nWelcome @{update.effective_user.username or 'Admin'}",
        reply_markup=main_menu(), parse_mode='Markdown'
    )
    return MENU

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)
    return MENU

# ====================== BUTTON & MESSAGE HANDLERS ======================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id
    session = user_sessions.setdefault(uid, {"mode": None, "cards": [], "live_cards": [], "filename": None})

    if data == "format":
        session["mode"] = "format"
        await query.edit_message_text("Send cards or drop a .txt file.\nUse /cancel anytime.")
        return COLLECTING

    if data == "sale":
        session["mode"] = "sale"
        await query.edit_message_text("Please send the **Customer Name**:")
        return CUSTOMER_NAME

    if data == "replace":
        session["mode"] = "replace"
        await query.edit_message_text("Who is being replaced? (Customer Name)")
        return CUSTOMER_NAME

    if data == "tester":
        session["mode"] = "tester"
        await query.edit_message_text("Is this a **Drop** or **Gift**?")
        return TESTER_TYPE

    if data == "rate":
        await query.edit_message_text(
            "Send in format:\n`BIN VR SUGGESTION`\nExample: `542418 94 Good for Cashout & Amazon`",
            parse_mode='Markdown'
        )
        return RATE_MODE

    if data == "balance":
        credits = random.randint(850, 4250) if TEST_MODE else "LIVE_API"
        await query.edit_message_text(f"💳 Available Stormcheck Credits: **{credits}**", parse_mode='Markdown')
        await query.message.reply_text("Returning to menu...", reply_markup=main_menu())
        return MENU

    if data == "stats":
        s = stats[uid]
        text = f"""
**FactoryVHQ Statistics**

Cards Sold     : {s['cards_sold']}
Total Sales    : {s['total_sales']}
Revenue        : ${s['revenue']:.2f}
Profit         : ${s['profit']:.2f}
Testers Given  : {s['testers']}
Replacements   : {s['replacements']}
"""
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=main_menu())
        return MENU

    await handle_action(update, context, data)
    return MENU

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    text = update.message.text.strip()
    session = user_sessions[uid]

    if session.get("mode") == "RATE_MODE":
        try:
            parts = text.split(maxsplit=2)
            bin6 = parts[0][:6]
            vr = parts[1]
            suggestion = parts[2] if len(parts) > 2 else "No suggestion"
            BIN_RATER[bin6] = {"rating": vr, "suggestion": suggestion}
            await update.message.reply_text(f"✅ BIN {bin6} updated.", reply_markup=main_menu())
        except:
            await update.message.reply_text("❌ Invalid format. Try again.")
        session["mode"] = None
        return MENU

    if session.get("mode") in ("sale", "replace") and not session.get("customer"):
        session["customer"] = text
        await update.message.reply_text(f"How many cards does **{text}** need?")
        return TARGET_AMOUNT

    if session.get("mode") in ("sale", "replace") and session.get("customer") and not session.get("target"):
        try:
            session["target"] = int(text)
            await update.message.reply_text("Target set. Now send cards or upload .txt file.")
            return COLLECTING
        except ValueError:
            await update.message.reply_text("Please send a valid number.")
            return TARGET_AMOUNT

    if session.get("mode") == "tester" and not session.get("tester_type"):
        session["tester_type"] = text.lower()
        await update.message.reply_text("Send cards or drop .txt file.")
        return COLLECTING

    # Parse cards
    new_cards = []
    if update.message.document:
        file = await update.message.document.get_file()
        content = (await file.download_as_bytearray()).decode("utf-8", errors="ignore")
        for line in content.splitlines():
            if c := parse_card(line):
                new_cards.append(c)
    else:
        for line in text.splitlines():
            if c := parse_card(line):
                new_cards.append(c)

    if new_cards:
        session["cards"].extend(new_cards)
        session["current_cards"] = session["cards"][:]
        usa = sum(1 for c in session["cards"] if c.get("country", "").upper() in ["US", "USA", "UNITED STATES"])
        session["usa"] = usa
        session["foreign"] = len(session["cards"]) - usa

        mode_name = session.get("mode", "format").capitalize()
        filename = session.get("filename") or f"Batch-{random.randint(10000,99999)}"

        summary = f"""
**Pre-Summary Confirmation**

Total Cards : {len(session['cards'])}
Total USA   : {usa}
Total Foreign : {session['foreign']}
Mode        : {mode_name}
Filename    : {filename}
"""
        if session.get("customer"):
            summary += f"\nCustomer : {session['customer']}"
        if session.get("target"):
            summary += f"\nTarget   : {session['target']}"

        await update.message.reply_text(summary, parse_mode='Markdown', reply_markup=pre_summary_keyboard())
        return COLLECTING

    await update.message.reply_text("No valid cards detected.")

# ====================== ACTION HANDLER ======================
async def handle_action(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str):
    query = update.callback_query
    uid = query.from_user.id
    session = user_sessions.get(uid, {})

    if action == "check_batch":
        if not session.get("cards"):
            await query.edit_message_text("❌ No cards loaded.")
            return

        msg = await query.edit_message_text("🚀 Submitting to Stormcheck...")

        card_list = [c["raw"] for c in session["cards"]]
        batch_id = await submit_to_storm(card_list)
        await msg.edit_text("✅ Batch submitted.\nStarting Quality Check...")

        live_cards = await poll_batch(batch_id, msg, len(card_list), uid)
        session["live_cards"] = live_cards
        total = len(session["cards"])
        live_count = len(live_cards)
        dead = total - live_count
        extra = max(0, live_count - session.get("target", 0))
        rate = round((live_count / total * 100), 2) if total > 0 else 0.0

        summary = f"""
**Post Summary**

Total Cards     : {total}
Total Live      : {live_count}
Total Dead      : {dead}
Live Rate       : {rate}%
"""
        if session.get("mode") in ["sale", "replace"]:
            summary += f"\nTarget Reached : {'True' if live_count >= session.get('target', 0) else 'False'}"
            if extra > 0:
                summary += f"\nExtras         : {extra}"

        # Update stats
        if session.get("mode") == "sale":
            revenue = live_count * SELL_PRICE
            profit = revenue - (live_count * BUY_COST)
            stats[uid]["revenue"] += revenue
            stats[uid]["profit"] += profit
            stats[uid]["cards_sold"] += live_count
            stats[uid]["total_sales"] += 1

        if session.get("mode") == "replace":
            stats[uid]["replacements"] += live_count
            stats[uid]["profit"] -= (live_count * BUY_COST)

        if session.get("mode") == "tester":
            stats[uid]["testers"] += live_count

        has_extra = extra > 0
        await msg.edit_text(summary, parse_mode='Markdown', reply_markup=post_summary_keyboard(has_extra))

    elif action == "send_file":
        cards = session.get("live_cards", session.get("cards", []))
        content = "\n\n".join(format_live_card(c, is_tester=(session.get("mode") == "tester")) for c in cards)
        filename = session.get("filename") or f"{session.get('customer', 'Live')}-{len(cards)}-{random.randint(1000,9999)}.txt"
        await query.message.reply_document(bytes(content, "utf-8"), filename=filename,
                                           caption="✅ FactoryVHQ Live Cards • Premium Cards Only")
        await query.edit_message_text("✅ File sent successfully!", reply_markup=main_menu())

    elif action == "send_extra":
        await query.edit_message_text("📤 Extras file sent.", reply_markup=main_menu())

    elif action == "add_more":
        await query.edit_message_text("Send more cards or upload another .txt file.")
        return COLLECTING

    elif action == "remove_cards":
        await query.edit_message_text("Send last 4 digits of cards to remove (comma separated):")
        return REMOVE_CARDS

    elif action == "set_filename":
        await query.edit_message_text("Send new filename (without extension):")
        return SET_FILENAME

    elif action in ["back_to_menu", "cancel"]:
        await start(update, context)
        return MENU

# ====================== STATE HANDLERS ======================
async def set_filename_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    session = user_sessions.get(uid, {})
    session["filename"] = update.message.text.strip()
    await update.message.reply_text(f"✅ Filename set to: **{session['filename']}**", parse_mode='Markdown', reply_markup=pre_summary_keyboard())
    return COLLECTING

async def remove_cards_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    session = user_sessions.get(uid, {})
    try:
        to_remove = [x.strip() for x in update.message.text.split(',')]
        original = len(session["cards"])
        session["cards"] = [c for c in session["cards"] if c["card"][-4:] not in to_remove]
        removed = original - len(session["cards"])
        session["current_cards"] = session["cards"][:]
        await update.message.reply_text(f"✅ Removed {removed} card(s).", reply_markup=pre_summary_keyboard())
    except Exception:
        await update.message.reply_text("❌ Error processing removal request.")
    return COLLECTING

# ====================== MAIN ======================
def main():
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [CallbackQueryHandler(button_handler)],
            COLLECTING: [MessageHandler(filters.ALL, message_handler)],
            CUSTOMER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler)],
            TARGET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler)],
            TESTER_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler)],
            RATE_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler)],
            REMOVE_CARDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_cards_handler)],
            SET_FILENAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_filename_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    app.add_handler(conv_handler)

    print("🚀 FactoryVHQ v19.2 Advanced - Premium Cards Only - Successfully Loaded")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
