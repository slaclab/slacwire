from __future__ import annotations

import logging

from slacwire._constants import resolve_scan_mode

logger = logging.getLogger("wire_scan_logger")


class CollectMixin:
    """Methods for raw data collection without analysis."""

    def collect_single(
        self,
        wire: str,
        scan_mode: str | None = None,
    ):
        """Collect raw data for a single wire without analysis.

        Args:
            wire: Wire name (e.g. "WS28144"). Must exist in WIRE_AREA_LOOKUP.
            scan_mode: "otf" (on-the-fly) or "step". If None, uses the wire's
                default from ``SCAN_MODE_OVERRIDES`` ("otf" unless listed).
        """
        wire_name, _ = self._resolve_wire_and_area(wire)
        mode = resolve_scan_mode(wire_name, scan_mode)
        device = self._get_device(wire_name)

        self._run_device_scan(
            device=device,
            method=f"{mode}_collection",
            scan_fn=lambda dev, rms_detector=None: self._collect(
                dev, scan_mode=mode
            ),
            rms_detector=None,
            file_prefix=f"{'OTF' if mode == 'otf' else 'Step'}Collect",
        )

    def _collect(self, device, scan_mode: str):
        """Run collection only (no fitting/analysis)."""
        from slac_measurements.wires.collection import create_wire_collection

        collection = create_wire_collection(
            scan_mode=scan_mode,
            beam_profile_device=device,
            beampath=self.beampath,
        )
        return collection.measure()
