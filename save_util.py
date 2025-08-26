from pathlib import Path
from datetime import datetime

BASE_DIR = Path("/u1/lcls/physics/data/wire_scan")  # fixed, regardless of launch cwd


def dated_dir(dt: datetime | None = None) -> Path:
    """
    Ensure /u1/lcls/physics/data/wire_scan/YYYY/MM/DD exists and return it.
    """
    dt = dt or datetime.now()
    path = BASE_DIR / f"{dt:%Y}" / f"{dt:%m}" / f"{dt:%d}"
    path.mkdir(parents=True, exist_ok=True)
    return path
