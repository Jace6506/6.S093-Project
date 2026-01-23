"""High-level RAG retrieval functions."""
from typing import List, Dict, Tuple, Optional
from rag_database import get_rag_connection, check_content_embedded
from hybrid_search import hybrid_search
from embeddings import generate_embedding
from chunking import chunk_notion_content
from notion import (
    fetch_notion_database_pages,
    fetch_multiple_notion_pages,
    fetch_notion_page_content
)
import os


def format_context_for_prompt(results: List[Dict], max_chars: int = 4000) -> str:
    """
    Format search results into context for the LLM prompt.
    
    Args:
        results: List of search result dictionaries
        max_chars: Maximum characters for context
    
    Returns:
        Formatted context string
    """
    if not results:
        return "No relevant context found."
    
    context_parts = []
    chars_used = 0
    
    for i, result in enumerate(results, 1):
        header = f"[{i}. {result['source_type']}] (score: {result['final_score']:.2f})"
        content = result["content"]
        
        available = max_chars - chars_used - len(header) - 10
        if available <= 100:
            break
        
        if len(content) > available:
            content = content[:available - 3] + "..."
        
        entry = f"{header}\n{content}\n"
        context_parts.append(entry)
        chars_used += len(entry)
    
    return "\n".join(context_parts)


def retrieve_context(query: str, top_k: int = 10, keyword_weight: float = 0.5, semantic_weight: float = 0.5) -> Tuple[str, List[Dict]]:
    """
    High-level function to retrieve and format context for RAG.
    
    Args:
        query: Search query
        top_k: Number of results to retrieve
        keyword_weight: Weight for BM25 search (0-1)
        semantic_weight: Weight for semantic search (0-1)
    
    Returns:
        Tuple of (formatted_context_string, list_of_results)
    """
    query_embedding = generate_embedding(query)
    
    with get_rag_connection() as conn:
        results = hybrid_search(
            conn,
            query,
            query_embedding,
            keyword_weight=keyword_weight,
            semantic_weight=semantic_weight,
            top_k=top_k
        )
    
    formatted = format_context_for_prompt(results, max_chars=4000)
    return formatted, results


def embed_notion_content(force_reembed: bool = False) -> int:
    """
    Fetch Notion content, chunk it, and embed it into the database.
    
    Args:
        force_reembed: If True, re-embed even if content already embedded
    
    Returns:
        Number of chunks embedded
    """
    from rag_database import save_embedding, get_rag_connection
    from embeddings import generate_embeddings_batch
    
    NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "")
    NOTION_PAGE_ID = os.environ.get("NOTION_PAGE_ID", "")
    
    total_chunks = 0
    
    with get_rag_connection() as conn:
        if NOTION_DATABASE_ID:
            source_type = "notion_database"
            source_id = NOTION_DATABASE_ID
            
            # Check if already embedded
            if not force_reembed and check_content_embedded(source_type, source_id):
                print(f"Content from database {source_id} already embedded. Use force_reembed=True to re-embed.")
                return 0
            
            print(f"Fetching content from Notion database: {source_id}")
            content = fetch_notion_database_pages(NOTION_DATABASE_ID, max_pages=10)
            
            if content:
                chunks = chunk_notion_content(content, source_id, source_type)
                print(f"Chunked into {len(chunks)} chunks")
                
                # Batch generate embeddings
                texts = [c["content"] for c in chunks]
                embeddings = generate_embeddings_batch(texts)
                
                # Save each chunk
                for chunk, embedding in zip(chunks, embeddings):
                    save_embedding(
                        conn,
                        source_type=source_type,
                        content=chunk["content"],
                        embedding=embedding,
                        source_id=source_id,
                        metadata=chunk["metadata"]
                    )
                    total_chunks += 1
                
                print(f"Embedded {total_chunks} chunks from database")
        
        elif NOTION_PAGE_ID:
            page_ids = [pid.strip() for pid in NOTION_PAGE_ID.split(",") if pid.strip()]
            
            for page_id in page_ids:
                source_type = "notion_page"
                source_id = page_id
                
                # Check if already embedded
                if not force_reembed and check_content_embedded(source_type, source_id):
                    print(f"Content from page {source_id} already embedded. Skipping.")
                    continue
                
                print(f"Fetching content from Notion page: {source_id}")
                
                if len(page_ids) > 1:
                    content = fetch_multiple_notion_pages([page_id])
                else:
                    content = fetch_notion_page_content(page_id)
                
                if content:
                    chunks = chunk_notion_content(content, source_id, source_type)
                    print(f"Chunked into {len(chunks)} chunks")
                    
                    # Batch generate embeddings
                    texts = [c["content"] for c in chunks]
                    embeddings = generate_embeddings_batch(texts)
                    
                    # Save each chunk
                    for chunk, embedding in zip(chunks, embeddings):
                        save_embedding(
                            conn,
                            source_type=source_type,
                            content=chunk["content"],
                            embedding=embedding,
                            source_id=source_id,
                            metadata=chunk["metadata"]
                        )
                        total_chunks += 1
                    
                    print(f"Embedded {total_chunks} chunks from page {source_id}")
        else:
            print("No NOTION_DATABASE_ID or NOTION_PAGE_ID found in environment")
            return 0
    
    return total_chunks
