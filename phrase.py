"""
BIP39 24-word mnemonic generator bot.

Sends a .txt file of freshly generated, cryptographically random
24-word BIP39 seed phrases (one per line) whenever you send /generate.

Setup:
    pip install pyTelegramBotAPI mnemonic

    1. Get a bot token from @BotFather on Telegram.
    2. Paste it into BOT_TOKEN below.
    3. Run: python3 bip39_bot.py
    4. Message your bot /generate on Telegram.

Notes:
- Uses the official `mnemonic` library, which uses the standard
  2048-word BIP39 English wordlist and Python's `secrets` module
  (CSPRNG) for entropy generation.
- 24 words = 256 bits of entropy + checksum, per the BIP39 spec, so
  every phrase generated is a fully valid mnemonic (not just 24
  random words strung together).
- Each /generate produces exactly MAX_PHRASES phrases in one file.
  Change MAX_PHRASES below to adjust the count.
- Each user only gets their own generated file sent to their own
  chat — nothing is logged or stored anywhere.
"""

import io
import secrets

import telebot
from mnemonic import Mnemonic

BOT_TOKEN = "8876484848:AAF0c5el6Rs6aUmwzR5psy1QYJbml8uTJeg"

# Safety cap: keeps generation fast and the file well under Telegram's
# 50MB bot-upload limit (a 24-word line is ~180-200 bytes, so 10,000
# lines is only ~2MB).
MAX_PHRASES = 200_000

bot = telebot.TeleBot(BOT_TOKEN)
mnemo = Mnemonic("english")


def generate_24_word_phrase() -> str:
    # 256 bits of entropy -> 24-word mnemonic with valid checksum
    entropy = secrets.token_bytes(32)
    return mnemo.to_mnemonic(entropy)


@bot.message_handler(commands=["start", "help"])
def handle_start(message):
    bot.reply_to(
        message,
        f"Send /generate to get a .txt file with {MAX_PHRASES:,} random "
        "24-word BIP39 seed phrases, one per line.\n\n"
        "⚠️ Anyone who has this file can access anything secured by "
        "any of these phrases. Don't share it, and delete it from "
        "Telegram once you've saved it somewhere safe offline.",
    )


@bot.message_handler(commands=["generate"])
def handle_generate(message):
    phrases = [generate_24_word_phrase() for _ in range(MAX_PHRASES)]
    content = "\n".join(phrases)

    file_bytes = io.BytesIO(content.encode("utf-8"))
    file_bytes.name = f"seed_phrases_{MAX_PHRASES}.txt"

    bot.send_document(message.chat.id, file_bytes)


if __name__ == "__main__":
    print("Bot running (polling)...")
    bot.infinity_polling()
