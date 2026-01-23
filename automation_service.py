"""Standalone automation service that can run as a background process."""
import asyncio
import os
from dotenv import load_dotenv
from automation import start_automation, stop_automation
from database import init_database
from rag_database import init_rag_database
import signal
import sys

# Load environment variables
load_dotenv()

# Initialize databases before starting automation
print("Initializing databases...")
init_database()
init_rag_database()
print("✅ Databases initialized")


def signal_handler(sig, frame):
    """Handle shutdown signals gracefully."""
    print("\n🛑 Shutting down automation service...")
    stop_automation()
    sys.exit(0)


async def main():
    """Main entry point for automation service."""
    print("=" * 50)
    print("AUTOMATION SERVICE")
    print("=" * 50)
    print("\nStarting automation listeners...")
    print("   - Part 4: Auto-create posts from Notion updates")
    print("   - Part 5: Auto-reply to Mastodon notifications")
    print("\nPress Ctrl+C to stop\n")
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start automation (this will run until Ctrl+C)
    try:
        await start_automation()
    except KeyboardInterrupt:
        signal_handler(None, None)
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
