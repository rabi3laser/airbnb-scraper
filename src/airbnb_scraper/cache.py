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
    """
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
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
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, value, created_at, ttl) VALUES (?, ?, ?, ?)",
                (key, json.dumps(value, default=str), time.time(), ttl)
            )
            conn.commit()
    
    def delete(self, key: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            conn.commit()
            return cursor.rowcount > 0
    
    def clear_expired(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM cache WHERE (created_at + ttl) < ?",
                (time.time(),)
            )
            conn.commit()
            return cursor.rowcount
    
    def clear_all(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM cache")
            conn.commit()
            return cursor.rowcount
    
    def stats(self) -> dict:
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
