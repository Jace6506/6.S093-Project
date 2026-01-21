"""Telegram bot manager for running the bot in background."""
import os
import asyncio
import threading
from telegram.ext import Application
from telegram_handler import setup_handlers

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

_application = None
_bot_thread = None


def start_bot():
    """Start the Telegram bot in a background thread."""
    global _application, _bot_thread
    
    if not TELEGRAM_BOT_TOKEN:
        print("⚠️  TELEGRAM_BOT_TOKEN not set. Telegram features disabled.")
        return None
    
    if _application is not None:
        return _application
    
    def run_bot():
        async def main():
            global _application
            _application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
            setup_handlers(_application)
            await _application.initialize()
            await _application.start()
            await _application.updater.start_polling()
            print("✅ Telegram bot started")
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
        loop.run_forever()
    
    _bot_thread = threading.Thread(target=run_bot, daemon=True)
    _bot_thread.start()
    
    # Give bot time to start
    import time
    time.sleep(2)
    
    return _application


def stop_bot():
    """Stop the Telegram bot."""
    global _application, _bot_thread
    if _application:
        asyncio.run(_application.stop())
        _application = None
    _bot_thread = None
