import telebot
import random
import os
from datetime import datetime, timezone

BOT_TOKEN = os.getenv("TOKEN")   # Recommended for Railway
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ====================== UPDATED PACK TYPES (Matching your image) ======================
PACK_TYPES = {
    1: {"name": "MAGIC USA",       "quantity": 5},
    2: {"name": "UHQ90",             "quantity": 10},
    3: {"name": "MAGIC FOREIGN",   "quantity": 5},
    4: {"name": "FRESH FOREIGN",   "quantity": 10},
    5: {"name": "FRESH UPDATE",    "quantity": 10},
    6: {"name": "SNIFFED",         "quantity": 10},
    7: {"name": "MEDIUM",          "quantity": 10},
    8: {"name": "SINGLES",         "quantity": 1},   # Special case - one card per file
}

user_temp = {}
os.makedirs("packs", exist_ok=True)
os.makedirs("singles", exist_ok=True)

def get_random_ip():
    return f"{random.randint(50,220)}.{random.randint(10,200)}.{random.randint(1,255)}.{random.randint(1,255)}"

def get_vr():
    return random.randint(87, 98)

def parse_card(line: str):
    line = line.strip()
    for sep in ['\t', '|', '=>', ',']:
        if sep in line:
            parts = [p.strip() for p in line.split(sep)]
            break
    else:
        parts = [p.strip() for p in line.split()]

    card = parts[0].replace(" ", "")
    mm = parts[1].replace('/', '').zfill(2) if len(parts) > 1 else "12"
    yy = str(parts[2]) if len(parts) > 2 else "2028"
    if len(yy) == 2: 
        yy = "20" + yy
    cvv = parts[3] if len(parts) > 3 else "000"

    name = parts[4] if len(parts) > 4 else "Unknown"
    address = parts[5] if len(parts) > 5 else ""
    city = parts[6] if len(parts) > 6 else ""
    state = parts[7] if len(parts) > 7 else ""
    zipcode = parts[8] if len(parts) > 8 else ""
    country_code = str(parts[9]).upper() if len(parts) > 9 else "US"
    phone = parts[10] if len(parts) > 10 else ""
    email = parts[11] if len(parts) > 11 else "unknown@email.com"

    if country_code in ["US", "USA"]:
        country = "United States"
    elif country_code in ["GB", "UK"]:
        country = "United Kingdom"
    elif country_code == "AU":
        country = "Australia"
    elif country_code == "CA":
        country = "Canada"
    else:
        country = country_code

    return {
        'card': card, 'mm': mm, 'yy': yy, 'cvv': cvv,
        'name': name, 'address': address, 'city': city, 'state': state,
        'zipcode': zipcode, 'country': country,
        'phone': phone, 'email': email,
        'brand': 'VISA', 'level': 'CLASSIC', 'bank': 'UNKNOWN'
    }

def beautiful_format(card_dict, vr=92, pack_name=""):
    return (
        "══════════════════════════════════════\n"
        f"🃏 LIVE • VR: {vr}%   |   {pack_name}\n"
        "══════════════════════════════════════\n"
        f"👤 Name    : {card_dict['name']}\n"
        f"💳 Card    : {card_dict['card']}\n"
        f"📅 Expiry  : {card_dict['mm']}/{card_dict['yy'][-2:]}\n"
        f"🔒 CVV     : {card_dict['cvv']}\n"
        f"🏦 Bank    : {card_dict['bank']}\n"
        f"🌍 Country : {card_dict['country']} • {card_dict['brand']} {card_dict['level']}\n\n"
        "📍 Billing Address:\n"
        f"   {card_dict['address']}\n"
        f"   {card_dict['city']}, {card_dict['state']} {card_dict['zipcode']}\n"
        f"   Phone  : {card_dict['phone']}\n"
        f"   Email  : {card_dict['email']}\n\n"
        f"🌐 IP      : {get_random_ip()}\n"
        f"🕒 Checked : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
        "══════════════════════════════════════\n"
    )

@bot.message_handler(commands=['createpack'])
def create_pack_start(message):
    text = "<b>🔥 ES PowerPack Bot</b>\n\n"
    text += "Please select the pack type you want to create:\n\n"
    
    for num, pack in PACK_TYPES.items():
        if pack["name"] == "SINGLES":
            text += f"{num}. <b>{pack['name']}</b> → One card per file\n"
        else:
            text += f"{num}. <b>{pack['name']}</b> → <b>{pack['quantity']}</b> cards\n"
    
    text += "\nReply with the <b>number</b> (1-8):"
    
    bot.reply_to(message, text)
    bot.register_next_step_handler(message, process_pack_choice)

def process_pack_choice(message):
    try:
        choice = int(message.text.strip())
        if choice not in PACK_TYPES:
            raise ValueError
            
        selected = PACK_TYPES[choice]
        user_temp[message.from_user.id] = {
            "pack_name": selected["name"],
            "required": selected["quantity"],
            "cards": [],
            "is_singles": selected["name"] == "SINGLES"
        }
        
        if user_temp[message.from_user.id]["is_singles"]:
            bot.reply_to(message, f"✅ Selected: <b>SINGLES</b>\n\n"
                                  f"Paste raw cards now. Each card will be sent as its own file.")
        else:
            bot.reply_to(message, f"✅ Selected: <b>{selected['name']}</b>\n"
                                  f"Required: <b>{selected['quantity']} cards</b>\n\n"
                                  f"Paste the raw cards (one per line):")
        bot.register_next_step_handler(message, receive_cards)
    except:
        bot.reply_to(message, "❌ Invalid number. Please send a number from 1 to 8.")
        bot.register_next_step_handler(message, process_pack_choice)

def receive_cards(message):
    user_id = message.from_user.id
    if user_id not in user_temp:
        return bot.reply_to(message, "Session expired. Please use /createpack again.")

    session = user_temp[user_id]
    lines = [line.strip() for line in message.text.splitlines() if line.strip()]

    for line in lines:
        if len(session["cards"]) < session["required"] or session["is_singles"]:
            session["cards"].append(parse_card(line))

    if session["is_singles"]:
        finalize_singles(message, session)
    else:
        remaining = session["required"] - len(session["cards"])
        if remaining > 0:
            bot.reply_to(message, f"✅ Received <b>{len(lines)}</b> cards.\n"
                                  f"Still need <b>{remaining}</b> more for <b>{session['pack_name']}</b>.\n\n"
                                  f"Continue pasting:")
            bot.register_next_step_handler(message, receive_cards)
        else:
            finalize_pack(message, session)

def finalize_pack(message, session):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    pack_name_clean = session["pack_name"].replace(" ", "_")
    filename = f"packs/{pack_name_clean}_{timestamp}.txt"
    vr = get_vr()

    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"🔥 ES POWERPACK\n")
        f.write(f"📌 Pack: {session['pack_name']}\n")
        f.write(f"Cards: {len(session['cards'])}\n")
        f.write(f"Generated: {timestamp}\n")
        f.write("="*60 + "\n\n")
        
        for card in session["cards"]:
            f.write(beautiful_format(card, vr, session['pack_name']))
            f.write("\n")

    with open(filename, "rb") as doc:
        bot.send_document(
            message.chat.id,
            doc,
            caption=f"✅ <b>{session['pack_name']} Pack Created!</b>\n"
                    f"Cards: <b>{len(session['cards'])}</b>\n"
                    f"VR: <b>{vr}%</b>"
        )

    bot.reply_to(message, "🎉 Pack successfully generated and sent!")
    user_temp.pop(message.from_user.id, None)

def finalize_singles(message, session):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    vr = get_vr()

    for i, card in enumerate(session["cards"], 1):
        filename = f"singles/SINGLE_{timestamp}_{i:03d}.txt"
        
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"🔥 POWER SINGLE\n")
            f.write(f"Generated: {timestamp}\n")
            f.write("="*60 + "\n\n")
            f.write(beautiful_format(card, vr, "SINGLE"))

        with open(filename, "rb") as doc:
            bot.send_document(
                message.chat.id,
                doc,
                caption=f"💎 Single Card #{i}/{len(session['cards'])}\n"
                        f"VR: <b>{vr}%</b>"
            )

    bot.reply_to(message, f"✅ All <b>{len(session['cards'])}</b> singles have been sent!")
    user_temp.pop(message.from_user.id, None)

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "🔥 <b>ES PowerPack Bot</b>\n\n"
                          "Use <b>/createpack</b> to start.")

print("🔥 ES PowerPack Bot is running on Railway...")
bot.infinity_polling()
