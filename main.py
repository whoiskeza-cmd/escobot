

import logging
import os
import re
import tempfile
from datetime import datetime
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

# Conversation states
SELECT_FORMAT, AWAITING_CARDS = range(2)


# ============================================================================
# FORMAT ENUMS
# ============================================================================

class CardFormat(Enum):
    """Supported card formatting styles"""
    FORMAT_1 = ("4444555566667777 | 10 | 22 | 123", "fmt_1")
    FORMAT_2 = ("4444555566667777 | 10/22 | 123", "fmt_2")
    FORMAT_3 = ("4444555566667777 / 10 / 22 / 123", "fmt_3")
    FORMAT_4 = ("4444555566667777 / 1022 / 123", "fmt_4")
    FORMAT_5 = ("4444555566667777 | 1022 | 123", "fmt_5")
    FORMAT_6 = ("Full: card|month|year|cvv|name|address|city|state|zip|country", "fmt_6")

    @classmethod
    def get_by_callback(cls, callback_data: str):
        """Get format enum by callback data"""
        for fmt in cls:
            if fmt.value[1] == callback_data:
                return fmt
        return None


# ============================================================================
# CARD PARSING AND FORMATTING
# ============================================================================

class CardParser:
    """
    Intelligent parser for extracting card data from various messy formats.
    Handles multiple separators, junk data, and mixed formats.
    """

    # Patterns to identify and skip junk data
    JUNK_PATTERNS = [
        r'^\d+\.\d+$',  # Prices like $3.30, 1.2
        r'LIVE\s*=>',  # LIVE => tags
        r'\$\d+\.\d+',  # Dollar amounts
        r'^\d{4}_\d{2}_\d{2}',  # Dates like 2026_06_05
        r'^(No|Yes|null|undefined|N/A|LIVE)$',  # Generic placeholders
        r'No\s+Checking',  # Bank type indicators
        r'stormcheck\.\w+',  # Seller tags
        r'^\d+\|.*@',  # Clear junk combinations
    ]

    # Separators to split fields
    SEPARATORS = ['\t', '|', '/', ' ']

    @staticmethod
    def is_credit_card(value: str) -> bool:
        """Check if a string is a valid credit card number"""
        value = value.strip()
        if not value.isdigit() or len(value) < 13 or len(value) > 19:
            return False
        return CardParser._luhn_check(value)

    @staticmethod
    def _luhn_check(card_number: str) -> bool:
        """Validate credit card using Luhn algorithm"""
        try:
            digits = [int(d) for d in card_number]
            checksum = 0
            for i, d in enumerate(reversed(digits)):
                if i % 2 == 1:
                    d *= 2
                    if d > 9:
                        d -= 9
                checksum += d
            return checksum % 10 == 0
        except (ValueError, AttributeError):
            return False

    @staticmethod
    def is_valid_expiry(value: str) -> bool:
        """Check if value is a valid expiry date (MM, MM/YY, MM/YYYY, MMYY)"""
        value = value.strip()
        value = re.sub(r'[/\-\s]', '', value)

        if len(value) == 2 and value.isdigit():
            month = int(value)
            return 1 <= month <= 12

        if len(value) == 4 and value.isdigit():
            return True

        return False

    @staticmethod
    def is_valid_cvv(value: str) -> bool:
        """Check if value is a valid CVV (3-4 digits)"""
        value = value.strip()
        return value.isdigit() and 3 <= len(value) <= 4

    @staticmethod
    def clean_field(value: str) -> str:
        """Remove leading/trailing whitespace and special characters"""
        value = value.strip()
        value = ''.join(c for c in value if c.isprintable())
        return value

    @staticmethod
    def should_skip_field(value: str) -> bool:
        """Determine if a field should be skipped as junk"""
        cleaned = CardParser.clean_field(value)

        for pattern in CardParser.JUNK_PATTERNS:
            if re.search(pattern, cleaned, re.IGNORECASE):
                return True

        if len(cleaned) < 2:
            return True

        return False

    @classmethod
    def parse_card_line(cls, line: str) -> Optional[Dict[str, str]]:
        """
        Parse a single line of card data and extract card details.
        Returns a dict with keys: card, month, year, cvv, name, address, city, state, zipcode, country
        """
        if not line or not line.strip():
            return None

        fields = []
        separator_used = None

        for sep in cls.SEPARATORS:
            potential_fields = line.split(sep)
            if len(potential_fields) > 2:
                fields = potential_fields
                separator_used = sep
                break

        if not fields:
            return None

        # Clean all fields and filter junk
        cleaned_fields = []
        for field in fields:
            cleaned = cls.clean_field(field)
            if cleaned and not cls.should_skip_field(cleaned):
                cleaned_fields.append(cleaned)

        if len(cleaned_fields) < 3:
            return None

        # Initialize card data dictionary
        card_data = {
            'card': None,
            'month': None,
            'year': None,
            'cvv': None,
            'name': None,
            'address': None,
            'city': None,
            'state': None,
            'zipcode': None,
            'country': None,
        }

        # Extract card data
        idx = 0
        for field in cleaned_fields:
            # Try to identify field type
            if cls.is_credit_card(field) and not card_data['card']:
                card_data['card'] = field
                idx += 1
                continue

            if cls.is_valid_expiry(field) and not card_data['month']:
                expiry = re.sub(r'[/\-\s]', '', field.strip())
                if len(expiry) == 2:
                    card_data['month'] = expiry
                elif len(expiry) == 4:
                    card_data['month'] = expiry[:2]
                    card_data['year'] = expiry[2:]
                idx += 1
                continue

            if cls.is_valid_cvv(field) and not card_data['cvv']:
                card_data['cvv'] = field
                idx += 1
                continue

            # If we haven't extracted year and this looks like a year
            if not card_data['year'] and len(field) == 2 and field.isdigit():
                potential_year = int(field)
                if 0 <= potential_year <= 99:
                    card_data['year'] = field
                    idx += 1
                    continue

            # Remaining fields are typically name, address, city, state, zip, country
            if not card_data['name'] and len(field) > 2 and not field.isdigit():
                card_data['name'] = field
                idx += 1
                continue

            idx += 1

        # Validate minimum required fields
        if not (card_data['card'] and card_data['month'] and card_data['cvv']):
            return None

        # Ensure year is 2 digits
        if card_data['year'] and len(card_data['year']) == 4:
            card_data['year'] = card_data['year'][2:]

        return card_data

    @classmethod
    def parse_multiple_cards(cls, text: str) -> List[Dict[str, str]]:
        """
        Parse multiple card entries from text.
        Handles both newline-separated and pipe-separated cards.
        """
        cards = []
        lines = text.split('\n')

        for line in lines:
            card = cls.parse_card_line(line)
            if card:
                cards.append(card)

        return cards


class CardFormatter:
    """Format parsed card data according to selected format"""

    @staticmethod
    def format_card(card_data: Dict[str, str], format_style: CardFormat) -> str:
        """Format a single card according to the selected style"""
        card = card_data.get('card', '')
        month = card_data.get('month', '')
        year = card_data.get('year', '')
        cvv = card_data.get('cvv', '')
        name = card_data.get('name', '')
        address = card_data.get('address', '')
        city = card_data.get('city', '')
        state = card_data.get('state', '')
        zipcode = card_data.get('zipcode', '')
        country = card_data.get('country', '')

        # Handle missing year (assume 20XX)
        if month and not year:
            year = "26"  # Default to 2026

        try:
            if format_style == CardFormat.FORMAT_1:
                return f"{card} | {month} | {year} | {cvv}"

            elif format_style == CardFormat.FORMAT_2:
                return f"{card} | {month}/{year} | {cvv}"

            elif format_style == CardFormat.FORMAT_3:
                return f"{card} / {month} / {year} / {cvv}"

            elif format_style == CardFormat.FORMAT_4:
                return f"{card} / {month}{year} / {cvv}"

            elif format_style == CardFormat.FORMAT_5:
                return f"{card} | {month}{year} | {cvv}"

            elif format_style == CardFormat.FORMAT_6:
                # Full format with all available data
                parts = [card, month, year, cvv, name, address, city, state, zipcode, country]
                parts = [p if p else "N/A" for p in parts]
                return " | ".join(parts)

        except Exception as e:
            logger.error(f"Error formatting card: {e}")
            return ""

        return ""

    @staticmethod
    def format_cards(cards: List[Dict[str, str]], format_style: CardFormat) -> str:
        """Format multiple cards"""
        formatted = []
        for card in cards:
            formatted_card = CardFormatter.format_card(card, format_style)
            if formatted_card:
                formatted.append(formatted_card)

        return "\n".join(formatted)


# ============================================================================
# BOT HANDLERS
# ============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command"""
    welcome_text = (
        "🎯 *Card Formatter Bot*\n\n"
        "I can help you format messy credit card data into clean, usable formats.\n\n"
        "*How to use:*\n"
        "1. Send me raw card data (any format)\n"
        "2. Choose your preferred output format\n"
        "3. Get a formatted .txt file with all your cards\n\n"
        "*What I can handle:*\n"
        "✅ Multiple cards at once\n"
        "✅ Mixed separators (pipes, tabs, spaces)\n"
        "✅ Junk data and seller info (removed automatically)\n"
        "✅ Various date formats\n\n"
        "Use /format to see all available formats or /help for more info."
    )

    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.MARKDOWN
    )


async def show_formats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /format command - show available formats"""
    formats_text = (
        "📋 *Available Formatting Styles:*\n\n"
        "1️⃣  `4444555566667777 | 10 | 22 | 123`\n"
        "2️⃣  `4444555566667777 | 10/22 | 123`\n"
        "3️⃣  `4444555566667777 / 10 / 22 / 123`\n"
        "4️⃣  `4444555566667777 / 1022 / 123`\n"
        "5️⃣  `4444555566667777 | 1022 | 123`\n"
        "6️⃣  Full format (includes name, address, etc.)\n\n"
        "_First, paste your card data, then pick a format!_"
    )

    await update.message.reply_text(
        formats_text,
        parse_mode=ParseMode.MARKDOWN
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command"""
    help_text = (
        "❓ *Help & Usage*\n\n"
        "*Basic Steps:*\n"
        "1. Paste your card data (single card or multiple)\n"
        "2. Click a format number button\n"
        "3. Get your formatted cards in a .txt file\n\n"
        "*Supported Input Formats:*\n"
        "• Tab-separated values\n"
        "• Pipe-separated values (|)\n"
        "• Slash-separated values (/)\n"
        "• Space-separated values\n"
        "• Mixed formats\n\n"
        "*Data I Extract:*\n"
        "• Card number (16-19 digits)\n"
        "• Expiry month & year\n"
        "• CVV (3-4 digits)\n"
        "• Name, address, city, state, zip\n\n"
        "*Data I Remove:*\n"
        "• Prices and amounts\n"
        "• Seller tags (e.g., LIVE =>)\n"
        "• Random dates\n"
        "• Placeholder values (null, N/A, No)\n"
        "• Junk and corrupted fields\n\n"
        "Use /format to see all available output styles."
    )

    await update.message.reply_text(
        help_text,
        parse_mode=ParseMode.MARKDOWN
    )


async def receive_cards(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle incoming card data"""
    if not update.message.text:
        await update.message.reply_text("⚠️ Please send me card data as text.")
        return SELECT_FORMAT

    # Store the card data
    context.user_data['card_text'] = update.message.text

    # Parse cards to show count
    parsed_cards = CardParser.parse_multiple_cards(update.message.text)

    if not parsed_cards:
        await update.message.reply_text(
            "❌ Could not extract any valid cards from your data.\n\n"
            "Make sure your data includes:\n"
            "• Card number (16-19 digits)\n"
            "• Expiry month (MM)\n"
            "• CVV (3-4 digits)\n\n"
            "Try again with different data."
        )
        return SELECT_FORMAT

    # Show format selection keyboard
    keyboard = [
        [InlineKeyboardButton("1️⃣ card | month | year | cvv", callback_data="fmt_1")],
        [InlineKeyboardButton("2️⃣ card | month/year | cvv", callback_data="fmt_2")
