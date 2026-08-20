from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..view import WireScanView

from slac_devices.reader import create_wire

from ..registry import RunRegistry
from ._constants import WIRE_AREA_LOOKUP, _SCOPE_DATA_DIR, dated_output_dir

logger = logging.getLogger("wire_scan_logger")


@dataclass
class WireScanSuiteBase:
    """Base dataclass with fields and infrastructure for WireScanSuite."""

    wires: list = field(default_factory=lambda: ["WS28144"])
    devices: dict = field(default_factory=dict)
    beampath: str = "CU_HXR"
    detector: str | None = None
    outdir: Path = field(default_factory=dated_output_dir)
    plotdir: Path | None = None
    save: bool = True
    show: bool = True
    save_plots: bool = True
    dev_mode: bool = False
    results: dict = field(default_factory=dict)
    registry: RunRegistry = field(default_factory=RunRegistry)
    view: "WireScanView" = field(init=False)  # type: ignore[assignment]

    def __post_init__(self):
        """Initialize the wire scan suite after dataclass construction."""
        self._build_devices()
        self.view = self._build_view()
        self.outdir = Path(self.outdir)
        self.plotdir = self.outdir / "plots"
        self.outdir.mkdir(parents=True, exist_ok=True)
        self.plotdir.mkdir(parents=True, exist_ok=True)

    def __repr__(self) -> str:
        """Return a concise representation of suite state for debugging."""
        instantiated_wires = sorted(self.wires)
        result_counts = {
            wire: len(runs)
            for wire, runs in self.results.items()
            if runs
        }
        total_results = sum(result_counts.values())
        has_results = total_results > 0

        return (
            f"WireScanSuite(beampath={self.beampath!r}, "
            f"wire_list={instantiated_wires!r}, "
            f"has_results={has_results}, "
            f"result_counts={result_counts!r})"
        )

    def _build_devices(self):
        """Initialize all wire device instances based on configured wires."""
        self.devices = {wire: self._make_device(wire) for wire in self.wires}

    def _build_view(self):
        """Create the plotting view instance used by the suite."""
        from ..view import WireScanView

        return WireScanView()

    def _get_device(self, wire: str):
        """Get or lazily create a device for a wire name."""
        if wire not in self.devices:
            self.devices[wire] = self._make_device(wire)
        return self.devices[wire]

    def _make_device(self, wire: str):
        """Create a wire device instance."""
        wire_name, area = self._resolve_wire_and_area(wire)
        return create_wire(area, wire_name)

    def _resolve_scope_data_path(
        self,
        wire: str,
        method: str,
        since: datetime | None = None,
    ) -> Path | None:
        """Return latest scope CSV path for an OTF run, if available."""
        if method != "otf":
            return None

        wire_dir = _SCOPE_DATA_DIR / wire
        if not wire_dir.exists() or not wire_dir.is_dir():
            return None

        csv_files = sorted(
            [
                path
                for path in wire_dir.glob(f"{wire}_*.csv")
                if path.is_file()
            ],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not csv_files:
            return None

        if since is None:
            return csv_files[0]

        since_ts = since.timestamp() - 2.0
        for candidate in csv_files:
            if candidate.stat().st_mtime >= since_ts:
                return candidate

        return csv_files[0]

    def _resolve_wire_and_area(self, wire: str) -> tuple[str, str]:
        """Resolve a wire input to wire name and area."""
        wire = wire.strip()

        if not wire:
            raise ValueError("Wire name cannot be empty.")

        area = WIRE_AREA_LOOKUP.get(wire)
        if area is None:
            raise KeyError(
                f"No area mapping found for wire '{wire}'. Add it to "
                "WIRE_AREA_LOOKUP."
            )
        return wire, area

    def _stamp(self) -> str:
        """Generate a timestamp string for file naming."""
        return datetime.now().strftime("%Y%m%d_%H%M%S")
