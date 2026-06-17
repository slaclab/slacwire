from __future__ import annotations

import logging

from ..otf_motion_test import run_otf_motion_test
from ..step_motion_test import run_step_motion_test

logger = logging.getLogger("wire_scan_logger")

_MOTION_TEST_FNS = {
    "otf": run_otf_motion_test,
    "step": run_step_motion_test,
}


class MotionTestMixin:
    """Methods for beam-less wire motion validation."""

    def motion_test(self, wire: str, scan_mode: str = "otf", plot: bool = True):
        """Run beam-less motion validation for a single wire.

        Args:
            wire: Wire name (e.g. "WS28144"). Must exist in WIRE_AREA_LOOKUP.
            scan_mode: "otf" (on-the-fly) or "step". Default "otf".
            plot: If True, display trajectory plot of motor position vs scan
                point. Also saves PNG if suite.save_plots is True.
        """
        mode = scan_mode.lower()
        if mode not in _MOTION_TEST_FNS:
            raise ValueError(
                f"Invalid scan_mode '{scan_mode}'. Use 'otf' or 'step'."
            )

        wire_name, _ = self._resolve_wire_and_area(wire)
        device = self._get_device(wire_name)
        result = _MOTION_TEST_FNS[mode](device)
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
