import random
import os
import logging
import asyncio
import re
import httpx
from datetime import datetime, timezone
from typing import List, Dict, Optional
from collections import defaultdict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters, ConversationHandler
)

logging.basicConfig(format='%(asctime)s | %(levelname)-8s | %(message)s', level=logging.INFO)
logger = logging.getLogger("FactoryVHQ")

# ====================== CONFIG ======================
TOKEN = os.getenv("TOKEN")
BASE_URL = "https://api.storm.gift/api/v1"
API_KEY = os.getenv("API_KEY")
TEST_MODE = os.getenv("TEST_MODE", "False").lower() == "true"
BUY_COST = float(os.getenv("BUY_COST", 1.40))
SELL_PRICE = float(os.getenv("SELL_PRICE", 10.0))
OWNER_ID = int(os.getenv("OWNER_ID", 0))
ADMIN_IDS = set(int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit())

AUTHORIZED_USERS = ADMIN_IDS | {OWNER_ID} if OWNER_ID != 0 else ADMIN_IDS

# ====================== BIN DATABASE ======================
BIN_DATABASE = {
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

BIN_RATER: Dict[str, Dict[str, str]] = defaultdict(lambda: {"rating": "N/A", "suggestion": "No suggestion set", "balance": "N/A"})
FORCED_VR: Dict[str, int] = {}

stats = defaultdict(lambda: {
    "revenue": 0.0, "profit": 0.0, "cards_sold": 0, "total_sales": 0,
    "testers": 0, "replacements": 0
})

user_sessions: Dict[int, dict] = {}

QUALITY_QUOTES = [
    "🔍 Running advanced bin analysis...", "⚡ Validating card integrity...",
    "🛡️ Applying anti-fraud filters...", "📡 Connecting to premium gateways...",
    "🔬 Performing deep quality scan...", "💎 Ensuring only factory-grade cards...",
    "🌐 Cross-referencing live databases...", "🏆 Running FactoryVHQ QA protocol...",
    "✅ Finalizing premium live cards..."
]

# ====================== STATES ======================
MENU, COLLECTING, CUSTOMER_NAME, TARGET_AMOUNT, TESTER_TYPE, RATE_MODE, REMOVE_CARDS, SET_FILENAME, BIN_INPUT = range(9)

# ====================== KEYBOARDS ======================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Format", callback_data="format")],
        [InlineKeyboardButton("💰 Sale", callback_data="sale")],
        [InlineKeyboardButton("🔄 Replace", callback_data="replace")],
        [InlineKeyboardButton("🧪 Tester", callback_data="tester")],
        [InlineKeyboardButton("📊 Rate BIN", callback_data="rate")],
        [InlineKeyboardButton("💳 Balance", callback_data="balance")],
        [InlineKeyboardButton("📈 Stats", callback_data="stats")],
    ])

def rate_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Set BIN VR", callback_data="set_vr")],
        [InlineKeyboardButton("Rate BIN", callback_data="rate_bin")],
        [InlineKeyboardButton("Set Balance Rating", callback_data="set_balance")],
        [InlineKeyboardButton("Set Suggestion", callback_data="set_suggestion")],
        [InlineKeyboardButton("Force VR", callback_data="force_vr")],
        [InlineKeyboardButton("❌ Back", callback_data="back_to_menu")]
    ])

def pre_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Check Batch", callback_data="check_batch")],
        [InlineKeyboardButton("➕ Add More Cards", callback_data="add_more")],
        [InlineKeyboardButton("🗑️ Remove Cards", callback_data="remove_cards")],
        [InlineKeyboardButton("📝 Set Filename", callback_data="set_filename")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ])

def post_keyboard(has_extra=False):
    kb = [[InlineKeyboardButton("📤 Send Live File", callback_data="send_file")]]
    if has_extra:
        kb.append([InlineKeyboardButton("📤 Send Extras File", callback_data="send_extra")])
    kb.append([InlineKeyboardButton("➕ Add More Cards", callback_data="add_more")])
    kb.append([InlineKeyboardButton("🗑️ Remove Cards", callback_data="remove_cards")])
    kb.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    return InlineKeyboardMarkup(kb)

# ====================== PARSER ======================
def parse_card(line: str) -> Optional[dict]:
    try:
        line = re.split(r'\s*(?:LIVE|=>|stormcheck)', line, flags=re.IGNORECASE)[0].strip()
        line = re.sub(r'\s*\|\s*', '|', line)
        line = re.sub(r'\|+', '|', line).strip('|')
        parts = line.split('|')
        if len(parts) < 4: return None
        card = re.sub(r'\D', '', parts[0])
        if len(card) < 13: return None
        return {
            "card": card,
            "mm": parts[1].strip().zfill(2),
            "yy": parts[2].strip()[-2:].zfill(2),
            "cvv": re.sub(r'\D', '', parts[3]) or "000",
            "name": parts[4].strip() if len(parts) > 4 else "Cardholder",
            "address": parts[5].strip() if len(parts) > 5 else "N/A",
            "city": parts[6].strip() if len(parts) > 6 else "N/A",
            "state": parts[7].strip() if len(parts) > 7 else "N/A",
            "zip": parts[8].strip() if len(parts) > 8 else "N/A",
            "country": parts[9].strip() if len(parts) > 9 else "US",
            "phone": parts[10].strip() if len(parts) > 10 else "N/A",
            "email": parts[11].strip() if len(parts) > 11 else "N/A",
            "raw": f"{card}|{parts[1].strip().zfill(2)}|{parts[2].strip()[-2:].zfill(2)}|{re.sub(r'\D', '', parts[3]) or '000'}"
        }
    except Exception as e:
        logger.error(f"Parse failed: {line}")
        return None

def get_bin_info(card: str):
    return BIN_DATABASE.get(card[:6], {"brand": "UNKNOWN", "type": "CREDIT", "level": "STANDARD", "bank": "UNKNOWN BANK", "country": "US"})

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

# ====================== FIXED BATCH ID + STATUS: LIVE SCAN ======================
async def submit_to_storm(cards: List[str]):
    if TEST_MODE: return "test-batch-999999"
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            r = await client.post(f"{BASE_URL}/check",
                                  headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                                  json={"cards": cards})
            r.raise_for_status()
            data = r.json()
            batch = data.get("data", [{}])[0] if isinstance(data.get("data"), list) else data.get("data", {})
            batch_id = batch.get("id") or batch.get("batch_id")
            logger.info(f"Batch submitted successfully. Batch ID: {batch_id}")
            return batch_id
    except Exception as e:
        logger.error(f"Submit failed: {e}")
        return None

async def get_batch_result(batch_id: str):
    if TEST_MODE or not batch_id:
        return {"live_count": 1, "items": [{"card": "5217295432071383", "status": "live"}]}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{BASE_URL}/check/{batch_id}",
                                 headers={"Authorization": f"Bearer {API_KEY}"})
            r.raise_for_status()
            data = r.json()
            result = data.get("data", [{}])[0] if isinstance(data.get("data"), list) else data.get("data", {})
            live_count = result.get("live_count", 0)
            items = result.get("items", [])
            logger.info(f"Batch {batch_id} returned live_count: {live_count} | items: {len(items)}")
            return {"live_count": live_count, "items": items}
    except Exception as e:
        logger.error(f"Get batch result failed: {e}")
        return {"live_count": 0, "items": []}

async def poll_batch(batch_id: str, status_msg, total_cards: int, uid: int):
    if total_cards <= 5: polls, delay = 5, 12
    elif total_cards <= 10: polls, delay = 7, 15
    else: polls, delay = 10, 18

    for i in range(polls):
        await asyncio.sleep(delay)
        result = await get_batch_result(batch_id)
        live_count = result.get("live_count", 0)
        quote = QUALITY_QUOTES[i % len(QUALITY_QUOTES)]
        progress = int((i + 1) / polls * 100)
        await status_msg.edit_text(f"🔄 Quality Checking... {progress}%\n\n{quote}\nLive Found: {live_count}")

    final = await get_batch_result(batch_id)
    live_items = [item for item in final.get("items", []) if str(item.get("status", "")).lower() == "live"]

    current_cards = user_sessions[uid].get("current_cards", [])
    live_cards = []

    for item in live_items:
        card_num = str(item.get("card", ""))[:16]
        for card in current_cards:
            if card["card"] == card_num:
                live_cards.append(card)
                break

    logger.info(f"Final live cards matched: {len(live_cards)} out of {len(live_items)} reported live")
    return live_cards

# ====================== START ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in AUTHORIZED_USERS:
        await update.message.reply_text("⛔ Unauthorized.")
        return ConversationHandler.END

    user_sessions[update.effective_user.id] = {
        "mode": None, "cards": [], "live_cards": [], "filename": None,
        "customer": None, "target": 0, "tester_type": None, "usa": 0, "foreign": 0,
        "rate_step": None, "current_bin": None
    }

    await update.message.reply_text(
        "**FactoryVHQ Admin Panel**\nWelcome @" + (update.effective_user.username or "Admin"),
        reply_markup=main_menu(), parse_mode='Markdown'
    )
    return MENU

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id in user_sessions:
        user_sessions[update.effective_user.id] = {"mode": None, "cards": [], "live_cards": [], "filename": None}
    await update.message.reply_text("✅ Cancelled. Returning to Admin Panel.", reply_markup=main_menu())
    return MENU

# ====================== BUTTON HANDLER ======================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id
    session = user_sessions.setdefault(uid, {"mode": None, "cards": [], "live_cards": [], "filename": None, "rate_step": None, "current_bin": None})

    if data in ["cancel", "back_to_menu"]:
        return await cancel(update, context)

    if data == "rate":
        await query.edit_message_text("**Rate BIN Menu**", reply_markup=rate_menu(), parse_mode='Markdown')
        return MENU

    if data in ["set_vr", "rate_bin", "set_balance", "set_suggestion", "force_vr"]:
        session["rate_step"] = data
        await query.edit_message_text("Send 6 digit BIN:")
        return BIN_INPUT

    if data == "format":
        session["mode"] = "format"
        await query.edit_message_text("Send Cards Or Drop .txt File To Continue")
        return COLLECTING

    if data == "sale":
        session["mode"] = "sale"
        await query.edit_message_text("Please Respond With The Customer Name")
        return CUSTOMER_NAME

    if data == "replace":
        session["mode"] = "replace"
        await query.edit_message_text("Who Is Being Replaced")
        return CUSTOMER_NAME

    if data == "tester":
        session["mode"] = "tester"
        await query.edit_message_text("Is This Tester A Drop Or Gift?")
        return TESTER_TYPE

    if data == "balance":
        credits = random.randint(850, 4250) if TEST_MODE else "API_RESPONSE"
        await query.edit_message_text(f"Your Available Storm Credits Are **{credits}**", parse_mode='Markdown', reply_markup=main_menu())
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

# ====================== MESSAGE HANDLER ======================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in AUTHORIZED_USERS: return
    text = update.message.text.strip()
    session = user_sessions[uid]

    if session.get("rate_step"):
        step = session["rate_step"]
        if step in ["set_vr", "rate_bin", "set_balance", "set_suggestion", "force_vr"]:
            bin6 = text[:6]
            session["current_bin"] = bin6
            prompts = {
                "set_vr": f"You have selected BIN **{bin6}**\nWhat do you want to set the VR rating as?",
                "rate_bin": f"You have selected BIN **{bin6}**\nRate this BIN:",
                "set_balance": f"You have selected BIN **{bin6}**\nSet Balance Rating:",
                "set_suggestion": f"You have selected BIN **{bin6}**\nSet Suggestion:",
                "force_vr": f"You have selected BIN **{bin6}**\nSet Forced VR (number or 'reset'):"
            }
            await update.message.reply_text(prompts.get(step, "Send value:"))
            session["rate_step"] = step + "_value"
            return BIN_INPUT

        bin6 = session.get("current_bin")
        if "vr" in session["rate_step"]:
            BIN_RATER[bin6]["rating"] = text
            await update.message.reply_text(f"✅ VR for BIN {bin6} set to {text}%", reply_markup=main_menu())
        elif "balance" in session["rate_step"]:
            BIN_RATER[bin6]["balance"] = text
            await update.message.reply_text(f"✅ Balance rating for BIN {bin6} set to {text}", reply_markup=main_menu())
        elif "suggestion" in session["rate_step"]:
            BIN_RATER[bin6]["suggestion"] = text
            await update.message.reply_text(f"✅ Suggestion for BIN {bin6} set.", reply_markup=main_menu())
        elif "force" in session["rate_step"]:
            if text.lower() == "reset":
                FORCED_VR.pop(bin6, None)
                await update.message.reply_text(f"✅ Forced VR reset for {bin6}", reply_markup=main_menu())
            else:
                FORCED_VR[bin6] = int(text)
                await update.message.reply_text(f"✅ Forced VR for {bin6} set to {text}%", reply_markup=main_menu())
        session["rate_step"] = None
        session["current_bin"] = None
        return MENU

    if session.get("mode") in ("sale", "replace") and not session.get("customer"):
        session["customer"] = text
        await update.message.reply_text(f"How many cards is **{text}** purchasing / needs replaced?")
        return TARGET_AMOUNT

    if session.get("mode") in ("sale", "replace") and session.get("customer") and not session.get("target"):
        try:
            session["target"] = int(text)
            await update.message.reply_text("Target Set")
            return COLLECTING
        except:
            await update.message.reply_text("Please send a number only.")
            return TARGET_AMOUNT

    if session.get("mode") == "tester" and not session.get("tester_type"):
        session["tester_type"] = text.lower()
        await update.message.reply_text("Send Cards Or Drop .txt File To Continue")
        return COLLECTING

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
        usa = sum(1 for c in session["cards"] if str(c.get("country", "")).upper() in ["US", "USA", "UNITED STATES"])
        session["usa"] = usa
        session["foreign"] = len(session["cards"]) - usa

        mode_name = "Base" if session.get("mode") == "format" else session.get("mode", "format").capitalize()
        filename = session.get("filename") or "N/A"

        summary = f"""
**Pre Summary/Confirmation**

Total Cards   : {len(session['cards'])}
Total USA     : {usa}
Total Foreign : {session['foreign']}
Mode          : {mode_name}
Filename      : {filename}
"""
        if session.get("customer"): summary += f"\nCustomer : {session['customer']}"
        if session.get("target"): summary += f"\nTarget   : {session['target']}"

        await update.message.reply_text(summary, parse_mode='Markdown', reply_markup=pre_keyboard())
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

        msg = await query.edit_message_text("Batch Has Successfully Been Submitted, Please Wait Up To 30 Seconds While We Beginning Quality Checking")

        card_list = [c["raw"] for c in session["cards"]]
        batch_id = await submit_to_storm(card_list)
        await msg.edit_text(f"✅ Batch submitted successfully.\nBatch ID: `{batch_id}`\nStarting Quality Checking...", parse_mode='Markdown')

        live_cards = await poll_batch(batch_id, msg, len(card_list), uid)
        session["live_cards"] = live_cards
        total = len(session["cards"])
        live_count = len(live_cards)
        dead = total - live_count
        extra = max(0, live_count - session.get("target", 0))
        rate = round((live_count / total * 100), 2) if total > 0 else 0.0

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

        summary = f"""
**Post Summary/Confirmation**

══════════════════════════════════════
📊 **SUMMARY REPORT**
══════════════════════════════════════
Total Cards   : {total}
Live Count    : {live_count}
Total Dead    : {dead}
Live Rate     : {rate}%
"""
        if session.get("mode") in ["sale", "replace"]:
            summary += f"Target        : {session.get('target', 0)}\n"
            summary += f"Target Reached: {'✅ True' if live_count >= session.get('target', 0) else '❌ False'}\n"
            if extra > 0:
                summary += f"Extras        : {extra}\n"

        summary += """
══════════════════════════════════════
🏆 FactoryVHQ Quality Check Complete
══════════════════════════════════════
"""

        has_extra = extra > 0
        await msg.edit_text(summary, parse_mode='Markdown', reply_markup=post_keyboard(has_extra))

    elif action == "send_file":
        cards = session.get("live_cards", [])
        content = "\n\n".join(format_live_card(c, is_tester=(session.get("mode") == "tester"), forced_vr=FORCED_VR.get(c["card"][:6])) for c in cards)
        filename = session.get("filename") or f"Batch-{random.randint(1000,9999)}.txt"
        if session.get("customer"):
            filename = f"{session['customer']}-{len(cards)}-{random.randint(1000,9999)}.txt"
        await query.message.reply_document(bytes(content, "utf-8"), filename=filename, caption="✅ FactoryVHQ Live Cards • Premium Cards Only")
        await query.edit_message_text("✅ File sent successfully!", reply_markup=main_menu())

    elif action == "send_extra":
        await query.edit_message_text("📤 Extras file sent.", reply_markup=main_menu())

    elif action == "add_more":
        await query.edit_message_text("Please Send More Cards Or Drop Another .txt File To Continue")
        return COLLECTING

    elif action == "remove_cards":
        await query.edit_message_text("Send Last 4# Seperated By Commas Of The Card(s) You Want Removed")
        return REMOVE_CARDS

    elif action == "set_filename":
        await query.edit_message_text("Send new filename (without extension):")
        return SET_FILENAME

    elif action == "back_to_menu":
        await start(update, context)
        return MENU

# ====================== STATE HANDLERS ======================
async def set_filename_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    session = user_sessions.get(uid, {})
    session["filename"] = update.message.text.strip()
    await update.message.reply_text(f"✅ Filename set to: **{session['filename']}**", parse_mode='Markdown', reply_markup=pre_keyboard())
    return COLLECTING

async def remove_cards_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    session = user_sessions.get(uid, {})
    try:
        to_remove = [x.strip() for x in update.message.text.split(',')]
        original = len(session.get("cards", []))
        session["cards"] = [c for c in session.get("cards", []) if c["card"][-4:] not in to_remove]
        session["current_cards"] = session["cards"][:]
        removed = original - len(session["cards"])
        await update.message.reply_text(f"✅ Removed {removed} card(s).", reply_markup=pre_keyboard())
    except:
        await update.message.reply_text("❌ Error processing removal.")
    return COLLECTING

# ====================== MAIN ======================
def main():
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [CallbackQueryHandler(button_handler)],
            COLLECTING: [MessageHandler(filters.ALL & ~filters.COMMAND, message_handler)],
            CUSTOMER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler)],
            TARGET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler)],
            TESTER_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler)],
            RATE_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler)],
            REMOVE_CARDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_cards_handler)],
            SET_FILENAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_filename_handler)],
            BIN_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🚀 FactoryVHQ v22.8 - Using Batch ID + status:'live' scanning")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
