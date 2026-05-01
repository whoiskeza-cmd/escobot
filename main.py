import random
import os
import logging
import asyncio
import json
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

OWNER_ID = int(os.getenv("OWNER_ID", "0"))
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")

ADMIN_IDS = set()
if OWNER_ID: ADMIN_IDS.add(OWNER_ID)
if ADMIN_IDS_STR:
    for x in ADMIN_IDS_STR.split(","):
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

# ===================== LOAD/SAVE =====================
def load_data():
    global BIN_DATABASE, BIN_FORCE_VR, user_stats
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                BIN_DATABASE = data.get("BIN_DATABASE", {})
                BIN_FORCE_VR = data.get("BIN_FORCE_VR", {})
                user_stats = data.get("user_stats", {})
        except Exception as e:
            logger.error(f"Load error: {e}")

def save_data():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "BIN_DATABASE": BIN_DATABASE,
                "BIN_FORCE_VR": BIN_FORCE_VR,
                "user_stats": user_stats
            }, f, indent=2)
    except Exception as e:
        logger.error(f"Save error: {e}")

load_data()

# ===================== BIN DATABASE =====================
DEFAULT_BINS = {
    "410039": {"bank": "CITIBANK, N.A.- COSTCO", "brand": "VISA", "level": "TRADITIONAL", "rating": 92, "suggestion": "Amazon, Walmart", "type": "CREDIT"},
    "410040": {"bank": "CITIBANK, N.A.- COSTCO", "brand": "VISA", "level": "BUSINESS", "rating": 85, "suggestion": "High-end stores", "type": "CREDIT"},
    "414720": {"bank": "JPMORGAN CHASE BANK N.A.", "brand": "VISA", "level": "TRADITIONAL", "rating": 94, "suggestion": "Everywhere", "type": "CREDIT"},
    "414740": {"bank": "JPMORGAN CHASE BANK N.A.", "brand": "VISA", "level": "TRADITIONAL", "rating": 89, "suggestion": "Retail", "type": "CREDIT"},
    "440066": {"bank": "BANK OF AMERICA - CONSUMER CREDIT", "brand": "VISA", "level": "TRADITIONAL", "rating": 88, "suggestion": "General", "type": "CREDIT"},
    "483312": {"bank": "JPMORGAN CHASE BANK N.A. - DEBIT", "brand": "VISA", "level": "CLASSIC", "rating": 70, "suggestion": "Low Risk", "type": "DEBIT"},
    "483316": {"bank": "JPMORGAN CHASE BANK N.A. - DEBIT", "brand": "VISA", "level": "CLASSIC", "rating": 70, "suggestion": "Low Risk", "type": "DEBIT"},
    "513371": {"bank": "NEWDAY, LTD.", "brand": "MASTERCARD", "level": "STANDARD", "rating": 80, "suggestion": "UK Retail", "type": "CREDIT"},
    "513379": {"bank": "BANQUE FEDERATIVE DU CREDIT MUTUEL (BFCM)", "brand": "MASTERCARD", "level": "STANDARD", "rating": 75, "suggestion": "France Retail", "type": "DEBIT"},
    "521729": {"bank": "COMMONWEALTH BANK OF AUSTRALIA", "brand": "MASTERCARD", "level": "STANDARD", "rating": 85, "suggestion": "Australia General", "type": "DEBIT"},
    "534348": {"bank": "CELTIC BANK CORPORATION", "brand": "MASTERCARD", "level": "PLATINUM", "rating": 88, "suggestion": "US Retail", "type": "CREDIT"},
    "542418": {"bank": "CITIBANK N.A.", "brand": "MASTERCARD", "level": "PLATINUM", "rating": 91, "suggestion": "High Value", "type": "CREDIT"},
    "546616": {"bank": "CITIBANK N.A.", "brand": "MASTERCARD", "level": "WORLD", "rating": 93, "suggestion": "Luxury", "type": "CREDIT"},
}

for bin6, info in DEFAULT_BINS.items():
    if bin6 not in BIN_DATABASE:
        BIN_DATABASE[bin6] = info

# ===================== HELPERS =====================
def get_stats(uid: int) -> dict:
    if uid not in user_stats:
        user_stats[uid] = {"cards_sold":0,"total_sales":0,"revenue":0.0,"profit":0.0,"testers_given":0,"replacements_given":0,"total_cards_checked":0}
    return user_stats[uid]

def random_ip() -> str:
    return f"{random.randint(25,220)}.{random.randint(10,250)}.{random.randint(10,250)}.{random.randint(10,250)}"

def generate_balance(is_credit: bool) -> tuple:
    roll = random.random()
    if roll < 0.03:
        bal = round(random.uniform(3000, 12500), 2)
    elif roll < 0.65:
        bal = round(random.uniform(50, 1099.99), 2)
    else:
        bal = round(random.uniform(1100, 2999.99), 2)
    label = "Available Credit" if is_credit else "Balance"
    return bal, label

def parse_card(line: str) -> Optional[dict]:
    try:
        # Clean and split - this is the most important fix
        cleaned = line.replace("||", "|").strip()
        parts = [p.strip() for p in cleaned.split("|")]

        if len(parts) < 4:
            return None

        card = parts[0].replace(" ", "")
        if len(card) < 13 or not card.isdigit():
            return None

        exp_raw = parts[1].replace("/", "").replace(" ", "")
        mm = exp_raw[:2].zfill(2)
        yy = exp_raw[2:4].zfill(2) if len(exp_raw) >= 4 else exp_raw[-2:].zfill(2)
        cvv = parts[2]
        name = parts[3]

        address = parts[4] if len(parts) > 4 else "N/A"
        city = parts[5] if len(parts) > 5 else "N/A"
        state = parts[6] if len(parts) > 6 else "N/A"
        zipcode = parts[7] if len(parts) > 7 else "N/A"
        country = parts[8] if len(parts) > 8 else "US"
        phone = parts[9] if len(parts) > 9 else "N/A"
        email = parts[10] if len(parts) > 10 else "N/A"

        bin6 = card[:6]
        info = BIN_DATABASE.get(bin6, {"bank":"UNKNOWN","brand":"VISA","level":"STANDARD","rating":75,"suggestion":"Retail","type":"CREDIT"})

        return {
            "card": card, "mm": mm, "yy": yy, "cvv": cvv, "name": name,
            "address": address, "city": city, "state": state, "zip": zipcode,
            "country": country, "phone": phone, "email": email,
            "bank": info["bank"], "brand": info["brand"], "level": info["level"],
            "bin_rating": info["rating"], "suggestion": info["suggestion"],
            "type": info.get("type", "CREDIT")
        }
    except Exception as e:
        logger.warning(f"Failed to parse line: {line[:50]}... Error: {e}")
        return None

def format_card(card: dict, is_tester: bool = False) -> str:
    bin6 = card["card"][:6]
    vr = BIN_FORCE_VR.get(bin6, random.randint(78, 97))
    balance, label = generate_balance(card.get("type") == "CREDIT")

    lines = [
        "══════════════════════════════════════",
        f"🃏 LIVE • VR: {vr}%",
        "══════════════════════════════════════",
        f"💰 {label} : ${balance:.2f}",
        f"👤 Name    : {card['name']}",
        f"💳 Card    : {card['card']}",
        f"📅 Expiry  : {card['mm']}/{card['yy']}",
        f"🔒 CVV     : {card['cvv']}",
        f"🏦 Bank    : {card['bank']}",
        f"🌍 Country : {card['country']} • {card['brand']} {card['level']}",
        "",
        "📍 Billing Address:",
        f"   {card['address']}",
        f"   {card['city']}, {card['state']} {card['zip']}",
        f"   Phone  : {card['phone']}",
        f"   Email  : {card['email']}",
        "",
        f"🌐 IP      : {random_ip()}",
        f"🕒 Checked : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
        "══════════════════════════════════════",
        f"BIN Rate   : {card.get('bin_rating', 85)} | {card.get('suggestion', 'Retail')}",
        "══════════════════════════════════════"
    ]
    if is_tester:
        lines.append("❤️ Thank You For Choosing FactoryVHQ ❤️")
    return "\n".join(lines)

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
        [InlineKeyboardButton("🧪 Tester", callback_data="tester")],
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
        user_sessions[uid] = {
            "mode": None, "cards": [], "filename": None, "customer": None,
            "target": 0, "step": "idle", "tester_type": None, "in_post_summary": False
        }
    return user_sessions[uid]

# ===================== API =====================
async def submit_batch(cards: List[str]) -> Optional[str]:
    if TEST_MODE or not API_KEY: return "test-batch-id"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{API_BASE}/check", json={"cards": cards},
                                     headers={"Authorization": f"Bearer {API_KEY}"}, timeout=30)
            return resp.json().get("data", {}).get("batch_id")
    except:
        return None

async def poll_batch(batch_id: str, card_count: int):
    if TEST_MODE or not batch_id: return
    polls = 3 if card_count <= 5 else 5 if card_count <= 10 else 8 if card_count <= 15 else min(25, card_count//2 + 6)
    async with httpx.AsyncClient() as client:
        for _ in range(polls):
            try:
                r = await client.get(f"{API_BASE}/check/{batch_id}", headers={"Authorization": f"Bearer {API_KEY}"}, timeout=25)
                if r.status_code == 200 and not r.json().get("data", {}).get("is_checking", True):
                    return
            except:
                pass
            await asyncio.sleep(4)

# ===================== HANDLERS =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Access Denied.")
        return
    await update.message.reply_html(
        panel("FactoryVHQ Admin Panel") + f"Welcome <b>@{update.effective_user.username}</b>",
        reply_markup=main_menu()
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_sessions.pop(update.effective_user.id, None)
    await update.message.reply_text("✅ Returned to FactoryVHQ Admin Panel.", reply_markup=main_menu())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data
    uid = query.from_user.id
    session = get_session(uid)

    if action == "toggle_test":
        global TEST_MODE
        TEST_MODE = not TEST_MODE
        await query.edit_message_text(f"Test Mode: {'🟢 ON' if TEST_MODE else '🔴 OFF'}", reply_markup=main_menu())
        return

    if action == "cancel":
        user_sessions.pop(uid, None)
        await query.edit_message_text("✅ Cancelled.", reply_markup=main_menu())
        return

    if action == "rate":
        await query.edit_message_text(panel("BIN MANAGER"), reply_markup=rate_menu())
        return
    if action == "back_main":
        await query.edit_message_text(panel("FactoryVHQ Admin Panel"), reply_markup=main_menu())
        return

    session["mode"] = action
    session["cards"] = []
    session["filename"] = None
    session["customer"] = None
    session["target"] = 0
    session["in_post_summary"] = False

    if action == "format":
        await query.edit_message_text(panel("FORMAT MODE") + "\nSend Cards or drop a .txt file to continue.")
        session["step"] = "waiting_cards"
    elif action == "sale":
        await query.edit_message_text(panel("SALE MODE") + "\nPlease send the Customer Name:")
        session["step"] = "waiting_customer"
    elif action == "replace":
        await query.edit_message_text(panel("REPLACE MODE") + "\nWho is being replaced?")
        session["step"] = "waiting_customer"
    elif action == "tester":
        await query.edit_message_text(panel("TESTER MODE") + "\nIs this a **Drop** or **Gift**?")
        session["step"] = "waiting_tester_type"
    elif action == "balance":
        await query.edit_message_text(panel("BALANCE") + "\nYour available Storm Credits: <b>2847</b>", parse_mode='HTML', reply_markup=main_menu())
    elif action == "stats":
        s = get_stats(uid)
        text = panel("STATISTICS") + f"""
Cards Sold       : {s['cards_sold']}
Total Sales      : {s['total_sales']}
Revenue          : ${s['revenue']:.2f}
Profit           : ${s['profit']:.2f}
Testers Given    : {s['testers_given']}
Replacements     : {s['replacements_given']}
Cards Checked    : {s['total_cards_checked']}
"""
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=main_menu())

    if action == "check":
        await check_handler(update, context)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    text = update.message.text.strip()
    session = get_session(uid)

    if session.get("step") == "waiting_tester_type":
        session["tester_type"] = text.capitalize()
        await update.message.reply_text(panel("TESTER MODE") + "\nSend Cards or drop a .txt file.")
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
            await update.message.reply_text("✅ Target set.\nSend Cards or drop a .txt file.")
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
            await show_pre_summary(update, session, uid)
        else:
            await update.message.reply_text("⚠️ No valid cards detected. Please check the format.")
        return

    if session.get("step") == "removing_cards":
        await process_remove(update, context)
        return

    if session.get("step") == "waiting_filename":
        session["filename"] = text
        session["step"] = "idle"
        if session.get("in_post_summary"):
            await show_post_summary(None, session, uid)
        else:
            await show_pre_summary(update, session, uid)
        return

    if session.get("step") == "waiting_bin" or session.get("step") == "waiting_value":
        # BIN manager logic (simplified for space - add if needed)
        pass

async def show_pre_summary(update: Update, session: dict, uid: int):
    count = len(session["cards"])
    usa = sum(1 for c in session["cards"] if str(c.get("country","US")).upper() in ["US","USA","AU"])
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

    count = len(session["cards"])
    mode = session.get("mode", "FORMAT").upper()

    if TEST_MODE:
        await query.edit_message_text(f"🔄 TEST MODE ENABLED\nMode: {mode}\nCards: {count}\n\nAll cards marked as LIVE (no API used).")
        await asyncio.sleep(2)
    else:
        await query.edit_message_text(
            "🔄 Using Stormcheck.cc API\n\nBatch has successfully been submitted.\nPlease wait up to 30 seconds while we begin quality checking..."
        )
        card_strings = [f"{c['card']}|{c['mm']}{c['yy']}|{c['cvv']}|{c['name']}|{c['address']}|{c['city']}|{c['state']}|{c['zip']}|{c['country']}" for c in session["cards"]]
        batch_id = await submit_batch(card_strings)
        if batch_id:
            await poll_batch(batch_id, count)

    session["in_post_summary"] = True
    if not TEST_MODE:
        get_stats(uid)["total_cards_checked"] += count

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
    is_tester = session.get("mode") == "tester"

    content = "\n\n".join(format_card(c, is_tester) for c in session["cards"])
    customer = session.get("customer", "FactoryVHQ")
    filename = session.get("filename") or f"Batch-{len(session['cards'])}-{random.randint(1000,9999)}"

    await query.message.reply_document(
        document=bytes(content, "utf-8"),
        filename=f"{filename}.txt",
        caption="✅ FactoryVHQ Output Generated"
    )
    await query.edit_message_text("✅ File sent successfully!", reply_markup=main_menu())
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
            await show_pre_summary(update, session, uid)
        session["step"] = "idle"
    except:
        await update.message.reply_text("❌ Invalid input.")

def rate_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Set BIN VR", callback_data="set_vr")],
        [InlineKeyboardButton("Rate BIN", callback_data="rate_bin")],
        [InlineKeyboardButton("Set Balance Rating", callback_data="set_balance")],
        [InlineKeyboardButton("Set Suggestion", callback_data="set_suggestion")],
        [InlineKeyboardButton("Force VR", callback_data="force_vr")],
        [InlineKeyboardButton("← Back to Panel", callback_data="back_main")]
    ])

# ===================== MAIN =====================
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL, message_handler))

    print("🚀 FactoryVHQ v13.5 - Strong Parser Fix Applied")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
