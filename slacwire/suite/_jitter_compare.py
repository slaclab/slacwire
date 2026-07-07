from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np

from ._constants import _BASE_DIR


def _fit_profile(x_beam: np.ndarray, detector_values: np.ndarray) -> dict:
    """Fit a Gaussian to a profile and return fit curve data plus residuals.

    Returns dict with keys: x_sorted, y_sorted, fit_x, fit_curve, fit_sigma, residuals.
    All values are None (except x_sorted/y_sorted) if the fit fails.
    """
    from slac_measurements.fitting import gaussian

    sort_idx = np.argsort(x_beam)
    x_sorted = x_beam[sort_idx]
    y_sorted = detector_values[sort_idx]

    try:
        fp = gaussian.fit(pos=x_sorted, data=y_sorted)
        fit_x = np.linspace(x_sorted.min(), x_sorted.max(), 200)
        fit_params = {k: v for k, v in fp.items() if k != "error"}
        fit_curve = gaussian.curve(x=fit_x, **fit_params)
        fit_sigma = fp["sigma"]
        fit_at_data = gaussian.curve(x=x_sorted, **fit_params)
        residuals = y_sorted - fit_at_data
    except Exception:
        fit_x = None
        fit_curve = None
        fit_sigma = None
        residuals = None

    return {
        "x_sorted": x_sorted,
        "y_sorted": y_sorted,
        "fit_x": fit_x,
        "fit_curve": fit_curve,
        "fit_sigma": fit_sigma,
        "residuals": residuals,
    }


def _compute_fft(x: np.ndarray, residuals: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Compute FFT power spectrum of residuals interpolated onto a uniform grid.

    Returns (freqs, power) arrays.
    """
    n = len(residuals)
    x_uniform = np.linspace(x.min(), x.max(), n)
    resid_uniform = np.interp(x_uniform, x, residuals)

    step = (x.max() - x.min()) / (n - 1)
    freqs = np.fft.rfftfreq(n, d=step)
    power = np.abs(np.fft.rfft(resid_uniform)) ** 2
    return freqs, power


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
                    data.collection_result, meta.beampath, "BMAD"
                )
                jy = jitter_y[y_profile.profile_indices]
                x_beam_corrected = x_beam_uncorrected - jy
                jitter_rms = (float(np.std(jitter_x)), float(np.std(jitter_y)))
            except Exception:
                x_beam_corrected = None
                jitter_rms = None

            unc = _fit_profile(x_beam_uncorrected, detector_values)

            corr = None
            if x_beam_corrected is not None:
                corr = _fit_profile(x_beam_corrected, detector_values)

            ts = meta.timestamp
            stamp = ts.strftime("%Y%m%d_%H%M%S") if ts else self._stamp()

            if x_beam_corrected is not None and corr is not None:
                path = self.view.plot_jitter_compare(
                    x_uncorrected=x_beam_uncorrected,
                    x_corrected=x_beam_corrected,
                    detector_values=detector_values,
                    wire=wire,
                    detector=det,
                    jitter_rms=jitter_rms,
                    fit_x_uncorrected=unc["fit_x"],
                    fit_curve_uncorrected=unc["fit_curve"],
                    fit_sigma_uncorrected=unc["fit_sigma"],
                    fit_x_corrected=corr["fit_x"],
                    fit_curve_corrected=corr["fit_curve"],
                    fit_sigma_corrected=corr["fit_sigma"],
                    plotdir=plotdir,
                    stamp=stamp,
                    show=self.show,
                    save=self.save_plots,
                )
                if path is not None:
                    plot_paths.append(path)

            if unc["residuals"] is not None:
                if corr is not None and corr["residuals"] is not None:
                    fft_freqs, fft_power = _compute_fft(corr["x_sorted"], corr["residuals"])
                else:
                    fft_freqs, fft_power = _compute_fft(unc["x_sorted"], unc["residuals"])

                vib_path = self.view.plot_vibration_residuals(
                    x_uncorrected=unc["x_sorted"],
                    residuals_uncorrected=unc["residuals"],
                    x_corrected=corr["x_sorted"] if corr else None,
                    residuals_corrected=corr["residuals"] if corr else None,
                    fft_freqs=fft_freqs,
                    fft_power=fft_power,
                    wire=wire,
                    detector=det,
                    plotdir=plotdir,
                    stamp=stamp,
                    show=self.show,
                    save=self.save_plots,
                )
                if vib_path is not None:
                    plot_paths.append(vib_path)

        print(f"Plotted {len(plot_paths)} jitter comparison(s) for {wire} on {date}")
        return plot_paths

    def vibration_summary(
        self,
        wire: str,
        date: str,
        limit: int | None = 10,
        detector: str | None = None,
    ) -> dict:
        """Compute vibration RMS across scans for quantitative wire comparison.

        Returns dict with keys: wire, n_scans, rms_values, mean_rms, std_rms.
        """
        from slac_measurements.wires.coordinates import stage_to_beam
        from slac_measurements.wires.jitter_correction import compute_jitter

        scans = self.discover_scans(wire, date, limit)
        if not scans:
            print(f"No .h5 files found for {wire} on {date}")
            return {"wire": wire, "n_scans": 0, "rms_values": [], "mean_rms": None, "std_rms": None}

        rms_values: list[float] = []
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

            x_beam = stage_to_beam(x_stage, "y", install_angle)

            try:
                jitter_x, jitter_y = compute_jitter(
                    data.collection_result, meta.beampath, "BMAD"
                )
                jy = jitter_y[y_profile.profile_indices]
                x_beam = x_beam - jy
            except Exception:
                pass

            result = _fit_profile(x_beam, detector_values)
            if result["residuals"] is not None:
                rms_values.append(float(np.std(result["residuals"])))

        mean_rms = float(np.mean(rms_values)) if rms_values else None
        std_rms = float(np.std(rms_values)) if rms_values else None

        print(f"{wire}: mean vibration RMS = {mean_rms:.2f} ± {std_rms:.2f} ({len(rms_values)} scans)")
        return {
            "wire": wire,
            "n_scans": len(rms_values),
            "rms_values": rms_values,
            "mean_rms": mean_rms,
            "std_rms": std_rms,
        }
