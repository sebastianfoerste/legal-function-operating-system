"""Small SQLite store for the local pilot.

One file, standard library only. Every write happens inside a ``BEGIN IMMEDIATE``
transaction, so two processes cannot interleave a read-check-write sequence; the
matter ``revision`` column is the optimistic-concurrency token callers must echo.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from models import AuditChainVerification, compute_audit_event_hash

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS actors (actor_id TEXT PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS matters (
    matter_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    state TEXT NOT NULL,
    current_version INTEGER NOT NULL,
    revision INTEGER NOT NULL,
    closed_outcome TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS matter_versions (
    matter_id TEXT NOT NULL REFERENCES matters(matter_id),
    version INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    document_name TEXT NOT NULL,
    document_sha256 TEXT NOT NULL,
    document_blob BLOB NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (matter_id, version)
);
CREATE TABLE IF NOT EXISTS assignments (
    matter_id TEXT NOT NULL REFERENCES matters(matter_id),
    role TEXT NOT NULL,
    actor_id TEXT NOT NULL REFERENCES actors(actor_id),
    assigned_by TEXT NOT NULL,
    assigned_at TEXT NOT NULL,
    PRIMARY KEY (matter_id, role, actor_id)
);
CREATE TABLE IF NOT EXISTS findings (
    matter_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    finding_key TEXT NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (matter_id, version, finding_key)
);
CREATE TABLE IF NOT EXISTS changes (
    matter_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    change_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (matter_id, version, change_id)
);
CREATE TABLE IF NOT EXISTS comments (
    comment_id TEXT PRIMARY KEY,
    matter_id TEXT NOT NULL REFERENCES matters(matter_id),
    body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decisions (
    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id TEXT NOT NULL REFERENCES matters(matter_id),
    version INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    review_hash TEXT,
    kind TEXT NOT NULL,
    target_id TEXT,
    actor_id TEXT NOT NULL,
    role TEXT NOT NULL,
    outcome TEXT NOT NULL,
    note TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    invalidated_at TEXT,
    invalidated_reason TEXT
);
CREATE TABLE IF NOT EXISTS events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id TEXT NOT NULL REFERENCES matters(matter_id),
    seq INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    role TEXT NOT NULL,
    note TEXT NOT NULL,
    payload TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    fixture_at TEXT,
    effort_minutes INTEGER,
    system_ms REAL,
    prev_hash TEXT,
    event_hash TEXT NOT NULL,
    UNIQUE (matter_id, seq)
);
CREATE TABLE IF NOT EXISTS deliverable_manifests (
    manifest_id INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id TEXT NOT NULL REFERENCES matters(matter_id),
    version INTEGER NOT NULL,
    kind TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    review_hash TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class Clock(Protocol):
    def now(self) -> str: ...


class SystemClock:
    """Operational wall-clock time. Fixture timestamps never come from here."""

    def now(self) -> str:
        return datetime.now(tz=UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _event_body(row: sqlite3.Row | dict[str, Any]) -> str:
    """The part of an event the hash commits to besides seq, type, actor and time."""

    return canonical(
        {
            "matter_id": row["matter_id"],
            "role": row["role"],
            "note": row["note"],
            "payload": json.loads(row["payload"]),
            "fixture_at": row["fixture_at"],
            "effort_minutes": row["effort_minutes"],
            "system_ms": row["system_ms"],
        }
    )


class PilotStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # executescript manages its own transaction, so the schema is created outside ours.
        with self.reading() as connection:
            connection.executescript(_SCHEMA)
            connection.execute(
                "INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """A write transaction that holds the database lock from its first statement."""

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    @contextmanager
    def reading(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    # -- events -------------------------------------------------------------------

    @staticmethod
    def append_event(
        connection: sqlite3.Connection,
        *,
        matter_id: str,
        event_type: str,
        actor_id: str,
        role: str,
        note: str,
        occurred_at: str,
        payload: dict[str, Any] | None = None,
        fixture_at: str | None = None,
        effort_minutes: int | None = None,
        system_ms: float | None = None,
    ) -> int:
        last = connection.execute(
            "SELECT seq, event_hash FROM events WHERE matter_id = ? ORDER BY seq DESC LIMIT 1",
            (matter_id,),
        ).fetchone()
        seq = 0 if last is None else last["seq"] + 1
        prev_hash = None if last is None else last["event_hash"]
        row = {
            "matter_id": matter_id,
            "role": role,
            "note": note,
            "payload": canonical(payload or {}),
            "fixture_at": fixture_at,
            "effort_minutes": effort_minutes,
            "system_ms": system_ms,
        }
        event_hash = compute_audit_event_hash(
            seq, prev_hash, event_type, actor_id, _event_body(row), occurred_at
        )
        connection.execute(
            "INSERT INTO events (matter_id, seq, event_type, actor_id, role, note, payload, "
            "occurred_at, fixture_at, effort_minutes, system_ms, prev_hash, event_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                matter_id,
                seq,
                event_type,
                actor_id,
                role,
                note,
                row["payload"],
                occurred_at,
                fixture_at,
                effort_minutes,
                system_ms,
                prev_hash,
                event_hash,
            ),
        )
        return seq

    @staticmethod
    def verify_chain(connection: sqlite3.Connection, matter_id: str) -> AuditChainVerification:
        rows = connection.execute(
            "SELECT * FROM events WHERE matter_id = ? ORDER BY seq", (matter_id,)
        ).fetchall()
        if not rows:
            return AuditChainVerification(
                verified=False, event_count=0, reason="no matter events recorded"
            )
        expected_prev: str | None = None
        for index, row in enumerate(rows):
            problem = None
            if row["seq"] != index:
                problem = f"sequence gap at seq {row['seq']}"
            elif row["prev_hash"] != expected_prev:
                problem = f"prev_hash mismatch at seq {row['seq']}"
            elif (
                compute_audit_event_hash(
                    row["seq"],
                    row["prev_hash"],
                    row["event_type"],
                    row["actor_id"],
                    _event_body(row),
                    row["occurred_at"],
                )
                != row["event_hash"]
            ):
                problem = f"event_hash mismatch at seq {row['seq']}"
            if problem:
                return AuditChainVerification(
                    verified=False,
                    event_count=len(rows),
                    broken_at_seq=row["seq"],
                    reason=problem,
                )
            expected_prev = row["event_hash"]
        return AuditChainVerification(
            verified=True,
            event_count=len(rows),
            chain_root_hash=expected_prev,
            reason="chain intact",
        )
