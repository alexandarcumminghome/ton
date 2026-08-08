#!/usr/bin/env python3
"""
TON Seed Phrase Wallet Checker -- Telegram Bot
================================================
Send this bot a .txt file (one seed phrase per line) in a private chat.
It derives every common TON wallet-contract address for each phrase,
checks each on-chain for balance/NFTs, shows a live progress bar, and
sends back only the phrases that turned out to be real wallets.

SECURITY
--------
- Only ALLOWED_USER_ID (set below) can use this bot -- everyone else's
  messages are ignored. Get your own numeric ID by messaging
  @userinfobot on Telegram.
- The uploaded file is processed in memory and never written to disk.
- Only YOU (the allowed user) ever receive the recovered phrases, sent
  straight back to the same private chat you uploaded from.
- Still: run this bot on a VPS/host you control, keep BOT_TOKEN secret
  (anyone with it can operate the bot), and delete the result messages
  from your chat history once you've copied what you need -- Telegram
  keeps message history on its servers like any other chat.

SETUP
-----
    pip install -r requirements.txt --break-system-packages
    # fill in BOT_TOKEN and ALLOWED_USER_ID below
    python3 telegram_bot.py
"""

import asyncio
import io
import time

import aiohttp
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters

from ton_core import NetworkGlobalID
from tonutils.clients.http.tonapi import TonapiClient

from check_wallets import load_phrases_from_text, check_phrase, WALLET_VERSIONS  # noqa: F401 (re-exported for reuse)

# ============================== CONFIG ================================

BOT_TOKEN = "8689616167:AAEvm3LiJfgjuo1YcGSOHrSbjwJsuBOnOD8"            # from @BotFather
ALLOWED_USER_ID = 8702916389       # your numeric Telegram user ID, from @userinfobot -- REQUIRED

TONAPI_KEY = "e2db08b713d3acae8575ed0f994a7be21aef38b5bde986402a2d534c649bc992"           # optional, free key from https://tonconsole.com for higher rate limits
REQUESTS_PER_SECOND = 8 if TONAPI_KEY else 1

PROGRESS_EDIT_MIN_INTERVAL = 2.5  # seconds between progress-bar edits, keeps Telegram happy

# ========================================================================


def render_bar(done: int, total: int, width: int = 20) -> str:
    if total == 0:
        return "[no phrases found in file]"
    filled = int(width * done / total)
    bar = "▓" * filled + "░" * (width - filled)
    pct = int(100 * done / total)
    return f"[{bar}] {pct}%  ({done}/{total})"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    await update.message.reply_text(
        "Send me a .txt file with one TON seed phrase per line.\n"
        "I'll check each one on-chain and send back only the ones that "
        "are real wallets (have a balance or hold an NFT)."
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user is None or user.id != ALLOWED_USER_ID:
        return  # silently ignore anyone who isn't you

    doc = update.message.document
    if doc is None:
        return
    name = (doc.file_name or "").lower()
    if not (name.endswith(".txt") or (doc.mime_type or "").startswith("text/")):
        await update.message.reply_text("Please send a .txt file, one phrase per line.")
        return

    status_msg = await update.message.reply_text("Reading file...")

    # Download straight into memory -- never touches disk.
    tg_file = await doc.get_file()
    buf = io.BytesIO()
    await tg_file.download_to_memory(buf)
    text = buf.getvalue().decode("utf-8", errors="ignore")

    phrases, unreadable = load_phrases_from_text(text)
    if not phrases:
        await status_msg.edit_text(
            f"Couldn't find any valid-looking phrases in that file "
            f"({len(unreadable)} unreadable line(s))."
        )
        return

    await status_msg.edit_text(
        f"Loaded {len(phrases)} phrase(s), {len(unreadable)} unreadable line(s).\n"
        f"Checking on-chain now...\n\n{render_bar(0, len(phrases))}"
    )

    client = TonapiClient(NetworkGlobalID.MAINNET, api_key=TONAPI_KEY or None)
    headers = {"Authorization": f"Bearer {TONAPI_KEY}"} if TONAPI_KEY else {}
    limiter = asyncio.Semaphore(1)

    active_results = []
    last_edit = 0.0

    async with aiohttp.ClientSession() as session:
        for idx, (line_no, words, checksum_valid) in enumerate(phrases, 1):
            res = await check_phrase(client, session, headers, line_no, words, checksum_valid, limiter)
            if res.active:
                active_results.append(res)

            now = time.time()
            if now - last_edit >= PROGRESS_EDIT_MIN_INTERVAL or idx == len(phrases):
                try:
                    await status_msg.edit_text(
                        f"Checking on-chain...\n\n{render_bar(idx, len(phrases))}\n"
                        f"Hits so far: {len(active_results)}"
                    )
                    last_edit = now
                except Exception:
                    pass  # ignore "message not modified" / rate-limit hiccups

            await asyncio.sleep(1 / REQUESTS_PER_SECOND)

    await status_msg.edit_text(
        f"Done. Checked {len(phrases)} phrase(s), {len(unreadable)} unreadable.\n"
        f"Active wallets found: {len(active_results)}"
    )

    if not active_results:
        await update.message.reply_text("None of the phrases matched a funded or NFT-holding wallet.")
        return

    lines = []
    for res in active_results:
        flag = "" if res.checksum_valid else "  [checksum invalid, recovered anyway]"
        lines.append(f"=== line {res.line_no}{flag} ===")
        lines.append(f"phrase: {res.phrase}")
        for version, address, balance_ton, nft_count in res.hits:
            lines.append(f"  {version}: {address}  balance={balance_ton:.4f} TON  nfts={nft_count}")
        lines.append("")
    out_text = "\n".join(lines)

    if len(out_text) < 3500:
        await update.message.reply_text(f"<pre>{out_text}</pre>", parse_mode=ParseMode.HTML)
    else:
        out_bytes = io.BytesIO(out_text.encode("utf-8"))
        out_bytes.name = "active_wallets.txt"
        await update.message.reply_document(document=out_bytes, filename="active_wallets.txt",
                                             caption=f"{len(active_results)} active wallet(s) found.")


async def unauthorized_catch_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Any non-document message from a non-allowed user is ignored (no reply,
    # so the bot doesn't confirm to strangers that it's alive/listening).
    if update.effective_user and update.effective_user.id == ALLOWED_USER_ID:
        await update.message.reply_text("Send me a .txt file of seed phrases to check.")


def main():
    if not BOT_TOKEN or not ALLOWED_USER_ID:
        raise SystemExit("Set BOT_TOKEN and ALLOWED_USER_ID at the top of telegram_bot.py before running.")

    app: Application = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unauthorized_catch_all))

    print("Bot running (polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()
