"""
Cache Manager - SQLite-based persistent cache
"""

import json
import sqlite3
import time
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class CacheManager:
    """
    SQLite-based persistent cache with TTL support.
    
    Features:
    - Automatic expiration handling
    - Thread-safe operations
    - Configurable TTL per entry
    - Auto-cleanup of expired entries
    
    Example:
    -------
    ```python
    cache = CacheManager(Path("/tmp/cache.db"))
    
    # Store with 1 hour TTL
    cache.set("key1", {"data": "value"}, ttl=3600)
    
    # Retrieve (returns None if expired)
    data = cache.get("key1")
    
    # Clear expired entries
    cache.clear_expired()
    ```
    """
    
    def __init__(self, db_path: Path):
        """
        Initialize cache manager.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    created_at REAL,
                    ttl INTEGER
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_created ON cache(created_at)")
            conn.commit()
    
    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found/expired
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT value, created_at, ttl FROM cache WHERE key = ?", 
                (key,)
            )
            row = cursor.fetchone()
            
            if row:
                value, created_at, ttl = row
                if time.time() - created_at < ttl:
                    return json.loads(value)
                else:
                    conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                    conn.commit()
        return None
    
    def set(self, key: str, value: Any, ttl: int = 3600):
        """
        Store value in cache.
        
        Args:
            key: Cache key
            value: Value to store (must be JSON serializable)
            ttl: Time to live in seconds (default: 1 hour)
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, value, created_at, ttl) VALUES (?, ?, ?, ?)",
                (key, json.dumps(value, default=str), time.time(), ttl)
            )
            conn.commit()
    
    def delete(self, key: str) -> bool:
        """
        Delete a cache entry.
        
        Args:
            key: Cache key
            
        Returns:
            True if entry was deleted, False if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            conn.commit()
            return cursor.rowcount > 0
    
    def clear_expired(self) -> int:
        """
        Remove all expired entries.
        
        Returns:
            Number of entries removed
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM cache WHERE (created_at + ttl) < ?",
                (time.time(),)
            )
            conn.commit()
            return cursor.rowcount
    
    def clear_all(self) -> int:
        """
        Clear entire cache.
        
        Returns:
            Number of entries removed
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM cache")
            conn.commit()
            return cursor.rowcount
    
    def stats(self) -> dict:
        """
        Get cache statistics.
        
        Returns:
            Dict with total entries, expired count, and size
        """
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
            expired = conn.execute(
                "SELECT COUNT(*) FROM cache WHERE (created_at + ttl) < ?",
                (time.time(),)
            ).fetchone()[0]
            
        size_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0
        
        return {
            "total_entries": total,
            "expired_entries": expired,
            "active_entries": total - expired,
            "size_bytes": size_bytes,
            "size_mb": round(size_bytes / 1024 / 1024, 2),
        }