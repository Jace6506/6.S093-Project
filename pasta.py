"""Main entry point for Mastodon Post Generator."""
from modes import create_new_post_mode, craft_replies_mode


if __name__ == "__main__":
    # Ask user which mode they want
    print("=" * 50)
    print("MASTODON POST GENERATOR")
    print("=" * 50)
    print("\nWhat would you like to do?")
    print("  1. Create a new post from Notion content")
    print("  2. Craft replies to existing posts")
    
    mode = input("\nEnter choice (1 or 2): ").strip()
    
    if mode == "1":
        create_new_post_mode()
    elif mode == "2":
        craft_replies_mode()
    else:
        print("Invalid choice. Exiting.")
