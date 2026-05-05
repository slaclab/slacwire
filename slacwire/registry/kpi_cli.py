"""CLI for running Run Registry KPI queries against SQLite snapshots."""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import date, datetime
from pathlib import Path
import re
from typing import Any

from .kpi_queries import RunRegistryKPIReporter
from .registry_sqlite import convert_run_registry_json_to_sqlite

DEFAULT_PRODUCTION_JSON_PATH = Path(
    "/u1/lcls/physics/data/wire_scan/ws_run_registry.json"
)


def _previous_month_bounds(today: date | None = None) -> tuple[str, str]:
    """Return ISO start/end timestamps for the previous full calendar month."""
    today = today or date.today()
    first_of_this_month = today.replace(day=1)
    end_prev_month = first_of_this_month
    if first_of_this_month.month == 1:
        start_prev_month = first_of_this_month.replace(
            year=first_of_this_month.year - 1,
            month=12,
        )
    else:
        start_prev_month = first_of_this_month.replace(
            month=first_of_this_month.month - 1,
        )
    return (
        f"{start_prev_month.isoformat()}T00:00:00",
        f"{end_prev_month.isoformat()}T00:00:00",
    )


def run_kpi_bundle(
    sqlite_path: str | Path,
    start_ts: str,
    end_ts: str,
    cutoff_date: str,
) -> dict[str, Any]:
    """Execute the standard KPI bundle and return all outputs in one object."""
    reporter = RunRegistryKPIReporter.from_sqlite_path(sqlite_path)

    return {
        "metadata": {
            "sqlite_path": str(Path(sqlite_path).expanduser().resolve()),
            "start_ts": start_ts,
            "end_ts": end_ts,
            "cutoff_date": cutoff_date,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        },
        "executive_kpi_snapshot": reporter.executive_kpi_snapshot(start_ts, end_ts),
        "throughput_by_week": reporter.throughput_by_week(start_ts, end_ts),
        "success_failure_by_week": reporter.success_failure_by_week(start_ts, end_ts),
        "runs_by_method": reporter.runs_by_method(start_ts, end_ts),
        "failures_by_wire": reporter.failures_by_wire(start_ts, end_ts),
        "failures_by_beampath": reporter.failures_by_beampath(start_ts, end_ts),
        "failures_by_detector": reporter.failures_by_detector(start_ts, end_ts),
        "top_error_signatures": reporter.top_error_signatures(start_ts, end_ts),
        "file_completion_rate": reporter.file_completion_rate(start_ts, end_ts),
        "plot_completion_rate": reporter.plot_completion_rate(start_ts, end_ts),
        "wire_coverage_recency": reporter.wire_coverage_recency(cutoff_date),
        "red_wires_count": reporter.red_wires_count(cutoff_date),
        "duplicate_run_ids": reporter.duplicate_run_ids(),
        "status_distribution": reporter.status_distribution(),
        "orphan_plot_rows": reporter.orphan_plot_rows(),
        "missing_required_field_rows": reporter.missing_required_field_rows(),
    }


def _write_bundle(bundle: dict[str, Any], output_dir: str | Path) -> None:
    """Write one JSON file per section plus an all-in-one bundle file."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    all_path = output_path / "kpi_bundle.json"
    all_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")

    for key, value in bundle.items():
        section_path = output_path / f"{key}.json"
        section_path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def _resolve_output_dir(output_dir: str | Path, today: date | None = None) -> Path:
    """Return a dated output path under the provided base directory."""
    base = Path(output_dir)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", base.name):
        return base
    run_date = (today or date.today()).isoformat()
    return base / run_date


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI options for KPI report generation."""
    parser = argparse.ArgumentParser(
        prog="slacwire-kpi-report",
        description="Run RunRegistry KPI query bundle against a SQLite snapshot.",
    )
    input_group = parser.add_mutually_exclusive_group(required=False)
    input_group.add_argument(
        "--sqlite-path",
        help="Path to a SQLite snapshot produced by convert_run_registry_json_to_sqlite.",
    )
    input_group.add_argument(
        "--json-path",
        help=(
            "Path to a RunRegistry JSON file. The CLI will convert it to SQLite "
            "before querying. Defaults to "
            f"{DEFAULT_PRODUCTION_JSON_PATH}."
        ),
    )
    parser.add_argument(
        "--sqlite-output-path",
        default=None,
        help="Optional output path for converted SQLite when using --json-path.",
    )
    parser.add_argument(
        "--start-ts",
        default=None,
        help="Inclusive period start timestamp (ISO), e.g. 2026-04-01T00:00:00.",
    )
    parser.add_argument(
        "--end-ts",
        default=None,
        help="Exclusive period end timestamp (ISO), e.g. 2026-05-01T00:00:00.",
    )
    parser.add_argument(
        "--cutoff-date",
        default=None,
        help="Cutoff date for recency queries (YYYY-MM-DD). Defaults to end date.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "Optional base directory to write JSON artifacts. Results are written "
            "to a dated subdirectory (YYYY-MM-DD). If omitted, prints bundle JSON to stdout."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point for KPI report CLI."""
    args = _parse_args(argv)

    default_start_ts, default_end_ts = _previous_month_bounds()
    start_ts = args.start_ts or default_start_ts
    end_ts = args.end_ts or default_end_ts

    cutoff_date = args.cutoff_date
    if cutoff_date is None:
        cutoff_date = end_ts.split("T", 1)[0]

    json_path = Path(args.json_path) if args.json_path else DEFAULT_PRODUCTION_JSON_PATH

    if args.sqlite_path:
        bundle = run_kpi_bundle(
            sqlite_path=args.sqlite_path,
            start_ts=start_ts,
            end_ts=end_ts,
            cutoff_date=cutoff_date,
        )
    else:
        if not json_path.exists():
            raise FileNotFoundError(
                "No --sqlite-path provided and registry JSON not found at "
                f"{json_path}. Provide --json-path or --sqlite-path explicitly."
            )
        if args.sqlite_output_path:
            sqlite_path = Path(args.sqlite_output_path)
            convert_run_registry_json_to_sqlite(
                source_json=json_path,
                sqlite_path=sqlite_path,
                overwrite=True,
            )
            bundle = run_kpi_bundle(
                sqlite_path=sqlite_path,
                start_ts=start_ts,
                end_ts=end_ts,
                cutoff_date=cutoff_date,
            )
        else:
            with tempfile.TemporaryDirectory() as tmp:
                sqlite_path = Path(tmp) / "run_registry_reporting.sqlite3"
                convert_run_registry_json_to_sqlite(
                    source_json=json_path,
                    sqlite_path=sqlite_path,
                    overwrite=True,
                )
                bundle = run_kpi_bundle(
                    sqlite_path=sqlite_path,
                    start_ts=start_ts,
                    end_ts=end_ts,
                    cutoff_date=cutoff_date,
                )

    if args.output_dir:
        resolved_output_dir = _resolve_output_dir(args.output_dir)
        _write_bundle(bundle, resolved_output_dir)
        print(str(resolved_output_dir))
    else:
        print(json.dumps(bundle, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
