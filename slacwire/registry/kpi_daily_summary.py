#!/usr/bin/env python3
"""Display KPI summary since yesterday's start for quick login check."""

from datetime import datetime, timedelta
from pathlib import Path
import json
import sys
import subprocess

def main():
    """Run KPI report for yesterday and display key metrics."""
    # Calculate yesterday midnight to today midnight
    today = datetime.now()
    yesterday = today - timedelta(days=1)

    start_ts = yesterday.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    end_ts = today.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    try:
        # Run the KPI report
        result = subprocess.run(
            [
                sys.executable, "-m", "slacwire.registry.kpi_cli",
                "--start-ts", start_ts,
                "--end-ts", end_ts,
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        # Parse the output directory path
        output_dir = Path(result.stdout.strip())
        bundle_path = output_dir / "kpi_bundle.json"

        if bundle_path.exists():
            bundle = json.loads(bundle_path.read_text())
            snapshot = bundle.get("executive_kpi_snapshot", {})

            total_runs = snapshot.get("total_runs", 0)
            success_rate = snapshot.get("success_rate_pct", 0)
            successful = snapshot.get("successful_runs", 0)
            failed = snapshot.get("failed_runs", 0)

            print(f"\n{'='*50}")
            print(f"Wire Scan KPI Summary - Since {yesterday.strftime('%Y-%m-%d')}")
            print(f"{'='*50}")
            print(f"Total runs:     {total_runs}")
            print(f"Success rate:   {success_rate}%")
            print(f"  ✓ Successful: {successful}")
            print(f"  ✗ Failed:     {failed}")
            print(f"{'='*50}\n")
        else:
            print(f"Error: Bundle file not found at {bundle_path}")
            return 1

    except subprocess.CalledProcessError as e:
        print(f"Error running KPI report: {e.stderr}")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
