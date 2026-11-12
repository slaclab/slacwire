from __future__ import annotations

import logging

from slacwire._constants import resolve_scan_mode

logger = logging.getLogger("wire_scan_logger")


def _get_motion_fn(mode: str):
    from slac_measurements.wires.collection.beamless_otf import run_beamless_otf_scan
    from slac_measurements.wires.collection.beamless_step import run_beamless_step_scan

    fns = {"otf": run_beamless_otf_scan, "step": run_beamless_step_scan}
    return fns[mode]


class MotionTestMixin:
    """Methods for beam-less wire motion validation."""

    def motion_test(
        self, wire: str, scan_mode: str | None = None, plot: bool = True
    ):
        """Run beam-less motion validation for a single wire.

        Args:
            wire: Wire name (e.g. "WS28144"). Must exist in WIRE_AREA_LOOKUP.
            scan_mode: "otf" (on-the-fly) or "step". If None, uses the wire's
                default from ``SCAN_MODE_OVERRIDES`` ("otf" unless listed).
            plot: If True, display trajectory plot of motor position vs scan
                point. Also saves PNG if suite.save_plots is True.

        Returns:
            The motion test result object from the scan.
        """
        wire_name, _ = self._resolve_wire_and_area(wire)
        mode = resolve_scan_mode(wire_name, scan_mode)
        device = self._get_device(wire_name)
        result = _get_motion_fn(mode)(device)
        logger.info("%s motion test complete for %s.", mode.upper(), wire_name)

        if plot:
            logger.info("Rendering motion test plots for %s...", wire_name)
            self.view.render_motion_test(
                result,
                wire=wire_name,
                plotdir=self.plotdir,
                stamp=self._stamp(),
                show=self.show,
                save=self.save_plots,
            )
            logger.info("Plot rendering complete for %s.", wire_name)

        return result
