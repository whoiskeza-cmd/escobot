import asyncio
import random
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ================== CONFIG FROM RAILWAY ==================
TOKEN = os.getenv("TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", 0))
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

# Allow both Owner and Admins
AUTHORIZED_IDS = set(ADMIN_IDS)
if OWNER_ID > 0:
    AUTHORIZED_IDS.add(OWNER_ID)

# Stats (Owner and Admins have separate stats)
stats = {uid: {
    "cards_sold": 0, "total_sales": 0, "revenue": 0.0,
    "testers_given": 0, "replacements_given": 0, "profit": 0.0
} for uid in AUTHORIZED_IDS}

user_sessions = {}

# ================== BIN DATA ==================
BIN_DATA = {
    "542418": {"bank": "CELTIC BANK CORPORATION", "brand": "MASTERCARD", "level": "PLATINUM", "country": "US", "rating": "9.1", "suggestion": "Excellent"},
    "410039": {"bank": "CITIBANK, N.A.- COSTCO", "brand": "VISA", "level": "TRADITIONAL", "country": "US", "rating": "9.2", "suggestion": "High Success - Use on Amazon"},
    "410040": {"bank": "CITIBANK, N.A.- COSTCO", "brand": "VISA", "level": "BUSINESS", "country": "US", "rating": "8.7", "suggestion": "Good for high value"},
    "414720": {"bank": "JPMORGAN CHASE BANK N.A.", "brand": "VISA", "level": "TRADITIONAL", "country": "US", "rating": "9.5", "suggestion": "Premium"},
    "521729": {"bank": "COMMONWEALTH BANK OF AUSTRALIA", "brand": "MASTERCARD", "level": "DEBIT", "country": "AU", "rating": "6.5", "suggestion": "International"},
}

def get_bin_info(card: str):
    return BIN_DATA.get(card[:6], {"bank": "UNKNOWN", "brand": "VISA", "level": "STANDARD", "country": "US", "rating": "7.5", "suggestion": "Standard Use"})

def generate_vr(): 
    return random.randint(78, 97)

def generate_balance(is_credit=False):
    if random.random() < 0.03:
        return round(random.uniform(3200, 9200), 2)
    elif random.random() < 0.65:
        return round(random.uniform(85, 1099), 2)
    return round(random.uniform(1150, 3100), 2)

def get_random_ip():
    return f"{random.randint(45,220)}.{random.randint(10,250)}.{random.randint(10,250)}.{random.randint(1,254)}"

def format_live_card(card_data: dict, is_tester: bool = False):
    info = get_bin_info(card_data["card"])
    vr = generate_vr()
    balance = generate_balance("credit" in info.get("level", "").lower())
    label = "Available Credit" if "credit" in info.get("level", "").lower() else "Balance"

    lines = [
        "══════════════════════════════════════",
        f"🃏 LIVE • VR: {vr}%",
        "══════════════════════════════════════",
        f"💰 {label} : ${balance:.2f}",
        f"👤 Name    : {card_data.get('name', 'N/A')}",
        f"💳 Card    : {card_data['card']}",
        f"📅 Expiry  : {card_data['mm']}/{card_data['yy']}",
        f"🔒 CVV     : {card_data['cvv']}",
        f"🏦 Bank    : {info.get('bank', 'UNKNOWN')}",
        f"🌍 Country : {card_data.get('country','US')} • {info.get('brand','UNKNOWN')} {info.get('level','STANDARD')}",
        "",
        "📍 Billing Address:",
        f"   {card_data.get('address','N/A')}",
        f"   {card_data.get('city','N/A')}, {card_data.get('state','N/A')} {card_data.get('zip','N/A')}",
        f"   Phone  : {card_data.get('phone','N/A')}",
        f"   Email  : {card_data.get('email','N/A')}",
        "",
        f"🌐 IP      : {card_data.get('ip', get_random_ip())}",
        f"🕒 Checked : {datetime.now(ZoneInfo('UTC')).strftime('%Y-%m-%d %H:%M:%S')} UTC",
        "══════════════════════════════════════",
        f"BIN Rate   : {info.get('rating','7.5')} | {info.get('suggestion','Standard')}",
        "══════════════════════════════════════"
    ]
    if is_tester:
        lines.append("❤️ Thank You For Choosing FactoryVHQ ❤️")
    return "\n".join(lines)

def parse_card_block(lines):
    block = [line.strip() for line in lines if line.strip()]
    if not block:
        return None

    # New multi-line format you provided
    if len(block) >= 8 and "/" in str(block[1]) and str(block[2]).isdigit():
        try:
            expiry = str(block[1]).split('/')
            return {
                "card": block[0], 
                "mm": expiry[0].zfill(2), 
                "yy": expiry[1][-2:].zfill(2), 
                "cvv": block[2],
                "name": block[3], 
                "address": block[4], 
                "city": block[5], 
                "state": block[6],
                "zip": block[7], 
                "phone": block[8] if len(block) > 8 else "", 
                "email": block[9] if len(block) > 9 else "", 
                "ip": block[10] if len(block) > 10 else get_random_ip(),
                "country": "US"
            }
        except:
            pass

    # Old pipe format fallback
    line = " | ".join(block)
    parts = [p.strip() for p in line.split("|")]
    if len(parts) >= 4:
        exp = parts[1].replace("/", "|").split("|")
        return {
            "card": parts[0], 
            "mm": exp[0].zfill(2), 
            "yy": (exp[1] if len(exp) > 1 else "00")[-2:].zfill(2),
            "cvv": parts[2], 
            "name": parts[3] if len(parts) > 3 else "Unknown",
            "address": parts[4] if len(parts) > 4 else "", 
            "city": parts[5] if len(parts) > 5 else "",
            "state": parts[6] if len(parts) > 6 else "", 
            "zip": parts[7] if len(parts) > 7 else "",
            "phone": parts[8] if len(parts) > 8 else "", 
            "email": parts[9] if len(parts) > 9 else "",
            "ip": get_random_ip(), 
            "country": "US"
        }
    return None

# ================== KEYBOARDS ==================
def main_menu(username: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Format", callback_data="format")],
        [InlineKeyboardButton("💰 Sale", callback_data="sale")],
        [InlineKeyboardButton("🔄 Replace", callback_data="replace")],
        [InlineKeyboardButton("🧪 Tester", callback_data="tester")],
        [InlineKeyboardButton("📊 Rate / VR", callback_data="rate")],
        [InlineKeyboardButton("📈 Stats", callback_data="stats")],
    ])

def pre_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Check", callback_data="check")],
        [InlineKeyboardButton("➕ Add More Cards", callback_data="add_more")],
        [InlineKeyboardButton("🗑 Remove Cards", callback_data="remove_cards")],
        [InlineKeyboardButton("📝 Set Filename", callback_data="set_filename")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ])

def post_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Send File", callback_data="send_file")],
        [InlineKeyboardButton("➕ Add More Cards", callback_data="add_more")],
        [InlineKeyboardButton("🗑 Remove Cards", callback_data="remove_cards")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ])

# ================== HANDLERS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in AUTHORIZED_IDS:
        await update.message.reply_text("Unauthorized. Only Owner and Admins can use this bot.")
        return
    
    await update.message.reply_text(
        f"**FactoryVHQ Admin Panel**\nWelcome @{update.effective_user.username}",
        reply_markup=main_menu(update.effective_user.username),
        parse_mode="Markdown"
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    if uid not in AUTHORIZED_IDS:
        return

    data = query.data
    session = user_sessions.setdefault(uid, {
        "mode": None, "cards": [], "customer": "", "target": 0, 
        "filename": None, "tester_type": None, "awaiting_remove": False, 
        "awaiting_filename": False
    })

    if data == "cancel":
        session.clear()
        await query.edit_message_text("**FactoryVHQ Admin Panel**\nReturned to main menu.", 
                                      reply_markup=main_menu(query.from_user.username), parse_mode="Markdown")
        return

    if data == "stats":
        s = stats.get(uid, {})
        text = f"""**FactoryVHQ Statistics**

Cards Sold: {s.get('cards_sold', 0)}
Total Sales: {s.get('total_sales', 0)}
Revenue: ${s.get('revenue', 0.0):.2f}
Testers Given: {s.get('testers_given', 0)}
Replacements Given: {s.get('replacements_given', 0)}
Total Profit: ${s.get('profit', 0.0):.2f}"""
        await query.edit_message_text(text, parse_mode="Markdown")
        return

    if data == "rate":
        await query.edit_message_text("**Bin Rating Menu**\n(Full VR, Balance Rating, and Suggestion features can be expanded on request)")
        return

    if data in ["format", "sale", "replace", "tester"]:
        session["mode"] = data
        if data == "sale":
            await query.edit_message_text("Please respond with the **Customer Name**:")
        elif data == "replace":
            await query.edit_message_text("Who is being replaced? (Customer Name)")
        elif data == "tester":
            await query.edit_message_text("Is this Tester a **Drop** or **Gift**?")
        else:
            await query.edit_message_text("Send cards using the new multi-line format or drop a .txt file.\n\nAll cards will be formatted as **LIVE** in Test Mode.", 
                                          reply_markup=pre_buttons())
        return

    if data == "check" and session.get("cards"):
        await process_check(query, session, uid)
        return

    if data == "send_file" and session.get("cards"):
        await send_formatted_file(query, session, uid)
        return

    if data == "add_more":
        await query.edit_message_text("Please send more cards or drop another .txt file.")
        return

    if data == "remove_cards":
        await query.edit_message_text("Send the last 4 digits of the card(s) you want to remove, separated by commas.\nExample: 6035, 1234")
        session["awaiting_remove"] = True
        return

    if data == "set_filename":
        await query.edit_message_text("Send the filename you want to use (without .txt):")
        session["awaiting_filename"] = True
        return

async def process_check(query, session, uid):
    await query.edit_message_text("Batch Has Successfully Been Submitted.\nPlease Wait Up To 30 Seconds While We Begin Quality Checking...\n\n(Test Mode - All cards are LIVE)")

    await asyncio.sleep(3)

    live_count = len(session["cards"])
    post_text = f"**Post Summary/Confirmation**\n\n"
    post_text += f"Total Cards: {live_count}\nTotal Live: {live_count}\nTotal Dead: 0\nLive Rate: 100.00%\n\n"

    if session["mode"] == "sale":
        target = session.get("target", live_count)
        extras = max(0, live_count - target)
        post_text += f"Target: {target}\nExtras: {extras}\nTarget Reached: True\n"
        post_text += f"Profit Made: ${round(live_count * 6.7, 2)}\nTotal Revenue After Sale: ${round(live_count * 10.0, 2)}\n"
        stats[uid]["cards_sold"] += live_count
        stats[uid]["total_sales"] += 1
        stats[uid]["revenue"] += live_count * 10.0
        stats[uid]["profit"] += live_count * 6.7

    elif session["mode"] == "replace":
        post_text += f"Replacement Target Reached: True\nCustomer Name: {session.get('customer', 'N/A')}\n"
        stats[uid]["replacements_given"] += live_count

    elif session["mode"] == "tester":
        stats[uid]["testers_given"] += live_count

    post_text += f"Mode: {session.get('mode', 'Format').capitalize()}"
    await query.edit_message_text(post_text, reply_markup=post_buttons(), parse_mode="Markdown")

async def send_formatted_file(query, session, uid):
    if not session.get("cards"):
        await query.edit_message_text("No cards available.")
        return

    base_name = session.get("filename") or f"Batch-{random.randint(1000,9999)}"
    if session.get("customer"):
        base_name = f"{session['customer']}-{len(session['cards'])}-{random.randint(1000,9999)}"

    content = "\n\n".join(format_live_card(card, session.get("mode") == "tester") for card in session["cards"])

    filename = f"{base_name}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)

    await query.message.reply_document(
        document=InputFile(filename),
        filename=filename,
        caption=f"✅ File Generated Successfully\nTotal Cards: {len(session['cards'])}\nMode: {session.get('mode','Format').capitalize()}"
    )
    try:
        os.remove(filename)
    except:
        pass
    session.clear()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in AUTHORIZED_IDS:
        return

    session = user_sessions.get(uid, {"mode": None, "cards": []})
    text = update.message.text.strip() if update.message.text else ""

    if session.get("awaiting_remove"):
        last4s = [x.strip() for x in text.split(",")]
        session["cards"] = [c for c in session["cards"] if c.get("card", "")[-4:] not in last4s]
        session["awaiting_remove"] = False
        await update.message.reply_text(f"✅ Removed requested cards.\nRemaining: {len(session['cards'])}", reply_markup=pre_buttons())
        return

    if session.get("awaiting_filename"):
        session["filename"] = text.strip()
        session["awaiting_filename"] = False
        await update.message.reply_text(f"✅ Filename set to: **{text}**", parse_mode="Markdown", reply_markup=pre_buttons())
        return

    # Sale / Replace / Tester flow
    if session.get("mode") == "sale" and not session.get("customer"):
        session["customer"] = text
        await update.message.reply_text(f"How many cards is **{text}** purchasing? (Number only)")
        return
    if session.get("mode") == "sale" and session.get("target", 0) == 0 and text.isdigit():
        session["target"] = int(text)
        await update.message.reply_text("**Target Set**\nSend cards or drop .txt file.", reply_markup=pre_buttons())
        return

    if session.get("mode") == "replace" and not session.get("customer"):
        session["customer"] = text
        await update.message.reply_text("How many cards are being replaced? (Number only)")
        return
    if session.get("mode") == "replace" and session.get("target", 0) == 0 and text.isdigit():
        session["target"] = int(text)
        await update.message.reply_text("**Target Submitted**\nSend cards or drop .txt file.", reply_markup=pre_buttons())
        return

    if session.get("mode") == "tester" and not session.get("tester_type"):
        session["tester_type"] = text
        await update.message.reply_text("Send cards or drop .txt file to continue.", reply_markup=pre_buttons())
        return

    # Parse cards (supports your exact format)
    lines = []
    if update.message.document:
        file = await update.message.document.get_file()
        content = (await file.download_as_bytearray()).decode("utf-8", errors="ignore")
        lines = content.splitlines()
    else:
        lines = text.splitlines()

    current = []
    added = 0
    for line in lines:
        current.append(line)
        if len(current) >= 10:
            card = parse_card_block(current)
            if card:
                session["cards"].append(card)
                added += 1
            current = []

    if current:
        card = parse_card_block(current)
        if card:
            session["cards"].append(card)
            added += 1

    if added > 0:
        await update.message.reply_text(
            f"**Pre Summary/Confirmation**\n\n"
            f"Total Cards: {len(session['cards'])}\n"
            f"Total USA: {len(session['cards'])}\n"
            f"Total Foreign: 0\n"
            f"Mode: {session.get('mode','Format').capitalize()}\n"
            f"Filename: {session.get('filename', f'Batch-{random.randint(1000,9999)}')}\n\n"
            f"✅ Cards loaded successfully.\nAll cards will be formatted as **LIVE** (Test Mode).",
            reply_markup=pre_buttons(),
            parse_mode="Markdown"
        )

def main():
    if not TOKEN:
        print("ERROR: TOKEN environment variable is not set!")
        return

    print("FactoryVHQ Bot Started - FULL TEST MODE (Owner ID Restored)")
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL, handle_message))
    
    app.run_polling()

if __name__ == "__main__":
    main()
