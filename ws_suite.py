import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from lcls_tools.common.devices.reader import create_wire
from lcls_tools.common.measurements.ws_collection import (
    WireMeasurementCollection,
)
from lcls_tools.common.measurements.ws_analysis import (
    WireMeasurementAnalysis,
)

logger = logging.getLogger("wire_scan_logger")


@dataclass
class WireScanSuite:
    """High-level orchestration layer for wire scanner beam profile measurements.

    Transforms low-level EPICS device controls (wire positioning, data collection,
    Gaussian fitting) from lcls_tools.common into a complete scientific data
    acquisition system with human-readable results, automated plotting, and
    persistent run tracking.

    This class bridges the gap between the raw measurement/analysis primitives
    (WireMeasurementCollection, WireMeasurementAnalysis, create_wire) and
    operational requirements by providing:

    - Batch processing: Run multiple wires and scan types in sequence
    - Data provenance: Persistent JSON registry of all runs with metadata
    - Automated visualization: Publication-ready trajectory and profile plots
    - Structured file management: Timestamped HDF5 files and PNG plots
    - Simplified API: Single method calls replace multi-step workflows

    Typical usage:
        >>> suite = WireScanSuite(
        ...     wires=["WS28144:L3", "WS27644:L3"],
        ...     beampath="CU_HXR",
        ...     detector="PMT29150"
        ... )
        >>> suite.run(do_otf=True, do_step=True, save=True, save_plots=True)
        # Executes scans, saves data/plots, updates run registry

    Attributes:
        wires: Wire identifiers in "NAME:AREA" format (e.g., "WS28144:L3")
        devices: Cached wire device instances created via create_wire()
        beampath: Accelerator beampath identifier (e.g., "CU_HXR", "SC_BSYD")
        detector: Primary detector for measurements (e.g., "PMT29150")
        outdir: Output directory for HDF5 data files
        plotdir: Output directory for PNG plot files
        profiles: Profile dimensions to measure ("x", "y", "u")
        results: Dict storing measurement results keyed by wire name
        run_registry: List of run metadata entries for audit trail
        run_counter: Incremental run ID counter
    """
    wires: list = field(default_factory=lambda: ["WS28144:L3"])
    devices: dict = field(default_factory=dict)
    beampath: str = "CU_HXR"
    detector: str = "PMT29150"
    outdir: Path = Path("/home/physics/kabanaty/sandbox/ws_suite")
    plotdir: Path = Path("/home/physics/kabanaty/sandbox/ws_suite/plots/")
    profiles: tuple[str, ...] = ("x", "y", "u")
    results: dict = field(default_factory=dict)
    run_registry: list = field(default_factory=list)
    run_counter: int = 0

    def __post_init__(self):
        """Initialize the wire scan suite after dataclass construction.

        Creates device instances and ensures output directories exist.
        Loads existing run registry if available.
        """
        self.build_devices()
        self.outdir.mkdir(parents=True, exist_ok=True)
        self.plotdir.mkdir(parents=True, exist_ok=True)
        self._load_registry()
        self.run_counter = (
            max((entry["run_id"] for entry in self.run_registry), default=0)
        )

    def __repr__(self) -> str:
        """Return a concise representation of suite state for debugging.

        Includes instantiated wires, active beampath, and whether results
        have been collected.
        """
        instantiated_wires = sorted(self.devices.keys())
        result_counts = {
            wire: len(runs)
            for wire, runs in self.results.items()
            if runs
        }
        total_results = sum(result_counts.values())
        has_results = total_results > 0

        return (
            f"WireScanSuite(beampath={self.beampath!r}, "
            f"instantiated_wires={instantiated_wires!r}, "
            f"has_results={has_results}, "
            f"result_counts={result_counts!r})"
        )

    def _stamp(self) -> str:
        """Generate a timestamp string for file naming.

        Returns:
            str: Timestamp in format YYYYMMDD_HHMMSS
        """
        return datetime.now().strftime("%Y%m%d_%H%M%S")

    def _registry_path(self) -> Path:
        """Get the path to the run registry JSON file.

        Returns:
            Path: Path to ws_run_registry.json in base scan directory
        """
        base_dir = Path("/u1/lcls/physics/data/wire_scan")
        return base_dir / "ws_run_registry.json"

    def _load_registry(self):
        """Load run registry from JSON file if it exists.

        Populates self.run_registry with existing entries.
        If file doesn't exist or is invalid, starts with empty registry.
        """
        registry_file = self._registry_path()
        if not registry_file.exists():
            return

        try:
            with open(registry_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, list):
                    self.run_registry = loaded
        except (json.JSONDecodeError, OSError) as e:
            # Log error but continue with empty registry
            logger.warning(
                f"Could not load registry from {registry_file}: {e}"
            )

    def _save_registry(self):
        """Save run registry to JSON file atomically.

        Writes to a temporary file first, then renames to prevent corruption.
        """
        registry_file = self._registry_path()
        registry_file.parent.mkdir(parents=True, exist_ok=True)
        temp_file = registry_file.parent / (registry_file.name + ".tmp")

        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.run_registry, f, indent=2)
            temp_file.replace(registry_file)
        except OSError as e:
            logger.warning(
                f"Could not save registry to {registry_file}: {e}"
            )
            if temp_file.exists():
                temp_file.unlink()

    def _make_device(self, wire: str):
        """Create a wire device instance.

        Args:
            wire: Wire identifier string in format "WIRE_NAME:AREA"
                (e.g., "WS28144:L3")

        Returns:
            Wire device instance for the specified area and wire
        """
        wire_name, area = wire.split(":")
        return create_wire(area, wire_name)

    def _log_run(
        self,
        method: str,
        wire: str,
        filepath=None,
        status="ok",
        error=None,
    ):
        """Create and register a run entry in the run registry.

        Args:
            method: Measurement method ("otf" or "step")
            wire: Wire name (without area)
            filepath: Optional path to saved data file
            status: Run status ("ok" or "error")
            error: Optional error message

        Returns:
            dict: Run entry with run_id, timestamp, and metadata
        """
        self.run_counter += 1
        entry = {
            "run_id": self.run_counter,
            "timestamp": self._stamp(),
            "method": method,  # "otf" or "step"
            "wire": wire,
            "beampath": self.beampath,
            "detector": self.detector,
            "filepath": str(filepath) if filepath else None,
            "plots": [],
            "status": status,  # "ok" or "error"
            "error": error,
        }
        self.run_registry.append(entry)
        self._save_registry()
        return entry

    def _latest_run(self, wire: str):
        """Retrieve the most recent run result for a given wire.

        Args:
            wire: Wire identifier

        Returns:
            Latest measurement result data

        Raises:
            KeyError: If no results exist for the specified wire
        """
        runs = self.results.get(wire, [])
        if not runs:
            msg = f"No results found for {wire}. Run it first."
            raise KeyError(msg)
        return runs[-1]

    def build_devices(self):
        """Initialize all wire device instances based on configured wires."""
        self.devices = {wire: self._make_device(wire) for wire in self.wires}

    def otf_scan(self, device):
        """Perform an on-the-fly (OTF) wire beam profile measurement.

        Args:
            device: Wire device instance

        Returns:
            Measurement result object containing profile data
        """
        collection = WireMeasurementCollection(
            beam_profile_device=device, beampath=self.beampath
        )
        raw_data = collection.measure(scan_type="on_the_fly")
        analysis = WireMeasurementAnalysis(collection_result=raw_data)
        return analysis.analyze()

    def step_scan(self, device):
        """Perform a step wire beam profile measurement.

        Args:
            device: Wire device instance

        Returns:
            Measurement result object containing profile data
        """
        collection = WireMeasurementCollection(
            beam_profile_device=device, beampath=self.beampath
        )
        raw_data = collection.measure(scan_type="step")
        analysis = WireMeasurementAnalysis(collection_result=raw_data)
        return analysis.analyze()

    def save_run(self, data, filename: str):
        """Save measurement data to HDF5 file.

        Args:
            data: Measurement result data to save
            filename: Base filename (timestamp appended automatically)

        Returns:
            Path: Path to saved file
        """
        filepath = self.outdir / f"{filename}_{self._stamp()}.h5"
        data.save_to_h5(filepath)
        return filepath

    def save_fig(self, fig, name: str):
        """Save matplotlib figure to PNG file.

        Args:
            fig: Matplotlib figure object
            name: Base filename (timestamp appended automatically)

        Returns:
            Path: Path to saved PNG file
        """
        path = self.plotdir / f"{name}_{self._stamp()}.png"
        fig.savefig(path, dpi=150, bbox_inches="tight")
        return path

    def plot_trajectory(self, data, wire: str):
        """Generate a trajectory plot showing wire position and detector
           counts.

        Creates a dual-axis plot with wire position on left axis and detector
        counts on right axis.

        Args:
            data: Measurement result object
            wire: Wire identifier

        Returns:
            matplotlib.figure.Figure: Trajectory plot figure
        """
        traj = np.asarray(data.collection_result.raw_data[wire])
        det = np.asarray(data.collection_result.raw_data[self.detector])
        x = np.arange(len(traj))

        fig, ax1 = plt.subplots()
        ax2 = ax1.twinx()

        ax1.plot(x, traj, label="Wire Position", color="blue")
        ax1.set_xlabel("Scan Point")
        ax1.set_ylabel("Wire Position (um)")

        ax2.plot(x, det, label=f"{self.detector} counts", color="orange")
        ax2.set_ylabel(f"{self.detector} counts")

        ax1.set_title(f"{wire} Motion Trajectory")

        fig.tight_layout()
        return fig

    def plot_profile(self, data, profile: str, wire: str):
        """Generate a beam profile plot with fitted curve and parameters.

        Creates a plot with measured data, fitted curve, and fit parameters
        (mean, sigma, amplitude, offset) displayed as text.

        Args:
            data: Measurement result object
            profile: Profile dimension ("x", "y", or "u")
            wire: Wire identifier

        Returns:
            matplotlib.figure.Figure: Profile plot figure
        """
        p = data.profiles[profile]
        x_stage = np.asarray(p.positions)
        y_meas = np.asarray(p.detectors[self.detector].values)

        fig, ax = plt.subplots()
        ax.plot(x_stage, y_meas, label="Measured", linestyle="dotted")
        ax.set_xlabel("Wire Position (stage, µm)")
        ax.set_ylabel(f"{self.detector} Counts")

        scale = 1 if profile == "u" else np.cos(np.deg2rad(45))

        def stage_to_beam(x):
            return x * scale

        def beam_to_stage(x):
            return x / scale

        x_beam_fit = np.asarray(
            data.fit_result[profile].detectors[self.detector].positions
        )
        y_fit = np.asarray(
            data.fit_result[profile].detectors[self.detector].curve
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

        ax.set_title(f"{wire} {profile.upper()} Profile for {self.detector}")

        fp = data.fit_result[profile].detectors[self.detector]
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

    def _handle_plot(
        self, fig, entry, name: str, show: bool, save_plots: bool
    ):
        """Helper function to show and/or save a plot figure.

        Args:
            fig: matplotlib figure to process
            entry: run registry entry to append plot paths to
            name: base filename for saving (timestamp added automatically)
            show: whether to display the figure
            save_plots: whether to save the figure
        """
        if show:
            fig.show()
        if save_plots:
            png = self.save_fig(fig, name)
            entry["plots"].append(str(png))

    def _run_otf(self, device, wire, save, show, save_plots):
        """Execute a complete OTF scan with optional plotting and saving.

        Performs OTF scan, saves data if requested, generates and displays
        trajectory and profile plots, and logs the run.

        Args:
            device: Wire device instance
            wire: Wire name (without area)
            save: Whether to save measurement data
            show: Whether to display plots
            save_plots: Whether to save plots as PNG files
        """
        try:
            otf_data = self.otf_scan(device)
            self.results.setdefault(wire, []).append(otf_data)
            path = (
                self.save_run(otf_data, f"OTF_{wire}") if save else None
            )
            entry = self._log_run("otf", wire, filepath=path)

            fig_traj = self.plot_trajectory(otf_data, wire)
            self._handle_plot(
                fig_traj, entry, f"OTF_Trajectory_{wire}", show, save_plots
            )

            for profile in self.profiles:
                fig_prof = self.plot_profile(otf_data, profile, wire)
                self._handle_plot(
                    fig_prof,
                    entry,
                    f"OTF_Profile_{profile}_{wire}",
                    show,
                    save_plots,
                )
        except Exception as e:
            self._log_run(
                "otf", wire, status="error", error=str(e)
            )
            raise

    def _run_step(self, device, wire, save, show, save_plots):
        """Execute a complete step scan with optional plotting and saving.

        Performs step scan, saves data if requested, generates and displays
        trajectory and profile plots, and logs the run.

        Args:
            device: Wire device instance
            wire: Wire name (without area)
            save: Whether to save measurement data
            show: Whether to display plots
            save_plots: Whether to save plots as PNG files
        """
        try:
            step_data = self.step_scan(device)
            self.results.setdefault(wire, []).append(step_data)
            path = (
                self.save_run(step_data, f"Step_{wire}") if save else None
            )
            entry = self._log_run("step", wire, filepath=path)

            fig_traj = self.plot_trajectory(step_data, wire)
            self._handle_plot(
                fig_traj, entry, f"Step_Trajectory_{wire}", show, save_plots
            )

            for profile in self.profiles:
                fig_prof = self.plot_profile(step_data, profile, wire)
                self._handle_plot(
                    fig_prof,
                    entry,
                    f"Step_Profile_{profile}_{wire}",
                    show,
                    save_plots,
                )
        except Exception as e:
            self._log_run(
                "step", wire, status="error", error=str(e)
            )
            raise

    def run(
        self,
        do_otf: bool = False,
        do_step: bool = False,
        save: bool = True,
        show: bool = True,
        save_plots: bool = True,
    ):
        """Execute wire scans for all configured wires.

        Performs OTF and/or step scans for each wire with optional data saving
        and plot display.

        Args:
            do_otf: Whether to run OTF scans
            do_step: Whether to run step scans
            save: Whether to save measurement data
            show: Whether to display plots
            save_plots: Whether to save plots as PNG files
        """
        for wire in self.wires:
            wire_name = wire.split(":")[0]
            device = self.devices[wire]
            if not do_otf and not do_step:
                logger.warning("No scan type selected."
                               "Selecting scan method based on beam rate.")
                if device.beam_rate <= 120:
                    do_step = True
                elif device.beam_rate > 120 and device.beam_rate <= 16600:
                    do_otf = True
                else:
                    logger.error(f"Beam rate {device.beam_rate} is out of"
                                 f"expected range for both OTF and step scans."
                                 f"Skipping {wire_name}.")
            if do_otf:
                self._run_otf(device, wire_name, save, show, save_plots)
            if do_step:
                self._run_step(device, wire_name, save, show, save_plots)
