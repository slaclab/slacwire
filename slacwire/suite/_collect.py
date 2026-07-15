from __future__ import annotations

import logging

logger = logging.getLogger("wire_scan_logger")


class CollectMixin:
    """Methods for raw data collection without analysis."""

    def collect_single(
        self,
        wire: str,
        scan_mode: str = "otf",
    ):
        """Collect raw data for a single wire without analysis.

        Args:
            wire: Wire name (e.g. "WS28144"). Must exist in WIRE_AREA_LOOKUP.
            scan_mode: "otf" (on-the-fly) or "step". Default "otf".
        """
        wire_name, _ = self._resolve_wire_and_area(wire)
        device = self._get_device(wire_name)
        mode = scan_mode.lower()

        if mode not in ("otf", "step"):
            raise ValueError(
                f"Invalid scan_mode '{scan_mode}'. Use 'otf' or 'step'."
            )

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
