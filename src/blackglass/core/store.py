"""SQLite project store. The command log cannot be updated or deleted."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS project (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    owner TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scope_grant (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES project(id),
    kind TEXT NOT NULL,
    chain_id INTEGER,
    address TEXT,
    path TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS finding (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES project(id),
    campaign_key TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    statement TEXT NOT NULL,
    impact TEXT NOT NULL,
    vulnerable_broken INTEGER,
    patched_held INTEGER,
    created_at TEXT NOT NULL,
    UNIQUE(project_id, campaign_key)
);

CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY,
    finding_id INTEGER NOT NULL REFERENCES finding(id),
    source TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    collected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS campaign (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES project(id),
    campaign_key TEXT NOT NULL,
    result_path TEXT NOT NULL,
    imported_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS command_log (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES project(id),
    command TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS setting (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS command_log_no_update
BEFORE UPDATE ON command_log
BEGIN
    SELECT RAISE(ABORT, 'command log is append-only');
END;

CREATE TRIGGER IF NOT EXISTS command_log_no_delete
BEFORE DELETE ON command_log
BEGIN
    SELECT RAISE(ABORT, 'command log is append-only');
END;
"""


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def create_project(self, name: str, owner: str = "") -> int:
        cursor = self._conn.execute(
            "INSERT INTO project (name, owner, created_at) VALUES (?, ?, ?)",
            (name, owner, utc_now()),
        )
        self._conn.commit()
        project_id = int(cursor.lastrowid)
        self.log(project_id, f"project create {name}")
        self.open_project(name)
        return project_id

    def list_projects(self) -> list[sqlite3.Row]:
        return list(self._conn.execute("SELECT id, name, owner, created_at FROM project ORDER BY name"))

    def open_project(self, name: str) -> int:
        row = self._conn.execute("SELECT id FROM project WHERE name = ?", (name,)).fetchone()
        if row is None:
            raise LookupError(f"no project named {name}")
        project_id = int(row["id"])
        self._conn.execute(
            "INSERT INTO setting (key, value) VALUES ('current_project', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (name,),
        )
        self._conn.commit()
        self.log(project_id, f"project open {name}")
        return project_id

    def current(self) -> sqlite3.Row | None:
        setting = self._conn.execute("SELECT value FROM setting WHERE key = 'current_project'").fetchone()
        if setting is None:
            return None
        return self._conn.execute("SELECT * FROM project WHERE name = ?", (setting["value"],)).fetchone()

    def grant_path(self, project_id: int, path: str) -> None:
        self._conn.execute(
            "INSERT INTO scope_grant (project_id, kind, path, created_at) VALUES (?, 'path', ?, ?)",
            (project_id, path, utc_now()),
        )
        self._conn.commit()
        self.log(project_id, f"project scope path={path}")

    def grant_address(self, project_id: int, chain_id: int, address: str) -> None:
        self._conn.execute(
            "INSERT INTO scope_grant (project_id, kind, chain_id, address, created_at) VALUES (?, 'address', ?, ?, ?)",
            (project_id, chain_id, address, utc_now()),
        )
        self._conn.commit()
        self.log(project_id, f"project scope chain={chain_id} address={address}")

    def in_scope_path(self, project_id: int, path: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM scope_grant WHERE project_id = ? AND kind = 'path' AND path = ?",
            (project_id, path),
        ).fetchone()
        return row is not None

    def in_scope_address(self, project_id: int, chain_id: int, address: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM scope_grant WHERE project_id = ? AND kind = 'address' AND chain_id = ? AND address = ?",
            (project_id, chain_id, address),
        ).fetchone()
        return row is not None

    def add_finding(
        self,
        project_id: int,
        *,
        campaign_key: str,
        title: str,
        status: str,
        statement: str,
        impact: str,
        vulnerable_broken: bool | None,
        patched_held: bool | None,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO finding (
                project_id, campaign_key, title, status, statement, impact,
                vulnerable_broken, patched_held, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                campaign_key,
                title,
                status,
                statement,
                impact,
                _bit(vulnerable_broken),
                _bit(patched_held),
                utc_now(),
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def add_evidence(self, finding_id: int, *, source: str, sha256: str, collected_at: str) -> None:
        self._conn.execute(
            "INSERT INTO evidence (finding_id, source, sha256, collected_at) VALUES (?, ?, ?, ?)",
            (finding_id, source, sha256, collected_at),
        )
        self._conn.commit()

    def add_campaign(self, project_id: int, *, campaign_key: str, result_path: str) -> None:
        self._conn.execute(
            "INSERT INTO campaign (project_id, campaign_key, result_path, imported_at) VALUES (?, ?, ?, ?)",
            (project_id, campaign_key, result_path, utc_now()),
        )
        self._conn.commit()

    def findings(self, project_id: int) -> list[sqlite3.Row]:
        return list(self._conn.execute("SELECT * FROM finding WHERE project_id = ? ORDER BY id", (project_id,)))

    def evidence_for(self, finding_id: int) -> list[sqlite3.Row]:
        return list(self._conn.execute("SELECT * FROM evidence WHERE finding_id = ? ORDER BY id", (finding_id,)))

    def log(self, project_id: int, command: str) -> None:
        self._conn.execute(
            "INSERT INTO command_log (project_id, command, recorded_at) VALUES (?, ?, ?)",
            (project_id, command, utc_now()),
        )
        self._conn.commit()

    def command_log(self, project_id: int) -> list[sqlite3.Row]:
        return list(
            self._conn.execute(
                "SELECT command, recorded_at FROM command_log WHERE project_id = ? ORDER BY id",
                (project_id,),
            )
        )


def open_store(root: Path) -> Store:
    return Store(root / ".blackglass" / "project.db")


def _bit(value: bool | None) -> int | None:
    if value is None:
        return None
    return 1 if value else 0
