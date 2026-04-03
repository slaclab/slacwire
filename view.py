import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path


class WireScanView:
    """View component responsible for wire scan plotting."""

    def save_fig(self, fig, name: str, plotdir: Path, stamp: str):
        """Save matplotlib figure to PNG file."""
        path = plotdir / f"{name}_{stamp}.png"
        fig.savefig(path, dpi=150, bbox_inches="tight")
        return path

    def plot_trajectory(self, data, wire: str, detector: str):
        """Generate a trajectory plot for wire position and detector counts."""
        traj = np.asarray(data.collection_result.raw_data[wire])
        det = np.asarray(data.collection_result.raw_data[detector])
        x = np.arange(len(traj))

        fig, ax1 = plt.subplots()
        ax2 = ax1.twinx()

        ax1.plot(x, traj, label="Wire Position", color="blue")
        ax1.set_xlabel("Scan Point")
        ax1.set_ylabel("Wire Position (um)")

        ax2.plot(x, det, label=f"{detector} counts", color="orange")
        ax2.set_ylabel(f"{detector} counts")

        ax1.set_title(f"{wire} Motion Trajectory")

        fig.tight_layout()
        return fig

    def plot_profile(self, data, profile: str, wire: str, detector: str):
        """Generate a beam profile plot with fitted curve and parameters."""
        p = data.profiles[profile]
        x_stage = np.asarray(p.positions)
        y_meas = np.asarray(p.detectors[detector].values)

        fig, ax = plt.subplots()
        ax.plot(x_stage, y_meas, label="Measured", linestyle="dotted")
        ax.set_xlabel("Wire Position (stage, µm)")
        ax.set_ylabel(f"{detector} Counts")

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
        plt.text(
            0.95,
            0.15,
            params_text,
            transform=plt.gca().transAxes,
            va="top",
            ha="left",
            fontsize=10,
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
        )

        ax.legend()
        fig.tight_layout()
        return fig
