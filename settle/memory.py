"""Alias memory.

The only thing worth carrying between runs is the answer to the one question
code cannot settle: which human is behind this spelling. Amounts, dates and
fees are recomputed every time; identity is remembered.

Entries are written only when a match is *approved* -- either by a human
clearing an exception, or by the verifier passing a high-confidence match.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .tools import normalise

SCHEMA = """
CREATE TABLE IF NOT EXISTS aliases (
    party_norm    TEXT PRIMARY KEY,
    party_raw     TEXT NOT NULL,
    customer_id   TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    source        TEXT NOT NULL,      -- human_approval | verifier_pass
    evidence      TEXT NOT NULL,
    first_seen    TEXT NOT NULL,
    times_used    INTEGER NOT NULL DEFAULT 0
);
"""


class AliasMemory:
    def __init__(self, path: Path | str = "state/aliases.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.execute(SCHEMA)
        self.conn.commit()

    # ---------------------------------------------------------------- read
    def lookup(self, party_name: str) -> str | None:
        row = self.conn.execute(
            "SELECT customer_id FROM aliases WHERE party_norm = ?",
            (normalise(party_name),)).fetchone()
        return row[0] if row else None

    def explain(self, party_name: str) -> dict | None:
        row = self.conn.execute(
            "SELECT party_raw, customer_id, customer_name, source, evidence, first_seen "
            "FROM aliases WHERE party_norm = ?", (normalise(party_name),)).fetchone()
        if not row:
            return None
        keys = ["party_raw", "customer_id", "customer_name", "source",
                "evidence", "first_seen"]
        return dict(zip(keys, row))

    def size(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]

    def dump(self) -> list[dict]:
        cur = self.conn.execute(
            "SELECT party_raw, customer_id, customer_name, source, evidence, "
            "first_seen, times_used FROM aliases ORDER BY first_seen")
        keys = ["party_raw", "customer_id", "customer_name", "source",
                "evidence", "first_seen", "times_used"]
        return [dict(zip(keys, r)) for r in cur.fetchall()]

    # --------------------------------------------------------------- write
    def remember(self, party_name: str, customer_id: str, customer_name: str,
                 source: str, evidence: str) -> bool:
        """Returns True if this is a new alias."""
        norm = normalise(party_name)
        if not norm:
            return False
        existing = self.conn.execute(
            "SELECT customer_id FROM aliases WHERE party_norm = ?", (norm,)).fetchone()
        if existing:
            self.conn.execute(
                "UPDATE aliases SET times_used = times_used + 1 WHERE party_norm = ?",
                (norm,))
            self.conn.commit()
            return False
        self.conn.execute(
            "INSERT INTO aliases (party_norm, party_raw, customer_id, customer_name,"
            " source, evidence, first_seen, times_used) VALUES (?,?,?,?,?,?,?,0)",
            (norm, party_name, customer_id, customer_name, source, evidence,
             datetime.now(timezone.utc).isoformat(timespec="seconds")))
        self.conn.commit()
        return True

    def reset(self) -> None:
        self.conn.execute("DELETE FROM aliases")
        self.conn.commit()
