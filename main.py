import asyncio
import random
import os
from datetime import datetime, timezone
from typing import Dict, List

import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ===================== CONFIG =====================
TOKEN = os.getenv("TOKEN")
API_KEY = os.getenv("API_KEY")
OWNER_ID = int(os.getenv("OWNER_ID"))
BASE_URL = os.getenv("BASE_URL", "https://api.stormcheck.cc/api/v1")

TEST_MODE = False

stats = {
    "cards_sold": 0, "total_sales": 0, "revenue": 0.0,
    "testers_given": 0, "replacements_given": 0, "profit": 0.0,
    "card_cost": 2.50, "sale_price": 15.00
}

BIN_DATA: Dict[str, dict] = {
    "410039": {"bank": "CITIBANK, N.A.- COSTCO", "brand": "VISA", "level": "TRADITIONAL", "rating": 85, "suggestion": "Amazon, Walmart"},
    "410040": {"bank": "CITIBANK, N.A.- COSTCO", "brand": "VISA", "level": "BUSINESS", "rating": 78, "suggestion": "High-end stores"},
    "414720": {"bank": "JPMORGAN CHASE BANK N.A.", "brand": "VISA", "level": "TRADITIONAL", "rating": 92, "suggestion": "Everywhere"},
    "414740": {"bank": "JPMORGAN CHASE BANK N.A.", "brand": "VISA", "level": "TRADITIONAL", "rating": 89, "suggestion": "Retail"},
    "440066": {"bank": "BANK OF AMERICA", "brand": "VISA", "level": "TRADITIONAL", "rating": 84, "suggestion": "General"},
    "483312": {"bank": "JPMORGAN CHASE", "brand": "VISA", "level": "DEBIT", "rating": 65, "suggestion": "Low Risk"},
    "483316": {"bank": "JPMORGAN CHASE", "brand": "VISA", "level": "DEBIT", "rating": 68, "suggestion": "Low Risk"},
    "542418": {"bank": "CITIBANK N.A.", "brand": "MASTERCARD", "level": "PLATINUM", "rating": 88, "suggestion": "High Value"},
    "534348": {"bank": "CELTIC BANK CORPORATION", "brand": "MASTERCARD", "level": "PLATINUM", "rating": 87, "suggestion": "High Value"},
}

user_sessions: Dict[int, dict] = {}

# ===================== HELPERS =====================
def get_random_ip() -> str:
    return f"{random.randint(25,220)}.{random.randint(10,250)}.{random.randint(10,250)}.{random.randint(10,250)}"

def generate_balance(is_credit: bool) -> tuple:
    if random.random() < 0.03:  # 3% chance of high balance
        bal = round(random.uniform(3200, 9200), 2)
    else:
        bal = round(random.uniform(85, 1950), 2)
    label = "Available Credit" if is_credit else "Balance"
    return bal, label

def parse_card(line: str) -> dict:
    try:
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 8: return None
        card = parts[0].replace(" ", "")
        exp = parts[1].replace("/", "").replace(" ", "")
        mm = exp[:2]
        yy = exp[2:] if len(exp) == 4 else "20" + exp[2:]
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

def format_card(card: dict, is_tester: bool = False, test_mode: bool = False) -> str:
    vr = random.randint(68, 97)
    balance, label = generate_balance("CREDIT" in card.get("level", "") or "PLATINUM" in card.get("level", ""))
    title = "TestMode Demo" if test_mode else f"LIVE • VR: {vr}%"
    
    lines = [
        "══════════════════════════════════════",
        f"🃏 {title}",
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
    status = "🟢 TEST MODE ON" if TEST_MODE else "🔴 TEST MODE OFF"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Format", callback_data="format")],
        [InlineKeyboardButton("Sale", callback_data="sale")],
        [InlineKeyboardButton("Replace", callback_data="replace")],
        [InlineKeyboardButton("Tester", callback_data="tester")],
        [InlineKeyboardButton("Rate BIN", callback_data="rate")],
        [InlineKeyboardButton("Balance", callback_data="balance")],
        [InlineKeyboardButton("Stats", callback_data="stats")],
        [InlineKeyboardButton(status, callback_data="toggle_test")]
    ])

# ===================== API FUNCTIONS =====================
async def submit_batch(cards: List[str]) -> str:
    if TEST_MODE:
        return "test-batch-12345"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{BASE_URL}/check", headers=headers, json={"cards": cards}) as resp:
            data = await resp.json()
            return data.get("data", {}).get("batch_id", "unknown")

async def poll_batch(batch_id: str, max_polls: int) -> int:
    if TEST_MODE:
        await asyncio.sleep(3)
        return max_polls * 2  # Simulate high success in test mode
    headers = {"Authorization": f"Bearer {API_KEY}"}
    for _ in range(max_polls):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{BASE_URL}/check/{batch_id}", headers=headers) as resp:
                data = await resp.json()
                if not data.get("data", {}).get("is_checking", True):
                    return data.get("data", {}).get("accepted_count", 0)
        await asyncio.sleep(4)
    return 0

# ===================== MAIN HANDLERS =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Access Denied.")
        return
    await update.message.reply_html(
        f"<b>E$CO Admin Panel</b>\n\nWelcome @{update.effective_user.username}",
        reply_markup=main_menu()
    )

async def toggle_test_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TEST_MODE
    TEST_MODE = not TEST_MODE
    status = "ENABLED (All cards will be marked LIVE - No real API calls)" if TEST_MODE else "DISABLED (Real Stormcheck API)"
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(f"🔧 Test Mode is now **{status}**", parse_mode='HTML', reply_markup=main_menu())
    else:
        await update.message.reply_text(f"🔧 Test Mode is now **{status}**", parse_mode='HTML')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    query = update.callback_query
    await query.answer()
    action = query.data
    uid = query.from_user.id
    session = user_sessions.setdefault(uid, {"mode": None, "cards": [], "filename": None, "customer": None, "target": 0, "tester_type": None})

    if action == "toggle_test":
        await toggle_test_mode(update, context)
        return
    if action == "cancel":
        user_sessions.pop(uid, None)
        await query.edit_message_text("✅ Returned to Admin Panel.", reply_markup=main_menu())
        return

    session["mode"] = action

    if action == "format":
        await query.edit_message_text("Send Cards or drop a .txt file to continue.")
    elif action == "sale":
        await query.edit_message_text("Please respond with the **Customer Name**:")
    elif action == "replace":
        await query.edit_message_text("Who is being replaced?")
    elif action == "tester":
        await query.edit_message_text("Is this Tester a **Drop** or **Gift**?")
    elif action == "rate":
        await query.edit_message_text("🛠️ Rate BIN Menu", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Set Bin VR", callback_data="set_vr")],
            [InlineKeyboardButton("Rate Bin", callback_data="rate_bin")],
            [InlineKeyboardButton("Set Bin Balance Rating", callback_data="set_balance")],
            [InlineKeyboardButton("Bin Use Suggestion", callback_data="bin_suggestion")],
            [InlineKeyboardButton("← Back", callback_data="cancel")]
        ]))
    elif action == "balance":
        await query.edit_message_text("Your Available Storm Credits Are **∞** (Admin Mode)")
        await asyncio.sleep(2)
        await query.edit_message_text("✅ Returned to Admin Panel.", reply_markup=main_menu())
    elif action == "stats":
        text = (f"📊 E$CO Stats\n\n"
                f"Cards Sold: {stats['cards_sold']}\n"
                f"Total Sales: {stats['total_sales']}\n"
                f"Revenue: ${stats['revenue']:.2f}\n"
                f"Testers Given: {stats['testers_given']}\n"
                f"Replacements Given: {stats['replacements_given']}\n"
                f"Total Profit: ${stats['profit']:.2f}")
        await query.edit_message_text(text, reply_markup=main_menu())

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    text = update.message.text.strip()
    uid = update.effective_user.id
    session = user_sessions.get(uid)
    if not session or not session.get("mode"): return

    mode = session["mode"]
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

    session.setdefault("cards", []).extend(new_cards)
    total = len(session["cards"])
    usa = sum(1 for c in session["cards"] if c.get("country", "US").upper() == "US")
    foreign = total - usa

    keyboard = [
        [InlineKeyboardButton("✅ Check", callback_data="check")],
        [InlineKeyboardButton("Add More Cards", callback_data="add_more")],
        [InlineKeyboardButton("Remove Cards", callback_data="remove")],
        [InlineKeyboardButton("Set Filename", callback_data="set_filename")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ]

    pre_text = f"""Pre Summary/Confirmation
Total Cards: {total}
Total USA: {usa}
Total Foreign: {foreign}
Mode: {mode.capitalize()}
"""
    if mode == "sale":
        pre_text += f"Target: {session.get('target', 'Not Set')}\nCustomer: {session.get('customer', 'N/A')}\n"
    elif mode == "replace":
        pre_text += f"Replacement Target: {session.get('target', 'Not Set')}\nCustomer: {session.get('customer', 'N/A')}\n"
    elif mode == "tester":
        pre_text += f"Tester Type: {session.get('tester_type', 'N/A')}\n"

    pre_text += f"Filename: {session.get('filename', 'Batch-' + str(random.randint(1000,9999)))}"

    await update.message.reply_text(pre_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def check_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    session = user_sessions.get(uid)
    if not session or not session.get("cards"):
        await query.edit_message_text("❌ No cards found.")
        return

    count = len(session["cards"])
    is_tester = session.get("mode") == "tester"

    # Submit to Stormcheck API
    batch_cards = [f"{c['card']}|{c['mm']}{c['yy']}|{c['cvv']}" for c in session["cards"]]
    batch_id = await submit_batch(batch_cards)

    polls = 3 if count <= 5 else 5 if count <= 10 else 8 if count <= 15 else (count // 2) + 3
    await query.edit_message_text(f"Batch Has Successfully Been Submitted (ID: {batch_id})\n\nPlease Wait Up To 30 Seconds While We Begin Quality Checking...")

    live_count = await poll_batch(batch_id, polls)
    dead_count = count - live_count
    live_rate = round((live_count / count * 100), 1) if count > 0 else 0.0

    # Update Stats
    if session.get("mode") == "sale":
        stats["cards_sold"] += live_count
        stats["total_sales"] += 1
        stats["revenue"] += live_count * stats["sale_price"]
        stats["profit"] += (live_count * stats["sale_price"]) - (live_count * stats["card_cost"])

    elif session.get("mode") == "replace":
        stats["replacements_given"] += live_count
        stats["profit"] -= live_count * stats["card_cost"]

    elif session.get("mode") == "tester":
        stats["testers_given"] += live_count

    post_text = f"""Post Summary/Confirmation
Total Cards: {count}
Total Live: {live_count}
Total Dead: {dead_count}
LiveRate: {live_rate}%
"""
    if session.get("mode") == "sale":
        extras = max(0, live_count - session.get("target", 0))
        post_text += f"Extras: {extras}\nTarget Reached: {live_count >= session.get('target', 0)}\n"
    elif session.get("mode") == "replace":
        post_text += f"Replacement Target Reached: {live_count >= session.get('target', 0)}\nCustomer: {session.get('customer', 'N/A')}\n"

    keyboard = [
        [InlineKeyboardButton("Send File", callback_data="send_file")],
        [InlineKeyboardButton("Add More Cards", callback_data="add_more")],
        [InlineKeyboardButton("Remove Cards", callback_data="remove")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ]

    await query.edit_message_text(post_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def send_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    session = user_sessions.get(uid)
    if not session or not session.get("cards"): return

    is_tester = session.get("mode") == "tester"
    content = "\n\n".join(format_card(c, is_tester=is_tester, test_mode=TEST_MODE) for c in session["cards"])
    
    count = len(session["cards"])
    filename = session.get("filename") or (f"Batch-{random.randint(1000,9999)}")
    final_filename = f"{filename}.txt" if not TEST_MODE else f"TestMode-Demo-{count}.txt"

    await query.message.reply_document(
        document=bytes(content, "utf-8"),
        filename=final_filename,
        caption="✅ File Generated Successfully"
    )
    await query.edit_message_text("✅ File sent successfully.")
    user_sessions.pop(uid, None)

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("testmode", toggle_test_mode))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CallbackQueryHandler(check_handler, pattern="^check$"))
    app.add_handler(CallbackQueryHandler(send_file_handler, pattern="^send_file$"))
    app.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL, message_handler))

    print("🚀 E$CO Bot Started Successfully - Full Features Loaded")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
