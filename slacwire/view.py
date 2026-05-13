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
            f"Amp: {fp.amplitude:.1f} %\n"
            f"Offset: {fp.offset:.1f} %"
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
