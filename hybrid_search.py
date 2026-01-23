"""Hybrid search combining BM25 (FTS5) and semantic (sqlite-vec) search."""
import sqlite3
import struct
from typing import Dict, List, Optional
from rag_database import get_rag_connection, get_metadata_by_ids


def serialize_embedding(embedding: List[float]) -> bytes:
    """Serialize embedding to binary format for sqlite-vec."""
    return struct.pack(f'{len(embedding)}f', *embedding)


def bm25_search(conn: sqlite3.Connection, query: str, limit: int = 100) -> Dict[int, float]:
    """
    Search using BM25 ranking via FTS5.
    
    Args:
        conn: Database connection
        query: Search query text
        limit: Maximum number of results
    
    Returns:
        Dict mapping embedding_id to raw BM25 score.
        Note: FTS5 BM25 scores are NEGATIVE (more negative = better match).
    """
    cursor = conn.cursor()
    
    # Escape special FTS5 characters
    safe_query = query.replace('"', '""')
    
    try:
        cursor.execute("""
            SELECT rowid, bm25(embeddings_fts) as score
            FROM embeddings_fts
            WHERE embeddings_fts MATCH ?
            LIMIT ?
        """, (safe_query, limit))
        
        return {row[0]: row[1] for row in cursor.fetchall()}
    except sqlite3.OperationalError:
        # No matches or invalid query
        return {}


def semantic_search(conn: sqlite3.Connection, query_embedding: List[float], limit: int = 100) -> Dict[int, float]:
    """
    Search using sqlite-vec's native cosine distance.
    
    Args:
        conn: Database connection
        query_embedding: Pre-computed embedding of the query (384 dimensions)
        limit: Maximum number of results
    
    Returns:
        Dict mapping rowid to cosine distance.
        Note: cosine distance is in [0, 2] where 0 = identical, 2 = opposite.
    """
    cursor = conn.cursor()
    
    try:
        # sqlite-vec requires 'k = ?' in the WHERE clause when using a parameterized limit
        cursor.execute("""
            SELECT rowid, distance
            FROM vec_embeddings
            WHERE embedding MATCH ?
              AND k = ?
            ORDER BY distance
        """, (serialize_embedding(query_embedding), limit))
        
        return {row[0]: row[1] for row in cursor.fetchall()}
    except sqlite3.OperationalError as e:
        # sqlite-vec might not be available or table doesn't exist
        print(f"Warning: Semantic search failed: {e}")
        return {}


def normalize_bm25_scores(bm25_scores: Dict[int, float]) -> Dict[int, float]:
    """
    Normalize BM25 scores to [0, 1] range.
    
    FTS5 BM25 scores are negative (more negative = better).
    We invert so that best match gets 1.0, worst gets 0.0.
    
    Args:
        bm25_scores: Dict of embedding_id -> BM25 score
    
    Returns:
        Dict of embedding_id -> normalized score [0, 1]
    """
    if not bm25_scores:
        return {}
    
    scores = list(bm25_scores.values())
    min_score = min(scores)  # Most negative = best
    max_score = max(scores)  # Least negative = worst
    
    if min_score == max_score:
        return {id: 1.0 for id in bm25_scores}
    
    score_range = max_score - min_score
    return {
        id: (max_score - score) / score_range
        for id, score in bm25_scores.items()
    }


def normalize_distances(distances: Dict[int, float]) -> Dict[int, float]:
    """
    Normalize cosine distances to similarity scores in [0, 1].
    
    Cosine distance is in [0, 2] where 0 = identical.
    We convert to similarity: 1 - (distance / 2)
    Then normalize so best match gets 1.0.
    
    Args:
        distances: Dict of embedding_id -> cosine distance
    
    Returns:
        Dict of embedding_id -> normalized similarity [0, 1]
    """
    if not distances:
        return {}
    
    # Convert distances to similarities
    similarities = {id: 1 - (dist / 2) for id, dist in distances.items()}
    
    # Normalize to [0, 1] range
    min_sim = min(similarities.values())
    max_sim = max(similarities.values())
    
    if min_sim == max_sim:
        return {id: 1.0 for id in similarities}
    
    sim_range = max_sim - min_sim
    return {
        id: (sim - min_sim) / sim_range
        for id, sim in similarities.items()
    }


def hybrid_search(
    conn: sqlite3.Connection,
    query: str,
    query_embedding: List[float],
    keyword_weight: float = 0.5,
    semantic_weight: float = 0.5,
    top_k: int = 10,
) -> List[Dict]:
    """
    Perform hybrid search combining BM25 and sqlite-vec cosine similarity.
    
    Formula: final_score = keyword_weight * bm25 + semantic_weight * cosine_sim
    
    Args:
        conn: Database connection
        query: Search query text
        query_embedding: Pre-computed embedding of the query
        keyword_weight: Weight for BM25 (0-1)
        semantic_weight: Weight for cosine similarity (0-1)
        top_k: Number of results to return
    
    Returns:
        List of results sorted by combined score (highest first)
    """
    # Step 1: Get BM25 scores from FTS5
    bm25_raw = bm25_search(conn, query)
    bm25_normalized = normalize_bm25_scores(bm25_raw)
    
    # Step 2: Get semantic distances from sqlite-vec
    semantic_raw = semantic_search(conn, query_embedding, limit=100)
    semantic_normalized = normalize_distances(semantic_raw)
    
    # Step 3: Get all unique IDs from both searches
    all_ids = set(bm25_normalized.keys()) | set(semantic_normalized.keys())
    
    if not all_ids:
        return []
    
    # Step 4: Get metadata for all candidates
    metadata = get_metadata_by_ids(conn, list(all_ids))
    
    # Step 5: Compute combined scores
    scored_results = []
    
    for id in all_ids:
        # BM25 score (0 if no keyword match)
        bm25_score = bm25_normalized.get(id, 0.0)
        
        # Semantic score (0 if not in top semantic results)
        semantic_score = semantic_normalized.get(id, 0.0)
        
        # Combined score
        final_score = (keyword_weight * bm25_score) + (semantic_weight * semantic_score)
        
        meta = metadata.get(id, {})
        scored_results.append({
            "id": id,
            "content": meta.get("content", ""),
            "source_type": meta.get("source_type", ""),
            "source_id": meta.get("source_id", ""),
            "metadata": meta.get("metadata", {}),
            "bm25_score": bm25_score,
            "semantic_score": semantic_score,
            "final_score": final_score,
        })
    
    # Sort by final score (descending)
    scored_results.sort(key=lambda x: x["final_score"], reverse=True)
    
    return scored_results[:top_k]
