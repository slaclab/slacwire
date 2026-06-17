from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

Beampath = Literal["CU_HXR", "CU_SXR", "SC_HXR", "SC_SXR", "SC_BSYD", "SC_DIAG0"]

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

_BASE_DIR = "/u1/lcls/physics/data/wire_scan"
_SCOPE_DATA_DIR = Path("/u1/lcls/physics/genMotion/wirescanners/scope_data")


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
