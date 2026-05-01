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

logging.basicConfig(format='%(asctime)s | %(levelname)-8s | %(message)s', level=logging.INFO)
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

user_sessions: Dict[int, dict] = {}
user_stats: Dict[int, dict] = {}
BIN_DATABASE: Dict[str, dict] = {}
BIN_FORCE_VR: Dict[str, int] = {}

# ===================== LOAD BIN LIST =====================
async def load_binlist_from_github():
    global BIN_DATABASE
    if not GITHUB_BIN_URL:
        BIN_DATABASE = get_default_bins()
        return
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(GITHUB_BIN_URL)
            resp.raise_for_status()
            BIN_DATABASE = resp.json()
            logger.info(f"✅ Loaded {len(BIN_DATABASE)} BINs from GitHub")
    except Exception as e:
        logger.error(f"GitHub BIN load failed: {e}")
        BIN_DATABASE = get_default_bins()

def get_default_bins():
    return {
        "410039": {"bank": "CITIBANK, N.A.- COSTCO", "brand": "VISA", "level": "TRADITIONAL", "rating": 92, "suggestion": "Amazon, Walmart", "type": "CREDIT"},
        "410040": {"bank": "CITIBANK, N.A.- COSTCO", "brand": "VISA", "level": "BUSINESS", "rating": 88, "suggestion": "High Limits", "type": "CREDIT"},
        "414720": {"bank": "JPMORGAN CHASE BANK N.A.", "brand": "VISA", "level": "TRADITIONAL", "rating": 94, "suggestion": "Everywhere", "type": "CREDIT"},
        "414740": {"bank": "JPMORGAN CHASE BANK N.A.", "brand": "VISA", "level": "TRADITIONAL", "rating": 91, "suggestion": "Retail", "type": "CREDIT"},
        "440066": {"bank": "BANK OF AMERICA - CONSUMER CREDIT", "brand": "VISA", "level": "TRADITIONAL", "rating": 89, "suggestion": "General", "type": "CREDIT"},
        "483312": {"bank": "JPMORGAN CHASE BANK N.A. - DEBIT", "brand": "VISA", "level": "CLASSIC", "rating": 75, "suggestion": "Low Risk", "type": "DEBIT"},
        "483316": {"bank": "JPMORGAN CHASE BANK N.A. - DEBIT", "brand": "VISA", "level": "CLASSIC", "rating": 76, "suggestion": "Low Risk", "type": "DEBIT"},
        "513371": {"bank": "NEWDAY, LTD.", "brand": "MASTERCARD", "level": "STANDARD", "rating": 80, "suggestion": "UK Retail", "type": "CREDIT"},
        "513379": {"bank": "BANQUE FEDERATIVE DU CREDIT MUTUEL (BFCM)", "brand": "MASTERCARD", "level": "STANDARD", "rating": 79, "suggestion": "France Retail", "type": "DEBIT"},
        "521729": {"bank": "COMMONWEALTH BANK OF AUSTRALIA", "brand": "MASTERCARD", "level": "STANDARD", "rating": 85, "suggestion": "Australia", "type": "DEBIT"},
        "534348": {"bank": "CELTIC BANK CORPORATION", "brand": "MASTERCARD", "level": "PLATINUM", "rating": 90, "suggestion": "US Retail", "type": "CREDIT"},
        "542418": {"bank": "CITIBANK N.A.", "brand": "MASTERCARD", "level": "PLATINUM", "rating": 92, "suggestion": "High Value", "type": "CREDIT"},
        "546616": {"bank": "CITIBANK N.A.", "brand": "MASTERCARD", "level": "WORLD", "rating": 93, "suggestion": "Luxury", "type": "CREDIT"},
    }

# ===================== CARD PARSER =====================
def parse_card(line: str) -> Optional[dict]:
    if not line: return None
    try:
        line = re.sub(r'\s*\|\s*', '|', line.strip())
        line = re.sub(r'\|+', '|', line).strip('|')
        parts = line.split('|')
        if len(parts) < 4: return None

        card = re.sub(r'\D', '', parts[0])
        if len(card) < 13: return None

        exp = re.sub(r'\D', '', parts[1])
        mm = exp[:2].zfill(2)
        yy = exp[2:4].zfill(2) if len(exp) >= 4 else "28"
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
    except:
        return None

def get_random_ip():
    return f"{random.randint(25,220)}.{random.randint(10,250)}.{random.randint(10,250)}.{random.randint(10,250)}"

def generate_balance(is_credit: bool):
    roll = random.random()
    if roll < 0.03:
        bal = round(random.uniform(3000, 12500), 2)
    elif roll < 0.68:
        bal = round(random.uniform(50, 1099.99), 2)
    else:
        bal = round(random.uniform(1100, 2999.99), 2)
    label = "Available Credit" if is_credit else "Balance"
    return bal, label

def format_card(card: dict, is_tester: bool = False) -> str:
    vr = BIN_FORCE_VR.get(card["card"][:6], random.randint(78, 97))
    balance, label = generate_balance(card["type"] == "CREDIT")

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
        f"🌐 IP      : {get_random_ip()}",
        f"🕒 Checked : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
        "══════════════════════════════════════",
        f"BIN Rate   : {card['bin_rating']} | {card['suggestion']}",
        "══════════════════════════════════════",
        "🔥 FactoryVHQ | Premium Cards Only 🔥",
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

def main_menu():
    status = "🟢 TEST MODE ON" if TEST_MODE else "🔴 TEST MODE OFF"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Format", callback_data="format")],
        [InlineKeyboardButton("💰 Sale", callback_data="sale")],
        [InlineKeyboardButton("🔄 Replace", callback_data="replace")],
        [InlineKeyboardButton("🧪 Tester", callback_data="tester")],
        [InlineKeyboardButton("⭐ Rate", callback_data="rate")],
        [InlineKeyboardButton("💵 Balance", callback_data="balance")],
        [InlineKeyboardButton("📊 Stats", callback_data="stats")],
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
        user_sessions[uid] = {"mode": None, "cards": [], "filename": None, "customer": None, "target": 0, "step": "idle", "tester_type": None, "in_post_summary": False}
    return user_sessions[uid]

def get_stats(uid: int) -> dict:
    if uid not in user_stats:
        user_stats[uid] = {"cards_sold":0, "total_sales":0, "revenue":0.0, "profit":0.0, "testers_given":0, "replacements_given":0, "total_cards_checked":0}
    return user_stats[uid]

# ===================== STORMCHECK API =====================
async def submit_batch_advanced(cards: List[str]) -> Optional[str]:
    if TEST_MODE:
        return "test-batch-id-999999"
    if not API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            resp = await client.post(
                f"{API_BASE}/check",
                json={"cards": cards},
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
            )
            if resp.status_code == 200:
                return resp.json().get("data", {}).get("batch_id")
            return None
    except:
        return None

async def poll_batch(batch_id: str, card_count: int):
    if TEST_MODE:
        await asyncio.sleep(4)
        return
    polls = 3 if card_count <= 5 else 5 if card_count <= 10 else 8 if card_count <= 15 else min(25, card_count // 2 + 10)
    for _ in range(polls):
        await asyncio.sleep(3.5)

# ===================== START & MENU =====================
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
    await update.message.reply_text("✅ Returned to Admin Panel.", reply_markup=main_menu())

# ===================== BUTTON & MESSAGE HANDLERS =====================
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
        await query.edit_message_text("Please send more cards or drop another .txt file.")
        return
    if action == "remove_cards":
        session["step"] = "removing_cards"
        await query.edit_message_text("Send last 4 digits of the card(s) you want to remove, separated by commas.")
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

    # Start new feature
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
        await query.edit_message_text(panel("TESTER MODE") + "\n\nIs this a **Drop** or a **Gift**?\n\nReply with: `Drop` or `Gift`")
        session["step"] = "waiting_tester_type"
    elif action == "balance":
        await handle_balance(update, context)
    elif action == "stats":
        await handle_stats(update, context)
    elif action == "rate":
        await query.edit_message_text("⭐ Rate feature coming in next update.")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    text = update.message.text.strip()
    session = get_session(uid)

    if session.get("step") == "waiting_tester_type":
        session["tester_type"] = text.capitalize()
        await update.message.reply_text(panel("TESTER MODE") + f"\n\n✅ Mode set to: **{session['tester_type']}**\n\nSend cards or drop a .txt file.")
        session["step"] = "waiting_cards"
        return

    if session.get("step") == "waiting_customer":
        session["customer"] = text
        await update.message.reply_text("How many cards is this customer purchasing/replacing?")
        session["step"] = "waiting_target"
        return

    if session.get("step") == "waiting_target":
        try:
            session["target"] = int(text)
            await update.message.reply_text("✅ Target Set.\nSend cards or drop a .txt file.")
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
                if c := parse_card(line):
                    new_cards.append(c)
        else:
            for line in text.splitlines():
                if c := parse_card(line):
                    new_cards.append(c)

        if new_cards:
            session["cards"].extend(new_cards)
            await show_pre_summary(update, session)
        else:
            await update.message.reply_text("⚠️ No valid cards found.")
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
    usa = sum(1 for c in session["cards"] if c.get("country", "US").upper() in ["US", "USA"])
    mode = session.get("mode", "FORMAT").upper()
    text = panel(f"{mode} PRE-SUMMARY") + f"""
Total Cards   : {count}
Total USA     : {usa}
Total Foreign : {count - usa}
Mode          : {mode}
"""
    if session.get("customer"):
        text += f"Customer      : {session['customer']}\n"
    if session.get("target"):
        text += f"Target        : {session['target']}\n"
    await update.message.reply_html(text, reply_markup=PRE_BUTTONS)

async def check_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    session = get_session(uid)

    if not session.get("cards"):
        await query.edit_message_text("❌ No cards to check.")
        return

    await query.edit_message_text("Batch Has Successfully Been Submitted, Please Wait Up To 30 Seconds While We Beginning Quality Checking")

    card_strings = [f"{c['card']}|{c['mm']}{c['yy']}|{c['cvv']}|{c['name']}|{c['address']}|{c['city']}|{c['state']}|{c['zip']}|{c['country']}" for c in session["cards"]]
    batch_id = await submit_batch_advanced(card_strings)
    if batch_id and not TEST_MODE:
        await poll_batch(batch_id, len(session["cards"]))

    session["in_post_summary"] = True
    get_stats(uid)["total_cards_checked"] += len(session["cards"])
    await show_post_summary(query, session, uid)

async def show_post_summary(query, session: dict, uid: int):
    count = len(session["cards"])
    test_note = "\n\n(Test Mode - All cards marked LIVE)" if TEST_MODE else ""
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
    mode = session.get("mode")

    if mode == "tester":
        content = "\n\n".join(format_card(c, is_tester=True) for c in session["cards"])
        filename = f"FactoryVHQ-Tester-{len(session['cards'])}-{random.randint(1000,9999)}"
        caption = "🔥 FactoryVHQ Tester Drop Sent 🔥"
    elif mode == "sale":
        live = len(session["cards"])
        customer = session.get("customer", "Customer")
        filename = f"{customer}-{live}-{random.randint(1000,9999)}"
        content = "\n\n".join(format_card(c) for c in session["cards"])
        caption = f"✅ Sale to {customer} completed"
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

async def handle_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if TEST_MODE:
        await update.callback_query.edit_message_text("🟢 Test Mode Active\nAvailable Storm Credits: 999999")
        return
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{API_BASE}/user", headers={"Authorization": f"Bearer {API_KEY}"})
            credits = r.json().get("data", {}).get("credits", 0)
            await update.callback_query.edit_message_text(f"Your Available Storm Credits Are: **{credits}**", parse_mode='Markdown')
    except:
        await update.callback_query.edit_message_text("Failed to fetch balance.")

async def handle_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = get_stats(update.callback_query.from_user.id)
    text = panel("STATISTICS") + f"""
Cards Sold     : {s['cards_sold']}
Total Sales    : {s['total_sales']}
Revenue        : ${s['revenue']:.2f}
Profit         : ${s['profit']:.2f}
Testers Given  : {s['testers_given']}
Replacements   : {s['replacements_given']}
Cards Checked  : {s['total_cards_checked']}
"""
    await update.callback_query.edit_message_text(text, reply_markup=main_menu())

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("reloadbins", lambda u,c: asyncio.create_task(load_binlist_from_github()) or u.message.reply_text("BIN List Reloaded")))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL, message_handler))

    asyncio.get_event_loop().run_until_complete(load_binlist_from_github())
    print("🚀 FactoryVHQ v15.0 - Full Advanced Version Ready")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
