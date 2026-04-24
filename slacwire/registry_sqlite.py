"""Utilities for converting RunRegistry JSON snapshots into SQLite databases.

The generated schema is aligned with reporting requirements documented in
``docs/run_registry_kpi_definitions.md``.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"


@dataclass(frozen=True)
class RegistrySQLiteSummary:
    """Summary details returned after conversion completes."""

    runs_inserted: int
    plots_inserted: int
    source_json: Path
    sqlite_path: Path


def _to_path(path: str | Path) -> Path:
    """Normalize string/path-like values into ``Path`` objects."""
    return path if isinstance(path, Path) else Path(path)


def _to_timestamp_iso(raw: str | None) -> str:
    """Convert registry timestamp strings into ISO-8601 local timestamps."""
    if not raw:
        raise ValueError("timestamp is required for conversion")
    dt = datetime.strptime(raw, TIMESTAMP_FORMAT)
    return dt.isoformat(timespec="seconds")


def _normalize_status(status: str | None) -> str:
    """Map status values to expected reporting categories."""
    if status in {"ok", "error", "unknown"}:
        return status
    return "unknown"


def _create_schema(conn: sqlite3.Connection) -> None:
    """Create KPI-oriented reporting tables and indexes."""
    conn.executescript(
        """
        CREATE TABLE runs (
            run_id INTEGER PRIMARY KEY,
            timestamp_raw TEXT NOT NULL,
            timestamp_iso TEXT NOT NULL,
            method TEXT NOT NULL,
            wire TEXT NOT NULL,
            beampath TEXT NOT NULL,
            detector TEXT,
            filepath TEXT,
            status TEXT NOT NULL,
            error TEXT,
            source_json TEXT NOT NULL,
            ingested_at TEXT NOT NULL
        );

        CREATE TABLE run_plots (
            run_id INTEGER NOT NULL,
            plot_index INTEGER NOT NULL,
            plot_path TEXT NOT NULL,
            PRIMARY KEY (run_id, plot_index),
            FOREIGN KEY (run_id) REFERENCES runs(run_id)
        );

        CREATE INDEX idx_runs_timestamp_iso ON runs(timestamp_iso);
        CREATE INDEX idx_runs_status_timestamp_iso ON runs(status, timestamp_iso);
        CREATE INDEX idx_runs_wire_timestamp_iso ON runs(wire, timestamp_iso);
        CREATE INDEX idx_runs_beampath_timestamp_iso ON runs(beampath, timestamp_iso);
        CREATE INDEX idx_runs_method_timestamp_iso ON runs(method, timestamp_iso);
        """
    )


def _load_entries(source_json: Path) -> list[dict]:
    """Load and validate the root structure of a RunRegistry JSON snapshot."""
    with open(source_json, "r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    if not isinstance(loaded, list):
        raise ValueError("Run registry JSON must contain a top-level list of entries")
    if not all(isinstance(entry, dict) for entry in loaded):
        raise ValueError("Each run registry item must be a JSON object")
    return loaded


def convert_run_registry_json_to_sqlite(
    source_json: str | Path,
    sqlite_path: str | Path,
    *,
    overwrite: bool = False,
) -> RegistrySQLiteSummary:
    """Convert a RunRegistry JSON snapshot into a SQLite reporting database.

    Args:
        source_json: Path to the JSON snapshot produced by ``RunRegistry``.
        sqlite_path: Path to the SQLite database to create.
        overwrite: If ``True``, replace an existing database at ``sqlite_path``.

    Returns:
        ``RegistrySQLiteSummary`` with record counts and output paths.
    """
    source_json_path = _to_path(source_json)
    sqlite_output_path = _to_path(sqlite_path)

    if not source_json_path.exists():
        raise FileNotFoundError(f"Run registry JSON not found: {source_json_path}")

    if sqlite_output_path.exists():
        if not overwrite:
            raise FileExistsError(
                f"SQLite output already exists: {sqlite_output_path}. "
                "Set overwrite=True to replace it."
            )
        sqlite_output_path.unlink()

    sqlite_output_path.parent.mkdir(parents=True, exist_ok=True)
    entries = _load_entries(source_json_path)
    ingested_at = datetime.now().isoformat(timespec="seconds")

    runs_inserted = 0
    plots_inserted = 0

    with sqlite3.connect(sqlite_output_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        _create_schema(conn)

        for entry in entries:
            run_id = int(entry["run_id"])
            timestamp_raw = entry["timestamp"]
            timestamp_iso = _to_timestamp_iso(timestamp_raw)
            method = entry["method"]
            wire = entry["wire"]
            beampath = entry["beampath"]
            detector = entry.get("detector")
            filepath = entry.get("filepath")
            status = _normalize_status(entry.get("status"))
            error = entry.get("error")

            conn.execute(
                """
                INSERT INTO runs (
                    run_id,
                    timestamp_raw,
                    timestamp_iso,
                    method,
                    wire,
                    beampath,
                    detector,
                    filepath,
                    status,
                    error,
                    source_json,
                    ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    timestamp_raw,
                    timestamp_iso,
                    method,
                    wire,
                    beampath,
                    detector,
                    filepath,
                    status,
                    error,
                    str(source_json_path),
                    ingested_at,
                ),
            )
            runs_inserted += 1

            plots = entry.get("plots") or []
            for plot_index, plot_path in enumerate(plots):
                conn.execute(
                    """
                    INSERT INTO run_plots (run_id, plot_index, plot_path)
                    VALUES (?, ?, ?)
                    """,
                    (run_id, plot_index, str(plot_path)),
                )
                plots_inserted += 1

    return RegistrySQLiteSummary(
        runs_inserted=runs_inserted,
        plots_inserted=plots_inserted,
        source_json=source_json_path,
        sqlite_path=sqlite_output_path,
    )