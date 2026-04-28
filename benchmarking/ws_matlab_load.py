from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
import logging

import h5py
import numpy as np
from numpy.typing import NDArray

from lcls_tools.common.measurements.ws_collection_results import (
    WireMeasurementCollectionResult,
    MeasurementMetadata,
)

logger = logging.getLogger(__name__)

# Configuration
PLANES = ("x", "y", "u")
DEFAULT_BEAMPATH = "CU_HXR"
DEFAULT_AREA = "N/A"
DEFAULT_INSTALL_ANGLE = 45.0

WIRE_SCAN_RANGES = {
    "WS02": {
        "x": (25000, 33000),
        "y": (40000, 44000),
        "u": (12000, 20000)
    },
    "WS03": {
        "x": (28000, 32000),
        "y": (39000, 44000),
        "u": (14000, 18000)
    },
    "WS12": {
        "x": (26000, 32000),
        "y": (38000, 44000),
        "u": (14000, 18000)
    },
    "WS27644": {
        "x": (29000, 32000),
        "y": (39000, 42000),
        "u": (15000, 18000)
    },
    "WS28144": {
        "x": (30000, 34000),
        "y": (38000, 42000),
        "u": (15000, 19000)
    },
    "WS28444": {
        "x": (28000, 32000),
        "y": (37000, 42000),
        "u": (14000, 19000)
    },
    "WS28744": {
        "x": (37000, 44000),
        "y": (27000, 32000),
        "u": (13000, 18000)
    }
}

WIRE_LOOKUP = {
    "WIRE:IN20:561": "WS02",
    "WIRE:IN20:611": "WS03",
    "WIRE:LI21:293": "WS12",
    "WIRE:LI27:644": "WS27644",
    "WIRE:LI28:144": "WS28144",
    "WIRE:LI28:444": "WS28444",
    "WIRE:LI28:744": "WS28744",
}


@dataclass
class MATLABScanData:
    """Structured data from a MATLAB-exported wire scan HDF5 file."""

    wire_name: str
    wire_data: NDArray[np.float64]
    pmt_list: list[str]
    selected_pmt_index: int
    pmt_all_data: NDArray[np.float64]
    pmt_selected_data: NDArray[np.float64]
    beam_rms: dict[str, float]
    wire_limits: dict[str, tuple[float, float]]
    source_file: Optional[str] = None


def clean_wire_name(raw: Any) -> Optional[str]:
    """
    Normalize wire name from HDF5.

    MATLAB exports may wrap strings in formats like "[b'WIRE:IN20:561']".
    This function extracts the actual wire name.

    Args:
        raw: Raw value from HDF5 file (may be bytes, str, or wrapped format)

    Returns:
        Normalized wire name string, or None if input is None
    """
    if raw is None:
        return None

    s = str(raw)

    # Strip list-like wrappers: [b'...'] -> b'...'
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1]

    # Strip byte literal wrapper: b'...' -> ...
    if s.startswith("b'") and s.endswith("'"):
        s = s[2:-1]

    return s


def load_ws_h5(path: Path | str) -> MATLABScanData:
    """
    Load a single wire-scan HDF5 file exported from MATLAB.

    Args:
        path: Path to HDF5 file

    Returns:
        MATLABScanData object with all scan data

    Raises:
        KeyError: If required HDF5 keys are missing
        OSError: If file cannot be read
    """
    path = Path(path)

    with h5py.File(path, "r") as f:
        # Validate required keys
        required_keys = ["/wire/name", "/wire/data", "/pmt/list",
                         "/pmt/selected_index", "/pmt/all_data",
                         "/pmt/selected_data"]
        for key in required_keys:
            if key not in f:
                raise KeyError(f"Missing required HDF5 key: {key} in {path}")

        # ---- Wire ----
        name = f["/wire/name"][()]
        wire_name = (
            name.decode()
            if isinstance(name, (bytes, bytearray))
            else str(name)
        )
        wire_data = np.asarray(f["/wire/data"])

        # ---- PMTs ----
        pmt_list = [
            s.decode() if isinstance(s, (bytes, bytearray)) else str(s)
            for s in f["/pmt/list"][()]
        ]
        selected_pmt_index = int(f["/pmt/selected_index"][()])
        pmt_all_data = np.asarray(f["/pmt/all_data"])
        pmt_selected_data = np.asarray(f["/pmt/selected_data"])

        # ---- Beam RMS ----
        beam_rms = {
            plane: (float(f[f"/beam/{plane}_rms"][()])
                    if f"/beam/{plane}_rms" in f else np.nan)
            for plane in PLANES
        }

        # ---- Wire Limits (scan ranges) ----
        wire_limits = {}
        for plane in PLANES:
            key = f"/wireLimit/{plane}"
            if key in f:
                limits = np.asarray(f[key])
                wire_limits[plane] = (
                    tuple(limits) if len(limits) == 2 else None
                )
            else:
                # Fallback to defaults if available
                if wire_name in WIRE_SCAN_RANGES:
                    wire_limits[plane] = WIRE_SCAN_RANGES[wire_name][plane]
                else:
                    logger.warning(
                        f"No scan range found for {wire_name}/{plane}"
                        )
                    wire_limits[plane] = None

    return MATLABScanData(
        wire_name=wire_name,
        wire_data=wire_data,
        pmt_list=pmt_list,
        selected_pmt_index=selected_pmt_index,
        pmt_all_data=pmt_all_data,
        pmt_selected_data=pmt_selected_data,
        beam_rms=beam_rms,
        wire_limits=wire_limits,
        source_file=path.name,
    )


def load_all_ws_h5(
    dir_path: Path | str, file_pattern: str = "*.h5"
) -> list[MATLABScanData]:
    """
    Load all wire-scan HDF5 files in a directory.

    Args:
        dir_path: Path to directory containing HDF5 files
        file_pattern: Glob pattern for matching files (default: "*.h5")

    Returns:
        List of MATLABScanData objects, one per successfully loaded scan
    """
    scans = []
    dir_path = Path(dir_path)

    if not dir_path.exists():
        logger.error(f"Directory does not exist: {dir_path}")
        return scans

    for h5_path in sorted(dir_path.glob(file_pattern)):
        try:
            scan_data = load_ws_h5(h5_path)
            scans.append(scan_data)
        except Exception as e:
            logger.warning(f"Failed to load {h5_path.name}: {e}")

    return scans


def matlab_h5_to_buffer_dict(
    scan: MATLABScanData,
    beampath: str = DEFAULT_BEAMPATH,
    area: str = DEFAULT_AREA,
    install_angle: float = DEFAULT_INSTALL_ANGLE,
) -> WireMeasurementCollectionResult:
    """
    Convert MATLAB scan data to WireMeasurementCollectionResult format.

    Args:
        scan: MATLAB scan data from load_ws_h5()
        beampath: Beam path identifier (default: CU_HXR)
        area: Area identifier (default: N/A)
        install_angle: Wire install angle in degrees (default: 45.0)

    Returns:
        WireMeasurementCollectionResult with raw data and metadata

    Raises:
        KeyError: If wire name not found in WIRE_LOOKUP
    """
    # Convert wire name using lookup
    cleaned_wire = clean_wire_name(scan.wire_name)
    if cleaned_wire not in WIRE_LOOKUP:
        raise KeyError(f"Unknown wire: {cleaned_wire}. Not in WIRE_LOOKUP.")

    wire_name = WIRE_LOOKUP[cleaned_wire]

    # Build raw data dict
    raw_data = {wire_name: scan.wire_data.flatten()}

    pmt_name = clean_wire_name(scan.pmt_list[scan.selected_pmt_index])
    raw_data[pmt_name] = scan.pmt_selected_data.flatten()

    # Create metadata
    metadata = MeasurementMetadata(
        wire_name=wire_name,
        area=area,
        beampath=beampath,
        detectors=[pmt_name],
        default_detector=pmt_name,
        scan_ranges=scan.wire_limits,
        timestamp=datetime.now(timezone.utc),
        active_profiles=list(PLANES),
        install_angle=install_angle,
    )

    return WireMeasurementCollectionResult(
        raw_data=raw_data,
        metadata=metadata,
    )
