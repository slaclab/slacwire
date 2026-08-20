"""Per-wire scan configuration stored in a shared SQLite database.

Operators persist their preferred scan settings (detector, toroid, fitting
method, jitter correction, BPM selection) per wire/beampath pair.  The suite
reads these at scan time; the GUI reads them on wire selection and writes them
on explicit "Save Config" clicks.
"""

from __future__ import annotations

import getpass
import json
import sqlite3
from dataclasses import dataclass, fields
from pathlib import Path

from slacwire.suite._constants import VALID_FIT_METHODS

_DB_PATH = Path("/u1/lcls/physics/data/wire_scan/wire_config.db")

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS wire_config (
    wire                 TEXT NOT NULL,
    beampath             TEXT NOT NULL,
    fitting_method       TEXT NOT NULL DEFAULT 'gaussian',
    detector             TEXT,
    toroid               TEXT,
    charge_normalization INTEGER NOT NULL DEFAULT 0,
    jitter_correction    INTEGER NOT NULL DEFAULT 0,
    jitter_bpms          TEXT,
    updated_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    updated_by           TEXT,
    PRIMARY KEY (wire, beampath)
);
"""


@dataclass
class WireConfig:
    """Per-wire scan configuration resolved from the database."""

    fitting_method: str = "gaussian"
    detector: str | None = None
    toroid: str | None = None
    charge_normalization: bool = False
    jitter_correction: bool = False
    jitter_bpms: list[str] | None = None


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or _DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(_SCHEMA)
    return conn


def get_wire_config(
    wire: str,
    beampath: str,
    *,
    db_path: Path | None = None,
) -> WireConfig:
    """Read config for a wire/beampath pair.

    Returns a WireConfig with defaults if no row exists.
    """
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT fitting_method, detector, toroid, charge_normalization, "
            "jitter_correction, jitter_bpms "
            "FROM wire_config WHERE wire = ? AND beampath = ?",
            (wire, beampath),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return WireConfig()

    fitting_method, detector, toroid, charge_norm, jitter_corr, jitter_bpms_json = row
    jitter_bpms = json.loads(jitter_bpms_json) if jitter_bpms_json else None

    return WireConfig(
        fitting_method=fitting_method,
        detector=detector,
        toroid=toroid,
        charge_normalization=bool(charge_norm),
        jitter_correction=bool(jitter_corr),
        jitter_bpms=jitter_bpms,
    )


def set_wire_config(
    wire: str,
    beampath: str,
    *,
    fitting_method: str | None = None,
    detector: str | None = None,
    toroid: str | None = None,
    charge_normalization: bool | None = None,
    jitter_correction: bool | None = None,
    jitter_bpms: list[str] | None = None,
    db_path: Path | None = None,
) -> None:
    """Upsert config fields for a wire/beampath pair.

    Only provided (non-None) fields are written.  Pass explicit None for
    detector/toroid/jitter_bpms to clear an override (fall through to metadata).
    """
    conn = _connect(db_path)
    try:
        existing = conn.execute(
            "SELECT 1 FROM wire_config WHERE wire = ? AND beampath = ?",
            (wire, beampath),
        ).fetchone()

        user = getpass.getuser()

        if existing:
            updates = {}
            if fitting_method is not None:
                updates["fitting_method"] = fitting_method
            if detector is not None:
                updates["detector"] = detector
            if toroid is not None:
                updates["toroid"] = toroid
            if charge_normalization is not None:
                updates["charge_normalization"] = int(charge_normalization)
            if jitter_correction is not None:
                updates["jitter_correction"] = int(jitter_correction)
            if jitter_bpms is not None:
                updates["jitter_bpms"] = json.dumps(jitter_bpms)

            if not updates:
                return

            updates["updated_by"] = user
            set_clause = ", ".join(
                f"{k} = ?" for k in updates
            )
            set_clause += ", updated_at = strftime('%Y-%m-%dT%H:%M:%S','now')"
            conn.execute(
                f"UPDATE wire_config SET {set_clause} "
                "WHERE wire = ? AND beampath = ?",
                (*updates.values(), wire, beampath),
            )
        else:
            config = WireConfig(
                fitting_method=fitting_method or "gaussian",
                detector=detector,
                toroid=toroid,
                charge_normalization=charge_normalization if charge_normalization is not None else False,
                jitter_correction=jitter_correction if jitter_correction is not None else False,
                jitter_bpms=jitter_bpms,
            )
            conn.execute(
                "INSERT INTO wire_config "
                "(wire, beampath, fitting_method, detector, toroid, "
                "charge_normalization, jitter_correction, jitter_bpms, updated_by) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    wire,
                    beampath,
                    config.fitting_method,
                    config.detector,
                    config.toroid,
                    int(config.charge_normalization),
                    int(config.jitter_correction),
                    json.dumps(config.jitter_bpms) if config.jitter_bpms else None,
                    user,
                ),
            )
        conn.commit()
    finally:
        conn.close()
