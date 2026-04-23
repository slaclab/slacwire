import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("wire_scan_logger")

DEFAULT_REGISTRY_PATH = Path("/u1/lcls/physics/data/wire_scan/ws_run_registry.json")


@dataclass
class RunRegistry:
    """Persistent audit trail of wire scan runs.

    Handles loading, appending, and atomically saving run entries to a JSON
    file. Manages run ID sequencing safely across concurrent instances by
    re-reading the file counter before each write.

    Attributes:
        path: Filesystem path to the JSON registry file.
        entries: In-memory list of run entry dicts loaded from / written to disk.
    """
    path: Path = DEFAULT_REGISTRY_PATH
    entries: list = field(default_factory=list)
    _counter: int = field(default=0, init=False, repr=False)

    def __post_init__(self):
        self._load()
        self._counter = self._max_run_id()

    def log(
        self,
        method: str,
        wire: str,
        beampath: str,
        detector=None,
        filepath=None,
        plots=None,
        status: str = "ok",
        error=None,
    ) -> dict:
        """Append a run entry and persist to disk.

        Re-syncs the run counter from disk before incrementing so that
        multiple Suite instances sharing the same registry file stay
        consistent.

        Args:
            method: Scan method label, e.g. ``"otf"`` or ``"step"``.
            wire: Wire device name, e.g. ``"WS28144"``.
            beampath: Accelerator beampath identifier, e.g. ``"CU_HXR"``.
            detector: Detector PV name used during the scan.
            filepath: Path to the saved HDF5 data file, if any.
            plots: List of paths to saved PNG plot files.
            status: ``"ok"`` on success, ``"error"`` on failure.
            error: Exception message string when ``status="error"``.

        Returns:
            The entry dict that was appended and persisted.
        """
        self._counter = max(self._counter, self._max_run_id())
        self._counter += 1

        entry = {
            "run_id": self._counter,
            "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "method": method,
            "wire": wire,
            "beampath": beampath,
            "detector": detector,
            "filepath": str(filepath) if filepath else None,
            "plots": [str(p) for p in plots] if plots else [],
            "status": status,
            "error": error,
        }
        self.entries.append(entry)
        self._save()
        return entry

    def _load(self):
        """Load entries from the JSON file on disk, if it exists."""
        if not self.path.exists():
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, list):
                self.entries = loaded
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Could not load registry from {self.path}: {e}")

    def _save(self):
        """Atomically write entries to the JSON file using a temp file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.parent / (self.path.name + ".tmp")
        try:
            with open(temp, "w", encoding="utf-8") as f:
                json.dump(self.entries, f, indent=2)
            temp.replace(self.path)
        except OSError as e:
            logger.warning(f"Could not save registry to {self.path}: {e}")
            if temp.exists():
                temp.unlink()

    def _max_run_id(self) -> int:
        """Read the highest run_id from disk to handle concurrent instances."""
        if not self.path.exists():
            return 0
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            return max(
                (
                    int(e["run_id"])
                    for e in loaded
                    if isinstance(e, dict) and "run_id" in e
                ),
                default=0,
            )
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            return 0
