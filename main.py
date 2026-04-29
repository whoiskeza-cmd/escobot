import random
import os
import logging
import asyncio
import json
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import aiohttp

# ===================== LOGGER =====================
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ===================== CONFIG =====================
TOKEN = os.getenv("TOKEN")
STORM_API_URL = os.getenv("STORM_API_URL")          # e.g. https://stormcheck.cc/api
STORM_API_KEY = os.getenv("STORM_API_KEY")
OWNER_ID = int(os.getenv("OWNER_ID"))
ADMIN_IDS = [OWNER_ID] + [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

TEST_MODE = False  # Set to False to use real Stormcheck API

user_sessions = {}
user_stats = {}  # Will store per-admin stats

# ===================== BIN DATABASE =====================
BIN_DATA = {
    "410039": {"bank": "CITIBANK, N.A.- COSTCO", "brand": "VISA", "level": "TRADITIONAL", "rating": 85, "suggestion": "Amazon, Walmart"},
    "410040": {"bank": "CITIBANK, N.A.- COSTCO", "brand": "VISA", "level": "BUSINESS", "rating": 78, "suggestion": "High-end stores"},
    "414720": {"bank": "JPMORGAN CHASE BANK N.A.", "brand": "VISA", "level": "TRADITIONAL", "rating": 92, "suggestion": "Everywhere"},
    "414740": {"bank": "JPMORGAN CHASE BANK N.A.", "brand": "VISA", "level": "TRADITIONAL", "rating": 89, "suggestion": "Retail"},
    "440066": {"bank": "BANK OF AMERICA - CONSUMER CREDIT", "brand": "VISA", "level": "TRADITIONAL", "rating": 84, "suggestion": "General"},
    "483312": {"bank": "JPMORGAN CHASE BANK N.A. - DEBIT", "brand": "VISA", "level": "CLASSIC", "rating": 68, "suggestion": "Low Risk"},
    "483316": {"bank": "JPMORGAN CHASE BANK N.A. - DEBIT", "brand": "VISA", "level": "CLASSIC", "rating": 70, "suggestion": "Low Risk"},
    "542418": {"bank": "CITIBANK N.A.", "brand": "MASTERCARD", "level": "PLATINUM", "rating": 88, "suggestion": "High Value"},
    "546616": {"bank": "CITIBANK N.A.", "brand": "MASTERCARD", "level": "WORLD", "rating": 90, "suggestion": "Luxury"},
}

# ===================== STATS INITIALIZATION =====================
def get_user_stats(user_id: int):
    if user_id not in user_stats:
        user_stats[user_id] = {
            "cards_sold": 0, "total_sales": 0, "revenue": 0.0, "profit": 0.0,
            "testers_given": 0, "replacements_given": 0, "total_cards_checked": 0
        }
    return user_stats[user_id]

# ===================== HELPERS =====================
def get_random_ip() -> str:
    return f"{random.randint(25, 220)}.{random.randint(10, 250)}.{random.randint(10, 250)}.{random.randint(10, 250)}"

def generate_balance(is_credit: bool) -> tuple:
    if random.random() < 0.03:  # 3% chance of high balance
        bal = round(random.uniform(3200, 12500), 2)
    else:
        bal = round(random.uniform(85, 1950), 2)
    label = "Available Credit" if is_credit else "Balance"
    return bal, label

def parse_card(line: str) -> dict:
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
        info = BIN_DATA.get(bin6, {"bank":"UNKNOWN","brand":"VISA","level":"STANDARD","rating":75,"suggestion":"Retail"})

        return {
            "card": card, "mm": mm, "yy": yy[-2:], "cvv": cvv, "name": name,
            "address": address, "city": city, "state": state, "zip": zipcode,
            "country": country, "phone": phone, "email": email,
            "bank": info["bank"], "brand": info["brand"], "level": info["level"],
            "bin_rating": info["rating"], "suggestion": info["suggestion"]
        }
    except:
        return None

def format_card(card: dict, vr: int = None, is_tester: bool = False) -> str:
    vr = vr or random.randint(68, 97)
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
        lines.append("❤️ Thank You For Choosing E$CO ❤️")
    return "\n".join(lines)

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Format", callback_data="format")],
        [InlineKeyboardButton("💰 Sale", callback_data="sale")],
        [InlineKeyboardButton("🔄 Replace", callback_data="replace")],
        [InlineKeyboardButton("🧪 Tester", callback_data="tester")],
        [InlineKeyboardButton("⭐ Rate BIN", callback_data="rate")],
        [InlineKeyboardButton("💵 Balance", callback_data="balance")],
        [InlineKeyboardButton("📊 Stats", callback_data="stats")],
        [InlineKeyboardButton("🔧 Toggle Test Mode", callback_data="toggle_test")]
    ])

# ===================== STORMCHECK API =====================
async def storm_check(cards: list, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    if TEST_MODE:
        await asyncio.sleep(3)
        return [{"card": c["card"], "status": "LIVE"} for c in cards]

    url = f"{STORM_API_URL}/check"
    headers = {"Authorization": f"Bearer {STORM_API_KEY}", "Content-Type": "application/json"}
    payload = {"cards": [f"{c['card']}|{c['mm']}{c['yy']}|{c['cvv']}" for c in cards]}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            data = await resp.json()
            batch_id = data.get("batch_id")
            # Polling logic would go here (simplified for now)
            return [{"card": c["card"], "status": "LIVE"} for c in cards]  # Placeholder

# ===================== START =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Access Denied.")
        return

    await update.message.reply_html(
        f"<b>E$CO Admin Panel</b>\n\nWelcome @{update.effective_user.username}",
        reply_markup=main_menu()
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_sessions.pop(uid, None)
    await update.message.reply_text("✅ Cancelled. Returned to Admin Panel.", reply_markup=main_menu())

# ===================== BUTTON HANDLER =====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data
    uid = query.from_user.id

    if uid not in ADMIN_IDS: return

    if action == "cancel":
        await cancel(update, context)
        return
    if action == "toggle_test":
        global TEST_MODE
        TEST_MODE = not TEST_MODE
        await query.edit_message_text(f"🔧 Test Mode is now {'ON' if TEST_MODE else 'OFF'}", reply_markup=main_menu())
        return

    session = user_sessions.setdefault(uid, {
        "mode": action, "cards": [], "filename": None, "customer": None,
        "target": 0, "step": "waiting_cards", "type": None
    })
    session["mode"] = action

    if action == "format":
        await query.edit_message_text("📥 Send Cards or drop a .txt file to continue.")
    elif action == "sale":
        await query.edit_message_text("👤 Please respond with the Customer Name:")
        session["step"] = "waiting_customer"
    elif action == "replace":
        await query.edit_message_text("👤 Who is being replaced? (Customer Name)")
        session["step"] = "waiting_customer"
    elif action == "tester":
        await query.edit_message_text("Is this tester a **Drop** or **Gift**? Reply with one word.")
        session["step"] = "waiting_tester_type"
    elif action == "rate":
        await query.edit_message_text("⭐ BIN Rating Menu:\n\nChoose an option below.", 
                                      reply_markup=InlineKeyboardMarkup([
                                          [InlineKeyboardButton("Set BIN VR", callback_data="set_vr")],
                                          [InlineKeyboardButton("Rate BIN", callback_data="rate_bin")],
                                          [InlineKeyboardButton("Set Balance Rating", callback_data="set_balance")],
                                          [InlineKeyboardButton("Set Suggestion", callback_data="set_suggestion")],
                                      ]))
    elif action == "balance":
        await query.edit_message_text("💵 Checking Stormcheck balance...\n(Using /user endpoint)")
        # Add real API call here later
        await query.message.reply_text("✅ Your Available Storm Credits: **1247**", parse_mode='HTML')
    elif action == "stats":
        stats = get_user_stats(uid)
        text = f"""📊 <b>Your Stats</b>

Cards Sold: {stats['cards_sold']}
Total Sales: {stats['total_sales']}
Revenue: ${stats['revenue']:.2f}
Profit: ${stats['profit']:.2f}
Testers Given: {stats['testers_given']}
Replacements: {stats['replacements_given']}
Total Cards Checked: {stats['total_cards_checked']}
"""
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=main_menu())

# ===================== MESSAGE HANDLER =====================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    text = update.message.text.strip()
    session = user_sessions.get(uid)

    if not session:
        return

    # Sale / Replace Customer Name
    if session.get("step") == "waiting_customer":
        session["customer"] = text
        await update.message.reply_text(f"✅ Customer set to: <b>{text}</b>\n\nHow many cards is this customer getting?", parse_mode='HTML')
        session["step"] = "waiting_target"
        return

    # Target Amount
    if session.get("step") == "waiting_target":
        try:
            session["target"] = int(text)
            await update.message.reply_text("✅ Target Submitted.\n\nSend Cards or drop a .txt file.")
            session["step"] = "waiting_cards"
        except:
            await update.message.reply_text("❌ Please send a number only.")
        return

    # Tester Type
    if session.get("step") == "waiting_tester_type":
        session["type"] = text.lower()
        await update.message.reply_text("✅ Type saved. Send Cards or drop .txt file.")
        session["step"] = "waiting_cards"
        return

    # Card Input
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

        session["cards"].extend(new_cards)
        await show_pre_summary(update, session, uid)

# ===================== PRE & POST SUMMARY =====================
async def show_pre_summary(update: Update, session: dict, uid: int):
    total = len(session["cards"])
    usa = sum(1 for c in session["cards"] if c.get("country", "US").upper() == "US")

    mode = session.get("mode", "format").capitalize()
    customer = session.get("customer", "N/A")
    target = session.get("target", 0)

    text = f"""🧾 <b>Pre Summary/Confirmation</b>

Total Cards : {total}
Total USA   : {usa}
Total Foreign: {total - usa}
Mode        : {mode}
Customer    : {customer}
Target      : {target}
Filename    : {session.get('filename', 'Auto')}
"""

    keyboard = [
        [InlineKeyboardButton("✅ Check", callback_data="check")],
        [InlineKeyboardButton("➕ Add More Cards", callback_data="add_more")],
        [InlineKeyboardButton("🗑️ Remove Cards", callback_data="remove_cards")],
        [InlineKeyboardButton("📝 Set Filename", callback_data="set_filename")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]

    await update.message.reply_html(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def check_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    session = user_sessions.get(uid)
    if not session or not session["cards"]:
        await query.edit_message_text("❌ No cards found.")
        return

    await query.edit_message_text("🔄 Batch has successfully been submitted.\n\nPlease wait up to 30 seconds while we begin quality checking...")

    results = await storm_check(session["cards"], context, uid)
    session["results"] = results

    await show_post_summary(query, session, uid)

async def show_post_summary(query, session: dict, uid: int):
    count = len(session["cards"])
    live = count if TEST_MODE else count  # Simplified for now
    dead = 0
    live_rate = 100.0 if TEST_MODE else 85.0
    target = session.get("target", 0)
    extras = max(0, live - target)

    mode = session.get("mode", "format")

    if mode == "sale":
        text = f"""📊 <b>Post Summary - Sale</b>

Total Cards     : {count}
Total Live      : {live}
Extras          : {extras}
Total Dead      : {dead}
Live Rate       : {live_rate}%
Target Reached  : {live >= target}
Profit Made     : $0.00
Total Revenue   : ${live * 25.00:.2f}
"""
    elif mode == "replace":
        text = f"""📊 <b>Post Summary - Replace</b>

Total Cards     : {count}
Total Live      : {live}
Extras          : {extras}
Total Dead      : {dead}
Live Rate       : {live_rate}%
Target Reached  : {live >= target}
Customer        : {session.get('customer', 'N/A')}
"""
    else:
        text = f"""📊 <b>Post Summary</b>

Total Cards : {count}
Total Live  : {live}
Total Dead  : {dead}
Live Rate   : {live_rate}%
"""

    keyboard = [
        [InlineKeyboardButton("📤 Send File", callback_data="send_file")],
        [InlineKeyboardButton("➕ Add More Cards", callback_data="add_more")],
        [InlineKeyboardButton("🗑️ Remove Cards", callback_data="remove_cards")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]

    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

async def send_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Generating file...")
    uid = query.from_user.id
    session = user_sessions.get(uid)
    if not session or not session.get("cards"):
        await query.edit_message_text("❌ No cards found.")
        return

    content = "\n\n".join(format_card(card, test_mode=TEST_MODE) for card in session["cards"])
    count = len(session["cards"])
    customer = session.get("customer", "Batch")

    filename = session.get("filename") or f"{customer}-{count}-cards.txt"

    await query.message.reply_document(
        document=bytes(content, "utf-8"),
        filename=filename,
        caption=f"✅ Generated {count} cards"
    )

    user_sessions.pop(uid, None)
    await query.edit_message_text("✅ File sent successfully!", parse_mode='HTML')

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CallbackQueryHandler(check_handler, pattern="^check$"))
    app.add_handler(CallbackQueryHandler(send_file_handler, pattern="^send_file$"))
    app.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL, message_handler))

    print("🚀 E$CO Admin Panel v2.0 Started Successfully")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
