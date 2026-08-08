"""
BIP39 24-word mnemonic generator bot.

Sends a freshly generated, cryptographically random 24-word BIP39
seed phrase as a .txt file whenever you send /generate (or /start).

Setup:
    pip install pyTelegramBotAPI mnemonic

    1. Get a bot token from @BotFather on Telegram.
    2. Paste it into BOT_TOKEN below.
    3. Run: python3 bip39_bot.py
    4. Message your bot /generate on Telegram (or /generate 500 for
       500 phrases in one file, up to MAX_PHRASES).

Notes:
- Uses the official `mnemonic` library, which uses the standard
  2048-word BIP39 English wordlist and Python's `secrets` module
  (CSPRNG) for entropy generation.
- 24 words = 256 bits of entropy + checksum, per the BIP39 spec, so
  every phrase generated is a fully valid mnemonic (not just 24
  random words strung together).
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
        "Send /generate to get one random 24-word BIP39 seed phrase "
        "as a .txt file, or /generate <n> for multiple phrases in "
        f"one file (up to {MAX_PHRASES:,}).\n\n"
        "⚠️ Anyone who has this file can access anything secured by "
        "any of these phrases. Don't share it, and delete it from "
        "Telegram once you've saved it somewhere safe offline.",
    )


@bot.message_handler(commands=["generate"])
def handle_generate(message):
    parts = message.text.split()
    count = 1

    if len(parts) > 1:
        try:
            count = int(parts[1])
        except ValueError:
            bot.reply_to(message, "Usage: /generate or /generate <number>")
            return

        if count < 1:
            bot.reply_to(message, "Count must be at least 1.")
            return

        if count > MAX_PHRASES:
            bot.reply_to(
                message,
                f"Max is {MAX_PHRASES:,} phrases per file. "
                f"Sending {MAX_PHRASES:,} instead.",
            )
            count = MAX_PHRASES

    phrases = [generate_24_word_phrase() for _ in range(count)]
    content = "\n".join(phrases)

    file_bytes = io.BytesIO(content.encode("utf-8"))
    file_bytes.name = "seed_phrase.txt" if count == 1 else f"seed_phrases_{count}.txt"

    caption = (
        "🔑 Your 24-word BIP39 seed phrase. Keep it offline and private."
        if count == 1
        else f"🔑 {count:,} random 24-word BIP39 seed phrases, one per line. Keep this file offline and private."
    )

    bot.send_document(message.chat.id, file_bytes, caption=caption)


if __name__ == "__main__":
    print("Bot running (polling)...")
    bot.infinity_polling()
