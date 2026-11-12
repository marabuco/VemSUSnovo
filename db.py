"""SQLite (arquivo único). O catálogo é um *snapshot* da base oficial; nada de dado pessoal é gravado."""
import json
import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS units (
  id TEXT PRIMARY KEY, cnes TEXT, name TEXT NOT NULL, type TEXT NOT NULL,
  address TEXT NOT NULL, neighborhood TEXT, phone TEXT, schedule TEXT,
  lat REAL, lng REAL, geo_source TEXT NOT NULL, services TEXT NOT NULL,
  before_visit TEXT, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_units_type ON units(type);
CREATE TABLE IF NOT EXISTS geocode_cache (
  key TEXT PRIMARY KEY, lat REAL, lng REAL, fetched_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sync_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL, finished_at TEXT,
  ok INTEGER, units_saved INTEGER, without_geo INTEGER, error TEXT, diagnostics TEXT
);
"""


class Database:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.conn.executescript(SCHEMA)

    # ---- unidades
    def replace_units(self, units: list[dict]) -> None:
        """Troca o snapshot de forma atômica. Chamado só quando há unidades (nunca apaga o último bom)."""
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        rows = [
            (
                u["id"], u["cnes"], u["name"], u["type"], u["address"], u["neighborhood"], u["phone"],
                u["schedule"], u["lat"], u["lng"], u["geo_source"], json.dumps(u["services"], ensure_ascii=False),
                u["before_visit"], now,
            )
            for u in units
        ]
        with self.lock, self.conn:
            self.conn.execute("DELETE FROM units")
            self.conn.executemany("INSERT INTO units VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)

    def all_units(self) -> list[dict]:
        with self.lock:
            rows = self.conn.execute("SELECT * FROM units").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["services"] = json.loads(d["services"])
            out.append(d)
        return out

    # ---- cache de geocodificação ((lat,lng) | () = falha conhecida | None = sem entrada)
    def geocode_cache_get(self, key: str, retry_days: int):
        with self.lock:
            r = self.conn.execute("SELECT lat,lng,fetched_at FROM geocode_cache WHERE key=?", (key,)).fetchone()
        if not r:
            return None
        if r["lat"] is None:
            return () if time.time() - r["fetched_at"] < retry_days * 86400 else None
        return (r["lat"], r["lng"])

    def geocode_cache_put(self, key: str, coords) -> None:
        lat, lng = coords if coords else (None, None)
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO geocode_cache VALUES (?,?,?,?)", (key, lat, lng, time.time())
            )

    # ---- log de sincronização
    def log_start(self) -> int:
        with self.lock, self.conn:
            cur = self.conn.execute(
                "INSERT INTO sync_log(started_at) VALUES (?)", (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),)
            )
            return int(cur.lastrowid)

    def log_finish(self, log_id: int, ok: bool, saved: int, without_geo: int, error: str | None, diag: dict | None):
        with self.lock, self.conn:
            self.conn.execute(
                "UPDATE sync_log SET finished_at=?, ok=?, units_saved=?, without_geo=?, error=?, diagnostics=? WHERE id=?",
                (
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), int(ok), saved, without_geo, error,
                    json.dumps(diag, ensure_ascii=False) if diag else None, log_id,
                ),
            )

    def last_sync(self, only_ok: bool = False) -> dict | None:
        q = "SELECT * FROM sync_log " + ("WHERE ok=1 " if only_ok else "") + "ORDER BY id DESC LIMIT 1"
        with self.lock:
            r = self.conn.execute(q).fetchone()
        if not r:
            return None
        d = dict(r)
        d["diagnostics"] = json.loads(d["diagnostics"]) if d["diagnostics"] else None
        return d
