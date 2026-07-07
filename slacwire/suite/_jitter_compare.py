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
        fit_amplitude = fp["amp"]
        fit_at_data = gaussian.curve(x=x_sorted, **fit_params)
        residuals = y_sorted - fit_at_data
    except Exception:
        fit_x = None
        fit_curve = None
        fit_sigma = None
        fit_amplitude = None
        residuals = None

    return {
        "x_sorted": x_sorted,
        "y_sorted": y_sorted,
        "fit_x": fit_x,
        "fit_curve": fit_curve,
        "fit_sigma": fit_sigma,
        "fit_amplitude": fit_amplitude,
        "residuals": residuals,
    }


def _highpass_residuals(x: np.ndarray, residuals: np.ndarray, cutoff: float = 0.005) -> np.ndarray:
    """Remove low-frequency content (beam drift) from residuals via FFT filtering.

    cutoff is in 1/µm — frequencies below this are zeroed.
    """
    n = len(residuals)
    x_uniform = np.linspace(x.min(), x.max(), n)
    resid_uniform = np.interp(x_uniform, x, residuals)

    step = (x.max() - x.min()) / (n - 1)
    freqs = np.fft.rfftfreq(n, d=step)
    spectrum = np.fft.rfft(resid_uniform)
    spectrum[freqs < cutoff] = 0
    filtered_uniform = np.fft.irfft(spectrum, n=n)
    return np.interp(x, x_uniform, filtered_uniform)


def _compute_fft(x: np.ndarray, residuals: np.ndarray, amplitude: float) -> tuple[np.ndarray, np.ndarray]:
    """Compute FFT power spectrum of normalized residuals on a uniform grid.

    Returns (freqs, power) arrays where power is in fractional units (residuals / amplitude).
    """
    n = len(residuals)
    x_uniform = np.linspace(x.min(), x.max(), n)
    resid_uniform = np.interp(x_uniform, x, residuals) / amplitude

    step = (x.max() - x.min()) / (n - 1)
    freqs = np.fft.rfftfreq(n, d=step)
    power = np.abs(np.fft.rfft(resid_uniform)) ** 2 / n
    return freqs, power


class JitterCompareMixin:
    """Compare Y profiles with and without jitter correction from stored data."""

    def _prepare_jitter_data(
        self,
        wire: str,
        date: str,
        profile: str = "y",
        limit: int | None = 10,
        detector: str | None = None,
    ) -> tuple[list[dict], Path]:
        """Load scans and compute jitter correction, fits, and FFT for each.

        Returns (records, plotdir) where each record contains all computed data
        needed by the individual plotting methods.
        """
        from slac_measurements.wires.coordinates import stage_to_beam
        from slac_measurements.wires.jitter_correction import compute_jitter

        scans = self.discover_scans(wire, date, limit)
        if not scans:
            print(f"No .h5 files found for {wire} on {date}")
            return [], Path()

        dt = datetime.strptime(date, "%Y-%m-%d")
        day_dir = Path(_BASE_DIR) / f"{dt:%Y}" / f"{dt:%m}" / f"{dt:%d}"
        plotdir = day_dir / "plots"
        plotdir.mkdir(parents=True, exist_ok=True)

        records: list[dict] = []
        for data in scans:
            meta = data.collection_result.metadata

            det = detector
            if det is None:
                det = getattr(meta, "rms_detector", None) or meta.default_detector

            if profile not in data.profiles:
                continue

            prof = data.profiles[profile]
            x_stage = np.asarray(prof.positions)
            detector_values = np.asarray(prof.detectors[det].values)
            install_angle = meta.install_angle

            x_beam_uncorrected = stage_to_beam(x_stage, profile, install_angle)

            try:
                jitter_x, jitter_y = compute_jitter(
                    data.collection_result, meta.beampath, "BMAD"
                )
                if profile == "x":
                    jitter_component = jitter_x[prof.profile_indices]
                elif profile == "y":
                    jitter_component = jitter_y[prof.profile_indices]
                else:
                    # u-wire at 45°: project jitter onto the diagonal axis
                    jx = jitter_x[prof.profile_indices]
                    jy = jitter_y[prof.profile_indices]
                    jitter_component = (jx + jy) / np.sqrt(2)

                x_beam_corrected = x_beam_uncorrected - jitter_component
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

            records.append({
                "wire": wire,
                "profile": profile,
                "detector": det,
                "stamp": stamp,
                "x_beam_uncorrected": x_beam_uncorrected,
                "x_beam_corrected": x_beam_corrected,
                "detector_values": detector_values,
                "jitter_rms": jitter_rms,
                "unc": unc,
                "corr": corr,
            })

        return records, plotdir

    def jitter_compare(
        self,
        wire: str,
        date: str,
        profile: str = "y",
        limit: int | None = 10,
        detector: str | None = None,
    ) -> list[Path]:
        """Side-by-side jitter-corrected and uncorrected profiles with Gaussian fits.

        Args:
            wire: Wire name to filter .h5 files by (e.g. "WS28444").
            date: ISO date string (YYYY-MM-DD) identifying the data directory.
            profile: Profile plane to analyze ("x", "y", or "u").
            limit: Maximum number of scans to plot (most recent first).
                Pass None to plot all matching scans.
            detector: Detector override. If None, uses each file's default.

        Returns:
            List of Paths to saved plot PNGs.
        """
        records, plotdir = self._prepare_jitter_data(wire, date, profile, limit, detector)
        if not records:
            return []

        plot_paths: list[Path] = []
        for rec in records:
            unc, corr = rec["unc"], rec["corr"]
            if rec["x_beam_corrected"] is None or corr is None:
                continue

            path = self.view.plot_jitter_compare(
                x_uncorrected=rec["x_beam_uncorrected"],
                x_corrected=rec["x_beam_corrected"],
                detector_values=rec["detector_values"],
                wire=rec["wire"],
                detector=rec["detector"],
                jitter_rms=rec["jitter_rms"],
                fit_x_uncorrected=unc["fit_x"],
                fit_curve_uncorrected=unc["fit_curve"],
                fit_sigma_uncorrected=unc["fit_sigma"],
                fit_x_corrected=corr["fit_x"],
                fit_curve_corrected=corr["fit_curve"],
                fit_sigma_corrected=corr["fit_sigma"],
                plotdir=plotdir,
                stamp=rec["stamp"],
                show=self.show,
                save=self.save_plots,
            )
            if path is not None:
                plot_paths.append(path)

        print(f"Plotted {len(plot_paths)} jitter comparison(s) for {wire} on {date}")
        return plot_paths

    def residual_compare(
        self,
        wire: str,
        date: str,
        profile: str = "y",
        limit: int | None = 10,
        detector: str | None = None,
    ) -> list[Path]:
        """Side-by-side uncorrected and jitter-corrected residual scatter plots.

        Args:
            wire: Wire name to filter .h5 files by (e.g. "WS28444").
            date: ISO date string (YYYY-MM-DD) identifying the data directory.
            profile: Profile plane to analyze ("x", "y", or "u").
            limit: Maximum number of scans to plot (most recent first).
                Pass None to plot all matching scans.
            detector: Detector override. If None, uses each file's default.

        Returns:
            List of Paths to saved plot PNGs.
        """
        records, plotdir = self._prepare_jitter_data(wire, date, profile, limit, detector)
        if not records:
            return []

        plot_paths: list[Path] = []
        for rec in records:
            unc, corr = rec["unc"], rec["corr"]
            if unc["residuals"] is None:
                continue

            path = self.view.plot_residual_compare(
                x_uncorrected=unc["x_sorted"],
                residuals_uncorrected=unc["residuals"],
                x_corrected=corr["x_sorted"] if corr else None,
                residuals_corrected=corr["residuals"] if corr else None,
                wire=rec["wire"],
                detector=rec["detector"],
                plotdir=plotdir,
                stamp=rec["stamp"],
                show=self.show,
                save=self.save_plots,
            )
            if path is not None:
                plot_paths.append(path)

        print(f"Plotted {len(plot_paths)} residual comparison(s) for {wire} on {date}")
        return plot_paths

    def fft_spectrum(
        self,
        wire: str,
        date: str,
        profile: str = "y",
        limit: int | None = 10,
        detector: str | None = None,
    ) -> list[Path]:
        """FFT power spectrum of fit residuals.

        Uses jitter-corrected residuals when available, otherwise uncorrected.

        Args:
            wire: Wire name to filter .h5 files by (e.g. "WS28444").
            date: ISO date string (YYYY-MM-DD) identifying the data directory.
            profile: Profile plane to analyze ("x", "y", or "u").
            limit: Maximum number of scans to plot (most recent first).
                Pass None to plot all matching scans.
            detector: Detector override. If None, uses each file's default.

        Returns:
            List of Paths to saved plot PNGs.
        """
        records, plotdir = self._prepare_jitter_data(wire, date, profile, limit, detector)
        if not records:
            return []

        plot_paths: list[Path] = []
        for rec in records:
            unc, corr = rec["unc"], rec["corr"]
            if unc["residuals"] is None:
                continue

            if corr is not None and corr["residuals"] is not None:
                freqs, power = _compute_fft(corr["x_sorted"], corr["residuals"], corr["fit_amplitude"])
            else:
                freqs, power = _compute_fft(unc["x_sorted"], unc["residuals"], unc["fit_amplitude"])

            path = self.view.plot_fft_spectrum(
                fft_freqs=freqs,
                fft_power=power,
                wire=rec["wire"],
                detector=rec["detector"],
                plotdir=plotdir,
                stamp=rec["stamp"],
                show=self.show,
                save=self.save_plots,
            )
            if path is not None:
                plot_paths.append(path)

        print(f"Plotted {len(plot_paths)} FFT spectrum(s) for {wire} on {date}")
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
            if result["residuals"] is not None and result["fit_amplitude"] is not None:
                filtered = _highpass_residuals(result["x_sorted"], result["residuals"])
                rms_values.append(round(float(np.std(filtered)) / result["fit_amplitude"], 4))

        mean_rms = round(float(np.mean(rms_values)), 4) if rms_values else None
        std_rms = round(float(np.std(rms_values)), 4) if rms_values else None

        if rms_values:
            print(f"{wire}: mean vibration RMS = {mean_rms:.4f} ± {std_rms:.4f} ({len(rms_values)} scans)")
        else:
            print(f"{wire}: no valid scans with successful fits")
        return {
            "wire": wire,
            "n_scans": len(rms_values),
            "rms_values": rms_values,
            "mean_rms": mean_rms,
            "std_rms": std_rms,
        }
