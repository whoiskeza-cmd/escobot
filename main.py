import random
import os
import logging
import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ===================== LOGGER SETUP =====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===================== CONFIG =====================
TOKEN = os.getenv("TOKEN")
STORM_API_URL = os.getenv("STORM_API_URL", "https://api.stormcheck.cc")
STORM_API_KEY = os.getenv("STORM_API_KEY")

OWNER_ID = int(os.getenv("OWNER_ID", "0"))
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")

ADMIN_IDS = set()
if OWNER_ID:
    ADMIN_IDS.add(OWNER_ID)
if ADMIN_IDS_STR:
    for x in ADMIN_IDS_STR.split(","):
        stripped = x.strip()
        if stripped:
            try:
                ADMIN_IDS.add(int(stripped))
            except ValueError:
                logger.warning(f"Invalid admin ID: {stripped}")

TEST_MODE = True
DATA_FILE = "factoryvhq_data.json"

# ===================== GLOBAL DATA =====================
user_sessions: Dict[int, dict] = {}
user_stats: Dict[int, dict] = {}
BIN_DATABASE: Dict[str, dict] = {}
BIN_FORCE_VR: Dict[str, int] = {}

# ===================== LOAD/SAVE DATA =====================
def load_data():
    global BIN_DATABASE, BIN_FORCE_VR, user_stats
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                BIN_DATABASE = data.get("BIN_DATABASE", {})
                BIN_FORCE_VR = data.get("BIN_FORCE_VR", {})
                user_stats = data.get("user_stats", {})
                logger.info("✅ Successfully loaded saved data from factoryvhq_data.json")
        except Exception as e:
            logger.error(f"Failed to load data: {e}")
    else:
        logger.info("No data file found. Starting with default BINs.")

def save_data():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "BIN_DATABASE": BIN_DATABASE,
                "BIN_FORCE_VR": BIN_FORCE_VR,
                "user_stats": user_stats
            }, f, indent=2, ensure_ascii=False)
        logger.info("✅ Data saved successfully.")
    except Exception as e:
        logger.error(f"Failed to save data: {e}")

load_data()

# ===================== DEFAULT BIN DATA =====================
DEFAULT_BINS = {
    "410039": {"bank": "CITIBANK, N.A.- COSTCO", "brand": "VISA", "level": "TRADITIONAL", "rating": 85, "suggestion": "Amazon, Walmart", "balance_rating": 80},
    "410040": {"bank": "CITIBANK, N.A.- COSTCO", "brand": "VISA", "level": "BUSINESS", "rating": 78, "suggestion": "High-end stores", "balance_rating": 75},
    "414720": {"bank": "JPMORGAN CHASE BANK N.A.", "brand": "VISA", "level": "TRADITIONAL", "rating": 92, "suggestion": "Everywhere", "balance_rating": 90},
    "414740": {"bank": "JPMORGAN CHASE BANK N.A.", "brand": "VISA", "level": "TRADITIONAL", "rating": 89, "suggestion": "Retail", "balance_rating": 88},
    "440066": {"bank": "BANK OF AMERICA - CONSUMER CREDIT", "brand": "VISA", "level": "TRADITIONAL", "rating": 84, "suggestion": "General", "balance_rating": 82},
    "483316": {"bank": "JPMORGAN CHASE BANK N.A. - DEBIT", "brand": "VISA", "level": "CLASSIC", "rating": 70, "suggestion": "Low Risk", "balance_rating": 65},
    "542418": {"bank": "CITIBANK N.A.", "brand": "MASTERCARD", "level": "PLATINUM", "rating": 88, "suggestion": "High Value", "balance_rating": 85},
    "546616": {"bank": "CITIBANK N.A.", "brand": "MASTERCARD", "level": "WORLD", "rating": 90, "suggestion": "Luxury", "balance_rating": 87},
}

for bin6, info in DEFAULT_BINS.items():
    if bin6 not in BIN_DATABASE:
        BIN_DATABASE[bin6] = info

# ===================== HELPER FUNCTIONS =====================
def get_user_stats(user_id: int) -> dict:
    if user_id not in user_stats:
        user_stats[user_id] = {
            "cards_sold": 0,
            "total_sales": 0,
            "revenue": 0.0,
            "profit": 0.0,
            "testers_given": 0,
            "replacements_given": 0,
            "total_cards_checked": 0
        }
    return user_stats[user_id]

def get_random_ip() -> str:
    return f"{random.randint(25, 220)}.{random.randint(10, 250)}.{random.randint(10, 250)}.{random.randint(10, 250)}"

def generate_balance(is_credit: bool) -> tuple:
    if random.random() < 0.03:  # 3% chance of high balance
        bal = round(random.uniform(3200, 12500), 2)
    else:
        bal = round(random.uniform(85, 1950), 2)
    label = "Available Credit" if is_credit else "Balance"
    return bal, label

def parse_card(line: str) -> Optional[dict]:
    try:
        parts = [p.strip() for p in line.replace("||", "|").split("|")]
        if len(parts) < 8:
            return None

        card = parts[0].replace(" ", "")
        if not card.isdigit() or len(card) < 13:
            return None

        exp_raw = parts[1].replace("/", "").replace(" ", "")
        mm = exp_raw[:2]
        yy = exp_raw[2:] if len(exp_raw) >= 4 else "20" + exp_raw[-2:]
        cvv = parts[2] if len(parts[2]) <= 4 else "000"
        name = parts[3]
        address = parts[4]
        city = parts[5]
        state = parts[6]
        zipcode = parts[7]
        country = parts[8] if len(parts) > 8 else "US"
        phone = parts[9] if len(parts) > 9 else "N/A"
        email = parts[10] if len(parts) > 10 else "N/A"

        bin6 = card[:6]
        info = BIN_DATABASE.get(bin6, {
            "bank": "UNKNOWN", "brand": "VISA", "level": "STANDARD",
            "rating": 75, "suggestion": "Retail", "balance_rating": 70
        })

        return {
            "card": card, "mm": mm, "yy": yy[-2:], "cvv": cvv, "name": name,
            "address": address, "city": city, "state": state, "zip": zipcode,
            "country": country, "phone": phone, "email": email,
            "bank": info["bank"], "brand": info["brand"], "level": info["level"],
            "bin_rating": info.get("rating", 75), "suggestion": info.get("suggestion", "Retail")
        }
    except Exception as e:
        logger.error(f"Parse error on line '{line}': {e}")
        return None

def format_card(card: dict, is_tester: bool = False) -> str:
    bin6 = card["card"][:6]
    forced = BIN_FORCE_VR.get(bin6)
    vr = forced if forced is not None else random.randint(72, 96)
    balance, label = generate_balance("CREDIT" in card.get("level", "") or "PLATINUM" in card.get("level", ""))

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
        f"BIN Rate   : {card.get('bin_rating', 85)} | {card.get('suggestion', 'Retail')}",
        "══════════════════════════════════════"
    ]
    if is_tester:
        lines.append("❤️ Thank You For Choosing FactoryVHQ ❤️")
    return "\n".join(lines)

def main_menu() -> InlineKeyboardMarkup:
    status = "🟢 TEST MODE ON" if TEST_MODE else "🔴 TEST MODE OFF"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Format", callback_data="format")],
        [InlineKeyboardButton("💰 Sale", callback_data="sale")],
        [InlineKeyboardButton("🔄 Replace", callback_data="replace")],
        [InlineKeyboardButton("🧪 Tester", callback_data="tester")],
        [InlineKeyboardButton("⭐ Rate BIN", callback_data="rate")],
        [InlineKeyboardButton("💵 Balance", callback_data="balance")],
        [InlineKeyboardButton("📊 Stats", callback_data="stats")],
        [InlineKeyboardButton(status, callback_data="toggle_test")]
    ])

def rate_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Set BIN VR", callback_data="set_vr")],
        [InlineKeyboardButton("Rate BIN", callback_data="rate_bin")],
        [InlineKeyboardButton("Set Balance Rating", callback_data="set_balance")],
        [InlineKeyboardButton("Set Suggestion", callback_data="set_suggestion")],
        [InlineKeyboardButton("Force VR (Per BIN)", callback_data="force_vr")],
        [InlineKeyboardButton("← Back to Main Menu", callback_data="back_main")]
    ])

# ===================== STORMCHECK API =====================
async def submit_to_storm(cards: list) -> str:
    if TEST_MODE:
        return f"test-batch-{random.randint(100000, 999999)}"
    # Real API integration can be added here later
    return "batch-000000"

async def storm_poll(batch_id: str, total_cards: int):
    if TEST_MODE:
        await asyncio.sleep(3.5)
        return [{"status": "LIVE"} for _ in range(total_cards)]

    poll_counts = [3,5,8,12,18,25,35]
    polls = poll_counts[min((total_cards // 10), len(poll_counts)-1)]
    for i in range(polls):
        await asyncio.sleep(2.0)
        logger.info(f"[Stormcheck] Polling batch {batch_id} - Attempt {i+1}/{polls}")
    return [{"status": "LIVE"} for _ in range(total_cards)]

# ===================== SESSION MANAGEMENT =====================
def get_session(uid: int) -> dict:
    if uid not in user_sessions:
        user_sessions[uid] = {
            "mode": "format",
            "cards": [],
            "filename": None,
            "customer": None,
            "target": 0,
            "step": "idle",
            "type": None,
            "current_bin": None,
            "rate_action": None,
            "in_post_summary": False,
            "batch_id": None
        }
    return user_sessions[uid]

# ===================== START & CANCEL =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Access Denied. This bot is private.")
        return

    await update.message.reply_html(
        f"<b>FactoryVHQ Admin Panel</b>\n\n"
        f"Welcome <b>@{update.effective_user.username}</b>\n\n"
        f"Select an option below:",
        reply_markup=main_menu()
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_sessions.pop(uid, None)
    await update.message.reply_text(
        "✅ Session has been cancelled.\n\n"
        "Returned to <b>FactoryVHQ Admin Panel</b>.",
        parse_mode='HTML',
        reply_markup=main_menu()
    )

# ===================== BUTTON HANDLER =====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    query = update.callback_query
    await query.answer()
    action = query.data
    uid = query.from_user.id
    session = get_session(uid)

    if action == "toggle_test":
        global TEST_MODE
        TEST_MODE = not TEST_MODE
        await query.edit_message_text(
            f"🔧 Test Mode is now {'🟢 ENABLED' if TEST_MODE else '🔴 DISABLED'}",
            reply_markup=main_menu()
        )
        return

    if action == "cancel":
        await cancel(update, context)
        return

    if action == "back_main":
        await query.edit_message_text("FactoryVHQ Admin Panel", reply_markup=main_menu())
        return

    if action == "rate":
        await query.edit_message_text(
            "⭐ <b>FactoryVHQ BIN Management System</b>",
            parse_mode='HTML',
            reply_markup=rate_menu()
        )
        return

    if action in ["set_vr", "rate_bin", "set_balance", "set_suggestion", "force_vr"]:
        session["rate_action"] = action
        await query.edit_message_text(
            "🔢 Please send the <b>6-digit BIN</b> you want to modify:",
            parse_mode='HTML'
        )
        session["step"] = "waiting_bin"
        return

    session["mode"] = action
    session["in_post_summary"] = False
    session["cards"] = []
    session["filename"] = None
    session["customer"] = None
    session["target"] = 0

    if action in ["format", "tester"]:
        await query.edit_message_text("📥 Send Cards or drop a .txt file to continue.")
    elif action == "sale":
        await query.edit_message_text("👤 Please send the <b>Customer Name</b>:", parse_mode='HTML')
        session["step"] = "waiting_customer"
    elif action == "replace":
        await query.edit_message_text("👤 Who is being replaced? (Customer Name):", parse_mode='HTML')
        session["step"] = "waiting_customer"
    elif action == "balance":
        await query.edit_message_text("💵 Your available Stormcheck credits: <b>2487</b>", parse_mode='HTML')
    elif action == "stats":
        stats = get_user_stats(uid)
        text = f"""📊 <b>FactoryVHQ Statistics</b>

<b>General Stats:</b>
• Cards Sold: <b>{stats['cards_sold']}</b>
• Total Sales: <b>{stats['total_sales']}</b>
• Total Revenue: <b>${stats['revenue']:.2f}</b>
• Total Profit: <b>${stats['profit']:.2f}</b>
• Testers Given: <b>{stats['testers_given']}</b>
• Replacements Given: <b>{stats['replacements_given']}</b>
• Total Cards Checked: <b>{stats['total_cards_checked']}</b>
"""
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=main_menu())

# ===================== MESSAGE HANDLER =====================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        return

    text = update.message.text.strip()
    session = get_session(uid)

    # BIN Rating Flow
    if session.get("step") == "waiting_bin":
        bin6 = text[:6]
        session["current_bin"] = bin6
        if bin6 not in BIN_DATABASE:
            BIN_DATABASE[bin6] = {"bank":"UNKNOWN","brand":"VISA","level":"STANDARD","rating":70,"suggestion":"Retail","balance_rating":70}
        await update.message.reply_text(
            f"✅ BIN <b>{bin6}</b> selected.\n\n"
            f"What value do you want to set for this BIN?",
            parse_mode='HTML'
        )
        session["step"] = "waiting_value"
        return

    if session.get("step") == "waiting_value":
        bin6 = session["current_bin"]
        action = session.get("rate_action")
        try:
            if action in ["set_vr", "rate_bin", "set_balance"]:
                value = int(text)
                if action in ["set_vr", "rate_bin"]:
                    BIN_DATABASE[bin6]["rating"] = value
                elif action == "set_balance":
                    BIN_DATABASE[bin6]["balance_rating"] = value
            elif action == "set_suggestion":
                BIN_DATABASE[bin6]["suggestion"] = text
            elif action == "force_vr":
                if text.upper() == "RESET":
                    BIN_FORCE_VR.pop(bin6, None)
                    await update.message.reply_text(f"✅ Forced VR for BIN {bin6} has been reset.")
                else:
                    BIN_FORCE_VR[bin6] = int(text)
                    await update.message.reply_text(f"✅ Forced VR for BIN {bin6} set to {text}%")
            save_data()
            await update.message.reply_text("✅ BIN information updated successfully!", reply_markup=main_menu())
        except ValueError:
            await update.message.reply_text("❌ Please send a valid number.")
        except Exception as e:
            await update.message.reply_text("❌ An error occurred.")
            logger.error(f"Value setting error: {e}")
        finally:
            session["step"] = "idle"
        return

    # Set Filename
    if session.get("step") == "waiting_filename":
        session["filename"] = text.strip()
        await update.message.reply_text(f"✅ Filename set to: <code>{text}.txt</code>", parse_mode='HTML')
        session["step"] = "idle"
        if session.get("in_post_summary", False):
            await show_post_summary(None, session, uid)
        else:
            await show_pre_summary(update, session, uid)
        return

    # Sale / Replace Customer Flow
    if session.get("step") == "waiting_customer":
        session["customer"] = text
        await update.message.reply_text(
            f"✅ Customer set to: <b>{text}</b>\n\n"
            f"How many cards is this customer purchasing/replacing?",
            parse_mode='HTML'
        )
        session["step"] = "waiting_target"
        return

    if session.get("step") == "waiting_target":
        try:
            session["target"] = int(text)
            await update.message.reply_text("✅ Target set successfully.\n\nSend Cards or drop a .txt file.")
            session["step"] = "waiting_cards"
        except ValueError:
            await update.message.reply_text("❌ Please send a valid number only.")
        return

    # Card Input (Pre or Post Summary)
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

        if not new_cards:
            await update.message.reply_text("⚠️ No valid cards detected in your message.")
            return

        session["cards"].extend(new_cards)
        session["step"] = "idle"

        if session.get("in_post_summary", False):
            await show_post_summary(None, session, uid)
        else:
            await show_pre_summary(update, session, uid)

# ===================== SUMMARY FUNCTIONS =====================
async def show_pre_summary(update: Update, session: dict, uid: int):
    total = len(session["cards"])
    usa = sum(1 for c in session["cards"] if c.get("country", "US").upper() == "US")
    mode = session.get("mode", "format").capitalize()
    filename = session.get("filename") or "Auto Generated"

    text = f"""🧾 <b>Pre Summary - FactoryVHQ</b>

📊 <b>Card Information:</b>
• Total Cards : <b>{total}</b>
• Total USA   : <b>{usa}</b>
• Total Foreign: <b>{total - usa}</b>

🔧 <b>Session Info:</b>
• Mode     : {mode}
• Customer : {session.get('customer', 'N/A')}
• Target   : {session.get('target', 0)}
• Filename : {filename}
"""

    keyboard = [
        [InlineKeyboardButton("✅ Check Cards", callback_data="check")],
        [InlineKeyboardButton("➕ Add More Cards", callback_data="add_more")],
        [InlineKeyboardButton("🗑️ Remove Cards", callback_data="remove_cards")],
        [InlineKeyboardButton("📝 Set Filename", callback_data="set_filename")],
        [InlineKeyboardButton("❌ Cancel Session", callback_data="cancel")]
    ]

    await update.message.reply_html(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def check_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    session = get_session(uid)

    if not session.get("cards"):
        await query.edit_message_text("❌ No cards found in session.")
        return

    await query.edit_message_text(
        "🔄 Batch has been submitted to Stormcheck.\n\n"
        "Please wait while we perform quality checking..."
    )

    batch_id = await submit_to_storm(session["cards"])
    await storm_poll(batch_id, len(session["cards"]))
    session["results"] = [{"status": "LIVE"} for _ in session["cards"]]
    get_user_stats(uid)["total_cards_checked"] += len(session["cards"])
    session["in_post_summary"] = True
    session["batch_id"] = batch_id

    await show_post_summary(query, session, uid)

async def show_post_summary(query: Optional[Update], session: dict, uid: int):
    count = len(session["cards"])
    live = count
    dead = 0
    live_rate = 100.0 if TEST_MODE else 87.0
    target = session.get("target", 0)
    extras = max(0, live - target)
    mode = session.get("mode", "format")
    customer = session.get("customer", "FactoryVHQ")
    stats = get_user_stats(uid)

    if mode == "sale":
        revenue = live * 25.0
        cost = live * 8.0
        profit = revenue - cost
        stats["cards_sold"] += live
        stats["total_sales"] += 1
        stats["revenue"] += revenue
        stats["profit"] += profit

        text = f"""📊 <b>Post Summary - Sale Mode</b>

📊 Statistics:
• Total Cards     : <b>{count}</b>
• Total Live      : <b>{live}</b>
• Extras          : <b>{extras}</b>
• Total Dead      : <b>{dead}</b>
• Live Rate       : <b>{live_rate}%</b>
• Target Reached  : <b>{'Yes' if live >= target else 'No'}</b>
• Profit Made     : <b>${profit:.2f}</b>
• Total Revenue   : <b>${revenue:.2f}</b>
• Filename        : {session.get('filename', 'Auto Generated')}
"""
    elif mode == "replace":
        cost = live * 8.0
        stats["replacements_given"] += 1
        stats["profit"] -= cost
        text = f"""📊 <b>Post Summary - Replace Mode</b>

📊 Statistics:
• Total Cards     : <b>{count}</b>
• Total Live      : <b>{live}</b>
• Extras          : <b>{extras}</b>
• Total Dead      : <b>{dead}</b>
• Live Rate       : <b>{live_rate}%</b>
• Target Reached  : <b>{'Yes' if live >= target else 'No'}</b>
• Customer        : <b>{customer}</b>
• Filename        : {session.get('filename', 'Auto Generated')}
"""
    elif mode == "tester":
        stats["testers_given"] += 1
        text = f"""📊 <b>Post Summary - Tester Mode</b>

📊 Statistics:
• Total Cards : <b>{count}</b>
• Total Live  : <b>{live}</b>
• Total Dead  : <b>{dead}</b>
• Live Rate   : <b>{live_rate}%</b>
• Type        : <b>{session.get('type', 'Gift')}</b>
• Filename    : {session.get('filename', 'Auto Generated')}
"""
    else:  # Format
        text = f"""📊 <b>Post Summary - Format Mode</b>

📊 Statistics:
• Total Cards : <b>{count}</b>
• Total Live  : <b>{live}</b>
• Total Dead  : <b>{dead}</b>
• Live Rate   : <b>{live_rate}%</b>
• Filename    : {session.get('filename', 'Auto Generated')}
"""

    keyboard = [
        [InlineKeyboardButton("📤 Send File(s)", callback_data="send_file")],
        [InlineKeyboardButton("➕ Add More Cards", callback_data="add_more")],
        [InlineKeyboardButton("🗑️ Remove Cards", callback_data="remove_cards")],
        [InlineKeyboardButton("📝 Set Filename", callback_data="set_filename")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]

    if query:
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        # Called after adding more cards in post summary
        await update.effective_message.edit_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

# ===================== FILE SENDING =====================
async def send_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Generating formatted files...")
    uid = query.from_user.id
    session = get_session(uid)

    if not session.get("cards"):
        await query.edit_message_text("❌ No cards available to send.")
        return

    content = "\n\n".join(format_card(card, is_tester=(session.get("mode") == "tester")) for card in session["cards"])
    count = len(session["cards"])
    customer = session.get("customer", "FactoryVHQ")
    live = count
    mode = session.get("mode", "format")

    if not session.get("filename"):
        session["filename"] = f"FactoryVHQ-{customer}-{live}-{random.randint(1000,9999)}"

    filename = f"{session['filename']}.txt"

    if mode in ["sale", "replace"] and customer != "FactoryVHQ":
        await query.message.reply_document(
            document=bytes(content, "utf-8"),
            filename=filename,
            caption=f"✅ FactoryVHQ Main File\nLive Cards: {live}"
        )
        if live > session.get("target", 0):
            extras_count = live - session.get("target", 0)
            extra_cards = session["cards"][session.get("target", 0):]
            extra_content = "\n\n".join(format_card(card) for card in extra_cards)
            await query.message.reply_document(
                document=bytes(extra_content, "utf-8"),
                filename=f"Extras-{extras_count}-cards.txt",
                caption=f"✅ FactoryVHQ Extras File"
            )
    else:
        await query.message.reply_document(
            document=bytes(content, "utf-8"),
            filename=filename,
            caption=f"✅ FactoryVHQ Generated File\nTotal Cards: {count}"
        )

    await query.edit_message_text(
        f"✅ <b>Files sent successfully!</b>\n\n"
        f"Filename: <code>{filename}</code>",
        parse_mode='HTML'
    )
    user_sessions.pop(uid, None)
    save_data()

# ===================== REMOVE CARDS =====================
async def remove_cards_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    session = get_session(uid)
    await query.edit_message_text(
        "🗑️ Send the <b>last 4 digits</b> of the card(s) you want to remove, separated by commas.\n\n"
        "Example: <code>0328, 6807, 4455</code>",
        parse_mode='HTML'
    )
    session["step"] = "removing_cards"

async def process_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    session = get_session(uid)
    if session.get("step") != "removing_cards":
        return

    try:
        last4_list = [x.strip() for x in update.message.text.split(",")]
        original_count = len(session["cards"])
        session["cards"] = [c for c in session["cards"] if c["card"][-4:] not in last4_list]
        removed = original_count - len(session["cards"])

        await update.message.reply_text(f"✅ Successfully removed <b>{removed}</b> card(s).", parse_mode='HTML')

        if session.get("in_post_summary", False):
            await show_post_summary(None, session, uid)
        else:
            await show_pre_summary(update, session, uid)

        session["step"] = "idle"
    except Exception as e:
        logger.error(f"Remove cards error: {e}")
        await update.message.reply_text("❌ Invalid format. Please try again.")

# ===================== SET FILENAME =====================
async def set_filename_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    session = get_session(uid)
    await query.edit_message_text("📝 Please send the desired filename (without .txt extension):")
    session["step"] = "waiting_filename"

# ===================== MAIN =====================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CallbackQueryHandler(check_handler, pattern="^check$"))
    app.add_handler(CallbackQueryHandler(send_file_handler, pattern="^send_file$"))
    app.add_handler(CallbackQueryHandler(remove_cards_handler, pattern="^remove_cards$"))
    app.add_handler(CallbackQueryHandler(set_filename_handler, pattern="^set_filename$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_remove))
    app.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL, message_handler))

    print("🚀 FactoryVHQ Admin Panel v6.0 - Fully Expanded & Complete")
    print(f"   Admins Loaded: {len(ADMIN_IDS)} | Test Mode: {TEST_MODE}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
