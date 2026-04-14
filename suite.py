import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from slac_devices.reader import create_wire
from slac_measurements.wires.scan import WireBeamProfileMeasurement
from view import WireScanView

logger = logging.getLogger("wire_scan_logger")


# Lookup table for wire name to area mapping.
WIRE_AREA_LOOKUP = {
    "WS01": "DL1",
    "WS02": "DL1",
    "WS03": "DL1",
    "WS04": "DL1",
    "WS11": "BC1",
    "WS12": "BC1",
    "WS13": "BC1",
    "WS27644": "L3",
    "WS28144": "L3",
    "WS28444": "L3",
    "WS28744": "L3",
    "WS0H04": "HTR",
    "WSDG01": "DIAG0",
    "WSC104": "COL1",
    "WSC106": "COL1",
    "WSC108": "COL1",
    "WSC110": "COL1",
    "WSEMIT2": "EMIT2",
    "WSBP2": "BYP",
    "WSBP3": "BYP",
    "WSBP4": "BYP",
    "WSSP1D": "SPD",
    "WS31": "LTUH",
    "WS32": "LTUH",
    "WS33": "LTUH",
    "WS34": "LTUH",
    "WS31B": "LTUS",
    "WS32B": "LTUS",
    "WS33B": "LTUS",
    "WS34B": "LTUS",
}


@dataclass
class WireScanSuite:
    """High-level orchestration layer for wire scanner beam profile measurements.

    Transforms low-level EPICS device controls (wire positioning, data collection,
    Gaussian fitting) from slac_devices into a complete scientific data
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
        ...     wires=["WS28144", "WS27644"],
        ...     beampath="CU_HXR",
        ...     detector="PMT29150"
        ... )
        >>> suite.run(do_otf=True, do_step=True, save=True, save_plots=True)
        # Executes scans, saves data/plots, updates run registry

    Attributes:
        wires: Wire names (e.g., "WS28144")
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
    wires: list = field(default_factory=lambda: ["WS28144"])
    devices: dict = field(default_factory=dict)
    beampath: str = "CU_HXR"
    detector: Optional[str] = None
    outdir: Path = Path("/home/physics/kabanaty/sandbox/ws_suite")
    plotdir: Path = Path("/home/physics/kabanaty/sandbox/ws_suite/plots/")
    profiles: tuple[str, ...] = ("x", "y", "u")
    results: dict = field(default_factory=dict)
    run_registry: list = field(default_factory=list)
    run_counter: int = 0
    view: WireScanView = field(init=False)

    def __post_init__(self):
        """Initialize the wire scan suite after dataclass construction.

        Creates device instances and ensures output directories exist.
        Loads existing run registry if available.
        """
        self._build_devices()
        self.view = WireScanView()
        self.outdir.mkdir(parents=True, exist_ok=True)
        self.plotdir.mkdir(parents=True, exist_ok=True)
        self._load_registry()
        self.run_counter = self._latest_run_id_from_registry()

    def __repr__(self) -> str:
        """Return a concise representation of suite state for debugging."""
        instantiated_wires = sorted(self.wires)
        result_counts = {
            wire: len(runs)
            for wire, runs in self.results.items()
            if runs
        }
        total_results = sum(result_counts.values())
        has_results = total_results > 0

        return (
            f"WireScanSuite(beampath={self.beampath!r}, "
            f"wire_list={instantiated_wires!r}, "
            f"has_results={has_results}, "
            f"result_counts={result_counts!r})"
        )

    def _build_devices(self):
        """Initialize all wire device instances based on configured wires."""
        self.devices = {wire: self._make_device(wire) for wire in self.wires}

    def latest_run(self, wire: str):
        """Retrieve the most recent run result for a given wire."""
        runs = self.results.get(wire, [])
        if not runs:
            msg = f"No results found for {wire}. Run it first."
            raise KeyError(msg)
        return runs[-1]

    def _latest_run_id_from_registry(self) -> int:
        """Return the highest run_id currently persisted in registry file."""
        registry_file = self._registry_path()
        if not registry_file.exists():
            return 0

        try:
            with open(registry_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if not isinstance(loaded, list):
                return 0

            max_run_id = 0
            for entry in loaded:
                if isinstance(entry, dict) and "run_id" in entry:
                    try:
                        run_id = int(entry["run_id"])
                    except (TypeError, ValueError):
                        continue
                    max_run_id = max(max_run_id, run_id)
            return max_run_id
        except (json.JSONDecodeError, OSError):
            return 0

    def _load_registry(self):
        """Load run registry from JSON file if it exists."""
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

    def _log_run(
        self,
        method: str,
        wire: str,
        detector=None,
        filepath=None,
        status="ok",
        error=None,
    ):
        """Create and register a run entry in the run registry."""
        def _save_registry():
            """Save run registry to JSON file atomically."""
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
        # Re-sync with persisted registry so concurrent/new instances
        # continue from the latest run id on disk.
        self.run_counter = max(
            self.run_counter,
            self._latest_run_id_from_registry(),
        )
        self.run_counter += 1
        entry = {
            "run_id": self.run_counter,
            "timestamp": self._stamp(),
            "method": method,  # "otf" or "step"
            "wire": wire,
            "beampath": self.beampath,
            "detector": detector,
            "filepath": str(filepath) if filepath else None,
            "plots": [],
            "status": status,  # "ok" or "error"
            "error": error,
        }
        self.run_registry.append(entry)
        _save_registry()
        return entry

    def _make_device(self, wire: str):
        """Create a wire device instance."""
        wire_name, area = self._resolve_wire_and_area(wire)
        return create_wire(area, wire_name)

    def _otf_scan(self, device, rms_detector: str | None = None):
        """Perform an on-the-fly (OTF) wire beam profile measurement."""
        measurement = WireBeamProfileMeasurement(
            beam_profile_device=device, beampath=self.beampath
        )
        # scan.py now orchestrates collection + analysis in one call.
        return measurement.measure(scan_mode="otf")

    def _registry_path(self) -> Path:
        """Get the path to the run registry JSON file."""
        base_dir = Path("/u1/lcls/physics/data/wire_scan")
        return base_dir / "ws_run_registry.json"

    def _resolve_wire_and_area(self, wire: str) -> tuple[str, str]:
        """Resolve a wire input to wire name and area."""
        wire = wire.strip()

        if not wire:
            raise ValueError("Wire name cannot be empty.")

        area = WIRE_AREA_LOOKUP.get(wire)
        if area is None:
            raise KeyError(
                f"No area mapping found for wire '{wire}'. Add it to "
                "WIRE_AREA_LOOKUP."
            )
        return wire, area

    def run_all(
        self,
        scan_mode: str = "auto",
        save: bool = True,
        show: bool = True,
        save_plots: bool = True,
        rms_detector: str | None = None,
    ):
        """Run all configured wires in the requested scan mode."""
        for wire in self.wires:
            self.run_single(
                wire=wire,
                scan_mode=scan_mode,
                save=save,
                show=show,
                save_plots=save_plots,
                rms_detector=rms_detector,
            )

    def _run_device_scan(
        self,
        device,
        method: str,
        scan_fn,
        rms_detector: str | None,
        file_prefix: str,
        save: bool,
        show: bool,
        save_plots: bool,
    ):
        """Execute common scan flow for a single device and method."""
        def _detector_for_device(device) -> str:
            """Return detector for a device using metadata.default_detector."""
            return device.metadata.default_detector

        def _handle_plot(
            fig, entry, name: str, show: bool, save_plots: bool
        ):
            """Helper function to show and/or save a plot figure."""
            if show:
                fig.show()
            if save_plots:
                png = self.view.save_fig(fig, name, self.plotdir, self._stamp())
                entry["plots"].append(str(png))

        def _save_run(data, filename: str):
            """Save measurement data to HDF5 file."""
            filepath = self.outdir / f"{filename}_{self._stamp()}.h5"
            data.save_to_h5(filepath)
            return filepath

        # Resolve one detector choice for the entire scan.
        default_detector = _detector_for_device(device)
        selected_detector = (
            rms_detector if rms_detector is not None else default_detector
        )
        if ":" in selected_detector:
            selected_detector = selected_detector.split(":", 1)[0]

        try:
            data = scan_fn(device, rms_detector=selected_detector)
            self.results.setdefault(device.name, []).append(data)
            path = (
                _save_run(data, f"{file_prefix}_{device.name}")
                if save
                else None
            )
            entry = self._log_run(
                method,
                device.name,
                detector=selected_detector,
                filepath=path,
            )

            fig_traj = self.view.plot_trajectory(
                data,
                device.name,
                selected_detector,
            )
            _handle_plot(
                fig_traj,
                entry,
                f"{file_prefix}_Trajectory_{device.name}",
                show,
                save_plots,
            )

            for profile in self.profiles:
                fig_prof = self.view.plot_profile(
                    data,
                    profile,
                    device.name,
                    selected_detector,
                )
                _handle_plot(
                    fig_prof,
                    entry,
                    f"{file_prefix}_Profile_{profile}_{device.name}",
                    show,
                    save_plots,
                )
        except Exception as e:
            self._log_run(
                method,
                device.name,
                detector=selected_detector,
                status="error",
                error=str(e),
            )
            raise

    def _run_otf_device(
        self,
        device,
        save,
        show,
        save_plots,
        rms_detector: str | None = None,
    ):
        """Execute a complete OTF scan with optional plotting and saving."""
        self._run_device_scan(
            device=device,
            method="otf",
            scan_fn=self._otf_scan,
            rms_detector=rms_detector,
            file_prefix="OTF",
            save=save,
            show=show,
            save_plots=save_plots,
        )

    def run_single(
        self,
        wire: str,
        scan_mode: str = "auto",
        save: bool = True,
        show: bool = True,
        save_plots: bool = True,
        rms_detector: str | None = None,
    ):
        """Run a single wire in the requested scan mode."""
        def _auto_scan_mode(device):
            """Determine scan mode from beam rate."""
            if device.beam_rate <= 120:
                return "step"
            if device.beam_rate <= 16600:
                return "otf"
            logger.error(
                f"Beam rate {device.beam_rate} is out of expected range "
                f"for both OTF and step scans. Skipping {device.name}."
            )
            return None

        def _get_device_for_wire(wire: str):
            """Get or lazily create a device for a wire name."""
            if wire not in self.devices:
                self.devices[wire] = self._make_device(wire)
            return self.devices[wire]

        wire_name, _ = self._resolve_wire_and_area(wire)
        device = _get_device_for_wire(wire_name)

        mode = scan_mode.lower()
        if mode == "auto":
            selected = _auto_scan_mode(device)
            if selected is None:
                return
            mode = selected

        if mode == "otf":
            self._run_otf_device(
                device,
                save,
                show,
                save_plots,
                rms_detector=rms_detector,
            )
            return
        if mode == "step":
            self._run_step_device(
                device,
                save,
                show,
                save_plots,
                rms_detector=rms_detector,
            )
            return

        raise ValueError(
            f"Invalid scan_mode '{scan_mode}'. Use 'auto', 'otf', or 'step'."
        )

    def _run_step_device(
        self,
        device,
        save,
        show,
        save_plots,
        rms_detector: str | None = None,
    ):
        """Execute a complete step scan with optional plotting and saving."""
        self._run_device_scan(
            device=device,
            method="step",
            scan_fn=self._step_scan,
            rms_detector=rms_detector,
            file_prefix="Step",
            save=save,
            show=show,
            save_plots=save_plots,
        )

    def _step_scan(self, device, rms_detector: str | None = None):
        """Perform a step wire beam profile measurement."""
        measurement = WireBeamProfileMeasurement(
            beam_profile_device=device, beampath=self.beampath
        )
        # scan.py now orchestrates collection + analysis in one call.
        return measurement.measure(scan_mode="step")

    def _stamp(self) -> str:
        """Generate a timestamp string for file naming."""
        return datetime.now().strftime("%Y%m%d_%H%M%S")
