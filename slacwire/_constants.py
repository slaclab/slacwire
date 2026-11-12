from __future__ import annotations

from datetime import datetime
from pathlib import Path

VALID_BEAMPATHS = ["CU_HXR", "CU_SXR", "SC_HXR", "SC_SXR", "SC_BSYD", "SC_DIAG0"]

VALID_FIT_METHODS = [
    "gaussian",
    "asymmetric_gaussian",
    "super_gaussian",
    "rms_raw",
    "rms_cut_peak",
    "rms_cut_area",
    "rms_floor",
]

WIRE_AREA_LOOKUP = {
    "WS01": "DL1",
    "WS02": "DL1",
    "WS03": "DL1",
    "WS04": "DL1",
    "WS11": "BC1",
    "WS12": "BC1",
    "WS13": "BC1",
    "WS27644": "L3",
    "WS28144": "L3",
    "WS28444": "L3",
    "WS28744": "L3",
    "WS0H04": "HTR",
    "WSDG01": "DIAG0",
    "WSC104": "COL1",
    "WSC106": "COL1",
    "WSC108": "COL1",
    "WSC110": "COL1",
    "WSEMIT2": "EMIT2",
    "WSBP2": "BYP",
    "WSBP3": "BYP",
    "WSBP4": "BYP",
    "WSBP5": "BYP",
    "WSSP1D": "SPD",
    "WS31": "LTUH",
    "WS32": "LTUH",
    "WS33": "LTUH",
    "WS34": "LTUH",
    "WS31B": "LTUS",
    "WS32B": "LTUS",
    "WS33B": "LTUS",
    "WS34B": "LTUS",
}

VALID_SCAN_MODES = ("otf", "step")

# Per-wire default scan mode, applied by the suite, CLI, and GUI whenever no
# scan mode is explicitly requested. Wires not listed use DEFAULT_SCAN_MODE.
# WS02: OTF unsupported due to lagging hardware — use step scans.
SCAN_MODE_OVERRIDES = {
    "WS02": "step",
}
DEFAULT_SCAN_MODE = "otf"


def default_scan_mode(wire: str) -> str:
    """Return the default scan mode ("otf" or "step") for a wire."""
    return SCAN_MODE_OVERRIDES.get(wire.split(":")[0], DEFAULT_SCAN_MODE)


def resolve_scan_mode(wire: str, scan_mode: str | None = None) -> str:
    """Resolve the scan mode for a wire.

    ``None`` selects the per-wire default from ``SCAN_MODE_OVERRIDES``.
    An explicit mode is honored (case-insensitive) and validated.
    """
    if scan_mode is None:
        return default_scan_mode(wire)
    mode = scan_mode.lower()
    if mode not in VALID_SCAN_MODES:
        raise ValueError(f"Invalid scan_mode '{scan_mode}'. Use 'otf' or 'step'.")
    return mode


_BASE_DIR = Path("/u1/lcls/physics/data/wire_scan")
_SCOPE_DATA_DIR = Path("/u1/lcls/physics/genMotion/wirescanners/scope_data")
_REGISTRY_PATH = _BASE_DIR / "ws_run_registry.json"
_CONFIG_DB_PATH = _BASE_DIR / "wire_config.db"


def dated_output_dir(
    dt: datetime | None = None,
    base_dir: Path | str = _BASE_DIR,
) -> Path:
    """Create and return dated directory for wire scan data."""
    dt = dt or datetime.now()
    root = Path(base_dir)
    path = root / f"{dt:%Y}" / f"{dt:%m}" / f"{dt:%d}"
    path.mkdir(parents=True, exist_ok=True)
    (path / "plots").mkdir(parents=True, exist_ok=True)
    return path
