from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass
from datetime import datetime
import csv
import logging
import traceback

from lcls_tools.common.measurements.ws_analysis import WireMeasurementAnalysis

from benchmarking.ws_matlab_load import (
    load_all_ws_h5,
    matlab_h5_to_buffer_dict,
    MATLABScanData,
)

# Configuration
logging.disable(logging.CRITICAL)

WIRE_LOOKUP = {
    "WIRE:IN20:561": "WS02",
    "WIRE:IN20:611": "WS03",
    "WIRE:LI21:293": "WS12",
    "WIRE:LI27:644": "WS27644",
    "WIRE:LI28:144": "WS28144",
    "WIRE:LI28:444": "WS28444",
    "WIRE:LI28:744": "WS28744"
}

PLANES = ("x", "y", "u")
CSV_COLUMNS = ["wire", "plane", "matlab_rms", "python_rms", "pct_diff", "scan"]
DEFAULT_DATA_PATH = Path("/home/physics/kabanaty/sandbox/h5_exports")
_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
DEFAULT_OUTPUT_PATH = Path(f"ws_benchmark_{_timestamp}.csv")


@dataclass
class ComparisonRow:
    """
    Result of comparing MATLAB vs Python analysis for a single scan/plane.
    """

    wire: str
    plane: str
    matlab_rms: float
    python_rms: float
    pct_diff: float
    scan: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for CSV writing."""
        return {
            "wire": self.wire,
            "plane": self.plane,
            "matlab_rms": self.matlab_rms,
            "python_rms": self.python_rms,
            "pct_diff": self.pct_diff,
            "scan": self.scan,
        }


def analyze_single_scan(
    scan: MATLABScanData, analysis_class: type = WireMeasurementAnalysis
) -> Optional[list[ComparisonRow]]:
    """
    Analyze a single scan and compare MATLAB vs Python results.

    Args:
        scan: MATLAB scan data object
        analysis_class: Class to use for analysis
                        (default: WireMeasurementAnalysis)

    Returns:
        List of ComparisonRow objects, or None if analysis failed
    """
    data = matlab_h5_to_buffer_dict(scan)

    try:
        wma = analysis_class(collection_result=data)
        analysis = wma.analyze()
    except Exception as e:
        logging.error(f"Error analyzing scan {scan.source_file}: {e}")
        traceback.print_exc()
        return None

    # Extract MATLAB RMS values
    matlab_rms = {plane: scan.beam_rms.get(plane) for plane in PLANES}

    # Extract Python RMS values
    python_rms = {
        plane: analysis.fit_result[plane]
        .detectors[data.metadata.default_detector]
        .sigma
        for plane in PLANES
    }

    # Build comparison rows
    rows = []
    for plane in PLANES:
        if matlab_rms[plane] is None:
            continue

        matlab_val = matlab_rms[plane]
        python_val = python_rms[plane]
        # Symmetric percent difference
        pct_diff = (
            abs((python_val - matlab_val)) /
            ((python_val + matlab_val) / 2) * 100
        )
        row = ComparisonRow(
            wire=data.metadata.wire_name,
            plane=plane.upper(),
            matlab_rms=matlab_val,
            python_rms=python_val,
            pct_diff=pct_diff,
            scan=scan.source_file,
        )
        rows.append(row)

    return rows


def run_benchmark(
    data_path: Path = DEFAULT_DATA_PATH,
    analysis_class: type = WireMeasurementAnalysis
) -> list[ComparisonRow]:
    """
    Load all scans and compare MATLAB vs Python analysis results.

    Args:
        data_path: Path to directory containing h5 exports
        analysis_class: Class to use for analysis (for testing/mocking)

    Returns:
        List of all comparison rows
    """
    scans = load_all_ws_h5(str(data_path))
    all_rows = []

    for i, scan in enumerate(scans, 1):
        print(f"{i} scans / {len(scans)}")

        rows = analyze_single_scan(scan, analysis_class)
        if rows:
            all_rows.extend(rows)

    return all_rows


def print_table(rows: list[ComparisonRow]) -> None:
    """Print comparison rows as a formatted text table."""
    cols = CSV_COLUMNS

    def fmt(v: Any) -> str:
        return f"{v:.2f}" if isinstance(v, float) else str(v)

    # Build dict list for formatting
    row_dicts = [r.to_dict() for r in rows]

    # Calculate column widths
    widths = {
        c: max(len(c), *(len(fmt(rd[c])) for rd in row_dicts))
        for c in cols
    }

    print("  ".join(c.ljust(widths[c]) for c in cols))
    print("  ".join("-" * widths[c] for c in cols))

    for rd in row_dicts:
        print("  ".join(fmt(rd[c]).ljust(widths[c]) for c in cols))


def write_results(
    rows: list[ComparisonRow], output_path: Path = DEFAULT_OUTPUT_PATH
) -> None:
    """
    Write comparison results to CSV file.

    Args:
        rows: List of comparison rows
        output_path: Path to output CSV file
    """
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_dict())

    print(f"\nWrote {output_path}")


if __name__ == "__main__":
    results = run_benchmark()
    print_table(results)
    write_results(results)
