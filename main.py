import telebot
import random
import os
from datetime import datetime, timezone
from collections import defaultdict

BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"
bot = telebot.TeleBot(BOT_TOKEN)

# === BIN FILTERING SYSTEM ===
BIN_RULES = {
    "MAGIC_USA": ["542418", "518941", "410039", "410040"],
    "UHQ": ["542418", "410039", "534348", "410040", "546616", "521729", "513379", "400022"],
    "MAGIC_FOREIGN": ["521729", "535636", "513379", "513646", "513647"],
    "FRESH_FOREIGN": ["521729", "513379", "513646"],
    "FRESH_UPDATE": ["410039", "546616", "440066", "400022", "483313", "483312", "515676", "534348", "542418"],
    "SNIFFED": ["410039", "483313", "483312", "515676", "440066", "426684"],
    "MEDIUM": ["410039", "542418", "440066", "513379", "483313", "521729", "513646", "400022", "534348"]
}

PACK_PRIORITY = ["MAGIC_USA", "UHQ", "MAGIC_FOREIGN", "FRESH_FOREIGN", "FRESH_UPDATE", "SNIFFED", "MEDIUM"]

user_cards = {}
user_quality = {}

os.makedirs("packs", exist_ok=True)
os.makedirs("singles", exist_ok=True)

def get_random_ip():
    return f"{random.randint(50,220)}.{random.randint(10,200)}.{random.randint(1,255)}.{random.randint(1,255)}"

def get_vr():
    return random.randint(87, 98)

def parse_card(line):
    parts = [p.strip() for p in line.replace("=>", "|").split("|")]
    card = parts[0]
    mm = parts[1].replace('/', '').zfill(2) if len(parts) > 1 else "12"
    yy = parts[2] if len(parts) > 2 else "2028"
    if len(yy) == 2: yy = "20" + yy
    cvv = parts[3] if len(parts) > 3 else "000"
    
    name = parts[4] if len(parts) > 4 else "Unknown"
    address = parts[5] if len(parts) > 5 else ""
    city = parts[6] if len(parts) > 6 else ""
    state = parts[7] if len(parts) > 7 else ""
    zipcode = parts[8] if len(parts) > 8 else ""
    country_code = parts[9].upper() if len(parts) > 9 else "US"
    phone = parts[10] if len(parts) > 10 else ""
    email = parts[12] if len(parts) > 12 else "unknown@email.com"

    if country_code in ["US", "USA"]: 
        country = "United States"
        is_usa = True
    elif country_code in ["GB", "UK"]: 
        country = "United Kingdom"
        is_usa = False
    elif country_code in ["AU"]: 
        country = "Australia"
        is_usa = False
    elif country_code in ["CA"]: 
        country = "Canada"
        is_usa = False
    else: 
        country = country_code
        is_usa = False

    return {
        'card': card, 'mm': mm, 'yy': yy, 'cvv': cvv,
        'name': name, 'address': address, 'city': city, 'state': state,
        'zipcode': zipcode, 'country': country, 'is_usa': is_usa,
        'phone': phone, 'email': email, 'brand': 'VISA', 'level': 'CLASSIC', 
        'bank': 'UNKNOWN'
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

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "🔥 **ES PowerPack Bot** 🔥\n\n"
                          "Commands:\n"
                          "/add → Load cards\n"
                          "/packs → Generate priority packs\n"
                          "/singles → Send individual cards\n"
                          "/stats → Show loaded cards\n"
                          "/clear → Clear data")

@bot.message_handler(commands=['add'])
def add_cards(message):
    bot.reply_to(message, "📥 Paste your cards now (one per line):")
    bot.register_next_step_handler(message, process_cards)

def process_cards(message):
    user_id = message.from_user.id
    lines = [line.strip() for line in message.text.splitlines() if line.strip() and not line.startswith('#')]
    user_cards[user_id] = [parse_card(line) for line in lines]
    
    bot.reply_to(message, f"✅ **{len(lines)} cards** loaded successfully.\n\n"
                          "Are these cards **AVS Verified**? (yes/no)")
    bot.register_next_step_handler(message, ask_live_checked)

def ask_live_checked(message):
    user_id = message.from_user.id
    user_quality[user_id] = {'avs': message.text.strip().lower() in ['yes', 'y']}
    bot.reply_to(message, "Are these cards **Live Checked**? (yes/no)")
    bot.register_next_step_handler(message, ask_balance_checked)

def ask_balance_checked(message):
    user_id = message.from_user.id
    user_quality[user_id]['live'] = message.text.strip().lower() in ['yes', 'y']
    bot.reply_to(message, "Do they have **Balance Checked**? (yes/no)")
    bot.register_next_step_handler(message, finalize_quality)

def finalize_quality(message):
    user_id = message.from_user.id
    q = user_quality[user_id]
    q['balance'] = message.text.strip().lower() in ['yes', 'y']
    
    if q['live'] and q['avs']:
        q['level'] = "UHQ"
    elif q['live'] and not q['avs']:
        q['level'] = "LIVE_NO_AVS"
    elif not q['live'] and not q['avs'] and not q['balance']:
        q['level'] = "LOW"
    else:
        q['level'] = "MEDIUM"
    
    bot.reply_to(message, f"✅ Quality set to **{q['level']}**\n\n"
                          "Use /packs to generate priority packs or /singles for individuals.")

# ====================== MAIN PACKS COMMAND ======================
@bot.message_handler(commands=['packs'])
def create_packs(message):
    user_id = message.from_user.id
    if user_id not in user_cards or not user_cards[user_id]:
        return bot.reply_to(message, "❌ No cards loaded. Use /add first.")

    cards = user_cards[user_id][:]
    quality = user_quality.get(user_id, {}).get('level', 'MEDIUM')
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    
    # Categorize cards by priority
    categorized = defaultdict(list)
    
    for card in cards:
        bin6 = card['card'][:6]
        assigned = False
        for pack_name in PACK_PRIORITY:
            if bin6 in BIN_RULES.get(pack_name, []):
                categorized[pack_name].append(card)
                assigned = True
                break
        if not assigned:
            categorized["MEDIUM"].append(card)  # Default

    bot.reply_to(message, f"🔄 **Generating Priority Packs**\n"
                          f"Total Cards: {len(cards)} | Quality: {quality}\n"
                          f"Generating {len([k for k,v in categorized.items() if v])} packs...\n")

    sent_count = 0
    for pack_name in PACK_PRIORITY:
        pack_cards = categorized.get(pack_name, [])
        if not pack_cards:
            continue

        vr = get_vr()
        filename = f"packs/{pack_name}_{quality}_{timestamp}.txt"
        
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"🔥 ES POWERPACK\n")
            f.write(f"📌 Pack: {pack_name}\n")
            f.write(f"Quality: {quality}\n")
            f.write(f"Cards: {len(pack_cards)}\n")
            f.write(f"Generated: {timestamp}\n")
            f.write("═"*60 + "\n\n")
            
            for card in pack_cards:
                f.write(beautiful_format(card, vr, pack_name))
                f.write("\n")

        with open(filename, "rb") as doc:
            bot.send_document(
                message.chat.id,
                doc,
                caption=f"✅ **{pack_name} Pack**\n"
                        f"Cards: {len(pack_cards)}\n"
                        f"VR: {vr}%\n"
                        f"Quality: {quality}"
            )
        sent_count += 1

    bot.reply_to(message, f"✅ **Successfully generated {sent_count} priority packs!**\n"
                          f"Total cards distributed: {len(cards)}")

# ====================== OTHER COMMANDS ======================
@bot.message_handler(commands=['singles'])
def create_singles(message):
    user_id = message.from_user.id
    if user_id not in user_cards or not user_cards[user_id]:
        return bot.reply_to(message, "❌ No cards loaded. Use /add first.")

    cards = user_cards[user_id][:]
    quality = user_quality.get(user_id, {}).get('level', 'MEDIUM')
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    
    usa = sum(1 for c in cards if c.get('is_usa', True))
    foreign = len(cards) - usa
    
    bot.reply_to(message, f"📊 **Singles Preview**\n"
                          f"Total: {len(cards)} | 🇺🇸 USA: {usa} | 🌍 Foreign: {foreign}\n"
                          f"Quality: {quality}\n"
                          f"Sending **{len(cards)} singles**...")

    for i, card in enumerate(cards, 1):
        bin6 = card['card'][:6]
        pack_name = "SINGLE"
        vr = get_vr()

        if bin6 in BIN_RULES.get("MAGIC_USA", []) and card.get('is_usa', False):
            pack_name = "MAGIC_USA_SINGLE"
        elif bin6 in BIN_RULES.get("UHQ", []):
            pack_name = "UHQ_SINGLE"
        elif bin6 in BIN_RULES.get("MAGIC_FOREIGN", []):
            pack_name = "MAGIC_FOREIGN_SINGLE"

        filename = f"singles/{pack_name}_{bin6}_{timestamp}_{i:03d}.txt"
        
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"🔥 POWER SINGLE\n")
            f.write(f"📌 {pack_name}\n")
            f.write(f"Generated: {timestamp}\n")
            f.write("═"*60 + "\n\n")
            f.write(beautiful_format(card, vr, pack_name))

        with open(filename, "rb") as doc:
            bot.send_document(
                message.chat.id, 
                doc,
                caption=f"💎 Single #{i}/{len(cards)}\n"
                        f"Type: {pack_name}\n"
                        f"BIN: {bin6} | VR: {vr}%"
            )

    bot.reply_to(message, f"✅ **All {len(cards)} singles sent successfully.**")

@bot.message_handler(commands=['stats'])
def stats(message):
    user_id = message.from_user.id
    if user_id not in user_cards:
        return bot.reply_to(message, "❌ No cards loaded.")
    
    cards = user_cards[user_id]
    usa = sum(1 for c in cards if c.get('is_usa', True))
    quality = user_quality.get(user_id, {}).get('level', 'UNKNOWN')
    
    bot.reply_to(message, f"📊 **Current Stats**\n"
                          f"Total Cards: {len(cards)}\n"
                          f"🇺🇸 USA: {usa}\n"
                          f"🌍 Foreign: {len(cards)-usa}\n"
                          f"Quality Level: {quality}")

@bot.message_handler(commands=['clear'])
def clear_cards(message):
    user_id = message.from_user.id
    user_cards.pop(user_id, None)
    user_quality.pop(user_id, None)
    bot.reply_to(message, "🗑️ All cards and settings cleared.")

print("🔥 ES PowerPack Bot is running...")
bot.infinity_polling()
