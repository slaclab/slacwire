from __future__ import annotations

from datetime import datetime
from pathlib import Path

from slac_measurements.wires.analysis.results import load_from_h5

from ._constants import _BASE_DIR


class LoaderMixin:
    """Load wire scan results from .h5 files on disk."""

    def load_scan(self, path: str | Path):
        """Load a single wire scan result from an .h5 file.

        Args:
            path: Path to the .h5 file.

        Returns:
            WireMeasurementAnalysisResult loaded from the file.
        """
        return load_from_h5(str(path))

    def discover_scans(
        self,
        wire: str,
        date: str,
        limit: int | None = 10,
        subdir: str | None = None,
    ) -> list:
        """Discover and load .h5 scans for a wire on a given date.

        Scans the dated directory for .h5 files, filters by wire name
        in metadata, and returns results sorted most-recent first.

        Args:
            wire: Wire name to match (e.g. "WS28444").
            date: ISO date string (YYYY-MM-DD).
            limit: Maximum results to return (most recent first).
                Pass None to return all matching scans.
            subdir: Optional subdirectory within the dated folder to search.

        Returns:
            List of WireMeasurementAnalysisResult, sorted by timestamp descending.
        """
        dt = datetime.strptime(date, "%Y-%m-%d")
        day_dir = Path(_BASE_DIR) / f"{dt:%Y}" / f"{dt:%m}" / f"{dt:%d}"

        scan_dir = day_dir / subdir if subdir else day_dir
        if not scan_dir.exists():
            return []

        candidates: list[tuple[datetime, object]] = []
        for h5_path in sorted(scan_dir.glob("*.h5")):
            try:
                data = load_from_h5(str(h5_path))
            except Exception:
                continue
            meta = data.collection_result.metadata
            if meta.wire_name != wire:
                continue
            ts = meta.timestamp or datetime.min
            candidates.append((ts, data))

        candidates.sort(key=lambda x: x[0], reverse=True)

        if limit is not None:
            candidates = candidates[:limit]

        return [data for _, data in candidates]
