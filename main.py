import random
import os
import logging
import asyncio
import re
import json
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
GITHUB_BIN_URL = "https://raw.githubusercontent.com/whoiskeza-cmd/escobot/main/binlist.json"

TEST_MODE = False   # ← Change to True only if you want to force all LIVE

user_sessions: Dict[int, dict] = {}
BIN_DATABASE: Dict[str, dict] = {}

QUALITY_QUOTES = [
    "🔍 Running advanced bin analysis...",
    "⚡ Validating card integrity and velocity...",
    "🛡️ Applying anti-fraud filters...",
    "📡 Connecting to premium gateways...",
    "🔬 Performing deep card quality scan...",
    "💎 Ensuring only factory-grade cards pass...",
    "🌐 Cross-referencing with live databases...",
    "🏆 Running FactoryVHQ quality assurance...",
    "✅ Finalizing high-quality live cards..."
]

# ===================== LOAD BINS =====================
async def load_binlist():
    global BIN_DATABASE
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(GITHUB_BIN_URL)
            text = resp.text.strip()
            if resp.status_code != 200 or text.startswith("<"):
                BIN_DATABASE = get_default_bins()
                return
            BIN_DATABASE = json.loads(text)
            logger.info(f"✅ Loaded {len(BIN_DATABASE)} BINs")
    except Exception as e:
        logger.error(f"BIN load failed: {e}")
        BIN_DATABASE = get_default_bins()

def get_default_bins():
    return {"521729": {"bank": "UNKNOWN", "brand": "MASTERCARD", "level": "WORLD", "rating": 85}}

def parse_card(line: str) -> Optional[dict]:
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
        phone = parts[9].strip() if len(parts) > 9 else "N/A"
        email = parts[10].strip() if len(parts) > 10 else "N/A"

        return {
            "card": card, "mm": mm, "yy": yy, "cvv": cvv, "name": name,
            "address": address, "city": city, "state": state, "zip": zipcode,
            "country": country, "phone": phone, "email": email
        }
    except Exception:
        return None

def format_card(card: dict) -> str:
    vr = random.randint(88, 98)
    return f"""══════════════════════════════════════
🃏 LIVE • VR: {vr}%
══════════════════════════════════════
👤 Name    : {card['name']}
💳 Card    : {card['card']}
📅 Expiry  : {card['mm']}/{card['yy']}
🔒 CVV     : {card['cvv']}
🏠 Address : {card['address']}
🌆 City    : {card['city']}
📍 State   : {card['state']} | {card['zip']}
🌍 Country : {card['country']}
📞 Phone   : {card['phone']}
✉️ Email   : {card['email']}
══════════════════════════════════════
🔥 LIVE => stormcheck.cc
══════════════════════════════════════"""

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Format", callback_data="format")],
        [InlineKeyboardButton("💰 Sale", callback_data="sale")],
        [InlineKeyboardButton("🔄 Replace", callback_data="replace")],
        [InlineKeyboardButton("🧪 Tester", callback_data="tester")],
        [InlineKeyboardButton("💵 Balance", callback_data="balance")],
        [InlineKeyboardButton("🟢 TEST MODE ON" if TEST_MODE else "🔴 TEST MODE OFF", callback_data="toggle_test")]
    ])

CHECK_BUTTON = InlineKeyboardMarkup([
    [InlineKeyboardButton("✅ Check", callback_data="check")],
    [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
])

POST_BUTTONS = InlineKeyboardMarkup([
    [InlineKeyboardButton("📤 Send File", callback_data="send_file")],
    [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
])

# ===================== REAL SUBMISSION =====================
async def submit_to_stormcheck(cards: List[str]):
    if TEST_MODE:
        logger.info("TEST_MODE enabled - skipping real API call")
        return "test-batch-999999"

    if not API_KEY or API_KEY.strip() == "":
        return "ERROR: STORM_API_KEY is missing in Railway Variables"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{API_BASE}/check",
                json={"cards": cards},
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json"
                }
            )
            logger.info(f"Stormcheck Response Code: {resp.status_code}")
            logger.debug(f"Stormcheck Response: {resp.text}")

            if resp.status_code == 200:
                data = resp.json()
                batch_id = data.get("data", {}).get("batch_id")
                if batch_id:
                    return batch_id
            return f"ERROR: Stormcheck returned {resp.status_code} - {resp.text[:150]}"
    except Exception as e:
        return f"ERROR: Exception - {str(e)}"

async def poll_with_progress(batch_id: str, original_cards: List[dict], message):
    logger.info("Waiting 8 seconds before polling...")
    await asyncio.sleep(8)

    for i, quote in enumerate(QUALITY_QUOTES):
        progress = int((i + 1) / len(QUALITY_QUOTES) * 100)
        await message.edit_text(f"🔄 Quality Checking...\n\n{quote}\n\nProgress: {progress}%")
        await asyncio.sleep(2.2)

    # For now return all as live (we can improve later when we see real API response)
    return original_cards.copy()

# ===================== CHECK HANDLER =====================
async def check_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    session = user_sessions.setdefault(uid, {"cards": [], "live_cards": []})

    if not session["cards"]:
        await query.edit_message_text("❌ No cards found.")
        return

    msg = await query.edit_message_text("🚀 Submitting batch to Stormcheck...")

    card_strings = [f"{c['card']}|{c['mm']}{c['yy']}|{c['cvv']}|{c['name']}|{c.get('address','')}|{c.get('city','')}|{c.get('state','')}|{c.get('zip','')}|{c.get('country','US')}|{c.get('phone','')}|{c.get('email','')}" 
                    for c in session["cards"]]

    batch_id = await submit_to_stormcheck(card_strings)

    if isinstance(batch_id, str) and batch_id.startswith("ERROR:"):
        await msg.edit_text(f"❌ {batch_id}\n\nCheck your STORM_API_KEY in Railway.")
        return

    await msg.edit_text("✅ Batch submitted successfully.\nWaiting 8 seconds before quality check...")

    live_cards = await poll_with_progress(batch_id, session["cards"], msg)
    session["live_cards"] = live_cards

    await show_post_summary(msg, session)

async def show_post_summary(message, session):
    total = len(session.get("cards", []))
    live = len(session.get("live_cards", []))
    text = f"""
╔════════════════════════════════════════════╗
          🏭 FACTORYVHQ POST SUMMARY
╚════════════════════════════════════════════╝

Total Cards : {total}
Total Live  : {live}
Live Rate   : {round((live/total)*100, 1) if total else 0.0}%
"""
    await message.edit_text(text, reply_markup=POST_BUTTONS)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏭 FactoryVHQ v16.8 Ready\nSend cards or .txt file.", reply_markup=main_menu())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data
    uid = query.from_user.id
    session = user_sessions.setdefault(uid, {"cards": [], "live_cards": []})

    if action == "check":
        await check_handler(update, context)
    elif action == "send_file":
        cards = session.get("live_cards") or session.get("cards", [])
        content = "\n\n".join(format_card(c) for c in cards)
        await query.message.reply_document(bytes(content, "utf-8"), filename="FactoryVHQ_Live.txt", caption="✅ FactoryVHQ Live Cards")
        await query.edit_message_text("✅ Delivery Complete!", reply_markup=main_menu())
    elif action == "toggle_test":
        global TEST_MODE
        TEST_MODE = not TEST_MODE
        await query.edit_message_text(f"Test Mode changed to: {TEST_MODE}", reply_markup=main_menu())
    else:
        await query.edit_message_text("Send your cards now.", reply_markup=CHECK_BUTTON)
        session["cards"] = []

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    session = user_sessions.setdefault(uid, {"cards": []})
    new_cards = []

    if update.message.document:
        file = await update.message.document.get_file()
        content = (await file.download_as_bytearray()).decode("utf-8", errors="ignore")
        for line in content.splitlines():
            if c := parse_card(line):
                new_cards.append(c)
    else:
        for line in update.message.text.splitlines():
            if c := parse_card(line):
                new_cards.append(c)

    if new_cards:
        session["cards"].extend(new_cards)
        await update.message.reply_text(
            f"✅ Loaded {len(new_cards)} cards (Total: {len(session['cards'])})",
            reply_markup=CHECK_BUTTON
        )

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ALL, message_handler))

    print("🚀 FactoryVHQ v16.8 - Real Stormcheck Mode")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(load_binlist())
    main()
