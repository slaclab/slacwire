import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path


class WireScanView:
    """View component responsible for wire scan plotting."""

    # ------------------------------------------------------------------
    # In-place draw methods: render into an existing figure (GUI canvases)
    # ------------------------------------------------------------------

    def draw_trajectory(self, fig, data, wire: str, detector: str):
        """Clear and redraw a trajectory plot into an existing figure.

        Intended for embedded GUI canvases where the figure already exists
        inside a widget layout. The caller is responsible for calling
        ``canvas.draw()`` after this returns.
        """
        traj = np.asarray(data.collection_result.raw_data[wire])
        det = np.asarray(data.collection_result.raw_data[detector])
        scan_points = np.arange(len(traj))
        detector_label = (
            "% Beam Loss" if detector == "TMITLOSS" else f"{detector} Counts"
        )

        fig.clf()
        ax1 = fig.add_subplot(1, 1, 1)
        ax2 = ax1.twinx()

        ax1.plot(scan_points, traj, label="Wire Position (µm)", color="#1f77b4")
        ax1.set_xlabel("Scan Point")
        ax1.set_ylabel("Wire Position (µm)", color="#1f77b4")
        ax1.tick_params(axis="y", labelcolor="#1f77b4")

        ax2.plot(scan_points, det, label=detector_label, color="#d95f02")
        ax2.set_ylabel(detector_label, color="#d95f02")
        ax2.tick_params(axis="y", labelcolor="#d95f02")

        ax1.set_title(f"{wire} Motion Trajectory")
        fig.tight_layout()

    def draw_profile(self, fig, data, wire: str, detector: str, profile: str):
        """Clear and redraw a beam profile plot into an existing figure.

        Intended for embedded GUI canvases. The caller is responsible for
        calling ``canvas.draw()`` after this returns.
        """
        p = data.profiles[profile]
        x_stage = np.asarray(p.positions)
        y_meas = np.asarray(p.detectors[detector].values)
        fit_result = data.fit_result[profile].detectors[detector]

        detector_label = (
            "% Beam Loss" if detector == "TMITLOSS" else f"{detector} Counts"
        )
        amp_off_units = "%" if detector == "TMITLOSS" else "Counts"
        scale = 1 if profile == "u" else np.cos(np.deg2rad(45))

        def stage_to_beam(x):
            return x * scale

        def beam_to_stage(x):
            return x / scale

        fig.clf()
        ax = fig.add_subplot(1, 1, 1)
        ax.plot(x_stage, y_meas, label="Measured", linestyle="dotted", color="blue")
        ax.set_xlabel("Wire Position (stage, µm)")
        ax.set_ylabel(detector_label)

        x_beam_fit = np.asarray(fit_result.positions)
        y_fit = np.asarray(fit_result.curve)
        ax.plot(beam_to_stage(x_beam_fit), y_fit, label="Fitted", linestyle="-")

        secax = ax.secondary_xaxis("top", functions=(stage_to_beam, beam_to_stage))
        secax.set_xlabel("Wire Position (beam, µm)")

        ax.set_title(f"{wire} {profile.upper()} Profile for {detector}")
        ax.legend(loc="upper right")
        ax.grid(True, which="both", linestyle="--", alpha=0.6)

        params_text = (
            f"Mean: {fit_result.mean:.1f} µm\n"
            f"Sigma: {fit_result.sigma:.1f} µm\n"
            f"Amplitude: {fit_result.amplitude:.1f} {amp_off_units}\n"
            f"Offset: {fit_result.offset:.1f} {amp_off_units}"
        )
        ax.text(
            0.95,
            0.15,
            params_text,
            transform=ax.transAxes,
            verticalalignment="bottom",
            horizontalalignment="right",
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
        )
        fig.tight_layout()

    # ------------------------------------------------------------------
    # Multi-view: up to 4 subplots per figure (trajectory + profiles)
    # ------------------------------------------------------------------

    def render_multi(
        self,
        data,
        wire: str,
        detector: str,
        profiles: tuple,
        file_prefix: str,
        plotdir: Path,
        stamp: str,
        show: bool = True,
        save: bool = True,
    ) -> Path | None:
        """Render trajectory and profiles into a single 2x2 figure.

        Layout: trajectory in top-left, then profiles (x, y, u) filling
        top-right, bottom-left, bottom-right. Unused panels are hidden.

        Returns:
            Path to saved PNG, or None if save is False.
        """
        available_profiles = [p for p in profiles if p in data.profiles]
        n_plots = 1 + len(available_profiles)
        ncols = 2
        nrows = 2 if n_plots > 2 else 1

        fig, axes = plt.subplots(nrows, ncols, figsize=(14, 5 * nrows))
        axes = np.atleast_2d(axes)

        self._subplot_trajectory(axes[0, 0], data, wire, detector)

        for i, profile in enumerate(available_profiles):
            row, col = divmod(i + 1, ncols)
            self._subplot_profile(axes[row, col], data, detector, profile)

        for i in range(n_plots, nrows * ncols):
            row, col = divmod(i, ncols)
            axes[row, col].set_visible(False)

        fig.suptitle(f"{wire} — {file_prefix} Scan ({detector})", fontsize=13)
        fig.tight_layout()

        path = None
        if save:
            path = self.save_fig(
                fig, f"{file_prefix}_Multi_{wire}", plotdir, stamp
            )
        if show:
            fig.show()
        return path

    def _subplot_trajectory(self, ax, data, wire: str, detector: str):
        """Draw trajectory into an existing axes."""
        traj = np.asarray(data.collection_result.raw_data[wire])
        det = np.asarray(data.collection_result.raw_data[detector])
        x = np.arange(len(traj))

        units = "% Loss" if detector == "TMITLOSS" else "Counts"

        ax.plot(x, traj, color="#1f77b4")
        ax.set_xlabel("Scan Point")
        ax.set_ylabel("Wire Position (µm)", color="#1f77b4")
        ax.tick_params(axis="y", labelcolor="#1f77b4")

        ax2 = ax.twinx()
        ax2.plot(x, det, color="#d95f02")
        ax2.set_ylabel(f"{detector} ({units})", color="#d95f02")
        ax2.tick_params(axis="y", labelcolor="#d95f02")

        ax.set_title(f"{wire} Trajectory")

    def _subplot_profile(self, ax, data, detector: str, profile: str):
        """Draw a profile fit into an existing axes."""
        p = data.profiles[profile]
        x_stage = np.asarray(p.positions)
        y_meas = np.asarray(p.detectors[detector].values)

        units = "% Loss" if detector == "TMITLOSS" else "Counts"
        scale = 1 if profile == "u" else np.cos(np.deg2rad(45))

        ax.plot(x_stage, y_meas, label="Measured", linestyle="dotted", color="blue")

        fit = data.fit_result[profile].detectors[detector]
        x_beam_fit = np.asarray(fit.positions)
        y_fit = np.asarray(fit.curve)
        ax.plot(x_beam_fit / scale, y_fit, label="Fitted", linestyle="-")

        ax.set_xlabel("Wire Position (µm)")
        ax.set_ylabel(f"{detector} ({units})")
        ax.set_title(f"{profile.upper()} Profile")
        ax.legend(loc="upper right", fontsize=8)

        params_text = (
            f"σ={fit.sigma:.1f}\n"
            f"µ={fit.mean:.1f}\n"
            f"A={fit.amplitude:.1f}"
        )
        ax.text(
            0.95, 0.55, params_text,
            transform=ax.transAxes, va="top", ha="right", fontsize=8,
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
        )

    # ------------------------------------------------------------------
    # Standalone figure methods: create and return a new figure (for saving)
    # ------------------------------------------------------------------

    def render(
        self,
        data,
        wire: str,
        detector: str,
        profiles: tuple,
        file_prefix: str,
        plotdir: Path,
        stamp: str,
        show: bool = True,
        save: bool = True,
    ) -> list:
        """Render trajectory and all available profile plots.

        Generates, optionally displays, and optionally saves all figures
        for a completed scan. This is the primary entry point for the
        Controller; individual plot methods remain available for direct use.

        Args:
            data: Scan result object with ``profiles`` and ``fit_result``.
            wire: Wire device name, used for plot titles and filenames.
            detector: Detector PV name, used for axis labels and filenames.
            profiles: Sequence of profile keys to attempt (e.g. ``("x", "y", "u")``).
            file_prefix: Filename prefix distinguishing scan type (``"OTF"`` / ``"Step"``).
            plotdir: Directory to write PNG files into.
            stamp: Timestamp string appended to each filename.
            show: If ``True``, call ``fig.show()`` on each figure.
            save: If ``True``, save each figure to ``plotdir`` as a PNG.

        Returns:
            List of :class:`~pathlib.Path` objects for every PNG written to disk.
        """
        plot_paths = []

        fig_traj = self.plot_trajectory(data, wire, detector)
        if show:
            fig_traj.show()
        if save:
            plot_paths.append(
                self.save_fig(fig_traj, f"{file_prefix}_Trajectory_{wire}", plotdir, stamp)
            )

        for profile in profiles:
            if profile not in data.profiles:
                continue
            fig_prof = self.plot_profile(data, profile, wire, detector)
            if show:
                fig_prof.show()
            if save:
                plot_paths.append(
                    self.save_fig(
                        fig_prof,
                        f"{file_prefix}_Profile_{profile}_{wire}",
                        plotdir,
                        stamp,
                    )
                )

        return plot_paths

    def save_fig(self, fig, name: str, plotdir: Path, stamp: str):
        """Save matplotlib figure to PNG file."""
        path = plotdir / f"{name}_{stamp}.png"
        self.save_fig_to_path(fig, path)
        return path

    def save_fig_to_path(self, fig, path: Path):
        """Save a figure to an explicit path with a white background.

        Forces both the figure and all axes patches to be opaque so that
        img2pdf (used by the logbook poster) does not encounter an alpha channel.
        """
        fig.patch.set_facecolor("white")
        for ax in fig.get_axes():
            ax.patch.set_facecolor("white")
        fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")

    def clear_figure(self, fig):
        """Clear all axes from a figure (e.g. when no data is available)."""
        fig.clf()

    def render_motion_test(
        self,
        data,
        wire: str,
        plotdir: Path,
        stamp: str,
        show: bool = True,
        save: bool = True,
    ) -> Path | None:
        """Render trajectory-only plot for a beam-less motion test.

        Args:
            data: WireMeasurementCollectionResult from run_motion_test.
            wire: Wire device name.
            plotdir: Directory to write PNG file into.
            stamp: Timestamp string for filename.
            show: If True, display the figure interactively.
            save: If True, save PNG to plotdir.

        Returns:
            Path to saved PNG, or None if save is False.
        """
        positions = np.asarray(data.raw_data[wire])
        scan_points = np.arange(len(positions))

        fig = plt.figure()
        ax = fig.add_subplot(1, 1, 1)
        ax.plot(scan_points, positions, color="#1f77b4")
        ax.set_xlabel("Scan Point")
        ax.set_ylabel("Wire Position (µm)")
        ax.set_title(f"{wire} Motion Test Trajectory")
        fig.tight_layout()

        path = None
        if save and plotdir is not None:
            path = self.save_fig(fig, f"MotionTest_Trajectory_{wire}", plotdir, stamp)
        if show:
            fig.show()
        return path

    def plot_trajectory(self, data, wire: str, detector: str):
        """Generate a trajectory plot for wire position and detector counts."""
        traj = np.asarray(data.collection_result.raw_data[wire])
        det = np.asarray(data.collection_result.raw_data[detector])
        x = np.arange(len(traj))

        fig = plt.figure()
        ax1 = fig.add_subplot(1, 1, 1)
        ax2 = ax1.twinx()

        ax1.plot(x, traj, label="Wire Position", color="blue")
        ax1.set_xlabel("Scan Point")
        ax1.set_ylabel("Wire Position (um)")

        units = "% Loss" if detector == "TMITLOSS" else "Counts"
        ax2.plot(x, det, label=f"{detector} {units}", color="orange")
        ax2.set_ylabel(f"{detector} ({units})")

        ax1.set_title(f"{wire} Motion Trajectory")

        fig.tight_layout()
        return fig

    def plot_profile(self, data, profile: str, wire: str, detector: str):
        """Generate a beam profile plot with fitted curve and parameters."""
        p = data.profiles[profile]
        x_stage = np.asarray(p.positions)
        y_meas = np.asarray(p.detectors[detector].values)

        fig = plt.figure()
        ax = fig.add_subplot(1, 1, 1)
        ax.plot(x_stage, y_meas, label="Measured", linestyle="dotted")
        ax.set_xlabel("Wire Position (stage, µm)")
        units = "% Loss" if detector == "TMITLOSS" else "Counts"
        ax.set_ylabel(f"{detector} ({units})")

        scale = 1 if profile == "u" else np.cos(np.deg2rad(45))

        def stage_to_beam(x):
            return x * scale

        def beam_to_stage(x):
            return x / scale

        x_beam_fit = np.asarray(
            data.fit_result[profile].detectors[detector].positions
        )
        y_fit = np.asarray(
            data.fit_result[profile].detectors[detector].curve
        )
        ax.plot(
            beam_to_stage(x_beam_fit),
            y_fit,
            label="Fitted",
            linestyle="-",
        )

        secax = ax.secondary_xaxis(
            "top",
            functions=(stage_to_beam, beam_to_stage),
        )
        secax.set_xlabel("Wire Position (beam, µm)")

        ax.set_title(f"{wire} {profile.upper()} Profile for {detector}")

        fp = data.fit_result[profile].detectors[detector]
        params_text = (
            f"Mean: {fp.mean:.1f} um\n"
            f"Sigma: {fp.sigma:.1f} um\n"
            f"Amp: {fp.amplitude:.1f} {units}\n"
            f"Offset: {fp.offset:.1f} {units}"
        )
        ax.text(
            0.95,
            0.15,
            params_text,
            transform=ax.transAxes,
            va="top",
            ha="left",
            fontsize=10,
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
        )

        ax.legend()
        fig.tight_layout()
        return fig

    # ------------------------------------------------------------------
    # Jitter comparison: corrected vs uncorrected Y profile overlay
    # ------------------------------------------------------------------

    def plot_jitter_compare(
        self,
        x_uncorrected: np.ndarray,
        x_corrected: np.ndarray,
        detector_values: np.ndarray,
        wire: str,
        detector: str,
        jitter_rms: tuple[float, float] | None,
        plotdir: Path,
        stamp: str,
        fit_x_uncorrected: np.ndarray | None = None,
        fit_curve_uncorrected: np.ndarray | None = None,
        fit_sigma_uncorrected: float | None = None,
        fit_x_corrected: np.ndarray | None = None,
        fit_curve_corrected: np.ndarray | None = None,
        fit_sigma_corrected: float | None = None,
        show: bool = True,
        save: bool = True,
    ) -> Path | None:
        """Side-by-side Y profiles: uncorrected (left) and jitter-corrected (right)."""
        units = "% Loss" if detector == "TMITLOSS" else "Counts"

        fig, (ax_left, ax_right) = plt.subplots(1, 2, figsize=(12, 5), sharey=True)

        # --- Uncorrected (left) ---
        sort_idx_unc = np.argsort(x_uncorrected)
        x_unc_sorted = x_uncorrected[sort_idx_unc]
        det_unc_sorted = detector_values[sort_idx_unc]

        if fit_x_uncorrected is not None:
            fit_min, fit_max = fit_x_uncorrected.min(), fit_x_uncorrected.max()
            in_fit = (x_unc_sorted >= fit_min) & (x_unc_sorted <= fit_max)
            yerr = np.where(in_fit, np.sqrt(np.abs(det_unc_sorted)), 0)
            ax_left.errorbar(
                x_unc_sorted, det_unc_sorted, yerr=yerr,
                fmt="o", markersize=3, color="#d62728",
                ecolor="#d62728", elinewidth=0.8, capsize=2,
                label="Data",
            )
        else:
            ax_left.plot(x_unc_sorted, det_unc_sorted, color="#d62728", label="Data")

        if fit_x_uncorrected is not None and fit_curve_uncorrected is not None:
            sigma_label = f"Fit (σ = {fit_sigma_uncorrected:.1f} µm)" if fit_sigma_uncorrected else "Fit"
            ax_left.plot(fit_x_uncorrected, fit_curve_uncorrected, color="#ff7f0e", linewidth=2, label=sigma_label)

        ax_left.set_xlabel("Beam Position (µm)")
        ax_left.set_ylabel(f"{detector} ({units})")
        ax_left.set_title("Uncorrected")
        ax_left.grid(True, which="both", linestyle="--", alpha=0.6)
        ax_left.legend(loc="upper right")

        # --- Corrected (right) ---
        sort_idx = np.argsort(x_corrected)
        x_corr_sorted = x_corrected[sort_idx]
        det_sorted = detector_values[sort_idx]

        if fit_x_corrected is not None:
            fit_min, fit_max = fit_x_corrected.min(), fit_x_corrected.max()
            in_fit = (x_corr_sorted >= fit_min) & (x_corr_sorted <= fit_max)
            yerr = np.where(in_fit, np.sqrt(np.abs(det_sorted)), 0)
            ax_right.errorbar(
                x_corr_sorted, det_sorted, yerr=yerr,
                fmt="o", markersize=3, color="#1f77b4",
                ecolor="#1f77b4", elinewidth=0.8, capsize=2,
                label="Data",
            )
        else:
            ax_right.plot(x_corr_sorted, det_sorted, color="#1f77b4", label="Data")

        if fit_x_corrected is not None and fit_curve_corrected is not None:
            sigma_label = f"Fit (σ = {fit_sigma_corrected:.1f} µm)" if fit_sigma_corrected else "Fit"
            ax_right.plot(fit_x_corrected, fit_curve_corrected, color="#ff7f0e", linewidth=2, label=sigma_label)

        ax_right.set_xlabel("Beam Position (µm)")
        ax_right.set_title("Jitter-corrected")
        ax_right.grid(True, which="both", linestyle="--", alpha=0.6)
        ax_right.legend(loc="upper right")

        rms_str = ""
        if jitter_rms is not None:
            rms_str = f"  —  jitter RMS: ({jitter_rms[0]:.1f}, {jitter_rms[1]:.1f}) µm"
        fig.suptitle(f"{wire} Y Profile ({stamp}){rms_str}", fontsize=12)
        fig.tight_layout()

        path = None
        if save:
            path = self.save_fig(fig, f"JitterCompare_{wire}", plotdir, stamp)
        if show:
            fig.show()
        return path

    # ------------------------------------------------------------------

    def plot_vibration_residuals(
        self,
        x_uncorrected: np.ndarray,
        residuals_uncorrected: np.ndarray,
        x_corrected: np.ndarray | None,
        residuals_corrected: np.ndarray | None,
        fft_freqs: np.ndarray,
        fft_power: np.ndarray,
        wire: str,
        detector: str,
        plotdir: Path,
        stamp: str,
        show: bool = True,
        save: bool = True,
    ) -> Path | None:
        """Side-by-side residual (data - fit) plots with FFT power spectrum."""
        units = "% Loss" if detector == "TMITLOSS" else "Counts"
        has_corrected = x_corrected is not None and residuals_corrected is not None
        ncols = 3 if has_corrected else 2

        fig, axes = plt.subplots(1, ncols, figsize=(6 * ncols, 5), squeeze=False)
        ax_left = axes[0, 0]

        ax_left.scatter(x_uncorrected, residuals_uncorrected, s=10, color="#d62728")
        ax_left.axhline(0, color="black", linewidth=0.8, linestyle="--")
        ax_left.set_xlabel("Beam Position (µm)")
        ax_left.set_ylabel(f"Residual ({units})")
        ax_left.set_title("Uncorrected Residuals")
        ax_left.grid(True, which="both", linestyle="--", alpha=0.6)

        if has_corrected:
            ax_mid = axes[0, 1]
            ax_mid.scatter(x_corrected, residuals_corrected, s=10, color="#1f77b4")
            ax_mid.axhline(0, color="black", linewidth=0.8, linestyle="--")
            ax_mid.set_xlabel("Beam Position (µm)")
            ax_mid.set_title("Jitter-corrected Residuals")
            ax_mid.grid(True, which="both", linestyle="--", alpha=0.6)

        ax_fft = axes[0, -1]
        ax_fft.plot(fft_freqs[1:], fft_power[1:], color="#2ca02c", linewidth=1)
        ax_fft.set_xlabel("Spatial Frequency (1/µm)")
        ax_fft.set_ylabel("Power")
        ax_fft.set_title("FFT Power Spectrum")
        ax_fft.grid(True, which="both", linestyle="--", alpha=0.6)

        fig.suptitle(f"{wire} Vibration Residuals ({stamp})", fontsize=12)
        fig.tight_layout()

        path = None
        if save:
            path = self.save_fig(fig, f"Vibration_{wire}", plotdir, stamp)
        if show:
            fig.show()
        return path

    # ------------------------------------------------------------------
    # Residual comparison (no FFT)
    # ------------------------------------------------------------------

    def plot_residual_compare(
        self,
        x_uncorrected: np.ndarray,
        residuals_uncorrected: np.ndarray,
        x_corrected: np.ndarray | None,
        residuals_corrected: np.ndarray | None,
        wire: str,
        detector: str,
        plotdir: Path,
        stamp: str,
        show: bool = True,
        save: bool = True,
    ) -> Path | None:
        """Side-by-side residual (data - fit) scatter plots."""
        units = "% Loss" if detector == "TMITLOSS" else "Counts"
        has_corrected = x_corrected is not None and residuals_corrected is not None
        ncols = 2 if has_corrected else 1

        fig, axes = plt.subplots(1, ncols, figsize=(6 * ncols, 5), squeeze=False)
        ax_left = axes[0, 0]

        ax_left.scatter(x_uncorrected, residuals_uncorrected, s=10, color="#d62728")
        ax_left.axhline(0, color="black", linewidth=0.8, linestyle="--")
        ax_left.set_xlabel("Beam Position (µm)")
        ax_left.set_ylabel(f"Residual ({units})")
        ax_left.set_title("Uncorrected Residuals")
        ax_left.grid(True, which="both", linestyle="--", alpha=0.6)

        if has_corrected:
            ax_right = axes[0, 1]
            ax_right.scatter(x_corrected, residuals_corrected, s=10, color="#1f77b4")
            ax_right.axhline(0, color="black", linewidth=0.8, linestyle="--")
            ax_right.set_xlabel("Beam Position (µm)")
            ax_right.set_ylabel(f"Residual ({units})")
            ax_right.set_title("Jitter-corrected Residuals")
            ax_right.grid(True, which="both", linestyle="--", alpha=0.6)

        fig.suptitle(f"{wire} Residual Comparison ({stamp})", fontsize=12)
        fig.tight_layout()

        path = None
        if save:
            path = self.save_fig(fig, f"Residuals_{wire}", plotdir, stamp)
        if show:
            fig.show()
        return path

    # ------------------------------------------------------------------
    # FFT power spectrum (standalone)
    # ------------------------------------------------------------------

    def plot_fft_spectrum(
        self,
        fft_freqs: np.ndarray,
        fft_power: np.ndarray,
        wire: str,
        detector: str,
        plotdir: Path,
        stamp: str,
        show: bool = True,
        save: bool = True,
    ) -> Path | None:
        """Standalone FFT power spectrum of fit residuals."""
        fig = plt.figure(figsize=(8, 5))
        ax = fig.add_subplot(1, 1, 1)

        ax.plot(fft_freqs[1:], fft_power[1:], color="#2ca02c", linewidth=1)
        ax.set_xlabel("Spatial Frequency (1/µm)")
        ax.set_ylabel("Power")
        ax.set_title(f"{wire} FFT Power Spectrum ({detector})")
        ax.grid(True, which="both", linestyle="--", alpha=0.6)

        fig.tight_layout()

        path = None
        if save:
            path = self.save_fig(fig, f"FFT_{wire}", plotdir, stamp)
        if show:
            fig.show()
        return path

    def plot_fft_overlay(
        self,
        spectra: list[tuple[np.ndarray, np.ndarray, str]],
        wire: str,
        detector: str,
        plotdir: Path,
        show: bool = True,
        save: bool = True,
    ) -> Path | None:
        """All FFT spectra for a wire overlaid on one plot."""
        fig = plt.figure(figsize=(10, 6))
        ax = fig.add_subplot(1, 1, 1)

        for freqs, power, stamp in spectra:
            ax.plot(freqs[1:], power[1:], linewidth=0.8, alpha=0.7, label=stamp)

        ax.set_xlabel("Spatial Frequency (1/µm)")
        ax.set_ylabel("Power")
        ax.set_title(f"{wire} FFT Power Spectra ({detector}) — {len(spectra)} scans")
        ax.grid(True, which="both", linestyle="--", alpha=0.6)
        ax.legend(fontsize=7)

        fig.tight_layout()

        path = None
        if save:
            stamp = spectra[0][2]
            path = self.save_fig(fig, f"FFT_overlay_{wire}", plotdir, stamp)
        if show:
            fig.show()
        return path
