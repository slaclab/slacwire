from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np

from ._constants import _BASE_DIR


class JitterCompareMixin:
    """Compare Y profiles with and without jitter correction from stored data."""

    def jitter_compare(
        self,
        wire: str,
        date: str,
        limit: int | None = 10,
        detector: str | None = None,
    ) -> list[Path]:
        """Side-by-side jitter-corrected and uncorrected Y profiles for a wire on a given date.

        Args:
            wire: Wire name to filter .h5 files by (e.g. "WS28444").
            date: ISO date string (YYYY-MM-DD) identifying the data directory.
            limit: Maximum number of scans to plot (most recent first).
                Pass None to plot all matching scans.
            detector: Detector override. If None, uses each file's default.

        Returns:
            List of Paths to saved plot PNGs.
        """
        from slac_measurements.wires.coordinates import stage_to_beam
        from slac_measurements.wires.jitter_correction import compute_jitter

        scans = self.discover_scans(wire, date, limit)
        if not scans:
            print(f"No .h5 files found for {wire} on {date}")
            return []

        dt = datetime.strptime(date, "%Y-%m-%d")
        day_dir = Path(_BASE_DIR) / f"{dt:%Y}" / f"{dt:%m}" / f"{dt:%d}"
        plotdir = day_dir / "plots"
        plotdir.mkdir(parents=True, exist_ok=True)

        plot_paths: list[Path] = []
        for data in scans:
            meta = data.collection_result.metadata

            det = detector
            if det is None:
                det = getattr(meta, "rms_detector", None) or meta.default_detector

            if "y" not in data.profiles:
                continue

            y_profile = data.profiles["y"]
            x_stage = np.asarray(y_profile.positions)
            detector_values = np.asarray(y_profile.detectors[det].values)
            install_angle = meta.install_angle

            x_beam_uncorrected = stage_to_beam(x_stage, "y", install_angle)

            try:
                jitter_x, jitter_y = compute_jitter(
                    data.collection_result, meta.beampath, "BLEM"
                )
                jy = jitter_y[y_profile.profile_indices]
                x_beam_corrected = x_beam_uncorrected - jy
            except Exception:
                continue

            jitter_rms = (float(np.std(jitter_x)), float(np.std(jitter_y)))

            ts = meta.timestamp
            stamp = ts.strftime("%Y%m%d_%H%M%S") if ts else self._stamp()

            path = self.view.plot_jitter_compare(
                x_uncorrected=x_beam_uncorrected,
                x_corrected=x_beam_corrected,
                detector_values=detector_values,
                wire=wire,
                detector=det,
                jitter_rms=jitter_rms,
                plotdir=plotdir,
                stamp=stamp,
                show=self.show,
                save=self.save_plots,
            )
            if path is not None:
                plot_paths.append(path)

        print(f"Plotted {len(plot_paths)} jitter comparison(s) for {wire} on {date}")
        return plot_paths
