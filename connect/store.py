"""SQLite storage: cases, their items, messages, what we learned, and the audit trail."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
  id INTEGER PRIMARY KEY, entity_id TEXT NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL,
  token TEXT UNIQUE, channel TEXT, language TEXT, expires_on TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES cases(id), entity_id TEXT NOT NULL,
  date TEXT NOT NULL, day_key TEXT NOT NULL, day_name_local TEXT, shown TEXT NOT NULL, proposed TEXT NOT NULL,
  basis TEXT, mode TEXT, confidence REAL, evidence TEXT, learning_notes TEXT, expected_views INTEGER,
  views_from_last_year INTEGER, decision TEXT NOT NULL DEFAULT 'PENDING', final_hours TEXT, decline_reason TEXT,
  decided_by TEXT, decided_at TEXT, write_status TEXT NOT NULL DEFAULT 'NONE', write_error TEXT,
  previous_hours TEXT, sandbox_readback TEXT);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY, case_id INTEGER NOT NULL, kind TEXT NOT NULL, channel TEXT, language TEXT,
  body TEXT NOT NULL, body_en TEXT, sent_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS preferences (
  entity_id TEXT PRIMARY KEY, standing_permission INTEGER, opted_out INTEGER);
CREATE TABLE IF NOT EXISTS learned (
  entity_id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY, at TEXT NOT NULL, entity_id TEXT, case_id INTEGER, step TEXT NOT NULL,
  actor TEXT NOT NULL, summary TEXT NOT NULL, data TEXT);
CREATE TABLE IF NOT EXISTS sandbox_entities (
  entity_id TEXT PRIMARY KEY, sandbox_id TEXT NOT NULL);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.db.executescript(SCHEMA)
            self.db.commit()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self.lock:
            cursor = self.db.execute(sql, params)
            self.db.commit()
            return cursor

    def all(self, sql: str, params: tuple = ()) -> list:
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, params).fetchall()]

    def one(self, sql: str, params: tuple = ()) -> dict | None:
        rows = self.all(sql, params)
        return rows[0] if rows else None

    def log(self, step: str, actor: str, summary: str, entity_id: str | None = None, case_id: int | None = None,
            data: dict | None = None) -> None:
        """Audit trail: every step, who did it and on what evidence."""
        self.execute("INSERT INTO events (at, entity_id, case_id, step, actor, summary, data) VALUES (?,?,?,?,?,?,?)",
                     (now(), entity_id, case_id, step, actor, summary, json.dumps(data, ensure_ascii=False) if data else None))

    def get_learned(self, entity_id: str) -> dict:
        row = self.one("SELECT data FROM learned WHERE entity_id = ?", (entity_id,))
        return json.loads(row["data"]) if row else {}

    def set_learned(self, entity_id: str, data: dict) -> None:
        self.execute("INSERT INTO learned (entity_id, data) VALUES (?, ?) ON CONFLICT(entity_id) DO UPDATE SET data = excluded.data",
                     (entity_id, json.dumps(data, ensure_ascii=False)))

    def reset(self) -> None:
        with self.lock:
            for table in ("items", "messages", "cases", "preferences", "learned", "events"):
                self.db.execute(f"DELETE FROM {table}")
            self.db.commit()
