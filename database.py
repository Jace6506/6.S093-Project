"""SQLite database module for Mastodon Post Generator."""
import sqlite3
import os
from datetime import datetime
from typing import List, Optional, Dict, Any
from contextlib import contextmanager

# Database file path
# Default to local data.db in current directory, or VM path if that doesn't exist
_default_db_path = os.path.join(os.path.dirname(__file__), "data.db")
if not os.path.exists(_default_db_path):
    _default_db_path = "/opt/sundai/data.db"
DB_PATH = os.getenv("DB_PATH", _default_db_path)


@contextmanager
def get_db_connection():
    """Context manager for database connections."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Enable column access by name
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_database():
    """Initialize the database with required tables."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Posts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                tags TEXT,
                notion_page_id TEXT,
                mastodon_post_id TEXT,
                status TEXT DEFAULT 'draft',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                posted_at TIMESTAMP
            )
        ''')
        
        # API requests log table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS api_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint TEXT NOT NULL,
                method TEXT NOT NULL,
                status_code INTEGER,
                response_time_ms REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Generated content cache table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS generated_content (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_posts_created_at ON posts(created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_api_requests_created_at ON api_requests(created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_generated_content_source ON generated_content(source_id, source_type)')
        
        conn.commit()
        print(f"Database initialized at {DB_PATH}")


def create_post(content: str, tags: Optional[List[str]] = None, 
                notion_page_id: Optional[str] = None, 
                status: str = "draft") -> int:
    """Create a new post in the database."""
    tags_str = ",".join(tags) if tags else None
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO posts (content, tags, notion_page_id, status, updated_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (content, tags_str, notion_page_id, status, datetime.now()))
        return cursor.lastrowid


def get_post(post_id: int) -> Optional[Dict[str, Any]]:
    """Get a post by ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM posts WHERE id = ?', (post_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


def get_posts(limit: int = 10, offset: int = 0, 
              status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get posts with optional filtering."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if status:
            cursor.execute('''
                SELECT * FROM posts 
                WHERE status = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            ''', (status, limit, offset))
        else:
            cursor.execute('''
                SELECT * FROM posts 
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            ''', (limit, offset))
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def update_post(post_id: int, content: Optional[str] = None,
                tags: Optional[List[str]] = None,
                status: Optional[str] = None,
                mastodon_post_id: Optional[str] = None) -> bool:
    """Update a post."""
    updates = []
    params = []
    
    if content is not None:
        updates.append("content = ?")
        params.append(content)
    
    if tags is not None:
        updates.append("tags = ?")
        params.append(",".join(tags) if tags else None)
    
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    
    if mastodon_post_id is not None:
        updates.append("mastodon_post_id = ?")
        params.append(mastodon_post_id)
        if status == "posted":
            updates.append("posted_at = ?")
            params.append(datetime.now())
    
    if not updates:
        return False
    
    updates.append("updated_at = ?")
    params.append(datetime.now())
    params.append(post_id)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f'''
            UPDATE posts 
            SET {', '.join(updates)}
            WHERE id = ?
        ''', params)
        return cursor.rowcount > 0


def delete_post(post_id: int) -> bool:
    """Delete a post."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM posts WHERE id = ?', (post_id,))
        return cursor.rowcount > 0


def log_api_request(endpoint: str, method: str, 
                   status_code: int, response_time_ms: float):
    """Log an API request."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO api_requests (endpoint, method, status_code, response_time_ms)
            VALUES (?, ?, ?, ?)
        ''', (endpoint, method, status_code, response_time_ms))


def get_stats() -> Dict[str, Any]:
    """Get database statistics."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Total posts
        cursor.execute('SELECT COUNT(*) as count FROM posts')
        total_posts = cursor.fetchone()['count']
        
        # Posts by status
        cursor.execute('''
            SELECT status, COUNT(*) as count 
            FROM posts 
            GROUP BY status
        ''')
        posts_by_status = {row['status']: row['count'] for row in cursor.fetchall()}
        
        # Total API requests
        cursor.execute('SELECT COUNT(*) as count FROM api_requests')
        total_requests = cursor.fetchone()['count']
        
        return {
            "total_posts": total_posts,
            "posts_by_status": posts_by_status,
            "total_api_requests": total_requests
        }
