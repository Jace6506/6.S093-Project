#!/usr/bin/env python3
"""Initialize RAG database and embed Notion content."""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from rag_database import init_rag_database, get_embedding_stats
from rag_retrieval import embed_notion_content


def main():
    """Initialize RAG database and embed content."""
    print("=" * 50)
    print("RAG System Initialization")
    print("=" * 50)
    
    # Check for required environment variables
    NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
    NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")
    NOTION_PAGE_ID = os.environ.get("NOTION_PAGE_ID")
    
    if not NOTION_API_KEY:
        print("Error: NOTION_API_KEY not found in environment variables")
        print("Please set it in your .env file")
        return 1
    
    if not NOTION_DATABASE_ID and not NOTION_PAGE_ID:
        print("Error: Neither NOTION_DATABASE_ID nor NOTION_PAGE_ID found")
        print("Please set at least one in your .env file")
        return 1
    
    # Initialize RAG database
    print("\n1. Initializing RAG database...")
    try:
        init_rag_database()
        print("   ✓ Database initialized")
    except Exception as e:
        print(f"   ✗ Error initializing database: {e}")
        return 1
    
    # Embed Notion content
    print("\n2. Embedding Notion content...")
    try:
        chunks_embedded = embed_notion_content(force_reembed=False)
        print(f"   ✓ Embedded {chunks_embedded} chunks")
    except Exception as e:
        print(f"   ✗ Error embedding content: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Get statistics
    print("\n3. RAG System Statistics:")
    try:
        stats = get_embedding_stats()
        print(f"   Total embeddings: {stats['total_embeddings']}")
        for source_type, count in stats['by_source_type'].items():
            print(f"   - {source_type}: {count}")
    except Exception as e:
        print(f"   Warning: Could not get statistics: {e}")
    
    print("\n" + "=" * 50)
    print("Initialization complete!")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
