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

            from slac_measurements.fitting import gaussian

            # Fit uncorrected profile
            sort_idx_unc = np.argsort(x_beam_uncorrected)
            x_sorted_unc = x_beam_uncorrected[sort_idx_unc]
            y_sorted_unc = detector_values[sort_idx_unc]

            try:
                fp_unc = gaussian.fit(pos=x_sorted_unc, data=y_sorted_unc)
                fit_x_unc = np.linspace(x_sorted_unc.min(), x_sorted_unc.max(), 200)
                fit_curve_unc = gaussian.curve(x=fit_x_unc, **{k: v for k, v in fp_unc.items() if k != "error"})
                fit_sigma_unc = fp_unc["sigma"]
            except Exception:
                fit_x_unc = None
                fit_curve_unc = None
                fit_sigma_unc = None

            # Fit corrected profile
            sort_idx = np.argsort(x_beam_corrected)
            x_sorted = x_beam_corrected[sort_idx]
            y_sorted = detector_values[sort_idx]

            try:
                fp = gaussian.fit(pos=x_sorted, data=y_sorted)
                fit_x = np.linspace(x_sorted.min(), x_sorted.max(), 200)
                fit_curve = gaussian.curve(x=fit_x, **{k: v for k, v in fp.items() if k != "error"})
                fit_sigma = fp["sigma"]
            except Exception:
                fit_x = None
                fit_curve = None
                fit_sigma = None

            ts = meta.timestamp
            stamp = ts.strftime("%Y%m%d_%H%M%S") if ts else self._stamp()

            path = self.view.plot_jitter_compare(
                x_uncorrected=x_beam_uncorrected,
                x_corrected=x_beam_corrected,
                detector_values=detector_values,
                wire=wire,
                detector=det,
                jitter_rms=jitter_rms,
                fit_x_uncorrected=fit_x_unc,
                fit_curve_uncorrected=fit_curve_unc,
                fit_sigma_uncorrected=fit_sigma_unc,
                fit_x_corrected=fit_x,
                fit_curve_corrected=fit_curve,
                fit_sigma_corrected=fit_sigma,
                plotdir=plotdir,
                stamp=stamp,
                show=self.show,
                save=self.save_plots,
            )
            if path is not None:
                plot_paths.append(path)

        print(f"Plotted {len(plot_paths)} jitter comparison(s) for {wire} on {date}")
        return plot_paths
