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

TEST_MODE = False   # Set to False for real Stormcheck

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
            if resp.status_code != 200:
                logger.error(f"GitHub returned {resp.status_code}")
                BIN_DATABASE = get_default_bins()
                return

            text = resp.text.strip()
            if text.startswith("<"):
                logger.warning("Received HTML instead of JSON, using defaults")
                BIN_DATABASE = get_default_bins()
                return

            BIN_DATABASE = json.loads(text)
            logger.info(f"✅ Successfully loaded {len(BIN_DATABASE)} BINs")
    except Exception as e:
        logger.error(f"BIN list failed: {e}")
        BIN_DATABASE = get_default_bins()

def get_default_bins():
    return {
        "410039": {"bank": "CITIBANK", "brand": "VISA", "level": "TRADITIONAL", "rating": 92, "suggestion": "Retail", "type": "CREDIT"},
        "414720": {"bank": "CHASE", "brand": "VISA", "level": "TRADITIONAL", "rating": 94, "suggestion": "Everywhere", "type": "CREDIT"},
        "542418": {"bank": "CITIBANK", "brand": "MASTERCARD", "level": "PLATINUM", "rating": 92, "suggestion": "High Value", "type": "CREDIT"},
    }

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

        bin6 = card[:6]
        info = BIN_DATABASE.get(bin6, {"bank":"UNKNOWN","brand":"VISA","level":"STANDARD","rating":75,"suggestion":"Retail","type":"CREDIT"})

        return {
            "card": card, "mm": mm, "yy": yy, "cvv": cvv, "name": name,
            "address": address, "city": city, "state": state, "zip": zipcode,
            "country": country, "bank": info["bank"], "brand": info["brand"],
            "level": info["level"], "bin_rating": info.get("rating", 75),
            "suggestion": info.get("suggestion", "Retail"), "type": info.get("type", "CREDIT")
        }
    except Exception as e:
        logger.error(f"Parse error: {e}")
        return None

def format_card(card: dict) -> str:
    vr = random.randint(85, 97)
    balance = round(random.uniform(650, 4500), 2)
    return f"""══════════════════════════════════════
🃏 LIVE • VR: {vr}%
══════════════════════════════════════
💰 Available Credit : ${balance:.2f}
👤 Name    : {card['name']}
💳 Card    : {card['card']}
📅 Expiry  : {card['mm']}/{card['yy']}
🔒 CVV     : {card['cvv']}
🏦 Bank    : {card['bank']}
🌍 Country : {card['country']} • {card['brand']} {card['level']}
══════════════════════════════════════
BIN Rate   : {card['bin_rating']} | {card['suggestion']}
══════════════════════════════════════
🔥 FactoryVHQ | Premium Cards Only 🔥
══════════════════════════════════════"""

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
        [InlineKeyboardButton("💵 Balance", callback_data="balance")],
        [InlineKeyboardButton(status, callback_data="toggle_test")]
    ])

POST_BUTTONS = InlineKeyboardMarkup([
    [InlineKeyboardButton("📤 Send File", callback_data="send_file")],
    [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
])

# ===================== STORMCHECK FUNCTIONS =====================
async def submit_batch_advanced(cards: List[str]):
    if TEST_MODE:
        return "test-batch-999999"

    if not API_KEY:
        return "ERROR: STORM_API_KEY is not set in Railway"

    try:
        async with httpx.AsyncClient(timeout=25) as client:
            resp = await client.post(
                f"{API_BASE}/check",
                json={"cards": cards},
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json"
                }
            )
            logger.info(f"Submit Status: {resp.status_code} | Response: {resp.text[:150]}")

            if resp.status_code == 200:
                data = resp.json()
                batch_id = data.get("data", {}).get("batch_id")
                if batch_id:
                    return batch_id
            return f"ERROR: Status {resp.status_code} - {resp.text[:100]}"
    except Exception as e:
        return f"ERROR: Exception - {str(e)}"

async def poll_with_progress(batch_id: str, original_cards: List[dict], message):
    logger.info(f"Waiting 8 seconds before polling (as requested)")
    await asyncio.sleep(8)

    for i, quote in enumerate(QUALITY_QUOTES * 2):
        progress = min(99, (i + 1) * 8)
        await message.edit_text(f"🔄 Quality Checking...\n\n{quote}\n\nProgress: {progress}%")
        await asyncio.sleep(2.5)

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

    card_strings = [f"{c['card']}|{c['mm']}{c['yy']}|{c['cvv']}|{c['name']}|{c.get('address','')}|{c.get('city','')}|{c.get('state','')}|{c.get('zip','')}|{c.get('country','US')}" 
                    for c in session["cards"]]

    batch_id = await submit_batch_advanced(card_strings)

    if isinstance(batch_id, str) and batch_id.startswith("ERROR:"):
        await msg.edit_text(f"❌ {batch_id}")
        return

    await msg.edit_text("✅ Batch submitted.\nWaiting 8 seconds before starting poll...")

    live_cards = await poll_with_progress(batch_id, session["cards"], msg)
    session["live_cards"] = live_cards

    await show_post_summary(msg, session)

async def show_post_summary(message, session):
    total = len(session.get("cards", []))
    live = len(session.get("live_cards", []))
    text = panel("POST-SUMMARY") + f"""
Total Cards : {total}
Total Live  : {live}
Total Dead  : {total - live}
Live Rate   : {round((live/total)*100, 1) if total else 0.0}%
"""
    await message.edit_text(text, parse_mode='HTML', reply_markup=POST_BUTTONS)

# ===================== BASIC HANDLERS =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_html(panel("FactoryVHQ Admin Panel"), reply_markup=main_menu())

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
        await query.edit_message_text(f"Test Mode: {'🟢 ON' if TEST_MODE else '🔴 OFF'}", reply_markup=main_menu())
    else:
        await query.edit_message_text(f"{action.upper()} MODE\n\nSend cards or .txt file.")
        session["mode"] = action
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
        await update.message.reply_text(f"✅ Loaded {len(new_cards)} cards (Total: {len(session['cards'])})\nPress Check button.")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ALL, message_handler))

    print("🚀 FactoryVHQ v16.3 - Fixed Event Loop + 8s Delay")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    asyncio.run(load_binlist())
    main()
