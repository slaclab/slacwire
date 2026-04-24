"""SQLAlchemy query helpers for Run Registry KPI reporting.

This module complements the static SQL pack in
``docs/run_registry_kpi_queries.sql`` by offering reusable Python methods with
bound parameters and structured return values.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


def _sqlite_url(path: str | Path) -> str:
    """Build a SQLAlchemy SQLite URL from a filesystem path."""
    return f"sqlite:///{Path(path).expanduser().resolve()}"


@dataclass
class RunRegistryKPIReporter:
    """Query helper for KPI-focused reporting over run-registry SQLite snapshots."""

    engine: Engine

    @classmethod
    def from_sqlite_path(cls, sqlite_path: str | Path) -> "RunRegistryKPIReporter":
        """Create a reporter bound to a SQLite snapshot path."""
        engine = create_engine(_sqlite_url(sqlite_path))
        return cls(engine=engine)

    def _fetch_all(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        """Execute a query and return rows as dictionaries."""
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).mappings().all()
        return [dict(row) for row in rows]

    def _fetch_one(self, sql: str, **params: Any) -> dict[str, Any]:
        """Execute a query expected to return exactly one summary row."""
        rows = self._fetch_all(sql, **params)
        return rows[0] if rows else {}

    def executive_kpi_snapshot(self, start_ts: str, end_ts: str) -> dict[str, Any]:
        """Return top-level KPI values for the selected period."""
        return self._fetch_one(
            """
            SELECT
              COUNT(*) AS total_runs,
              SUM(CASE WHEN status = 'ok' THEN 1 ELSE 0 END) AS successful_runs,
              SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS failed_runs,
              SUM(CASE WHEN status = 'unknown' THEN 1 ELSE 0 END) AS unknown_runs,
              ROUND(
                100.0 * SUM(CASE WHEN status = 'ok' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
                1
              ) AS success_rate_pct,
              ROUND(
                100.0 * SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
                1
              ) AS failure_rate_pct,
              COUNT(DISTINCT wire) AS distinct_wires_scanned
            FROM runs
            WHERE timestamp_iso >= :start_ts
              AND timestamp_iso < :end_ts
            """,
            start_ts=start_ts,
            end_ts=end_ts,
        )

    def throughput_by_week(self, start_ts: str, end_ts: str) -> list[dict[str, Any]]:
        """Return weekly run totals and method mix."""
        return self._fetch_all(
            """
            SELECT
              strftime('%Y-W%W', timestamp_iso) AS year_week,
              COUNT(*) AS total_runs,
              SUM(CASE WHEN method = 'otf' THEN 1 ELSE 0 END) AS otf_runs,
              SUM(CASE WHEN method = 'step' THEN 1 ELSE 0 END) AS step_runs,
              SUM(CASE WHEN method NOT IN ('otf', 'step') THEN 1 ELSE 0 END) AS other_method_runs
            FROM runs
            WHERE timestamp_iso >= :start_ts
              AND timestamp_iso < :end_ts
            GROUP BY year_week
            ORDER BY year_week
            """,
            start_ts=start_ts,
            end_ts=end_ts,
        )

    def success_failure_by_week(self, start_ts: str, end_ts: str) -> list[dict[str, Any]]:
        """Return weekly success/failure totals and success rate."""
        return self._fetch_all(
            """
            SELECT
              strftime('%Y-W%W', timestamp_iso) AS year_week,
              COUNT(*) AS total_runs,
              SUM(CASE WHEN status = 'ok' THEN 1 ELSE 0 END) AS successful_runs,
              SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS failed_runs,
              ROUND(
                100.0 * SUM(CASE WHEN status = 'ok' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
                1
              ) AS success_rate_pct
            FROM runs
            WHERE timestamp_iso >= :start_ts
              AND timestamp_iso < :end_ts
            GROUP BY year_week
            ORDER BY year_week
            """,
            start_ts=start_ts,
            end_ts=end_ts,
        )

    def runs_by_method(self, start_ts: str, end_ts: str) -> list[dict[str, Any]]:
        """Return run counts grouped by method for a period."""
        return self._fetch_all(
            """
            SELECT method, COUNT(*) AS run_count
            FROM runs
            WHERE timestamp_iso >= :start_ts
              AND timestamp_iso < :end_ts
            GROUP BY method
            ORDER BY run_count DESC, method
            """,
            start_ts=start_ts,
            end_ts=end_ts,
        )

    def failures_by_wire(self, start_ts: str, end_ts: str) -> list[dict[str, Any]]:
        """Return failure concentration by wire with wire-level failure rate."""
        return self._fetch_all(
            """
            SELECT
              wire,
              COUNT(*) AS total_runs,
              SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS failed_runs,
              ROUND(
                100.0 * SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
                1
              ) AS wire_failure_rate_pct
            FROM runs
            WHERE timestamp_iso >= :start_ts
              AND timestamp_iso < :end_ts
            GROUP BY wire
            ORDER BY failed_runs DESC, wire_failure_rate_pct DESC, wire
            """,
            start_ts=start_ts,
            end_ts=end_ts,
        )

    def failures_by_beampath(self, start_ts: str, end_ts: str) -> list[dict[str, Any]]:
        """Return failure concentration by beampath with failure rate."""
        return self._fetch_all(
            """
            SELECT
              beampath,
              COUNT(*) AS total_runs,
              SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS failed_runs,
              ROUND(
                100.0 * SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
                1
              ) AS beampath_failure_rate_pct
            FROM runs
            WHERE timestamp_iso >= :start_ts
              AND timestamp_iso < :end_ts
            GROUP BY beampath
            ORDER BY failed_runs DESC, beampath_failure_rate_pct DESC, beampath
            """,
            start_ts=start_ts,
            end_ts=end_ts,
        )

    def failures_by_detector(self, start_ts: str, end_ts: str) -> list[dict[str, Any]]:
        """Return failure concentration by detector with failure rate."""
        return self._fetch_all(
            """
            SELECT
              COALESCE(NULLIF(TRIM(detector), ''), '(none)') AS detector_label,
              COUNT(*) AS total_runs,
              SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS failed_runs,
              ROUND(
                100.0 * SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
                1
              ) AS detector_failure_rate_pct
            FROM runs
            WHERE timestamp_iso >= :start_ts
              AND timestamp_iso < :end_ts
            GROUP BY detector_label
            ORDER BY failed_runs DESC, detector_failure_rate_pct DESC, detector_label
            """,
            start_ts=start_ts,
            end_ts=end_ts,
        )

    def top_error_signatures(
        self, start_ts: str, end_ts: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Return top recurring normalized error signatures."""
        return self._fetch_all(
            """
            SELECT
              LOWER(TRIM(COALESCE(error, '(no error text)'))) AS error_signature,
              COUNT(*) AS occurrences
            FROM runs
            WHERE timestamp_iso >= :start_ts
              AND timestamp_iso < :end_ts
              AND status = 'error'
            GROUP BY error_signature
            ORDER BY occurrences DESC, error_signature
            LIMIT :limit
            """,
            start_ts=start_ts,
            end_ts=end_ts,
            limit=limit,
        )

    def file_completion_rate(self, start_ts: str, end_ts: str) -> dict[str, Any]:
        """Return percent of runs with non-empty filepath values."""
        return self._fetch_one(
            """
            SELECT
              COUNT(*) AS total_runs,
              SUM(CASE WHEN filepath IS NOT NULL AND TRIM(filepath) <> '' THEN 1 ELSE 0 END) AS runs_with_filepath,
              ROUND(
                100.0 * SUM(CASE WHEN filepath IS NOT NULL AND TRIM(filepath) <> '' THEN 1 ELSE 0 END)
                / NULLIF(COUNT(*), 0),
                1
              ) AS file_completion_rate_pct
            FROM runs
            WHERE timestamp_iso >= :start_ts
              AND timestamp_iso < :end_ts
            """,
            start_ts=start_ts,
            end_ts=end_ts,
        )

    def plot_completion_rate(self, start_ts: str, end_ts: str) -> dict[str, Any]:
        """Return percent of runs with at least one row in run_plots."""
        return self._fetch_one(
            """
            WITH period_runs AS (
              SELECT run_id
              FROM runs
              WHERE timestamp_iso >= :start_ts
                AND timestamp_iso < :end_ts
            ),
            runs_with_plots AS (
              SELECT DISTINCT run_id
              FROM run_plots
            )
            SELECT
              COUNT(*) AS total_runs,
              SUM(CASE WHEN rwp.run_id IS NOT NULL THEN 1 ELSE 0 END) AS runs_with_plots,
              ROUND(
                100.0 * SUM(CASE WHEN rwp.run_id IS NOT NULL THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
                1
              ) AS plot_completion_rate_pct
            FROM period_runs pr
            LEFT JOIN runs_with_plots rwp ON pr.run_id = rwp.run_id
            """,
            start_ts=start_ts,
            end_ts=end_ts,
        )

    def wire_coverage_recency(self, cutoff_date: str) -> list[dict[str, Any]]:
        """Return last-scan recency per wire and bucket classification."""
        return self._fetch_all(
            """
            WITH latest_per_wire AS (
              SELECT wire, MAX(timestamp_iso) AS last_scan_iso
              FROM runs
              GROUP BY wire
            )
            SELECT
              lpw.wire,
              lpw.last_scan_iso,
              CAST(julianday(:cutoff_date) - julianday(date(lpw.last_scan_iso)) AS INTEGER) AS days_since_last_scan,
              CASE
                WHEN (julianday(:cutoff_date) - julianday(date(lpw.last_scan_iso))) <= 7 THEN 'green'
                WHEN (julianday(:cutoff_date) - julianday(date(lpw.last_scan_iso))) <= 14 THEN 'yellow'
                ELSE 'red'
              END AS recency_bucket
            FROM latest_per_wire lpw
            ORDER BY days_since_last_scan DESC, lpw.wire
            """,
            cutoff_date=cutoff_date,
        )

    def red_wires_count(self, cutoff_date: str) -> dict[str, Any]:
        """Return number of wires stale for 15 days or more."""
        return self._fetch_one(
            """
            WITH latest_per_wire AS (
              SELECT wire, MAX(timestamp_iso) AS last_scan_iso
              FROM runs
              GROUP BY wire
            )
            SELECT COUNT(*) AS red_wires
            FROM latest_per_wire
            WHERE (julianday(:cutoff_date) - julianday(date(last_scan_iso))) >= 15
            """,
            cutoff_date=cutoff_date,
        )

    def duplicate_run_ids(self) -> list[dict[str, Any]]:
        """Return duplicate run_id rows, if any."""
        return self._fetch_all(
            """
            SELECT run_id, COUNT(*) AS duplicate_count
            FROM runs
            GROUP BY run_id
            HAVING COUNT(*) > 1
            ORDER BY duplicate_count DESC, run_id
            """
        )

    def status_distribution(self) -> list[dict[str, Any]]:
        """Return observed status counts for data-quality checks."""
        return self._fetch_all(
            """
            SELECT status, COUNT(*) AS count_by_status
            FROM runs
            GROUP BY status
            ORDER BY count_by_status DESC, status
            """
        )

    def orphan_plot_rows(self) -> dict[str, Any]:
        """Return count of run_plots rows without a matching run row."""
        return self._fetch_one(
            """
            SELECT COUNT(*) AS orphan_plot_rows
            FROM run_plots rp
            LEFT JOIN runs r ON rp.run_id = r.run_id
            WHERE r.run_id IS NULL
            """
        )

    def missing_required_field_rows(self) -> dict[str, Any]:
        """Return count of run rows missing required reporting fields."""
        return self._fetch_one(
            """
            SELECT COUNT(*) AS invalid_required_field_rows
            FROM runs
            WHERE run_id IS NULL
               OR timestamp_raw IS NULL OR TRIM(timestamp_raw) = ''
               OR timestamp_iso IS NULL OR TRIM(timestamp_iso) = ''
               OR method IS NULL OR TRIM(method) = ''
               OR wire IS NULL OR TRIM(wire) = ''
               OR beampath IS NULL OR TRIM(beampath) = ''
               OR status IS NULL OR TRIM(status) = ''
            """
        )
