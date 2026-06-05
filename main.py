"""
Telegram Card Formatter Bot
Robust parser for messy credit card lines with improved junk removal.
"""

import logging
import os
import re
from typing import List, Dict, Optional
from enum import Enum
from io import BytesIO

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode

# ============================================================================
# CONFIGURATION
# ============================================================================

TOKEN = os.getenv("TOKEN", "YOUR_BOT_TOKEN_HERE")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============================================================================
# FORMAT ENUMS
# ============================================================================

class CardFormat(Enum):
    FORMAT_1 = ("card | month | year | cvv", "fmt_1")
    FORMAT_2 = ("card | month/year | cvv", "fmt_2")
    FORMAT_3 = ("card / month / year / cvv", "fmt_3")
    FORMAT_4 = ("card / MMYY / cvv", "fmt_4")
    FORMAT_5 = ("card | MMYY | cvv", "fmt_5")
    FORMAT_6 = ("Full Format (Name + Address)", "fmt_6")

    @classmethod
    def get_by_callback(cls, callback_data: str):
        for fmt in cls:
            if fmt.value[1] == callback_data:
                return fmt
        return None

# ============================================================================
# CARD PARSER - IMPROVED
# ============================================================================

class CardParser:
    JUNK_PATTERNS = [
        r'^\d+\.?\d*$',                    # prices like $ 3.30
        r'^\d{4}[-_]\d{2}[-_]\d{2}.*',    # 2026_06_05_US_TR_CA or 2026-06-05
        r'LIVE\s*=>.*',
        r'^(No|Yes|null|undefined|N/A|LIVE|CHECKING)$',
        r'No\s+Checking',
        r'stormcheck\.\w+',
        r'base|seller|mix|non.?ref|vr55',
        r'\*\*\*',                         # masked names like Dan***l
    ]

    SEPARATORS = ['\t', '|', ',', ';']

    @staticmethod
    def is_credit_card(value: str) -> bool:
        cleaned = re.sub(r'\s+', '', value.strip())
        if not cleaned.isdigit() or len(cleaned) < 13 or len(cleaned) > 19:
            return False
        return CardParser._luhn_check(cleaned)

    @staticmethod
    def _luhn_check(card_number: str) -> bool:
        digits = [int(d) for d in card_number]
        checksum = 0
        for i, d in enumerate(reversed(digits)):
            if i % 2 == 1:
                d *= 2
                if d > 9:
                    d -= 9
            checksum += d
        return checksum % 10 == 0

    @staticmethod
    def is_valid_expiry(value: str) -> bool:
        cleaned = re.sub(r'[^0-9]', '', value.strip())
        if len(cleaned) in (2, 4):
            month = int(cleaned[:2])
            return 1 <= month <= 12
        return False

    @staticmethod
    def is_valid_cvv(value: str) -> bool:
        cleaned = re.sub(r'[^0-9]', '', value.strip())
        return cleaned.isdigit() and 3 <= len(cleaned) <= 4

    @staticmethod
    def should_skip_field(value: str) -> bool:
        if not value or len(value.strip()) < 2:
            return True
        cleaned = value.strip()
        for pattern in CardParser.JUNK_PATTERNS:
            if re.search(pattern, cleaned, re.IGNORECASE):
                return True
        return False

    @classmethod
    def parse_card_line(cls, line: str) -> Optional[Dict[str, str]]:
        if not line or not line.strip():
            return None

        # Split on multiple spaces, tabs, or pipes
        fields = re.split(r'\s{2,}|\t|\|', line)
        cleaned_fields = [f.strip() for f in fields if f.strip() and not cls.should_skip_field(f.strip())]

        if len(cleaned_fields) < 3:
            return None

        card_data = {
            'card': None, 'month': None, 'year': None, 'cvv': None,
            'name': None, 'address': None, 'city': None, 'state': None,
            'zipcode': None, 'country': None, 'phone': None, 'email': None
        }

        for field in cleaned_fields:
            if cls.is_credit_card(field) and not card_data['card']:
                card_data['card'] = field
            elif cls.is_valid_cvv(field) and not card_data['cvv']:
                card_data['cvv'] = field
            elif cls.is_valid_expiry(field) and not card_data['month']:
                exp = re.sub(r'[^0-9]', '', field)
                card_data['month'] = exp[:2]
                if len(exp) == 4:
                    card_data['year'] = exp[2:]
            elif len(field) == 2 and field.isdigit() and card_data['month'] and not card_data['year']:
                card_data['year'] = field.zfill(2)
            elif any(c.isalpha() for c in field):
                if not card_data['name']:
                    card_data['name'] = field
                elif not card_data['address'] and any(d.isdigit() for d in field):
                    card_data['address'] = field
                elif not card_data['city']:
                    card_data['city'] = field
                elif re.match(r'^[A-Z]{2}$', field.upper()):
                    card_data['state'] = field.upper()
                elif re.match(r'^\d{5,10}$', field):
                    card_data['zipcode'] = field
            elif '@' in field:
                card_data['email'] = field
            elif re.match(r'^\+?1?\(?\d', field):
                card_data['phone'] = field

        if not all([card_data['card'], card_data['month'], card_data['cvv']]):
            return None

        if not card_data['year']:
            card_data['year'] = "26"

        return card_data

    @classmethod
    def parse_multiple_cards(cls, text: str) -> List[Dict[str, str]]:
        cards = []
        for line in text.split('\n'):
            if line.strip():
                card = cls.parse_card_line(line)
                if card:
                    cards.append(card)
        return cards

# ============================================================================
# CARD FORMATTER
# ============================================================================

class CardFormatter:
    @staticmethod
    def format_card(card_data: Dict[str, str], fmt: CardFormat) -> str:
        c = card_data
        if fmt == CardFormat.FORMAT_1:
            return f"{c['card']} | {c['month']} | {c['year']} | {c['cvv']}"
        elif fmt == CardFormat.FORMAT_2:
            return f"{c['card']} | {c['month']}/{c['year']} | {c['cvv']}"
        elif fmt == CardFormat.FORMAT_3:
            return f"{c['card']} / {c['month']} / {c['year']} / {c['cvv']}"
        elif fmt == CardFormat.FORMAT_4:
            return f"{c['card']} / {c['month']}{c['year']} / {c['cvv']}"
        elif fmt == CardFormat.FORMAT_5:
            return f"{c['card']} | {c['month']}{c['year']} | {c['cvv']}"
        elif fmt == CardFormat.FORMAT_6:
            parts = [
                c['card'], c['month'], c['year'], c['cvv'],
                c.get('name', 'N/A'), c.get('address', 'N/A'), c.get('city', 'N/A'),
                c.get('state', 'N/A'), c.get('zipcode', 'N/A'), c.get('country', 'N/A')
            ]
            return " | ".join(str(p) for p in parts)
        return ""

    @staticmethod
    def format_cards(cards: List[Dict], fmt: CardFormat) -> str:
        return "\n".join(CardFormatter.format_card(card, fmt) for card in cards)

# ============================================================================
# BOT HANDLERS
# ============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "🎯 <b>Card Formatter Bot</b>\n\nSend me your messy card data and choose a format."
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def show_formats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📋 <b>Available Formats:</b>\n\n"
        "1️⃣ <code>card | month | year | cvv</code>\n"
        "2️⃣ <code>card | month/year | cvv</code>\n"
        "3️⃣ <code>card / month / year / cvv</code>\n"
        "4️⃣ <code>card / MMYY / cvv</code>\n"
        "5️⃣ <code>card | MMYY | cvv</code>\n"
        "6️⃣ <b>Full Format</b> (Name + Address)\n\n"
        "<i>Paste cards first, then select format.</i>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ <b>Help</b>\n\n"
        "Paste any messy card data (with extra junk, prices, dates, etc.)\n"
        "I will automatically clean it and return a clean .txt file.",
        parse_mode=ParseMode.HTML
    )

async def receive_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    parsed = CardParser.parse_multiple_cards(text)

    if not parsed:
        await update.message.reply_text("❌ Could not detect any valid cards. Try sending again.")
        return

    context.user_data['parsed_cards'] = parsed

    keyboard = [
        [InlineKeyboardButton("1️⃣ card | month | year | cvv", callback_data="fmt_1")],
        [InlineKeyboardButton("2️⃣ card | month/year | cvv", callback_data="fmt_2")],
        [InlineKeyboardButton("3️⃣ card / month / year / cvv", callback_data="fmt_3")],
        [InlineKeyboardButton("4️⃣ card / MMYY / cvv", callback_data="fmt_4")],
        [InlineKeyboardButton("5️⃣ card | MMYY | cvv", callback_data="fmt_5")],
        [InlineKeyboardButton("6️⃣ Full Format (Name + Address)", callback_data="fmt_6")],
    ]

    await update.message.reply_text(
        f"✅ Found <b>{len(parsed)}</b> valid card(s)!\n\nChoose format:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )

async def format_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    fmt = CardFormat.get_by_callback(query.data)
    if not fmt or 'parsed_cards' not in context.user_data:
        await query.edit_message_text("❌ Session expired. Please send cards again.")
        return

    cards = context.user_data['parsed_cards']
    formatted_text = CardFormatter.format_cards(cards, fmt)

    bio = BytesIO()
    bio.write(formatted_text.encode('utf-8'))
    bio.seek(0)
    bio.name = "formatted_cards.txt"

    await query.edit_message_text("✅ Generating file...")

    await query.message.reply_document(
        document=bio,
        filename="formatted_cards.txt",
        caption=f"✅ {len(cards)} card(s) formatted successfully"
    )

    context.user_data.clear()

# ============================================================================
# MAIN
# ============================================================================

def main():
    if TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.error("Please set your TELEGRAM_BOT_TOKEN environment variable!")
        return

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("format", show_formats))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_cards))
    app.add_handler(CallbackQueryHandler(format_selection))

    logger.info("✅ Card Formatter Bot is now running...")
    app.run_polling()

if __name__ == "__main__":
    main()
