"""Benchmark jitter correction: compare Python and MATLAB orbit-fit results.

Usage:
    python -m benchmarking.jitter_benchmark <h5_dir> <mat_results_dir>

Expects .h5 files (Python analysis results) in h5_dir and corresponding
.mat files (MATLAB jitter_benchmark.m output) in mat_results_dir with
matching stems.
"""

import csv
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import scipy.io

from slac_measurements.wires.analysis_results import load_from_h5
from slac_measurements.wires.jitter_correction import (
    _extract_bpm_data,
    _compute_orbit_fit,
    get_jitter_rmat,
)

PLANES = ("X", "Y")
CSV_COLUMNS = [
    "wire_name",
    "beampath",
    "plane",
    "python_jitter_rms",
    "matlab_jitter_rms",
    "pct_diff",
    "source_file",
]
_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
DEFAULT_OUTPUT_PATH = Path(f"jitter_benchmark_{_timestamp}.csv")


@dataclass
class JitterComparisonRow:
    """Result of comparing MATLAB vs Python jitter RMS for one scan/plane."""

    wire_name: str
    beampath: str
    plane: str
    python_jitter_rms: float
    matlab_jitter_rms: float
    pct_diff: float
    source_file: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "wire_name": self.wire_name,
            "beampath": self.beampath,
            "plane": self.plane,
            "python_jitter_rms": self.python_jitter_rms,
            "matlab_jitter_rms": self.matlab_jitter_rms,
            "pct_diff": self.pct_diff,
            "source_file": self.source_file,
        }


def compare_single_scan(
    h5_path: str,
    mat_results_path: str,
    physics_model: str = "BLEM",
) -> list[JitterComparisonRow]:
    """Compare Python and MATLAB jitter RMS for a single scan.

    Parameters
    ----------
    h5_path : str
        Path to the Python .h5 analysis file.
    mat_results_path : str
        Path to the .mat file containing MATLAB results
        (output from jitter_benchmark.m, or the conversion .mat with
        matlab_jitter_rms_x/y fields added after MATLAB processing).
    physics_model : str
        Model source for R-matrix retrieval if re-computing Python jitter.

    Returns
    -------
    list[JitterComparisonRow]
    """
    result = load_from_h5(h5_path)
    metadata = result.collection_result.metadata

    if result.jitter_rms is not None:
        python_rms = result.jitter_rms
    else:
        bpm_x, bpm_y, bpm_names = _extract_bpm_data(
            result.collection_result.raw_data
        )
        rmat_x, rmat_y = get_jitter_rmat(
            metadata.wire_name, bpm_names, metadata.beampath, physics_model
        )
        jitter_x, jitter_y = _compute_orbit_fit(bpm_x, bpm_y, rmat_x, rmat_y)
        python_rms = (float(np.std(jitter_x)), float(np.std(jitter_y)))

    mat = scipy.io.loadmat(mat_results_path, squeeze_me=True)
    matlab_rms_x = float(mat["matlab_jitter_rms_x"])
    matlab_rms_y = float(mat["matlab_jitter_rms_y"])

    rows = []
    for plane, py_val, mat_val in [
        ("X", python_rms[0], matlab_rms_x),
        ("Y", python_rms[1], matlab_rms_y),
    ]:
        avg = (py_val + mat_val) / 2
        pct_diff = abs(py_val - mat_val) / avg * 100 if avg > 0 else 0.0
        rows.append(
            JitterComparisonRow(
                wire_name=metadata.wire_name,
                beampath=metadata.beampath,
                plane=plane,
                python_jitter_rms=py_val,
                matlab_jitter_rms=mat_val,
                pct_diff=pct_diff,
                source_file=Path(h5_path).name,
            )
        )

    return rows


def run_benchmark(
    h5_dir: Path,
    mat_dir: Path,
    physics_model: str = "BLEM",
) -> list[JitterComparisonRow]:
    """Run jitter benchmark on all .h5 files with matching .mat results.

    Parameters
    ----------
    h5_dir : Path
        Directory containing .h5 analysis files.
    mat_dir : Path
        Directory containing .mat result files (same stem as .h5 files).
    physics_model : str
        Model source for R-matrix retrieval.

    Returns
    -------
    list[JitterComparisonRow]
    """
    all_rows = []
    h5_files = sorted(Path(h5_dir).glob("*.h5"))

    for i, h5_path in enumerate(h5_files, 1):
        mat_path = Path(mat_dir) / h5_path.with_suffix(".mat").name
        if not mat_path.exists():
            logging.warning(f"No MATLAB results for {h5_path.name}, skipping.")
            continue

        print(f"{i}/{len(h5_files)}: {h5_path.name}")
        try:
            rows = compare_single_scan(
                str(h5_path), str(mat_path), physics_model
            )
            all_rows.extend(rows)
        except Exception as e:
            logging.warning(f"Failed to compare {h5_path.name}: {e}")

    return all_rows


def print_table(rows: list[JitterComparisonRow]) -> None:
    """Print comparison rows as a formatted text table."""

    def fmt(v: Any) -> str:
        return f"{v:.3f}" if isinstance(v, float) else str(v)

    row_dicts = [r.to_dict() for r in rows]
    widths = {
        c: max(len(c), *(len(fmt(rd[c])) for rd in row_dicts))
        for c in CSV_COLUMNS
    }

    print("  ".join(c.ljust(widths[c]) for c in CSV_COLUMNS))
    print("  ".join("-" * widths[c] for c in CSV_COLUMNS))
    for rd in row_dicts:
        print("  ".join(fmt(rd[c]).ljust(widths[c]) for c in CSV_COLUMNS))


def write_results(
    rows: list[JitterComparisonRow], output_path: Path = DEFAULT_OUTPUT_PATH
) -> None:
    """Write comparison results to CSV file."""
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_dict())

    print(f"\nWrote {output_path}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print(
            "Usage: python -m benchmarking.jitter_benchmark "
            "<h5_dir> <mat_results_dir>"
        )
        sys.exit(1)

    h5_dir = Path(sys.argv[1])
    mat_dir = Path(sys.argv[2])
    results = run_benchmark(h5_dir, mat_dir)
    print_table(results)
    write_results(results)
