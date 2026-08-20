#!/usr/bin/env python3
"""Display KPI summary since yesterday's start for quick login check."""

from datetime import datetime, timedelta
from pathlib import Path
import json
import os
import sys
import subprocess
import tempfile

from slacwire.suite._constants import _REGISTRY_PATH

try:
    from slacwire.registry.kpi_queries import RunRegistryKPIReporter
    from slacwire.registry.registry_sqlite import convert_run_registry_json_to_sqlite
except ImportError:
    from kpi_queries import RunRegistryKPIReporter
    from registry_sqlite import convert_run_registry_json_to_sqlite

def main():
    """Run KPI report for yesterday and display key metrics."""
    # Calculate yesterday midnight to today midnight
    today = datetime.now()
    yesterday = today - timedelta(days=1)

    start_ts = yesterday.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    end_ts = today.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    try:
        # Use production registry JSON
        json_path = _REGISTRY_PATH

        if not json_path.exists():
            print(f"Error: Registry JSON not found at {json_path}")
            return 1

        with tempfile.TemporaryDirectory() as tmp:
            sqlite_path = Path(tmp) / "run_registry_reporting.sqlite3"
            convert_run_registry_json_to_sqlite(
                source_json=json_path,
                sqlite_path=sqlite_path,
                overwrite=True,
            )
            reporter = RunRegistryKPIReporter.from_sqlite_path(sqlite_path)
            snapshot = reporter.executive_kpi_snapshot(start_ts, end_ts)

            # Get distinct wires
            wires = reporter._fetch_all(
                """
                SELECT DISTINCT wire
                FROM runs
                WHERE timestamp_iso >= :start_ts
                  AND timestamp_iso < :end_ts
                ORDER BY wire
                """,
                start_ts=start_ts,
                end_ts=end_ts,
            )

            total_runs = snapshot.get("total_runs", 0)
            success_rate = snapshot.get("success_rate_pct", 0)
            successful = snapshot.get("successful_runs", 0)
            failed = snapshot.get("failed_runs", 0)
            wire_names = [w["wire"] for w in wires]

            print(f"\n{'='*50}")
            print(f"Wire Scan KPI Summary - Since {yesterday.strftime('%Y-%m-%d')}")
            print(f"{'='*50}")
            print(f"Total runs:     {total_runs}")
            print(f"Success rate:   {success_rate}%")
            print(f"  ✓ Successful: {successful}")
            print(f"  ✗ Failed:     {failed}")
            print(f"Wires scanned:  {', '.join(wire_names) if wire_names else 'None'}")
            print(f"{'='*50}\n")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
