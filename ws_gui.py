import importlib
import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml
from pydm import Display
from PyQt5.QtCore import QThread, pyqtSignal
from qtpy.QtWidgets import QFileDialog, QVBoxLayout, QWidget

from widgets.measurement import MeasurementWidget, extract_measurement_data
from widgets.navigation import NavigationWidget
from widgets.plots import PlotWidget
from widgets.text_logger import attach_logger_to_widget
from ws_suite import WireScanSuite


class WireScanSuiteThread(QThread):
    scan_complete = pyqtSignal(str, str, object, dict)
    scan_failed = pyqtSignal(str, str)

    def __init__(
        self,
        suite: WireScanSuite,
        wire_identifier: str,
        beampath: str,
        detector: str,
        save_data: bool = True,
    ):
        super().__init__()
        self.suite = suite
        self.wire_identifier = wire_identifier
        self.beampath = beampath
        self.detector = detector
        self.save_data = save_data

    def run(self):
        try:
            wire_name, _ = self.wire_identifier.split(":")
            self.suite.beampath = self.beampath
            self.suite.detector = self.detector

            if self.wire_identifier not in self.suite.devices:
                self.suite.wires = [self.wire_identifier]
                self.suite.build_devices()

            device = self.suite.devices[self.wire_identifier]
            beam_rate = device.beam_rate

            if beam_rate <= 120:
                method = "step"
                data = self.suite.step_scan(device)
            elif beam_rate > 16000:
                raise ValueError(
                    (
                        f"Beam rate {beam_rate} is too high "
                        "for on-the-fly scanning."
                    )
                )
            else:
                method = "otf"
                data = self.suite.otf_scan(device)

            self.suite.results.setdefault(wire_name, []).append(data)
            save_path = None
            if self.save_data:
                save_path = self.suite.save_run(
                    data,
                    f"{method.upper()}_{wire_name}",
                )
            entry = self.suite._log_run(method, wire_name, filepath=save_path)
            self.scan_complete.emit(wire_name, method, data, entry)
        except Exception as exc:
            self.scan_failed.emit(self.wire_identifier, str(exc))


class WireScanSuiteGUI(Display):
    dataChanged = pyqtSignal()

    def __init__(self, parent=None, args=None, macros=None):
        self.base_path = Path(__file__).resolve().parent
        super().__init__(parent=parent, args=args, macros=macros)
        yaml_data = self._load_yaml()
        area_to_wires = extract_measurement_data(yaml_data)

        self.nav = NavigationWidget(yaml_data)
        self.measurement = MeasurementWidget(
            area_to_wires,
            create_wire_fn=self._create_wire,
        )
        self.plots = PlotWidget()

        self.suite = self._build_suite()
        self.current_runs = {}
        self.loaded_results = {}

        self.nav.areaChanged.connect(self.measurement.update_area)
        self.nav.beampathChanged.connect(self._on_beampath_changed)
        self.measurement.wireChanged.connect(self.update_parameters)
        self.measurement.wireChanged.connect(self.update_plots)
        self.measurement.detectorChanged.connect(self._on_detector_changed)
        self.measurement.detectorChanged.connect(self.update_plots)
        self.dataChanged.connect(self.update_plots)
        self.plots.profile_control.profileChanged.connect(
            self.update_profile_plot
        )

        self.init_ui()

    def _load_yaml(self):
        yaml_path = self.base_path / "wire_scan_gui.yaml"
        with open(yaml_path, "r", encoding="utf-8") as stream:
            return yaml.safe_load(stream)

    def _dated_dir(self, dt: datetime | None = None) -> Path:
        """Create and return dated directory for wire scan data.

        Args:
            dt: Optional datetime to use for directory structure.
                Defaults to current time.

        Returns:
            Path to /u1/lcls/physics/data/wire_scan/YYYY/MM/DD/
        """
        base_dir = Path("/u1/lcls/physics/data/wire_scan")
        dt = dt or datetime.now()
        path = base_dir / f"{dt:%Y}" / f"{dt:%m}" / f"{dt:%d}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _safe_output_dir(self) -> Path:
        try:
            return self._dated_dir()
        except Exception:
            fallback = (
                self.base_path
                / "wire_scan_output"
                / datetime.now().strftime("%Y/%m/%d")
            )
            fallback.mkdir(parents=True, exist_ok=True)
            return fallback

    def _build_suite(self) -> WireScanSuite:
        outdir = self._safe_output_dir()
        plotdir = outdir / "plots"
        return WireScanSuite(
            wires=[],
            beampath=self.nav.beampath,
            detector=self.measurement.detector or "PMT29150",
            outdir=outdir,
            plotdir=plotdir,
        )

    def _create_wire(self, area, name):
        from lcls_tools.common.devices.reader import create_wire

        return create_wire(area=area, name=name)

    def ui_filename(self):
        return "wire_scan_gui.ui"

    def ui_filepath(self):
        return str(self.base_path / self.ui_filename())

    def init_ui(self):
        self.ControlsLayout.insertWidget(0, self.nav)
        self.ControlsLayout.insertWidget(1, self.measurement)
        self.measurement.wireChanged.emit(self.measurement.wire)

        self.ui.startButton.clicked.connect(self.start_scan_callback)
        self.ui.saveDataButton.clicked.connect(self.save_callback)
        self.ui.loadDataButton.clicked.connect(self.load_callback)
        self.ui.logBookButton.clicked.connect(self.logbook_callback)

        self.ui.statusUpdate.setReadOnly(True)
        log_dest = (
            self._safe_output_dir()
            / f"WireScanLog-{datetime.now():%Y-%m-%d}.txt"
        )
        self.logger = self._build_logger(log_dest)
        self.logger.setLevel(logging.INFO)
        attach_logger_to_widget(self.logger, self.ui.statusUpdate)

        self.plotLayout = QVBoxLayout()
        self.ui.plotFrame.setLayout(self.plotLayout)
        self.plotLayout.addWidget(self.ui.logBookButton)
        self.plotLayout.addWidget(self.plots)

    def _build_logger(self, log_dest: Path):
        try:
            module = importlib.import_module(
                "lcls_tools.common.logger.file_logger"
            )
            custom_logger = module.custom_logger

            return custom_logger(log_file=log_dest, name="wire_scan_logger")
        except Exception:
            logger = logging.getLogger("wire_scan_logger")
            logger.handlers.clear()
            file_handler = logging.FileHandler(log_dest)
            file_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s - %(levelname)s - %(message)s"
                )
            )
            logger.addHandler(file_handler)
            logger.propagate = False
            return logger

    def _selected_wire_identifier(self) -> str:
        wire = self.measurement.wire
        area = self.measurement.wire_combo.currentData() or self.nav.area
        if ":" in wire:
            return wire
        return f"{wire}:{area}"

    def _on_beampath_changed(self, beampath: str):
        self.suite.beampath = beampath

    def _on_detector_changed(self, detector: str):
        if detector:
            self.suite.detector = detector

    def update_parameters(self):
        children = self.ui.ParametersGroupBox.findChildren(QWidget)
        for child in children:
            name = child.objectName()
            if name.endswith("Label"):
                continue
            pv_obj = getattr(
                self.measurement.active_wire.controls_information.PVs,
                name,
                None,
            )
            if pv_obj is not None:
                child.channel = pv_obj.pvname

    def start_scan_callback(self):
        wire_identifier = self._selected_wire_identifier()
        self.ui.startButton.setEnabled(False)

        self.suite.beampath = self.nav.beampath
        if self.measurement.detector:
            self.suite.detector = self.measurement.detector

        self.thread = WireScanSuiteThread(
            suite=self.suite,
            wire_identifier=wire_identifier,
            beampath=self.nav.beampath,
            detector=self.measurement.detector or self.suite.detector,
            save_data=True,
        )
        self.thread.scan_complete.connect(self.on_scan_complete)
        self.thread.scan_failed.connect(self.on_scan_failure)
        self.thread.start()

    def on_scan_complete(self, wire_name: str, method: str, data, entry: dict):
        self.ui.startButton.setEnabled(True)
        self.current_runs[wire_name] = {
            "method": method,
            "run_id": entry.get("run_id"),
            "timestamp": entry.get("timestamp"),
        }
        self.logger.info(
            "Scan complete for %s using %s (%s)",
            wire_name,
            method,
            entry.get("timestamp"),
        )
        self.dataChanged.emit()

    def on_scan_failure(self, wire_identifier: str, message: str):
        self.ui.startButton.setEnabled(True)
        wire_name = wire_identifier.split(":")[0]
        self.suite._log_run(
            method="unknown",
            wire=wire_name,
            status="error",
            error=message,
        )
        self.logger.error(
            "Scan failed for %s: %s",
            wire_identifier,
            message,
        )

    def _latest_result_for_wire(self, wire_name: str):
        # Check if we have results for this wire in the suite
        if wire_name in self.suite.results:
            return self.suite._latest_run(wire_name)

        # Fall back to loaded results if no suite results
        return self.loaded_results.get(wire_name)

    def save_callback(self):
        wire = self.measurement.wire
        data = self._latest_result_for_wire(wire)
        if data is None:
            self.logger.info("No data for %s to save", wire)
            return

        path = self.suite.save_run(data, f"Manual_{wire}")
        self.logger.info("Data saved to %s", path)

    def load_callback(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select a file",
            str(self.base_path),
        )
        if not file_path:
            return

        load_func = self._get_load_function()
        if load_func is None:
            self.logger.info(
                "Could not import load_from_h5 function for loading."
            )
            return

        try:
            result = load_func(file_path)
        except Exception as exc:
            self.logger.info("Failed to load data: %s", exc)
            return

        wire_name = getattr(
            getattr(result, "metadata", None),
            "wire_name",
            self.measurement.wire,
        )
        self.loaded_results[wire_name] = result
        self.logger.info("Successfully loaded data for %s", wire_name)
        self.dataChanged.emit()

    def _get_load_function(self):
        try:
            module = importlib.import_module(
                "lcls_tools.common.measurements.ws_analysis_results"
            )
            return module.load_from_h5
        except Exception:
            return None

    def logbook_callback(self):
        wire = self.measurement.wire
        detector = self.measurement.detector
        profile = self.plots.profile_control.profile

        if self.nav.beampath.startswith("SC"):
            logbook = "lcls2"
        elif self.nav.beampath.startswith("CU"):
            logbook = "lcls"
        else:
            self.logger.info(
                "Could not determine logbook for beampath %s",
                self.nav.beampath,
            )
            return

        title = f"{wire} Scan v. {detector} - {profile} Profile"
        image_path = self._safe_output_dir() / "profile_plot.png"
        self.plots.profile_plot.figure.savefig(image_path, dpi=150)

        try:
            elog = importlib.import_module("physicselog")
        except Exception:
            self.logger.info("physicselog is unavailable in this environment")
            return

        elog.submit_entry(
            logbook,
            "Wire Scan GUI",
            title,
            "",
            str(image_path),
        )
        self.save_callback()

    def update_trajectory_plot(self):
        wire = self.measurement.wire
        detector = self.measurement.detector
        trajectory_plot = self.plots.trajectory_plot
        data = self._latest_result_for_wire(wire)
        if data is None:
            return

        traj_wire = np.asarray(data.collection_result.raw_data[wire])
        scan_points = np.arange(len(traj_wire))
        traj_detector = np.asarray(data.collection_result.raw_data[detector])
        detector_label = (
            "% Beam Loss" if detector == "TMITLOSS" else f"{detector} Counts"
        )

        trajectory_plot.figure.clf()
        ax1 = trajectory_plot.figure.add_subplot(1, 1, 1)
        ax2 = ax1.twinx()
        trajectory_plot.axes = ax1
        trajectory_plot.secondary_axes = ax2

        ax1.plot(
            scan_points,
            traj_wire,
            label="Wire Position (µm)",
            color="#1f77b4",
        )
        ax1.set_xlabel("Scan Point")
        ax1.set_ylabel("Wire Position (µm)", color="#1f77b4")
        ax1.tick_params(axis="y", labelcolor="#1f77b4")

        ax2.plot(
            scan_points,
            traj_detector,
            label=detector_label,
            color="#d95f02",
        )
        ax2.set_ylabel(detector_label, color="#d95f02")
        ax2.tick_params(axis="y", labelcolor="#d95f02")

        ax1.set_title(f"{wire} Motion Trajectory")
        trajectory_plot.figure.tight_layout()
        trajectory_plot.draw()

    def update_profile_plot(self):
        wire = self.measurement.wire
        detector = self.measurement.detector
        profile_plot = self.plots.profile_plot
        data = self._latest_result_for_wire(wire)
        if data is None:
            return

        profile = self.plots.profile_control.profile.lower()
        if not profile:
            return

        p = data.profiles[profile]
        x_stage = np.asarray(p.positions)
        y_meas = np.asarray(p.detectors[detector].values)

        fit_result = data.fit_result[profile].detectors[detector]

        profile_plot.figure.clf()
        profile_plot.axes = profile_plot.figure.add_subplot(1, 1, 1)
        profile_plot.axes.plot(
            x_stage,
            y_meas,
            label="Measured",
            linestyle="dotted",
            color="blue",
        )
        profile_plot.axes.set_xlabel("Wire Position (stage, µm)")
        detector_label = (
            "% Beam Loss" if detector == "TMITLOSS" else f"{detector} Counts"
        )
        profile_plot.axes.set_ylabel(detector_label)

        scale = 1 if profile == "u" else np.cos(np.deg2rad(45))

        def stage_to_beam(x):
            return x * scale

        def beam_to_stage(x):
            return x / scale

        x_beam_fit = np.asarray(fit_result.positions)
        y_fit = np.asarray(fit_result.curve)
        profile_plot.axes.plot(
            beam_to_stage(x_beam_fit),
            y_fit,
            label="Fitted",
            linestyle="-",
        )

        secax = profile_plot.axes.secondary_xaxis(
            "top",
            functions=(stage_to_beam, beam_to_stage),
        )
        secax.set_xlabel("Wire Position (beam, µm)")

        profile_plot.axes.set_title(
            f"{wire} {profile.upper()} Profile for {detector}"
        )
        profile_plot.axes.legend(loc="upper right")
        profile_plot.axes.grid(True, which="both", linestyle="--", alpha=0.6)

        amp_off_units = "%" if detector == "TMITLOSS" else "Counts"
        params_text = (
            f"Mean: {fit_result.mean:.1f} µm\n"
            f"Sigma: {fit_result.sigma:.1f} µm\n"
            f"Amplitude: {fit_result.amplitude:.1f} {amp_off_units}\n"
            f"Offset: {fit_result.offset:.1f} {amp_off_units}"
        )
        profile_plot.axes.text(
            0.95,
            0.15,
            params_text,
            transform=profile_plot.axes.transAxes,
            verticalalignment="bottom",
            horizontalalignment="right",
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
        )

        profile_plot.figure.tight_layout()
        profile_plot.draw()

    def update_plots(self):
        if self._latest_result_for_wire(self.measurement.wire) is not None:
            self.update_trajectory_plot()
            self.update_profile_plot()
        else:
            self.plots.trajectory_plot.axes.cla()
            self.plots.profile_plot.axes.cla()
            self.plots.trajectory_plot.draw()
            self.plots.profile_plot.draw()
