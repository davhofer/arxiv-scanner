"""Simple sqlite3 storage for papers and topics."""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

class Storage:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS topics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    query TEXT NOT NULL,
                    last_run_at TEXT,
                    active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS papers (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    authors TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    abstract TEXT NOT NULL,
                    url TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS paper_topics (
                    paper_id TEXT,
                    topic_id INTEGER,
                    relevance_score REAL,
                    is_relevant INTEGER,
                    reasoning TEXT,
                    summary TEXT,
                    tags TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (paper_id, topic_id),
                    FOREIGN KEY (paper_id) REFERENCES papers (id),
                    FOREIGN KEY (topic_id) REFERENCES topics (id)
                )
            """)

    def add_topic(self, name: str, description: str, query: str):
        with self._get_conn() as conn:
            cursor = conn.execute(
                "INSERT INTO topics (name, description, query) VALUES (?, ?, ?)",
                (name, description, query)
            )
            return cursor.lastrowid

    def get_topics(self, active_only: bool = False) -> List[Dict[str, Any]]:
        query = "SELECT * FROM topics"
        if active_only:
            query += " WHERE active = 1"
        with self._get_conn() as conn:
            return [dict(row) for row in conn.execute(query).fetchall()]

    def get_topic(self, topic_id: int) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
            return dict(row) if row else None

    def update_topic_last_run(self, topic_id: int):
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE topics SET last_run_at = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), topic_id)
            )

    def save_paper(self, paper: Dict[str, Any]):
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO papers (id, title, authors, published_at, abstract, url)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                paper['id'], paper['title'], json.dumps(paper['authors']),
                paper['published_at'], paper['abstract'], paper['url']
            ))

    def save_paper_topic_link(self, paper_id: str, topic_id: int, result: Dict[str, Any]):
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO paper_topics 
                (paper_id, topic_id, relevance_score, is_relevant, reasoning, summary, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                paper_id, topic_id, 
                result.get('relevance_score'),
                1 if result.get('is_relevant') else 0,
                result.get('reasoning'),
                json.dumps(result.get('summary')),
                json.dumps(result.get('summary', {}).get('tags', []))
            ))

    def get_paper_topic_link(self, paper_id: str, topic_id: int):
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM paper_topics WHERE paper_id = ? AND topic_id = ?",
                (paper_id, topic_id)
            ).fetchone()
            return dict(row) if row else None

    def get_relevant_papers(self, topic_id: int) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT p.*, pt.relevance_score, pt.reasoning, pt.summary, pt.tags
                FROM papers p
                JOIN paper_topics pt ON p.id = pt.paper_id
                WHERE pt.topic_id = ? AND pt.is_relevant = 1
                ORDER BY p.published_at DESC
            """, (topic_id,)).fetchall()
            
            results = []
            for row in rows:
                d = dict(row)
                d['authors'] = json.loads(d['authors'])
                d['summary'] = json.loads(d['summary']) if d['summary'] else {}
                d['tags'] = json.loads(d['tags']) if d['tags'] else []
                results.append(d)
            return results
