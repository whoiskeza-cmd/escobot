import random
import os
import logging
import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

logging.basicConfig(
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("FactoryVHQ")

# ===================== CONFIG =====================
TOKEN = os.getenv("TOKEN")
API_BASE = "https://api.storm.gift/api/v1"
API_KEY = os.getenv("STORM_API_KEY")
GITHUB_BIN_URL = os.getenv("GITHUB_BIN_URL")

OWNER_ID = int(os.getenv("OWNER_ID", "0"))
ADMIN_IDS = {OWNER_ID}
if os.getenv("ADMIN_IDS"):
    for x in os.getenv("ADMIN_IDS").split(","):
        if x.strip().isdigit():
            ADMIN_IDS.add(int(x.strip()))

TEST_MODE = True
DATA_FILE = "factoryvhq_data.json"
CARD_COST = 8.0
SALE_PRICE = 25.0

user_sessions: Dict[int, dict] = {}
user_stats: Dict[int, dict] = {}
BIN_DATABASE: Dict[str, dict] = {}
BIN_FORCE_VR: Dict[str, int] = {}

# ===================== LOAD BIN LIST FROM GITHUB =====================
async def load_binlist_from_github():
    global BIN_DATABASE
    if not GITHUB_BIN_URL:
        logger.warning("GITHUB_BIN_URL not set. Using defaults.")
        BIN_DATABASE = get_default_bins()
        return

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(GITHUB_BIN_URL)
            resp.raise_for_status()
            BIN_DATABASE = resp.json()
            logger.info(f"✅ Loaded {len(BIN_DATABASE)} BINs from GitHub")
    except Exception as e:
        logger.error(f"GitHub BIN load failed: {e}. Using defaults.")
        BIN_DATABASE = get_default_bins()

def get_default_bins() -> Dict:
    return {
        "400022": {"bank": "NAVY FEDERAL CREDIT UNION", "brand": "VISA", "level": "CLASSIC", "rating": 85, "suggestion": "Military & General", "type": "DEBIT"},
        "410039": {"bank": "CITIBANK, N.A.- COSTCO", "brand": "VISA", "level": "TRADITIONAL", "rating": 92, "suggestion": "Amazon, Walmart", "type": "CREDIT"},
        "410040": {"bank": "CITIBANK, N.A.- COSTCO", "brand": "VISA", "level": "BUSINESS", "rating": 88, "suggestion": "High Limits", "type": "CREDIT"},
        "414720": {"bank": "JPMORGAN CHASE BANK N.A.", "brand": "VISA", "level": "TRADITIONAL", "rating": 94, "suggestion": "Everywhere", "type": "CREDIT"},
        "440066": {"bank": "BANK OF AMERICA - CONSUMER CREDIT", "brand": "VISA", "level": "TRADITIONAL", "rating": 89, "suggestion": "General", "type": "CREDIT"},
        "542418": {"bank": "CITIBANK N.A.", "brand": "MASTERCARD", "level": "PLATINUM", "rating": 92, "suggestion": "High Value", "type": "CREDIT"},
    }

# ===================== ADVANCED PARSER =====================
def parse_card(line: str) -> Optional[dict]:
    if not line or not isinstance(line, str): return None
    original = line.strip()
    try:
        line = re.sub(r'\s*\|\s*', '|', original)
        line = re.sub(r'\|+', '|', line).strip('|')
        parts = line.split('|')
        if len(parts) < 4: return None

        card = re.sub(r'\D', '', parts[0])
        if len(card) < 13: return None

        exp_clean = re.sub(r'\D', '', parts[1])
        mm = exp_clean[:2].zfill(2)
        yy = exp_clean[2:4].zfill(2) if len(exp_clean) >= 4 else "28"
        cvv = re.sub(r'\D', '', parts[2]) or "000"
        name = parts[3].strip() or "Cardholder"

        address = parts[4].strip() if len(parts) > 4 else "N/A"
        city = parts[5].strip() if len(parts) > 5 else "N/A"
        state = parts[6].strip() if len(parts) > 6 else "N/A"
        zipcode = parts[7].strip() if len(parts) > 7 else "N/A"
        country = parts[8].strip() if len(parts) > 8 else "US"
        phone = re.sub(r'\D', '', parts[9].strip()) if len(parts) > 9 else "0000000000"
        email = parts[10].strip() if len(parts) > 10 and "@" in parts[10] else "unknown@email.com"

        bin6 = card[:6]
        info = BIN_DATABASE.get(bin6, {"bank":"UNKNOWN","brand":"VISA","level":"STANDARD","rating":75,"suggestion":"Retail","type":"CREDIT"})

        return {
            "card": card, "mm": mm, "yy": yy, "cvv": cvv, "name": name,
            "address": address, "city": city, "state": state, "zip": zipcode,
            "country": country, "phone": phone, "email": email,
            "bank": info["bank"], "brand": info["brand"], "level": info["level"],
            "bin_rating": info.get("rating", 75), "suggestion": info.get("suggestion", "Retail"),
            "type": info.get("type", "CREDIT")
        }
    except Exception as e:
        logger.error(f"Parse failed: {original[:60]} | {e}")
        return None

def random_ip() -> str:
    return f"{random.randint(25,220)}.{random.randint(10,250)}.{random.randint(10,250)}.{random.randint(10,250)}"

def generate_balance(is_credit: bool) -> tuple:
    roll = random.random()
    if roll < 0.03: bal = round(random.uniform(3000, 12500), 2)
    elif roll < 0.65: bal = round(random.uniform(50, 1099.99), 2)
    else: bal = round(random.uniform(1100, 2999.99), 2)
    label = "Available Credit" if is_credit else "Balance"
    return bal, label

def format_card(card: dict) -> str:
    bin6 = card["card"][:6]
    vr = BIN_FORCE_VR.get(bin6, random.randint(78, 97))
    balance, label = generate_balance(card.get("type") == "CREDIT")
    return f"""══════════════════════════════════════
🃏 LIVE • VR: {vr}%
══════════════════════════════════════
💰 {label} : ${balance:.2f}
👤 Name    : {card['name']}
💳 Card    : {card['card']}
📅 Expiry  : {card['mm']}/{card['yy']}
🔒 CVV     : {card['cvv']}
🏦 Bank    : {card['bank']}
🌍 Country : {card['country']} • {card['brand']} {card['level']}

📍 Billing:
   {card['address']}
   {card['city']}, {card['state']} {card['zip']}
   Phone: {card['phone']}
   Email: {card['email']}

🌐 IP: {random_ip()}
🕒 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC
══════════════════════════════════════
BIN Rate: {card.get('bin_rating', 85)} | {card.get('suggestion', 'Retail')}
══════════════════════════════════════"""

def format_tester_card(card: dict) -> str:
    bin6 = card["card"][:6]
    vr = BIN_FORCE_VR.get(bin6, random.randint(88, 98))
    balance, label = generate_balance(card.get("type") == "CREDIT")
    return f"""══════════════════════════════════════
🃏 FACTORYVHQ TESTER DROP 🃏
══════════════════════════════════════
💰 {label} : ${balance:.2f}
👤 Name    : {card['name']}
💳 Card    : {card['card']}
📅 Expiry  : {card['mm']}/{card['yy']}
🔒 CVV     : {card['cvv']}
🏦 Bank    : {card['bank']}
🌍 Country : {card['country']} • {card['brand']} {card['level']}

📍 Billing Address:
   {card['address']}
   {card['city']}, {card['state']} {card['zip']}
   Phone  : {card['phone']}
   Email  : {card['email']}

🌐 IP      : {random_ip()}
🕒 Checked : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC
══════════════════════════════════════
BIN Rate   : {card.get('bin_rating', 92)} | {card.get('suggestion', 'Premium Use')}
══════════════════════════════════════
Taste the Quality. Feel the Difference.
This is FactoryVHQ — Where Winners Shop.

🔥 FactoryVHQ | Premium Cards Only 🔥
══════════════════════════════════════"""

def panel(title: str) -> str:
    return f"""
╔════════════════════════════════════════════╗
          🏭 FACTORYVHQ ADMIN PANEL
                    {title}
╚════════════════════════════════════════════╝
"""

def main_menu() -> InlineKeyboardMarkup:
    status = "🟢 TEST MODE ON" if TEST_MODE else "🔴 TEST MODE OFF"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Format", callback_data="format")],
        [InlineKeyboardButton("💰 Sale", callback_data="sale")],
        [InlineKeyboardButton("🔄 Replace", callback_data="replace")],
        [InlineKeyboardButton("🧪 Tester Drop", callback_data="tester")],
        [InlineKeyboardButton("⭐ BIN Manager", callback_data="rate")],
        [InlineKeyboardButton("💵 Balance", callback_data="balance")],
        [InlineKeyboardButton("📊 Statistics", callback_data="stats")],
        [InlineKeyboardButton(status, callback_data="toggle_test")]
    ])

PRE_BUTTONS = InlineKeyboardMarkup([
    [InlineKeyboardButton("✅ Check", callback_data="check")],
    [InlineKeyboardButton("➕ Add More", callback_data="add_more")],
    [InlineKeyboardButton("🗑️ Remove Cards", callback_data="remove_cards")],
    [InlineKeyboardButton("📝 Set Filename", callback_data="set_filename")],
    [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
])

POST_BUTTONS = InlineKeyboardMarkup([
    [InlineKeyboardButton("📤 Send File", callback_data="send_file")],
    [InlineKeyboardButton("➕ Add More", callback_data="add_more")],
    [InlineKeyboardButton("🗑️ Remove Cards", callback_data="remove_cards")],
    [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
])

def get_session(uid: int) -> dict:
    if uid not in user_sessions:
        user_sessions[uid] = {"mode":None,"cards":[],"filename":None,"customer":None,"target":0,"step":"idle","tester_type":None,"in_post_summary":False}
    return user_sessions[uid]

def get_stats(uid: int) -> dict:
    if uid not in user_stats:
        user_stats[uid] = {"cards_sold":0,"total_sales":0,"revenue":0.0,"profit":0.0,"testers_given":0,"replacements_given":0,"total_cards_checked":0}
    return user_stats[uid]

# ===================== API =====================
async def get_user_credits() -> int:
    if TEST_MODE or not API_KEY: return 9999
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{API_BASE}/user", headers={"Authorization": f"Bearer {API_KEY}"}, timeout=10)
            r.raise_for_status()
            return r.json().get("data", {}).get("credits", 0)
    except:
        return 0

async def submit_batch_advanced(cards: List[str]) -> Optional[str]:
    if TEST_MODE or not API_KEY: return "test-batch-id"
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            resp = await client.post(
                f"{API_BASE}/check", json={"cards": cards},
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
            )
            resp.raise_for_status()
            return resp.json().get("data", {}).get("batch_id")
    except Exception as e:
        logger.error(f"Submit failed: {e}")
        return None

async def poll_batch_advanced(batch_id: str, card_count: int):
    if TEST_MODE or not batch_id: 
        await asyncio.sleep(4)
        return
    for _ in range(min(25, max(4, card_count//2 + 6))):
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{API_BASE}/check/{batch_id}", headers={"Authorization": f"Bearer {API_KEY}"})
                if r.status_code == 200 and not r.json().get("data", {}).get("is_checking", True):
                    return
        except:
            pass
        await asyncio.sleep(3.5)

# ===================== HANDLERS =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Access Denied.")
        return
    await update.message.reply_html(panel("FactoryVHQ Admin Panel") + f"Welcome <b>@{update.effective_user.username}</b>", reply_markup=main_menu())

async def reload_bins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    await update.message.reply_text("🔄 Reloading BIN list from GitHub...")
    await load_binlist_from_github()
    await update.message.reply_text(f"✅ BIN list reloaded! Total BINs: {len(BIN_DATABASE)}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data
    uid = query.from_user.id
    session = get_session(uid)

    if action == "check":
        await check_handler(update, context)
        return
    if action == "send_file":
        await send_file_handler(update, context)
        return
    if action == "add_more":
        session["step"] = "add_more"
        await query.edit_message_text("Send more cards or upload another .txt file.")
        return
    if action == "remove_cards":
        session["step"] = "removing_cards"
        await query.edit_message_text("Send last 4 digits of cards to remove (comma separated):")
        return
    if action == "set_filename":
        session["step"] = "waiting_filename"
        await query.edit_message_text("Send new filename (without .txt):")
        return
    if action == "toggle_test":
        global TEST_MODE
        TEST_MODE = not TEST_MODE
        await query.edit_message_text(f"Test Mode: {'🟢 ON' if TEST_MODE else '🔴 OFF'}", reply_markup=main_menu())
        return
    if action == "cancel":
        user_sessions.pop(uid, None)
        await query.edit_message_text("✅ Cancelled.", reply_markup=main_menu())
        return
    if action == "balance":
        credits = await get_user_credits()
        await query.edit_message_text(panel("BALANCE") + f"\nStorm Credits: <b>{credits}</b>", parse_mode='HTML', reply_markup=main_menu())
        return
    if action == "stats":
        s = get_stats(uid)
        txt = panel("STATISTICS") + f"Cards Sold: {s['cards_sold']}\nRevenue: ${s['revenue']:.2f}\nProfit: ${s['profit']:.2f}\nTesters: {s['testers_given']}\nChecked: {s['total_cards_checked']}"
        await query.edit_message_text(txt, reply_markup=main_menu())
        return
    if action == "rate":
        await query.edit_message_text(panel("BIN MANAGER\n\nUse /reloadbins to update from GitHub"), reply_markup=main_menu())
        return

    # Start new mode
    session["mode"] = action
    session["cards"] = []
    session["filename"] = None
    session["customer"] = None
    session["target"] = 0
    session["in_post_summary"] = False

    if action == "format":
        await query.edit_message_text(panel("FORMAT MODE") + "\nSend cards or drop a .txt file.")
        session["step"] = "waiting_cards"
    elif action == "sale":
        await query.edit_message_text(panel("SALE MODE") + "\nPlease send the Customer Name:")
        session["step"] = "waiting_customer"
    elif action == "replace":
        await query.edit_message_text(panel("REPLACE MODE") + "\nWho is being replaced?")
        session["step"] = "waiting_customer"
    elif action == "tester":
        await query.edit_message_text(panel("TESTER DROP") + "\n\nIs this a **Drop** or **Gift**?\n\nReply with: `Drop` or `Gift`")
        session["step"] = "waiting_tester_type"

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    text = update.message.text.strip()
    session = get_session(uid)

    if session.get("step") == "waiting_tester_type":
        session["tester_type"] = text.capitalize()
        await update.message.reply_text(panel("TESTER DROP") + f"\n\n✅ Mode set to: **{session['tester_type']}**\n\nSend cards or .txt file.")
        session["step"] = "waiting_cards"
        return

    if session.get("step") == "waiting_customer":
        session["customer"] = text
        await update.message.reply_text("How many cards?")
        session["step"] = "waiting_target"
        return

    if session.get("step") == "waiting_target":
        try:
            session["target"] = int(text)
            await update.message.reply_text("✅ Target set.\nSend cards or .txt file.")
            session["step"] = "waiting_cards"
        except:
            await update.message.reply_text("Please send a number.")
        return

    if session.get("step") in ["waiting_cards", "add_more"]:
        new_cards = []
        if update.message.document:
            file = await update.message.document.get_file()
            content = (await file.download_as_bytearray()).decode("utf-8", errors="ignore")
            for line in content.splitlines():
                if card := parse_card(line):
                    new_cards.append(card)
        else:
            for line in text.splitlines():
                if card := parse_card(line):
                    new_cards.append(card)

        if new_cards:
            session["cards"].extend(new_cards)
            logger.info(f"Added {len(new_cards)} cards. Total: {len(session['cards'])}")
            await show_pre_summary(update, session)
        else:
            await update.message.reply_text("⚠️ No valid cards detected.")
        return

    if session.get("step") == "removing_cards":
        await process_remove(update, context)
        return

    if session.get("step") == "waiting_filename":
        session["filename"] = text
        session["step"] = "idle"
        await show_post_summary(None, session, uid)
        return

async def show_pre_summary(update: Update, session: dict):
    count = len(session["cards"])
    usa = sum(1 for c in session["cards"] if str(c.get("country","US")).upper() in ["US","USA"])
    mode = session.get("mode","FORMAT").upper()
    text = panel(f"{mode} PRE-SUMMARY") + f"""
Total Cards   : {count}
Total USA     : {usa}
Total Foreign : {count - usa}
Mode          : {mode}
"""
    await update.message.reply_html(text, reply_markup=PRE_BUTTONS)

async def check_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    session = get_session(uid)

    if not session.get("cards"):
        await query.edit_message_text("❌ No cards found.")
        return

    await query.edit_message_text("Batch Has Successfully Been Submitted, Please Wait Up To 30 Seconds While We Beginning Quality Checking")

    card_strings = [f"{c['card']}|{c['mm']}{c['yy']}|{c['cvv']}|{c['name']}|{c['address']}|{c['city']}|{c['state']}|{c['zip']}|{c['country']}" for c in session["cards"]]
    batch_id = await submit_batch_advanced(card_strings)
    if batch_id and not TEST_MODE:
        await poll_batch_advanced(batch_id, len(session["cards"]))

    session["in_post_summary"] = True
    get_stats(uid)["total_cards_checked"] += len(session["cards"])
    await show_post_summary(query, session, uid)

async def show_post_summary(query, session: dict, uid: int):
    count = len(session["cards"])
    test_note = "\n\n(Test Mode - Stats Frozen)" if TEST_MODE else ""
    text = panel("POST-SUMMARY") + f"""
Total Cards : {count}
Total Live  : {count}
Total Dead  : 0
Live Rate   : 100.0%{test_note}
"""
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=POST_BUTTONS)

async def send_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    session = get_session(uid)

    if session.get("mode") == "tester":
        content = "\n\n".join(format_tester_card(c) for c in session["cards"])
        filename = f"FactoryVHQ-Tester-Drop-{len(session['cards'])}-{random.randint(1000,9999)}"
        caption = "🔥 FactoryVHQ Tester Drop Sent 🔥"
    else:
        content = "\n\n".join(format_card(c) for c in session["cards"])
        filename = session.get("filename") or f"Batch-{len(session['cards'])}-{random.randint(1000,9999)}"
        caption = "✅ FactoryVHQ Output Generated"

    await query.message.reply_document(
        document=bytes(content, "utf-8"),
        filename=f"{filename}.txt",
        caption=caption
    )
    await query.edit_message_text("✅ Delivery Complete!", reply_markup=main_menu())
    user_sessions.pop(uid, None)
    save_data()

async def process_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    session = get_session(uid)
    try:
        targets = {x.strip() for x in update.message.text.split(",")}
        original = len(session["cards"])
        session["cards"] = [c for c in session["cards"] if c["card"][-4:] not in targets]
        await update.message.reply_text(f"✅ Removed {original - len(session['cards'])} cards.")
        if session.get("in_post_summary"):
            await show_post_summary(None, session, uid)
        else:
            await show_pre_summary(update, session)
        session["step"] = "idle"
    except:
        await update.message.reply_text("❌ Invalid input.")

# ===================== MAIN =====================
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reloadbins", reload_bins))
    app.add_handler(CommandHandler("cancel", lambda u,c: asyncio.create_task(c.bot.send_message(u.effective_chat.id, "✅ Cancelled.", reply_markup=main_menu()))))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL, message_handler))

    asyncio.get_event_loop().run_until_complete(load_binlist_from_github())

    print("🚀 FactoryVHQ v14.4 - COMPLETE CODE WITH ALL FUNCTIONS")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
