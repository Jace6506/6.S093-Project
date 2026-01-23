"""Main entry point for Mastodon Post Generator."""
from modes import create_new_post_mode, craft_replies_mode
from telegram_interactive import send_mode_selection, send_confirmation
import asyncio


if __name__ == "__main__":
    print("=" * 50)
    print("MASTODON POST GENERATOR")
    print("=" * 50)
    print("\nStarting Telegram bot...")
    
    # Ask user which mode they want via Telegram
    mode = send_mode_selection()
    
    if mode == "new_post":
        create_new_post_mode()
    elif mode == "craft_replies":
        craft_replies_mode()
    else:
        send_confirmation("❌ *Invalid choice or no response. Exiting.*")
        print("Invalid choice or no response. Exiting.")