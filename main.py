import asyncio
import random
import os
from datetime import datetime, timezone
from typing import Dict, List

import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ================= RAILWAY ENVIRONMENT VARIABLES =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
STORM_API_KEY = os.getenv("STORM_API_KEY")
OWNER_ID = int(os.getenv("USER_ID"))

API_BASE = "https://api.storm.gift/api/v1"

if not BOT_TOKEN or not STORM_API_KEY or not OWNER_ID:
    raise ValueError("BOT_TOKEN, STORM_API_KEY, and USER_ID must be set in Railway variables.")

# ===================== GLOBAL SETTINGS =====================
TEST_MODE = False  # Toggle with /testmode command

stats = {
    "cards_sold": 0, "total_sales": 0, "revenue": 0.0,
    "testers_given": 0, "replacements_given": 0, "profit": 0.0,
    "card_cost": 1.40, "sale_price": 5.00
}

BIN_DATA: Dict[str, dict] = {
    "410039": {"bank": "CITIBANK, N.A.- COSTCO", "brand": "VISA", "level": "TRADITIONAL", "vr": 85, "balance": 92, "suggestion": "Amazon, Walmart"},
    "410040": {"bank": "CITIBANK, N.A.- COSTCO", "brand": "VISA", "level": "BUSINESS", "vr": 78, "balance": 88, "suggestion": "High-end stores"},
    "414720": {"bank": "JPMORGAN CHASE BANK N.A.", "brand": "VISA", "level": "TRADITIONAL", "vr": 92, "balance": 95, "suggestion": "Everywhere"},
    "414740": {"bank": "JPMORGAN CHASE BANK N.A.", "brand": "VISA", "level": "TRADITIONAL", "vr": 89, "balance": 91, "suggestion": "Retail"},
    "440066": {"bank": "BANK OF AMERICA", "brand": "VISA", "level": "TRADITIONAL", "vr": 84, "balance": 87, "suggestion": "General"},
    "483312": {"bank": "JPMORGAN CHASE", "brand": "VISA", "level": "DEBIT", "vr": 65, "balance": 72, "suggestion": "Low Risk"},
    "483316": {"bank": "JPMORGAN CHASE", "brand": "VISA", "level": "DEBIT", "vr": 68, "balance": 75, "suggestion": "Low Risk"},
    "542418": {"bank": "CITIBANK N.A.", "brand": "MASTERCARD", "level": "PLATINUM", "vr": 88, "balance": 90, "suggestion": "High Value"},
}

user_sessions: Dict[int, dict] = {}

# ===================== HELPERS =====================
def get_random_ip() -> str:
    return f"{random.randint(25,220)}.{random.randint(10,250)}.{random.randint(10,250)}.{random.randint(10,250)}"

def generate_balance(is_credit: bool) -> tuple:
    if random.random() < 0.03:
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
        info = BIN_DATA.get(bin6, {"bank":"UNKNOWN","brand":"VISA","level":"STANDARD","vr":75,"balance":80,"suggestion":"Retail"})

        return {
            "card": card, "mm": mm, "yy": yy[-2:], "cvv": cvv, "name": name,
            "address": address, "city": city, "state": state, "zip": zipcode,
            "country": country, "phone": phone, "email": email,
            "bank": info["bank"], "brand": info["brand"], "level": info["level"],
            "bin_rating": info.get("vr", 75), "suggestion": info.get("suggestion", "Retail"),
            "last4": card[-4:]
        }
    except:
        return None

def format_live_card(card: dict, is_tester: bool = False) -> str:
    vr = random.randint(68, 97)
    balance, label = generate_balance("CREDIT" in card.get("level", ""))
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

async def submit_batch(cards: List[str]) -> str:
    if TEST_MODE:
        return "test-batch-12345"
    headers = {"Authorization": f"Bearer {STORM_API_KEY}", "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{API_BASE}/check", headers=headers, json={"cards": cards}) as resp:
            data = await resp.json()
            return data.get("data", {}).get("batch_id", "unknown")

async def poll_batch(batch_id: str, max_polls: int) -> int:
    if TEST_MODE:
        await asyncio.sleep(3)
        return len(batch_id.split("-"))  # Simulate all cards as LIVE in test mode
    headers = {"Authorization": f"Bearer {STORM_API_KEY}"}
    for _ in range(max_polls):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_BASE}/check/{batch_id}", headers=headers) as resp:
                data = await resp.json()
                if not data.get("data", {}).get("is_checking", True):
                    return data.get("data", {}).get("accepted_count", 0)
        await asyncio.sleep(4)
    return 0

def main_menu() -> InlineKeyboardMarkup:
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

# ===================== COMMAND HANDLERS =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Access Denied.")
        return
    await update.message.reply_html(
        f"<b>E$CO Admin Panel</b>\n\nWelcome @{update.effective_user.username}",
        reply_markup=main_menu()
    )

async def toggle_test_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    global TEST_MODE
    TEST_MODE = not TEST_MODE
    status = "ENABLED (All cards will be marked LIVE)" if TEST_MODE else "DISABLED (Real API will be used)"
    await update.message.reply_text(f"🔧 Test Mode is now **{status}**", parse_mode='HTML')
    await start(update, context)

# ===================== BUTTON & MESSAGE HANDLERS =====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.callback_query.answer("Access Denied.", show_alert=True)
        return

    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    action = query.data
    session = user_sessions.setdefault(uid, {
        "mode": None, "cards": [], "customer": None, "target": 0,
        "filename": None, "tester_type": None, "bin": None, "rating_type": None
    })

    if action == "cancel":
        user_sessions.pop(uid, None)
        await query.edit_message_text("✅ Returned to Admin Panel.", reply_markup=main_menu())
        return

    if action == "toggle_test":
        await toggle_test_mode(update, context)
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
    elif action == "balance":
        await query.edit_message_text("Your Available Storm Credits Are **∞** (Admin)")
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
    elif action == "rate":
        await query.edit_message_text("🛠️ Rate BIN Menu", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Set Bin VR", callback_data="set_vr")],
            [InlineKeyboardButton("Rate Bin", callback_data="rate_bin")],
            [InlineKeyboardButton("Set Bin Balance Rating", callback_data="set_balance")],
            [InlineKeyboardButton("Bin Use Suggestion", callback_data="bin_suggestion")],
            [InlineKeyboardButton("← Back", callback_data="cancel")]
        ]))

    elif action in ["set_vr", "rate_bin", "set_balance", "bin_suggestion"]:
        session["rating_type"] = action
        await query.edit_message_text("Send the 6-digit BIN you want to rate:")

    elif action == "remove":
        await query.edit_message_text("Send the last 4 digits of the card(s) you want to remove, separated by commas.\nExample: 0328,7675,1774")

    elif action == "set_filename":
        await query.edit_message_text("Send the filename you want to use (without .txt):")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    text = update.message.text.strip()
    uid = update.effective_user.id
    session = user_sessions.get(uid)
    if not session or not session.get("mode"): return

    mode = session["mode"]

    # Set Filename
    if session.get("mode") == "set_filename":
        session["filename"] = text.strip()
        await update.message.reply_text(f"✅ Filename set to: **{session['filename']}**", parse_mode='HTML')
        session["mode"] = session.get("previous_mode", "format")
        # Re-show summary
        total = len(session.get("cards", []))
        usa = sum(1 for c in session.get("cards", []) if c.get("country", "US").upper() == "US")
        foreign = total - usa
        keyboard = [
            [InlineKeyboardButton("Check", callback_data="check")],
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
Target: {session.get('target', 'N/A')}
Customer: {session.get('customer', 'N/A')}
Filename: {session.get('filename', f'Batch-{random.randint(1000,9999)}')}
"""
        await update.message.reply_text(pre_text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # Remove Cards by Last 4
    if any(x.isdigit() and len(x.strip()) == 4 for x in text.replace(" ", "").split(",")):
        to_remove = {x.strip() for x in text.split(",") if x.strip().isdigit() and len(x.strip()) == 4}
        original = len(session.get("cards", []))
        session["cards"] = [c for c in session.get("cards", []) if c.get("last4") not in to_remove]
        removed = original - len(session.get("cards", []))
        await update.message.reply_text(f"✅ Removed {removed} card(s).")

    # Rate BIN logic
    if mode in ["set_vr", "rate_bin", "set_balance", "bin_suggestion"] and not session.get("bin"):
        bin6 = text[:6]
        if bin6.isdigit():
            session["bin"] = bin6
            prompts = {
                "set_vr": f"You have selected BIN **{bin6}**\n\nWhat do you want to set the VR rating as? (0-100)",
                "rate_bin": f"You have selected BIN **{bin6}**\n\nRate this BIN (0-100):",
                "set_balance": f"You have selected BIN **{bin6}**\n\nWhat do you want to set the Balance Rating as? (0-100)",
                "bin_suggestion": f"You have selected BIN **{bin6}**\n\nEnter suggestion places to use this BIN:"
            }
            await update.message.reply_text(prompts.get(mode, "Enter value:"))
            return

    if session.get("bin") and session.get("rating_type"):
        bin6 = session["bin"]
        if bin6 not in BIN_DATA:
            BIN_DATA[bin6] = {"bank":"CUSTOM","brand":"VISA","level":"STANDARD","vr":75,"balance":80,"suggestion":"Retail"}

        if session["rating_type"] in ["set_vr", "rate_bin"]:
            BIN_DATA[bin6]["vr"] = int(text)
            await update.message.reply_text(f"✅ BIN {bin6} VR updated to {text}%")
        elif session["rating_type"] == "set_balance":
            BIN_DATA[bin6]["balance"] = int(text)
            await update.message.reply_text(f"✅ BIN {bin6} Balance Rating updated to {text}%")
        elif session["rating_type"] == "bin_suggestion":
            BIN_DATA[bin6]["suggestion"] = text
            await update.message.reply_text(f"✅ BIN {bin6} Suggestion updated.")

        session["bin"] = None
        session["rating_type"] = None
        await update.message.reply_text("✅ Rating updated. Returning to Admin Panel.", reply_markup=main_menu())
        return

    # Normal sequential input for Sale / Replace / Tester
    if mode == "sale" and not session.get("customer"):
        session["customer"] = text
        await update.message.reply_text("How many cards is this customer purchasing?")
        return
    if mode == "sale" and session.get("target", 0) == 0:
        session["target"] = int(text)
        await update.message.reply_text("Target Set. Send cards or drop .txt file.")
        return

    if mode == "replace" and not session.get("customer"):
        session["customer"] = text
        await update.message.reply_text("How many cards are being replaced?")
        return
    if mode == "replace" and session.get("target", 0) == 0:
        session["target"] = int(text)
        await update.message.reply_text("Target Submitted. Send cards or drop .txt file.")
        return

    if mode == "tester" and not session.get("tester_type"):
        session["tester_type"] = text
        await update.message.reply_text("Send cards or drop a .txt file to continue.")
        return

    # Parse incoming cards
    new_cards = []
    if update.message.document:
        file = await update.message.document.get_file()
        content = (await file.download_as_bytearray()).decode("utf-8")
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
        [InlineKeyboardButton("Check", callback_data="check")],
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
Target: {session.get('target', 'N/A')}
Customer: {session.get('customer', 'N/A')}
Filename: {session.get('filename', f'Batch-{random.randint(1000,9999)}')}
"""
    await update.message.reply_text(pre_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def check_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    session = user_sessions.get(uid)
    if not session or not session.get("cards"): return

    count = len(session["cards"])
    batch_id = await submit_batch([f"{c['card']}|{c['mm']}{c['yy']}|{c['cvv']}" for c in session["cards"]])

    polls = 3 if count <= 5 else 5 if count <= 10 else 8 if count <= 15 else (count // 2) + 3
    await query.edit_message_text(f"Batch Has Successfully Been Submitted (ID: {batch_id})\n\nPlease wait up to 30 seconds while we begin quality checking...")

    live_count = await poll_batch(batch_id, polls) if not TEST_MODE else count   # All cards LIVE in test mode
    dead_count = count - live_count
    live_rate = round((live_count / count * 100), 1) if count > 0 else 0.0
    extras = max(0, live_count - session.get("target", 0))
    target_reached = live_count >= session.get("target", 0)

    post_text = f"""Post Summary/Confirmation (Before Cards Are Sent Out)
Total Cards: {count}
Total Live: {live_count}
Total Dead: {dead_count}
LiveRate: {live_rate}%
Target Reached: {target_reached}
Extras: {extras}
Customer: {session.get('customer', 'N/A')}
Test Mode: {'ON (Simulated)' if TEST_MODE else 'OFF'}
"""

    keyboard = [
        [InlineKeyboardButton("Send File", callback_data="send_file")],
        [InlineKeyboardButton("Add More Cards", callback_data="add_more")],
        [InlineKeyboardButton("Remove Cards", callback_data="remove")],
        [InlineKeyboardButton("Set Filename", callback_data="set_filename")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ]

    await query.edit_message_text(post_text, reply_markup=InlineKeyboardMarkup(keyboard))

    # Update stats
    mode = session.get("mode")
    if mode == "sale":
        stats["cards_sold"] += live_count
        stats["total_sales"] += 1
        stats["revenue"] += live_count * stats["sale_price"]
        stats["profit"] += (live_count * stats["sale_price"]) - (count * stats["card_cost"])
    elif mode == "replace":
        stats["replacements_given"] += live_count
        stats["profit"] -= count * stats["card_cost"]
    elif mode == "tester":
        stats["testers_given"] += live_count

async def send_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    session = user_sessions.get(uid)
    if not session: return

    is_tester = session.get("mode") == "tester"
    content = "\n\n".join(format_live_card(c, is_tester) for c in session["cards"])
    
    filename_base = session.get("filename") or f"Batch-{random.randint(1000,9999)}"
    final_filename = f"{filename_base}-{len(session['cards'])}-{random.randint(1000,9999)}.txt"

    await query.message.reply_document(document=bytes(content, "utf-8"), filename=final_filename)
    await query.edit_message_text("✅ File sent successfully.")
    user_sessions.pop(uid, None)

# ===================== LAUNCH =====================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("testmode", toggle_test_mode))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CallbackQueryHandler(check_handler, pattern="^check$"))
    app.add_handler(CallbackQueryHandler(send_file_handler, pattern="^send_file$"))
    app.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL, message_handler))

    print("E$CO Admin Panel Bot Started | /testmode enabled | Full Feature Set")
    app.run_polling()

if __name__ == "__main__":
    main()
