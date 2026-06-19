"""Convert Python wire scan .h5 analysis files to .mat format for MATLAB jitter benchmarking.

Reads a WireMeasurementAnalysisResult .h5 file, extracts BPM data, fetches
R-matrices from meme.model, and saves a .mat file that can be consumed by
jitter_benchmark.m in the toolbox.
"""

from pathlib import Path

import numpy as np
import scipy.io

from slac_measurements.wires.analysis_results import load_from_h5
from slac_measurements.wires.jitter_correction import (
    _extract_bpm_data,
    get_jitter_rmat,
    _compute_orbit_fit,
)


def convert_h5_to_mat(
    h5_path: str,
    mat_path: str | None = None,
    beampath: str | None = None,
    physics_model: str = "BLEM",
) -> str:
    """Convert a Python .h5 analysis file to .mat for MATLAB jitter correction.

    Parameters
    ----------
    h5_path : str
        Path to the .h5 file saved via WireMeasurementAnalysisResult.save_to_h5().
    mat_path : str, optional
        Output .mat file path. Defaults to same name with .mat extension.
    beampath : str, optional
        Override beampath for R-matrix retrieval. Defaults to metadata beampath.
    physics_model : str
        Model source for R-matrices. Default "BLEM".

    Returns
    -------
    str
        Path to the saved .mat file.
    """
    result = load_from_h5(h5_path)
    collection = result.collection_result
    metadata = collection.metadata

    if beampath is None:
        beampath = metadata.beampath

    bpm_x_data, bpm_y_data, bpm_names = _extract_bpm_data(collection.raw_data)

    wire_name = metadata.wire_name
    rmat_x, rmat_y = get_jitter_rmat(wire_name, bpm_names, beampath, physics_model)

    # Build full 6x6 R-matrices as MATLAB expects in data.rMatList
    n_bpms = len(bpm_names)
    rmat_list = np.zeros((6, 6, n_bpms))
    for i in range(n_bpms):
        rmat_list[0, 0, i] = rmat_x[i, 0]  # R11
        rmat_list[0, 1, i] = rmat_x[i, 1]  # R12
        rmat_list[0, 5, i] = rmat_x[i, 2]  # R16
        rmat_list[2, 2, i] = rmat_y[i, 0]  # R33
        rmat_list[2, 3, i] = rmat_y[i, 1]  # R34
        rmat_list[2, 5, i] = rmat_y[i, 2]  # R36

    # Compute Python jitter RMS for embedding in .mat
    if result.jitter_rms is not None:
        python_jitter_rms = np.array(result.jitter_rms)
    else:
        jitter_x, jitter_y = _compute_orbit_fit(
            bpm_x_data, bpm_y_data, rmat_x, rmat_y
        )
        python_jitter_rms = np.array([np.std(jitter_x), np.std(jitter_y)])

    select_bpm = np.ones(n_bpms, dtype=np.double)

    mat_data = {
        "BPMXData": bpm_x_data,
        "BPMYData": bpm_y_data,
        "rMatList": rmat_list,
        "selectBPM": select_bpm,
        "wireName": wire_name,
        "beampath": beampath,
        "bpmNames": np.array(bpm_names, dtype=object),
        "nBPMs": n_bpms,
        "nPulses": bpm_x_data.shape[1],
        "python_jitter_rms": python_jitter_rms,
    }

    if mat_path is None:
        mat_path = str(Path(h5_path).with_suffix(".mat"))

    scipy.io.savemat(mat_path, mat_data)
    print(f"Saved {mat_path}")
    return mat_path


def convert_directory(
    h5_dir: str,
    mat_dir: str | None = None,
    beampath: str | None = None,
    physics_model: str = "BLEM",
) -> list[str]:
    """Convert all .h5 files in a directory to .mat format.

    Parameters
    ----------
    h5_dir : str
        Directory containing .h5 analysis files.
    mat_dir : str, optional
        Output directory for .mat files. Defaults to h5_dir.
    beampath : str, optional
        Override beampath for R-matrix retrieval.
    physics_model : str
        Model source for R-matrices. Default "BLEM".

    Returns
    -------
    list[str]
        Paths to saved .mat files.
    """
    h5_dir = Path(h5_dir)
    if mat_dir is None:
        mat_dir = h5_dir
    else:
        mat_dir = Path(mat_dir)
        mat_dir.mkdir(parents=True, exist_ok=True)

    mat_paths = []
    for h5_path in sorted(h5_dir.glob("*.h5")):
        mat_path = str(mat_dir / h5_path.with_suffix(".mat").name)
        try:
            result = convert_h5_to_mat(
                str(h5_path), mat_path, beampath, physics_model
            )
            mat_paths.append(result)
        except Exception as e:
            print(f"Failed to convert {h5_path.name}: {e}")

    return mat_paths


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m benchmarking.jitter_h5_to_mat <h5_dir> [mat_dir]")
        sys.exit(1)

    h5_dir = sys.argv[1]
    mat_dir = sys.argv[2] if len(sys.argv) > 2 else None
    convert_directory(h5_dir, mat_dir)
