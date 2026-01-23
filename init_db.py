#!/usr/bin/env python3
"""Initialize SQLite database for Mastodon Post Generator."""
import os
import sys
from database import init_database, DB_PATH

def main():
    """Initialize the database."""
    print(f"Initializing database at {DB_PATH}...")
    
    # Ensure directory exists
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
        print(f"Created directory: {db_dir}")
    
    try:
        init_database()
        print("Database initialized successfully!")
        
        # Set permissions
        if os.path.exists(DB_PATH):
            os.chmod(DB_PATH, 0o644)
            print(f"Database file permissions set: {oct(os.stat(DB_PATH).st_mode)[-3:]}")
        
        return 0
    except Exception as e:
        print(f"Error initializing database: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
