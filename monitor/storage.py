from pathlib import Path
from contextlib import contextmanager
import sqlite3
import time


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS checks (
                id INTEGER PRIMARY KEY, service_key TEXT NOT NULL,
                checked_at REAL NOT NULL, status TEXT NOT NULL,
                latency_ms REAL NOT NULL, message TEXT NOT NULL,
                http_status INTEGER, expires_at TEXT, days_remaining INTEGER)""")
            db.execute("CREATE INDEX IF NOT EXISTS checks_service ON checks(service_key, id DESC)")
            db.execute("CREATE INDEX IF NOT EXISTS checks_time ON checks(checked_at)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def save_round(self, results, retention_days):
        with self.connect() as db:
            db.executemany("""INSERT INTO checks
                (service_key, checked_at, status, latency_ms, message, http_status, expires_at, days_remaining)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", [
                (s.key, r.checked_at, r.status, r.latency_ms, r.message,
                 r.http_status, r.expires_at, r.days_remaining) for s, r in results])
            db.execute("DELETE FROM checks WHERE checked_at < ?", (time.time() - retention_days * 86400,))

    def snapshot(self, services):
        with self.connect() as db:
            output = []
            for s in services:
                rows = db.execute("""SELECT checked_at, status, latency_ms, message, http_status,
                    expires_at, days_remaining FROM checks WHERE service_key = ? ORDER BY id DESC LIMIT 50""",
                                  (s.key,)).fetchall()
                # O painel não precisa exibir URLs que podem conter query strings.
                output.append(dict(id=s.id, name=s.name, type=s.kind,
                                   latest=dict(rows[0]) if rows else None,
                                   history=[dict(row) for row in rows]))
        return output
