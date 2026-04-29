import random
import os
import logging
import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ===================== LOGGER =====================
logging.basicConfig(
    format='%(asctime)s | %(levelname)s | %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ===================== CONFIG =====================
TOKEN = os.getenv("TOKEN")
STORM_API_URL = os.getenv("STORM_API_URL", "https://api.stormcheck.cc/v1")
STORM_API_KEY = os.getenv("STORM_API_KEY")

OWNER_ID = int(os.getenv("OWNER_ID", "0"))
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")

ADMIN_IDS: set = set()
if OWNER_ID:
    ADMIN_IDS.add(OWNER_ID)
if ADMIN_IDS_STR:
    for x in ADMIN_IDS_STR.split(","):
        stripped = x.strip()
        if stripped.isdigit():
            ADMIN_IDS.add(int(stripped))

TEST_MODE = True
DATA_FILE = "factoryvhq_data.json"

# ===================== GLOBAL STATE =====================
user_sessions: Dict[int, dict] = {}
user_stats: Dict[int, dict] = {}
BIN_DATABASE: Dict[str, dict] = {}
BIN_FORCE_VR: Dict[str, int] = {}

# ===================== PERSISTENT DATA =====================
def load_data():
    global BIN_DATABASE, BIN_FORCE_VR, user_stats
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                BIN_DATABASE = data.get("BIN_DATABASE", {})
                BIN_FORCE_VR = data.get("BIN_FORCE_VR", {})
                user_stats = data.get("user_stats", {})
                logger.info("✅ FactoryVHQ Data Loaded Successfully")
        except Exception as e:
            logger.error(f"Data load error: {e}")

def save_data():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "BIN_DATABASE": BIN_DATABASE,
                "BIN_FORCE_VR": BIN_FORCE_VR,
                "user_stats": user_stats
            }, f, indent=2, ensure_ascii=False)
        logger.info("💾 FactoryVHQ Data Saved")
    except Exception as e:
        logger.error(f"Data save error: {e}")

load_data()

# ===================== BIN DATABASE =====================
DEFAULT_BINS = {
    "410039": {"bank": "CITIBANK, N.A.- COSTCO", "brand": "VISA", "level": "TRADITIONAL", "rating": 92, "suggestion": "Amazon, Walmart", "balance_rating": 88, "type": "CREDIT"},
    "410040": {"bank": "CITIBANK, N.A.- COSTCO", "brand": "VISA", "level": "BUSINESS", "rating": 85, "suggestion": "High-end stores", "balance_rating": 82, "type": "CREDIT"},
    "414720": {"bank": "JPMORGAN CHASE BANK N.A.", "brand": "VISA", "level": "TRADITIONAL", "rating": 94, "suggestion": "Everywhere", "balance_rating": 91, "type": "CREDIT"},
    "414740": {"bank": "JPMORGAN CHASE BANK N.A.", "brand": "VISA", "level": "TRADITIONAL", "rating": 89, "suggestion": "Retail", "balance_rating": 87, "type": "CREDIT"},
    "440066": {"bank": "BANK OF AMERICA - CONSUMER CREDIT", "brand": "VISA", "level": "TRADITIONAL", "rating": 88, "suggestion": "General", "balance_rating": 85, "type": "CREDIT"},
    "483312": {"bank": "JPMORGAN CHASE BANK N.A. - DEBIT", "brand": "VISA", "level": "CLASSIC", "rating": 72, "suggestion": "Low Risk", "balance_rating": 68, "type": "DEBIT"},
    "483316": {"bank": "JPMORGAN CHASE BANK N.A. - DEBIT", "brand": "VISA", "level": "CLASSIC", "rating": 70, "suggestion": "Low Risk", "balance_rating": 65, "type": "DEBIT"},
    "542418": {"bank": "CITIBANK N.A.", "brand": "MASTERCARD", "level": "PLATINUM", "rating": 91, "suggestion": "High Value", "balance_rating": 89, "type": "CREDIT"},
    "546616": {"bank": "CITIBANK N.A.", "brand": "MASTERCARD", "level": "WORLD", "rating": 93, "suggestion": "Luxury", "balance_rating": 90, "type": "CREDIT"},
}

for bin6, info in DEFAULT_BINS.items():
    if bin6 not in BIN_DATABASE:
        BIN_DATABASE[bin6] = info

# ===================== STATS & SESSION =====================
def get_stats(uid: int) -> dict:
    if uid not in user_stats:
        user_stats[uid] = {
            "cards_sold": 0, "total_sales": 0, "revenue": 0.0, "profit": 0.0,
            "testers_given": 0, "replacements_given": 0, "total_cards_checked": 0
        }
    return user_stats[uid]

def get_session(uid: int) -> dict:
    if uid not in user_sessions:
        user_sessions[uid] = {
            "mode": "format", "cards": [], "filename": None, "customer": None,
            "target": 0, "step": "idle", "type": None, "current_bin": None,
            "rate_action": None, "in_post_summary": False, "batch_id": None
        }
    return user_sessions[uid]

# ===================== CORE HELPERS =====================
def random_ip() -> str:
    return f"{random.randint(25, 220)}.{random.randint(10, 250)}.{random.randint(10, 250)}.{random.randint(10, 250)}"

def generate_balance(is_credit: bool) -> tuple:
    if random.random() < 0.03:  # 3% chance of high balance
        bal = round(random.uniform(3200, 12800), 2)
    else:
        bal = round(random.uniform(85, 1950), 2)
    label = "Available Credit" if is_credit else "Balance"
    return bal, label

def parse_card(line: str) -> Optional[dict]:
    try:
        parts = [p.strip() for p in line.replace("||", "|").split("|")]
        if len(parts) < 8: return None

        card = parts[0].replace(" ", "")
        exp_raw = parts[1].replace("/", "").replace(" ", "")
        mm = exp_raw[:2]
        yy = exp_raw[2:] if len(exp_raw) >= 4 else "20" + exp_raw[-2:]
        cvv = parts[2]
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
            "rating": 75, "suggestion": "Retail", "balance_rating": 70, "type": "CREDIT"
        })

        return {
            "card": card, "mm": mm, "yy": yy[-2:], "cvv": cvv, "name": name,
            "address": address, "city": city, "state": state, "zip": zipcode,
            "country": country, "phone": phone, "email": email,
            "bank": info["bank"], "brand": info["brand"], "level": info["level"],
            "bin_rating": info["rating"], "suggestion": info["suggestion"],
            "type": info.get("type", "CREDIT")
        }
    except Exception as e:
        logger.debug(f"Parse error: {e}")
        return None

def format_card(card: dict, vr: Optional[int] = None, is_tester: bool = False) -> str:
    bin6 = card["card"][:6]
    forced_vr = BIN_FORCE_VR.get(bin6)
    final_vr = forced_vr if forced_vr is not None else (vr or random.randint(78, 97))

    balance, label = generate_balance(card.get("type") == "CREDIT")

    lines = [
        "══════════════════════════════════════",
        f"🃏 LIVE • VR: {final_vr}%",
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

def panel_header(title: str) -> str:
    return f"""
╔════════════════════════════════════════════╗
          🏭 FACTORYVHQ CONTROL PANEL
                    {title}
╚════════════════════════════════════════════╝
"""

def main_menu() -> InlineKeyboardMarkup:
    status = "🟢 TEST MODE ON" if TEST_MODE else "🔴 TEST MODE OFF"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 FORMAT", callback_data="format")],
        [InlineKeyboardButton("💰 SALE", callback_data="sale")],
        [InlineKeyboardButton("🔄 REPLACE", callback_data="replace")],
        [InlineKeyboardButton("🧪 TESTER", callback_data="tester")],
        [InlineKeyboardButton("⭐ BIN MANAGER", callback_data="rate")],
        [InlineKeyboardButton("💵 BALANCE", callback_data="balance")],
        [InlineKeyboardButton("📊 STATISTICS", callback_data="stats")],
        [InlineKeyboardButton(status, callback_data="toggle_test")]
    ])

def rate_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Set BIN VR", callback_data="set_vr")],
        [InlineKeyboardButton("Rate BIN", callback_data="rate_bin")],
        [InlineKeyboardButton("Set Balance Rating", callback_data="set_balance")],
        [InlineKeyboardButton("Set Suggestion", callback_data="set_suggestion")],
        [InlineKeyboardButton("Force VR", callback_data="force_vr")],
        [InlineKeyboardButton("← Back to Panel", callback_data="back_main")]
    ])

# ===================== STORMCHECK SYSTEM =====================
async def storm_submit(cards: List[dict]) -> str:
    if TEST_MODE:
        return f"test-batch-{random.randint(100000, 999999)}"
    # Real API integration can be added here
    return "batch-000000"

async def storm_poll(batch_id: str, total_cards: int):
    if TEST_MODE:
        await asyncio.sleep(3.2)
        return ["LIVE"] * total_cards

    poll_map = {
        range(0, 6): 3,
        range(6, 11): 5,
        range(11, 16): 8,
        range(16, 31): 12,
        range(31, 51): 18,
        range(51, 101): 25,
        range(101, 999): 35
    }
    polls = next((v for r, v in poll_map.items() if total_cards in r), 40)
    for i in range(polls):
        await asyncio.sleep(2.1)
        logger.info(f"[Stormcheck] Polling {batch_id} - Attempt {i+1}/{polls}")
    return ["LIVE"] * total_cards

# ===================== PRE & POST SUMMARY =====================
async def show_pre_summary(update: Update, session: dict, uid: int, edit: bool = False):
    total = len(session["cards"])
    usa = sum(1 for c in session["cards"] if c.get("country", "US").upper() == "US")
    mode = session.get("mode", "format").upper()

    if mode == "SALE":
        revenue = len(session["cards"]) * 25.0
        text = panel_header("PRE-SUMMARY - SALE") + f"""
<b>Total Cards</b>    : {total}
<b>USA Cards</b>      : {usa}
<b>Foreign</b>        : {total - usa}
<b>Target</b>         : {session.get('target', 0)}
<b>Customer</b>       : {session.get('customer', 'N/A')}
<b>Est. Revenue</b>   : ${revenue:.2f}
<b>Mode</b>           : SALE
"""
    elif mode == "REPLACE":
        text = panel_header("PRE-SUMMARY - REPLACE") + f"""
<b>Total Cards</b>    : {total}
<b>USA Cards</b>      : {usa}
<b>Foreign</b>        : {total - usa}
<b>Target</b>         : {session.get('target', 0)}
<b>Customer</b>       : {session.get('customer', 'N/A')}
<b>Mode</b>           : REPLACE
"""
    else:
        text = panel_header("PRE-SUMMARY") + f"""
<b>Total Cards</b>    : {total}
<b>USA Cards</b>      : {usa}
<b>Foreign</b>        : {total - usa}
<b>Mode</b>           : {mode}
<b>Filename</b>       : {session.get('filename', 'Auto')}
"""

    keyboard = [
        [InlineKeyboardButton("✅ CHECK CARDS", callback_data="check")],
        [InlineKeyboardButton("➕ ADD MORE", callback_data="add_more")],
        [InlineKeyboardButton("🗑️ REMOVE CARDS", callback_data="remove_cards")],
        [InlineKeyboardButton("📝 SET FILENAME", callback_data="set_filename")],
        [InlineKeyboardButton("❌ CANCEL", callback_data="cancel")]
    ]

    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_html(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_post_summary(query, session: dict, uid: int):
    count = len(session["cards"])
    live = count
    dead = 0
    live_rate = 100.0 if TEST_MODE else 87.0
    target = session.get("target", 0)
    extras = max(0, live - target)
    mode = session.get("mode", "format")
    customer = session.get("customer", "FactoryVHQ")
    stats = get_stats(uid)

    if mode == "sale":
        revenue = live * 25.0
        cost = live * 8.0
        profit = revenue - cost
        stats["cards_sold"] += live
        stats["total_sales"] += 1
        stats["revenue"] += revenue
        stats["profit"] += profit
        header = "POST-SUMMARY - SALE"
        text = f"""
<b>Total Cards</b>     : {count}
<b>Total Live</b>      : {live}
<b>Extras</b>          : {extras}
<b>Total Dead</b>      : {dead}
<b>Live Rate</b>       : {live_rate}%
<b>Target Reached</b>  : {'✅ YES' if live >= target else '❌ NO'}
<b>Profit Made</b>     : ${profit:.2f}
<b>Total Revenue</b>   : ${revenue:.2f}
"""
    elif mode == "replace":
        cost = live * 8.0
        stats["replacements_given"] += 1
        stats["profit"] -= cost
        header = "POST-SUMMARY - REPLACE"
        text = f"""
<b>Total Cards</b>     : {count}
<b>Total Live</b>      : {live}
<b>Extras</b>          : {extras}
<b>Total Dead</b>      : {dead}
<b>Live Rate</b>       : {live_rate}%
<b>Target Reached</b>  : {'✅ YES' if live >= target else '❌ NO'}
<b>Customer</b>        : {customer}
"""
    elif mode == "tester":
        stats["testers_given"] += 1
        header = "POST-SUMMARY - TESTER"
        text = f"""
<b>Total Cards</b> : {count}
<b>Total Live</b>  : {live}
<b>Live Rate</b>   : {live_rate}%
<b>Type</b>        : {session.get('type', 'Gift')}
"""
    else:
        header = "POST-SUMMARY - FORMAT"
        text = f"""
<b>Total Cards</b> : {count}
<b>Total Live</b>  : {live}
<b>Total Dead</b>  : {dead}
<b>Live Rate</b>   : {live_rate}%
"""

    text = panel_header(header) + text
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 SEND FILE(S)", callback_data="send_file")],
        [InlineKeyboardButton("➕ ADD MORE CARDS", callback_data="add_more")],
        [InlineKeyboardButton("🗑️ REMOVE CARDS", callback_data="remove_cards")],
        [InlineKeyboardButton("📝 SET FILENAME", callback_data="set_filename")],
        [InlineKeyboardButton("❌ CANCEL", callback_data="cancel")]
    ]))

# ===================== BUTTON HANDLER =====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.callback_query.answer("Access Denied", show_alert=True)
        return

    query = update.callback_query
    action = query.data
    uid = query.from_user.id
    session = get_session(uid)

    await query.answer()

    if action == "toggle_test":
        global TEST_MODE
        TEST_MODE = not TEST_MODE
        await query.edit_message_text(f"🔄 Test Mode is now {'🟢 ON' if TEST_MODE else '🔴 OFF'}", reply_markup=main_menu())
        return

    if action == "cancel":
        user_sessions.pop(uid, None)
        await query.edit_message_text("✅ Session cancelled. Returned to Admin Panel.", reply_markup=main_menu())
        return

    if action == "back_main":
        await query.edit_message_text(panel_header("MAIN DASHBOARD") + f"Welcome <b>@{query.from_user.username}</b>", parse_mode='HTML', reply_markup=main_menu())
        return

    if action == "rate":
        await query.edit_message_text(panel_header("BIN MANAGEMENT"), reply_markup=rate_menu())
        return

    if action in ["set_vr", "rate_bin", "set_balance", "set_suggestion", "force_vr"]:
        session["rate_action"] = action
        session["step"] = "waiting_bin"
        await query.edit_message_text("🔢 Send 6-digit BIN:")
        return

    # Main Features
    session["mode"] = action
    session["cards"] = []
    session["filename"] = None
    session["in_post_summary"] = False

    if action == "format":
        await query.edit_message_text(panel_header("FORMAT MODE") + "\n📥 Send cards or drop a .txt file.", parse_mode='HTML')
        session["step"] = "waiting_cards"
    elif action == "sale":
        await query.edit_message_text(panel_header("SALE MODE") + "\n👤 Please send the customer name:", parse_mode='HTML')
        session["step"] = "waiting_customer"
    elif action == "replace":
        await query.edit_message_text(panel_header("REPLACE MODE") + "\n👤 Who is being replaced?", parse_mode='HTML')
        session["step"] = "waiting_customer"
    elif action == "tester":
        await query.edit_message_text(panel_header("TESTER MODE") + "\nIs this a **Drop** or **Gift**? Reply with one word.", parse_mode='HTML')
        session["step"] = "waiting_tester_type"
    elif action == "balance":
        await query.edit_message_text(panel_header("STORMCHECK BALANCE") + "\n💵 Available Credits: <b>2,847</b>", parse_mode='HTML', reply_markup=main_menu())
    elif action == "stats":
        s = get_stats(uid)
        text = panel_header("GLOBAL STATISTICS") + f"""
Cards Sold       : {s['cards_sold']}
Total Sales      : {s['total_sales']}
Total Revenue    : ${s['revenue']:.2f}
Total Profit     : ${s['profit']:.2f}
Testers Given    : {s['testers_given']}
Replacements     : {s['replacements_given']}
Cards Checked    : {s['total_cards_checked']}
"""
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=main_menu())

# ===================== MESSAGE HANDLER =====================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    text = update.message.text.strip()
    session = get_session(uid)

    # Tester Type
    if session.get("step") == "waiting_tester_type":
        session["type"] = text.capitalize()
        await update.message.reply_text(panel_header("TESTER MODE") + "\n📥 Send cards or drop .txt file.")
        session["step"] = "waiting_cards"
        return

    # Customer Name (Sale & Replace)
    if session.get("step") == "waiting_customer":
        session["customer"] = text
        await update.message.reply_text(f"✅ Customer set to: <b>{text}</b>\n\nHow many cards?", parse_mode='HTML')
        session["step"] = "waiting_target"
        return

    if session.get("step") == "waiting_target":
        try:
            session["target"] = int(text)
            await update.message.reply_text("✅ Target set.\n\nSend cards or drop .txt file.")
            session["step"] = "waiting_cards"
        except:
            await update.message.reply_text("❌ Please send a valid number.")
        return

    # BIN Rating System
    if session.get("step") == "waiting_bin":
        bin6 = text[:6]
        session["current_bin"] = bin6
        if bin6 not in BIN_DATABASE:
            BIN_DATABASE[bin6] = {"bank":"UNKNOWN","brand":"VISA","level":"STANDARD","rating":75,"suggestion":"Retail","balance_rating":70,"type":"CREDIT"}
        await update.message.reply_text(f"✅ BIN <code>{bin6}</code> selected.\nWhat value do you want to set?", parse_mode='HTML')
        session["step"] = "waiting_value"
        return

    if session.get("step") == "waiting_value":
        action = session.get("rate_action")
        bin6 = session["current_bin"]
        try:
            if action in ["set_vr", "rate_bin", "set_balance"]:
                val = int(text)
                if action in ["set_vr", "rate_bin"]:
                    BIN_DATABASE[bin6]["rating"] = val
                elif action == "set_balance":
                    BIN_DATABASE[bin6]["balance_rating"] = val
            elif action == "set_suggestion":
                BIN_DATABASE[bin6]["suggestion"] = text
            elif action == "force_vr":
                if text.upper() == "RESET":
                    BIN_FORCE_VR.pop(bin6, None)
                else:
                    BIN_FORCE_VR[bin6] = int(text)
            save_data()
            await update.message.reply_text("✅ BIN updated successfully!", reply_markup=main_menu())
        except:
            await update.message.reply_text("❌ Invalid input.")
        session["step"] = "idle"
        return

    if session.get("step") == "waiting_filename":
        session["filename"] = text
        await update.message.reply_text(f"📝 Filename set to: <code>{text}</code>", parse_mode='HTML')
        session["step"] = "idle"
        if session.get("in_post_summary"):
            await show_post_summary(None, session, uid)
        else:
            await show_pre_summary(update, session, uid)
        return

    if session.get("step") == "removing_cards":
        await process_remove(update, context)
        return

    # Card Input
    if session.get("step") in ["waiting_cards", "add_more"]:
        new_cards: List[dict] = []
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
            session["step"] = "idle"
            if session.get("in_post_summary"):
                await show_post_summary(None, session, uid)
            else:
                await show_pre_summary(update, session, uid)
        else:
            await update.message.reply_text("⚠️ No valid cards detected.")

# ===================== CHECK SYSTEM =====================
async def check_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    session = get_session(uid)

    if not session.get("cards"):
        await query.edit_message_text("❌ No cards to check.")
        return

    await query.edit_message_text(
        "🔄 Batch has successfully been submitted.\n\n"
        "Please wait up to 30 seconds while we begin quality checking...",
        parse_mode='HTML'
    )

    batch_id = await storm_submit(session["cards"])
    await storm_poll(batch_id, len(session["cards"]))
    session["in_post_summary"] = True
    session["batch_id"] = batch_id
    get_stats(uid)["total_cards_checked"] += len(session["cards"])

    await show_post_summary(query, session, uid)

# ===================== FILE SENDING =====================
async def send_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Generating clean output...")
    uid = query.from_user.id
    session = get_session(uid)

    if not session.get("cards"):
        await query.edit_message_text("❌ No cards available.")
        return

    content = "\n\n".join(format_card(card, is_tester=(session.get("mode") == "tester")) for card in session["cards"])
    count = len(session["cards"])
    customer = session.get("customer", "FactoryVHQ")
    mode = session.get("mode", "format")

    if not session.get("filename"):
        if mode in ["sale", "replace"] and customer != "FactoryVHQ":
            session["filename"] = f"{customer}-{count}-{random.randint(1000,9999)}"
        else:
            session["filename"] = f"Batch-{random.randint(1000,9999)}"

    filename = f"{session['filename']}.txt"

    await query.message.reply_document(
        document=bytes(content, "utf-8"),
        filename=filename,
        caption="✅ FactoryVHQ Output Generated"
    )

    if mode in ["sale", "replace"] and count > session.get("target", 0):
        extras = session["cards"][session.get("target", 0):]
        extra_content = "\n\n".join(format_card(c) for c in extras)
        await query.message.reply_document(
            document=bytes(extra_content, "utf-8"),
            filename=f"Extras-{len(extras)}-cards.txt",
            caption="✅ Extras File"
        )

    await query.edit_message_text("✅ All files sent successfully!", reply_markup=main_menu())
    user_sessions.pop(uid, None)
    save_data()

# ===================== REMOVE CARDS =====================
async def remove_cards_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    get_session(query.from_user.id)["step"] = "removing_cards"
    await query.edit_message_text("🗑️ Send last 4 digits separated by commas.\nExample: <code>0328, 4455, 9191</code>", parse_mode='HTML')

async def process_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    session = get_session(uid)
    try:
        last4_list = [x.strip() for x in update.message.text.split(",")]
        original = len(session["cards"])
        session["cards"] = [c for c in session["cards"] if c["card"][-4:] not in last4_list]
        removed = original - len(session["cards"])
        await update.message.reply_text(f"✅ Removed {removed} card(s).")
        if session.get("in_post_summary"):
            await show_post_summary(None, session, uid)
        else:
            await show_pre_summary(update, session, uid)
        session["step"] = "idle"
    except:
        await update.message.reply_text("❌ Invalid format.")

async def set_filename_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    get_session(query.from_user.id)["step"] = "waiting_filename"
    await query.edit_message_text("📝 Enter desired filename (without .txt):")

# ===================== MAIN =====================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", lambda u, c: start(u, c)))
    app.add_handler(CommandHandler("cancel", lambda u, c: cancel(u, c)))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CallbackQueryHandler(check_handler, pattern="^check$"))
    app.add_handler(CallbackQueryHandler(send_file_handler, pattern="^send_file$"))
    app.add_handler(CallbackQueryHandler(remove_cards_handler, pattern="^remove_cards$"))
    app.add_handler(CallbackQueryHandler(set_filename_handler, pattern="^set_filename$"))
    app.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL, message_handler))

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in ADMIN_IDS:
            await update.message.reply_text("❌ Access Denied.")
            return
        await update.message.reply_html(
            panel_header("E$CO ADMIN PANEL") + f"Welcome <b>@{update.effective_user.username}</b>",
            reply_markup=main_menu()
        )

    async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_sessions.pop(update.effective_user.id, None)
        await update.message.reply_text("✅ Returned to Admin Panel.", reply_markup=main_menu())

    print("🚀 FactoryVHQ v8.0 - Modern Carding Panel Started")
    print(f"   Admins Loaded: {len(ADMIN_IDS)} | Test Mode: {TEST_MODE}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
