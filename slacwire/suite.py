import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from slac_devices.reader import create_wire
from slac_measurements.wires.scan import WireBeamProfileMeasurement
from .registry import RunRegistry
from .view import WireScanView

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
        >>> suite.run(do_otf=True, do_step=False, save=True, save_plots=True)
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
        registry: Persistent run registry for audit trail
        save: If ``True``, write HDF5 data files after each scan.
        show: If ``True``, call ``fig.show()`` on each generated plot.
        save_plots: If ``True``, write PNG plot files after each scan.
    """
    wires: list = field(default_factory=lambda: ["WS28144"])
    devices: dict = field(default_factory=dict)
    beampath: str = "CU_HXR"
    detector: Optional[str] = None
    outdir: Path = Path("/home/physics/kabanaty/sandbox/ws_suite")
    plotdir: Path = Path("/home/physics/kabanaty/sandbox/ws_suite/plots/")
    profiles: tuple[str, ...] = ("x", "y", "u")
    save: bool = True
    show: bool = True
    save_plots: bool = True
    results: dict = field(default_factory=dict)
    registry: RunRegistry = field(default_factory=RunRegistry)
    view: WireScanView = field(init=False)

    def __post_init__(self):
        """Initialize the wire scan suite after dataclass construction.

        Creates device instances and ensures output directories exist.
        """
        self._build_devices()
        self.view = WireScanView()
        self.outdir.mkdir(parents=True, exist_ok=True)
        self.plotdir.mkdir(parents=True, exist_ok=True)

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
        rms_detector: str | None = None,
    ):
        """Run all configured wires in the requested scan mode."""
        for wire in self.wires:
            self.run_single(
                wire=wire,
                scan_mode=scan_mode,
                rms_detector=rms_detector,
            )

    def _run_device_scan(
        self,
        device,
        method: str,
        scan_fn,
        rms_detector: str | None,
        file_prefix: str,
    ):
        """Execute common scan flow for a single device and method."""
        # Resolve one detector choice for the entire scan.
        default_detector = device.metadata.default_detector
        selected_detector = (
            rms_detector if rms_detector is not None else default_detector
        )
        if ":" in selected_detector:
            selected_detector = selected_detector.split(":", 1)[0]

        try:
            data = scan_fn(device, rms_detector=selected_detector)
            self.results.setdefault(device.name, []).append(data)

            path = None
            if self.save:
                path = self.outdir / f"{file_prefix}_{device.name}_{self._stamp()}.h5"
                data.save_to_h5(path)

            plot_paths = self.view.render(
                data,
                wire=device.name,
                detector=selected_detector,
                profiles=self.profiles,
                file_prefix=file_prefix,
                plotdir=self.plotdir,
                stamp=self._stamp(),
                show=self.show,
                save=self.save_plots,
            )

            self.registry.log(
                method=method,
                wire=device.name,
                beampath=self.beampath,
                detector=selected_detector,
                filepath=path,
                plots=plot_paths,
            )
        except Exception as e:
            self.registry.log(
                method=method,
                wire=device.name,
                beampath=self.beampath,
                detector=selected_detector,
                status="error",
                error=str(e),
            )
            raise

    def _run_otf_device(self, device, rms_detector: str | None = None):
        """Execute a complete OTF scan with optional plotting and saving."""
        self._run_device_scan(
            device=device,
            method="otf",
            scan_fn=self._otf_scan,
            rms_detector=rms_detector,
            file_prefix="OTF",
        )

    def run_single(
        self,
        wire: str,
        scan_mode: str = "auto",
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
            self._run_otf_device(device, rms_detector=rms_detector)
            return
        if mode == "step":
            self._run_step_device(device, rms_detector=rms_detector)
            return

        raise ValueError(
            f"Invalid scan_mode '{scan_mode}'. Use 'auto', 'otf', or 'step'."
        )

    def _run_step_device(self, device, rms_detector: str | None = None):
        """Execute a complete step scan with optional plotting and saving."""
        self._run_device_scan(
            device=device,
            method="step",
            scan_fn=self._step_scan,
            rms_detector=rms_detector,
            file_prefix="Step",
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
