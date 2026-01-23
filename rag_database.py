"""RAG database module with FTS5 and sqlite-vec support."""
import json
import sqlite3
import struct
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any
from contextlib import contextmanager

try:
    import sqlite_vec
except ImportError:
    sqlite_vec = None

# Database file path - use same database as main app
DB_PATH = os.getenv("DB_PATH", "/opt/sundai/data.db")


@contextmanager
def get_rag_connection():
    """Context manager for RAG database connections with sqlite-vec support."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # Load sqlite-vec extension if available
    if sqlite_vec:
        try:
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
        except Exception as e:
            print(f"Warning: Could not load sqlite-vec extension: {e}")
    
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_rag_database():
    """Initialize RAG database with embeddings tables, FTS5, and sqlite-vec."""
    with get_rag_connection() as conn:
        cursor = conn.cursor()
        
        # Metadata table (stores content and metadata, linked to vectors by rowid)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS embeddings_meta (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,
                source_id TEXT,
                content TEXT NOT NULL,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Vector table using sqlite-vec (384 dimensions for MiniLM-L6-v2)
        if sqlite_vec:
            try:
                cursor.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS vec_embeddings USING vec0(
                        embedding float[384] distance_metric=cosine
                    )
                """)
            except sqlite3.OperationalError as e:
                # Table might already exist with different schema
                print(f"Note: vec_embeddings table issue: {e}")
        
        # FTS5 virtual table for BM25 keyword search
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS embeddings_fts USING fts5(
                content,
                source_type,
                source_id,
                content='embeddings_meta',
                content_rowid='id'
            )
        """)
        
        # Triggers to keep FTS5 in sync with embeddings_meta table
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS embeddings_ai AFTER INSERT ON embeddings_meta BEGIN
                INSERT INTO embeddings_fts(rowid, content, source_type, source_id)
                VALUES (new.id, new.content, new.source_type, new.source_id);
            END
        """)
        
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS embeddings_ad AFTER DELETE ON embeddings_meta BEGIN
                INSERT INTO embeddings_fts(embeddings_fts, rowid, content, source_type, source_id)
                VALUES ('delete', old.id, old.content, old.source_type, old.source_id);
            END
        """)
        
        # Create indexes for better performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_embeddings_meta_source 
            ON embeddings_meta(source_type, source_id)
        """)
        
        conn.commit()
        print(f"RAG database initialized at {DB_PATH}")


def serialize_embedding(embedding: List[float]) -> bytes:
    """Serialize embedding to binary format for sqlite-vec."""
    return struct.pack(f'{len(embedding)}f', *embedding)


def save_embedding(
    conn: sqlite3.Connection,
    source_type: str,
    content: str,
    embedding: List[float],
    source_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> int:
    """
    Save an embedding to the database.
    
    Inserts into:
    1. embeddings_meta - content and metadata (FTS5 updated via trigger)
    2. vec_embeddings - vector for similarity search (matched by rowid)
    """
    cursor = conn.cursor()
    
    # Insert metadata (FTS5 index updated automatically via trigger)
    cursor.execute(
        """
        INSERT INTO embeddings_meta (source_type, source_id, content, metadata, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            source_type,
            source_id,
            content,
            json.dumps(metadata) if metadata else None,
            datetime.now().isoformat(),
        ),
    )
    rowid = cursor.lastrowid
    
    # Insert vector with matching rowid (if sqlite-vec is available)
    if sqlite_vec and len(embedding) == 384:
        try:
            cursor.execute(
                """
                INSERT INTO vec_embeddings (rowid, embedding)
                VALUES (?, ?)
                """,
                (rowid, serialize_embedding(embedding)),
            )
        except sqlite3.OperationalError as e:
            print(f"Warning: Could not insert vector: {e}")
    
    conn.commit()
    return rowid


def get_metadata_by_ids(conn: sqlite3.Connection, ids: List[int]) -> Dict[int, Dict[str, Any]]:
    """Retrieve metadata for given IDs from embeddings_meta table."""
    if not ids:
        return {}
    
    cursor = conn.cursor()
    placeholders = ",".join("?" * len(ids))
    cursor.execute(f"""
        SELECT id, source_type, source_id, content, metadata
        FROM embeddings_meta
        WHERE id IN ({placeholders})
    """, ids)
    
    results = {}
    for row in cursor.fetchall():
        results[row[0]] = {
            "source_type": row[1],
            "source_id": row[2],
            "content": row[3],
            "metadata": json.loads(row[4]) if row[4] else {},
        }
    return results


def check_content_embedded(source_type: str, source_id: str) -> bool:
    """Check if content from a source has already been embedded."""
    with get_rag_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM embeddings_meta
            WHERE source_type = ? AND source_id = ?
        """, (source_type, source_id))
        result = cursor.fetchone()
        return result['count'] > 0 if result else False


def get_embedding_stats() -> Dict[str, Any]:
    """Get statistics about embedded content."""
    with get_rag_connection() as conn:
        cursor = conn.cursor()
        
        # Total embeddings
        cursor.execute("SELECT COUNT(*) as count FROM embeddings_meta")
        total = cursor.fetchone()['count']
        
        # By source type
        cursor.execute("""
            SELECT source_type, COUNT(*) as count
            FROM embeddings_meta
            GROUP BY source_type
        """)
        by_type = {row['source_type']: row['count'] for row in cursor.fetchall()}
        
        return {
            "total_embeddings": total,
            "by_source_type": by_type
        }
