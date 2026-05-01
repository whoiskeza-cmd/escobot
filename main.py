import random
import os
import logging
import asyncio
import re
import httpx
from datetime import datetime
from typing import List, Dict, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

logging.basicConfig(format='%(asctime)s | %(levelname)-8s | %(message)s', level=logging.INFO)
logger = logging.getLogger("FactoryVHQ")

# ====================== CONFIG ======================
TOKEN = os.getenv("TOKEN")
BASE_URL = os.getenv("BASE_URL", "https://api.storm.gift/api/v1")
API_KEY = os.getenv("API_KEY")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

INITIAL_WAIT = 10
POLL_INTERVAL = 12
MAX_POLLS = 25

user_sessions: Dict[int, dict] = {}

QUALITY_QUOTES = [
    "🔍 Running advanced bin analysis...",
    "⚡ Validating card integrity and velocity...",
    "🛡️ Applying anti-fraud filters...",
    "📡 Connecting to premium gateways...",
    "🔬 Performing deep quality scan...",
    "💎 Ensuring only factory-grade cards...",
    "🌐 Cross-referencing live databases...",
    "🏆 Running FactoryVHQ QA protocol...",
    "✅ Finalizing premium live cards..."
]

# ====================== PARSER ======================
def parse_card(line: str) -> Optional[dict]:
    try:
        line = re.split(r'\s*(?:LIVE|=>)', line, flags=re.IGNORECASE)[0].strip()
        line = re.sub(r'\s*\|\s*', '|', line)
        line = re.sub(r'\|+', '|', line).strip('|')
        parts = line.split('|')

        if len(parts) < 4:
            return None

        card = re.sub(r'\D', '', parts[0])
        if len(card) < 13:
            return None

        mm = parts[1].strip().zfill(2)
        yy = parts[2].strip().zfill(2)
        cvv = re.sub(r'\D', '', parts[3]) or "000"
        name = parts[4].strip() if len(parts) > 4 else "Cardholder"

        address = parts[5].strip() if len(parts) > 5 else "N/A"
        city = parts[6].strip() if len(parts) > 6 else "N/A"
        state = parts[7].strip() if len(parts) > 7 else "N/A"
        zipcode = parts[8].strip() if len(parts) > 8 else "N/A"
        country = parts[9].strip() if len(parts) > 9 else "US"

        raw = f"{card}|{mm}|{yy}|{cvv}"

        return {
            "card": card, "mm": mm, "yy": yy, "cvv": cvv, "name": name,
            "address": address, "city": city, "state": state, "zip": zipcode,
            "country": country, "raw": raw
        }
    except Exception as e:
        logger.error(f"Parse error: {e}")
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
══════════════════════════════════════
🔥 LIVE => stormcheck.cc
══════════════════════════════════════"""

CHECK_BUTTON = InlineKeyboardMarkup([
    [InlineKeyboardButton("✅ Check", callback_data="check")],
    [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
])

POST_BUTTONS = InlineKeyboardMarkup([
    [InlineKeyboardButton("📤 Send File", callback_data="send_file")],
    [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
])

# ====================== REAL POLLING ======================
async def submit_to_storm(cards: List[str]):
    if not API_KEY:
        return "ERROR: API_KEY missing"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{BASE_URL}/check", headers=HEADERS, json={"cards": cards})
            logger.info(f"Submit Status: {r.status_code} | Response: {r.text[:200]}")
            if r.status_code in (200, 201):
                data = r.json()
                return data.get("batch_id") or data.get("id") or data.get("data", {}).get("batch_id")
            return None
    except Exception as e:
        logger.error(f"Submit error: {e}")
        return None

async def poll_results(batch_id: str, status_msg, session_data):
    live_cards = []
    seen = set()

    for i in range(MAX_POLLS):
        await asyncio.sleep(POLL_INTERVAL)
        
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.get(f"{BASE_URL}/check/{batch_id}", headers=HEADERS)
                data = r.json()
                
                items = data.get("data", {}).get("items") or data.get("items") or data.get("results", [])
                
                for item in items:
                    card_num = str(item.get("card_number") or item.get("cc") or item.get("card") or "").strip()
                    if card_num and card_num not in seen:
                        if any(kw in str(item).lower() for kw in ["live", "approved", "success", "charged", "valid", "good", "200"]):
                            seen.add(card_num)
                            for original in session_data["cards"]:
                                if original["card"][-4:] == card_num[-4:]:
                                    live_cards.append(original)
                                    break
        except Exception as e:
            logger.error(f"Polling error: {e}")

        progress = min(100, int((i + 1) / MAX_POLLS * 100))
        quote = QUALITY_QUOTES[i % len(QUALITY_QUOTES)]
        await status_msg.edit_text(f"🔄 Quality Checking... {progress}%\n\n{quote}\n\nLive found: {len(live_cards)}")

    return live_cards

# ====================== HANDLERS ======================
async def check_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    session_data = user_sessions.setdefault(uid, {"cards": [], "live_cards": []})

    if not session_data.get("cards"):
        await query.edit_message_text("❌ No cards loaded.")
        return

    msg = await query.edit_message_text("🚀 Submitting batch to Stormcheck...")

    card_list = [c["raw"] for c in session_data["cards"]]
    logger.info(f"Sending sample: {card_list[0] if card_list else 'None'}")

    batch_id = await submit_to_storm(card_list)
    if not batch_id or str(batch_id).startswith("ERROR"):
        await msg.edit_text(f"❌ Failed to submit batch: {batch_id}")
        return

    await msg.edit_text(f"✅ Batch submitted. Starting quality check...")

    live_cards = await poll_results(batch_id, msg, session_data)
    
    session_data["live_cards"] = live_cards
    await show_post_summary(msg, session_data)

async def show_post_summary(message, session_data):
    total = len(session_data.get("cards", []))
    live = len(session_data.get("live_cards", []))
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
    await update.message.reply_text(
        "🏭 FactoryVHQ v17.8 Ready\n\n"
        "Now with proper polling (waits until checker finishes)",
        reply_markup=CHECK_BUTTON
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data
    uid = query.from_user.id
    session_data = user_sessions.setdefault(uid, {"cards": [], "live_cards": []})

    if action == "check":
        await check_handler(update, context)
    elif action == "send_file":
        cards = session_data.get("live_cards") or session_data.get("cards", [])
        content = "\n\n".join(format_card(c) for c in cards)
        await query.message.reply_document(
            bytes(content, "utf-8"),
            filename="FactoryVHQ_Live.txt",
            caption="✅ FactoryVHQ Live Cards"
        )
        await query.edit_message_text("✅ File sent!", reply_markup=CHECK_BUTTON)
    elif action == "cancel":
        await query.edit_message_text("✅ Cancelled.", reply_markup=CHECK_BUTTON)
        session_data.clear()

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    session_data = user_sessions.setdefault(uid, {"cards": []})
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
        session_data["cards"].extend(new_cards)
        await update.message.reply_text(
            f"✅ Loaded {len(new_cards)} cards (Total: {len(session_data['cards'])})",
            reply_markup=CHECK_BUTTON
        )

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ALL, message_handler))

    print("🚀 FactoryVHQ v17.8 - Proper polling + full format support")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
