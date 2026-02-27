import io
import importlib
import logging
from datetime import datetime
from pathlib import Path

import matplotlib.image as mpimg
import yaml
from pydm import Display
from PyQt5.QtCore import QThread, pyqtSignal
from qtpy.QtWidgets import QFileDialog, QVBoxLayout, QWidget

from h5_io import load_measurement_result
from save_util import dated_dir
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

            self.suite.results[method].setdefault(wire_name, []).append(data)
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
        super().__init__(parent=parent, args=args, macros=macros)

        self.base_path = Path(__file__).resolve().parent
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

    def _safe_output_dir(self) -> Path:
        try:
            return dated_dir()
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

            return custom_logger(log_file=log_dest, name="ws_suite_gui_logger")
        except Exception:
            logger = logging.getLogger("ws_suite_gui_logger")
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
        self.logger.exception(
            "Scan failed for %s: %s",
            wire_identifier,
            message,
        )

    def _latest_result_for_wire(self, wire_name: str):
        run = self.current_runs.get(wire_name)
        if run:
            method = run.get("method")
            if method and wire_name in self.suite.results.get(method, {}):
                return self.suite._latest_run(method, wire_name)

        for method in ("otf", "step"):
            if wire_name in self.suite.results.get(method, {}):
                return self.suite._latest_run(method, wire_name)

        return self.loaded_results.get(wire_name)

    def _render_figure_on_canvas(self, fig, canvas):
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", dpi=150, bbox_inches="tight")
        buffer.seek(0)

        canvas.axes.cla()
        canvas.axes.imshow(mpimg.imread(buffer, format="png"))
        canvas.axes.axis("off")
        canvas.draw()
        fig.clear()

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

        result_class = self._wire_result_class()
        if result_class is None:
            self.logger.info(
                "Could not import WireBeamProfileMeasurementResult "
                "for loading."
            )
            return

        try:
            result = load_measurement_result(file_path, result_class)
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

    def _wire_result_class(self):
        try:
            module = importlib.import_module(
                "lcls_tools.common.measurements.wire_scan_results"
            )
            return module.WireBeamProfileMeasurementResult
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
        data = self._latest_result_for_wire(wire)
        if data is None:
            return

        fig = self.suite.plot_trajectory(data, wire)
        self._render_figure_on_canvas(fig, self.plots.trajectory_plot)

    def update_profile_plot(self):
        wire = self.measurement.wire
        data = self._latest_result_for_wire(wire)
        if data is None:
            return

        profile = self.plots.profile_control.profile.lower()
        if not profile:
            return

        fig = self.suite.plot_profile(data, profile, wire)
        self._render_figure_on_canvas(fig, self.plots.profile_plot)

    def update_plots(self):
        if self._latest_result_for_wire(self.measurement.wire) is not None:
            self.update_trajectory_plot()
            self.update_profile_plot()
        else:
            self.plots.trajectory_plot.axes.cla()
            self.plots.profile_plot.axes.cla()
            self.plots.trajectory_plot.draw()
            self.plots.profile_plot.draw()
