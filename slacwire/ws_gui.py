import logging
import traceback
from datetime import datetime
from pathlib import Path

import yaml
from pydm import Display
from PyQt5.QtCore import QThread, pyqtSignal
from qtpy.QtWidgets import QFileDialog, QMessageBox, QVBoxLayout, QWidget

from slac_devices.reader import create_wire
from slacwire._constants import _BASE_DIR
from slacwire.widgets.measurement import MeasurementWidget, extract_measurement_data
from slacwire.widgets.navigation import NavigationWidget
from slacwire.widgets.plots import PlotWidget
from slacwire.widgets.text_logger import attach_logger_to_widget
from slacwire.suite import WireScanSuite


class WireScanSuiteThread(QThread):
    scan_complete = pyqtSignal(str, str, object, dict)
    scan_failed = pyqtSignal(str, str, str)

    def __init__(
        self,
        suite: WireScanSuite,
        wire_identifier: str,
        beampath: str,
        detector: str,
        jitter_correction: bool = False,
        charge_normalization: bool = False,
    ):
        super().__init__()
        self.suite = suite
        self.wire_identifier = wire_identifier
        self.beampath = beampath
        self.detector = detector
        self.jitter_correction = jitter_correction
        self.charge_normalization = charge_normalization

    def run(self):
        try:
            # Extract wire name from identifier (format: "WIRE:AREA")
            wire_name = self.wire_identifier.split(":")[0]

            # Set beampath and detector on suite
            self.suite.beampath = self.beampath
            self.suite.detector = self.detector

            # Use suite's orchestrated run_single() method which handles:
            # - Device creation/caching
            # - Execution of OTF or step scan
            # - Data saving and logging
            self.suite.run_single(
                wire=wire_name,
                scan_mode="otf",
                jitter_correction=self.jitter_correction,
                charge_normalization=self.charge_normalization,
            )

            # Retrieve the latest run data and entry from registry
            try:
                data = self.suite.latest_run(wire_name)
            except KeyError:
                # No results were produced
                self.scan_failed.emit(
                    self.wire_identifier,
                    f"No data returned from scan for {wire_name}",
                    "",
                )
                return

            # Find the corresponding entry in run_registry (most recent for this wire)
            entry = None
            for reg_entry in reversed(self.suite.registry.entries):
                if reg_entry.get("wire") == wire_name:
                    entry = reg_entry
                    break

            if entry is None:
                entry = {"wire": wire_name, "timestamp": datetime.now().isoformat()}

            method = entry.get("method", "unknown")
            self.scan_complete.emit(wire_name, method, data, entry)
        except Exception as exc:
            tb = traceback.format_exc()
            self.scan_failed.emit(self.wire_identifier, str(exc), tb)


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
        self.measurement.set_fit_control(self.plots.fit_control)

        self.suite = self._build_suite()
        self.current_runs = {}
        self.loaded_results = {}

        self.nav.areaChanged.connect(self.measurement.update_area)
        self.nav.beampathChanged.connect(self._on_beampath_changed)
        self.nav.beampathChanged.connect(self.measurement.set_beampath)
        self.measurement.wireChanged.connect(self.update_parameters)
        self.measurement.wireChanged.connect(self.update_plots)
        self.measurement.detectorChanged.connect(self._on_detector_changed)
        self.measurement.detectorChanged.connect(self.update_plots)
        self.measurement.jitter_checkbox.stateChanged.connect(
            self._on_jitter_toggled
        )
        self.dataChanged.connect(self.update_plots)
        self.plots.profile_control.profileChanged.connect(
            self.update_profile_plot
        )
        self.plots.fit_control.fitMethodChanged.connect(
            self._on_fit_method_changed
        )

        self.init_ui()

    def _load_yaml(self):
        yaml_path = self.base_path / "wire_scan_gui.yaml"
        with open(yaml_path, "r", encoding="utf-8") as stream:
            return yaml.safe_load(stream)

    def _build_suite(self) -> WireScanSuite:
        return WireScanSuite(
            wires=[],
            beampath=self.nav.beampath,
            detector=self.measurement.detector or "PMT29150",
        )

    def _create_wire(self, area, name):
        return create_wire(area=area, name=name)

    def ui_filename(self):
        return "wire_scan_gui.ui"

    def ui_filepath(self):
        return str(self.base_path / self.ui_filename())

    def init_ui(self):
        self.ControlsLayout.insertWidget(0, self.nav)
        self.ControlsLayout.insertWidget(1, self.measurement)
        self.measurement.wireChanged.emit(self.measurement.wire)

        self.ui.verticalLayout_4.setStretch(0, 0)
        self.ui.verticalLayout_4.setStretch(1, 1)
        self.ui.verticalLayout_4.setStretch(2, 0)
        self.ui.LeftLayout.setStretch(0, 0)
        self.ui.LeftLayout.setStretch(1, 0)
        self.ui.LeftLayout.setStretch(2, 1)

        self.ui.startButton.clicked.connect(self.start_scan_callback)
        self.ui.startButton.setToolTip(
            "Begin an on-the-fly wire scan for the selected device"
        )
        self.ui.saveDataButton.clicked.connect(self.save_callback)
        self.ui.saveDataButton.setToolTip("Export scan results to an HDF5 file")
        self.ui.loadDataButton.clicked.connect(self.load_callback)
        self.ui.loadDataButton.setToolTip(
            "Import a previously saved scan from file"
        )
        self.ui.logBookButton.clicked.connect(self.logbook_callback)
        self.ui.logBookButton.setToolTip(
            "Post the current profile plot to the e-log"
        )
        self.ui.logBookButton.setStyleSheet(
            self.ui.logBookButton.styleSheet()
            + " QToolTip { background-color: white; color: black; }"
        )
        self.ui.saveConfigButton.clicked.connect(self.save_config_callback)
        self.ui.saveConfigButton.setToolTip(
            "Save current measurement settings for this wire/beampath"
        )
        self.ui.loadConfigButton.clicked.connect(self.load_config_callback)
        self.ui.loadConfigButton.setToolTip(
            "Restore saved measurement settings for this wire/beampath"
        )

        self.ui.ParametersGroupBox.setToolTip(
            "Live EPICS readbacks for the selected wire scanner"
        )
        self.ui.abortButton.setToolTip(
            "Stop the current wire scan in progress"
        )

        self.ui.statusUpdate.setReadOnly(True)
        self.ui.statusUpdate.setToolTip("Scan activity log for this session")
        log_dest = self.suite.outdir / f"WireScanLog-{datetime.now():%Y-%m-%d}.txt"
        self.logger = self._build_logger(log_dest)
        self.logger.setLevel(logging.INFO)
        attach_logger_to_widget(self.logger, self.ui.statusUpdate)

        self.plotLayout = QVBoxLayout()
        self.ui.plotFrame.setLayout(self.plotLayout)
        self.plotLayout.addWidget(self.ui.logBookButton)
        self.plotLayout.addWidget(self.plots)

    def _build_logger(self, log_dest: Path):
        import slac_measurements.logger.file_logger

        logger = logging.getLogger("wire_scan_logger")
        logger.handlers.clear()
        logger.propagate = False
        return slac_measurements.logger.file_logger.custom_logger(
            log_file=str(log_dest), name="wire_scan_logger"
        )

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

    def _on_jitter_toggled(self, state: int):
        wire = self.measurement.wire
        data = self._latest_result_for_wire(wire)
        if data is None or not hasattr(data, "reanalyze"):
            return

        jitter_on = state != 0
        new_data = data.reanalyze(jitter_correction=jitter_on)

        if wire in self.suite.results and self.suite.results[wire]:
            self.suite.results[wire][-1] = new_data
        elif wire in self.loaded_results:
            self.loaded_results[wire] = new_data

        self.dataChanged.emit()

    def _on_fit_method_changed(self, method: str):
        wire = self.measurement.wire
        data = self._latest_result_for_wire(wire)
        if data is None or not hasattr(data, "reanalyze"):
            return

        new_data = data.reanalyze(fitting_method=method)

        if wire in self.suite.results and self.suite.results[wire]:
            self.suite.results[wire][-1] = new_data
        elif wire in self.loaded_results:
            self.loaded_results[wire] = new_data

        self.dataChanged.emit()

    def save_config_callback(self):
        self.measurement.save_config()
        self.logger.info(
            "Config saved for %s on %s",
            self.measurement.wire,
            self.nav.beampath,
        )

    def load_config_callback(self):
        self.measurement._apply_config()
        self.logger.info(
            "Config loaded for %s on %s",
            self.measurement.wire,
            self.nav.beampath,
        )

    def update_parameters(self):
        if self.measurement.active_wire is None:
            return

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
        self.suite.save = True
        self.suite.show = False       # GUI renders plots after thread completes
        self.suite.save_plots = False  # GUI renders plots after thread completes

        self.thread = WireScanSuiteThread(
            suite=self.suite,
            wire_identifier=wire_identifier,
            beampath=self.nav.beampath,
            detector=self.measurement.detector or self.suite.detector,
            jitter_correction=self.measurement.jitter_enabled,
            charge_normalization=self.measurement.charge_normalized,
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

    def on_scan_failure(self, wire_identifier: str, message: str, tb: str):
        self.ui.startButton.setEnabled(False)
        wire_name = wire_identifier.split(":")[0]
        self.suite.registry.log(
            method="unknown",
            wire=wire_name,
            beampath=self.suite.beampath,
            status="error",
            error=message,
        )
        self.logger.error(
            "Scan failed for %s: %s",
            wire_identifier,
            message,
        )

        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Critical)
        dialog.setWindowTitle("Scan Failed")
        dialog.setText(f"Scan failed for {wire_identifier}")
        dialog.setInformativeText(message)
        if tb:
            dialog.setDetailedText(tb)
        dialog.setStandardButtons(QMessageBox.Ok)
        dialog.exec_()
        self.ui.startButton.setEnabled(True)

    def _latest_result_for_wire(self, wire_name: str):
        # Check if we have results for this wire in the suite
        if wire_name in self.suite.results:
            try:
                return self.suite.latest_run(wire_name)
            except KeyError:
                pass

        # Fall back to loaded results if no suite results
        return self.loaded_results.get(wire_name)

    def save_callback(self):
        wire = self.measurement.wire
        data = self._latest_result_for_wire(wire)
        if data is None:
            self.logger.info("No data for %s to save", wire)
            return

        # Save the data to an HDF5 file
        path = self._save_data_to_file(data, f"Manual_{wire}")
        if path:
            self.logger.info("Data saved to %s", path)
        else:
            self.logger.error("Failed to save data for %s", wire)

    def _save_data_to_file(self, data, filename_prefix: str) -> Path | None:
        """Save measurement data to HDF5 file.

        Args:
            data: The measurement data object to save
            filename_prefix: Prefix for the filename (without timestamp or extension)

        Returns:
            Path to saved file, or None if save failed
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = self.suite.outdir / f"{filename_prefix}_{timestamp}.h5"
            filepath.parent.mkdir(parents=True, exist_ok=True)
            data.save_to_h5(filepath)
            return filepath
        except Exception as e:
            self.logger.error("Error saving data: %s", str(e))
            return None

    def load_callback(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select a file",
            str(_BASE_DIR),
        )
        if not file_path:
            return

        try:
            result = self.suite.load_scan(file_path)
        except Exception as exc:
            self.logger.info("Failed to load data: %s", exc)
            return

        wire_name = getattr(
            getattr(result, "metadata", None),
            "wire_name",
            self.measurement.wire,
        )
        self.loaded_results[wire_name] = result
        self._navigate_to_wire(wire_name)
        self.logger.info("Successfully loaded data for %s", wire_name)
        self.dataChanged.emit()

    def _navigate_to_wire(self, wire_name: str):
        for beampath, areas in self.nav.data.items():
            for area, wires in areas.items():
                if wire_name in wires:
                    self.nav.beampath_combo.setCurrentText(beampath)
                    self.nav.area_combo.setCurrentText(area)
                    self.measurement.wire_combo.setCurrentText(wire_name)
                    return

    def logbook_callback(self):
        wire = self.measurement.wire
        detector = self.measurement.detector
        profile = self.plots.profile_control.profile

        title = f"{wire} Scan v. {detector} - {profile} Profile"
        body = f"Wire scan for {wire} using {detector} with {profile} profile."

        image_path = self.suite.plotdir / "profile_plot.png"
        self.suite.view.save_fig_to_path(self.plots.profile_plot.figure, image_path)

        try:
            self.suite.post_to_logbook(
                title=title,
                body=body,
                attachment=str(image_path),
            )
        except Exception as e:
            self.logger.error("Failed to post to logbook: %s", e)
            return

        self.logger.info("%s %s posted to logbook", wire, profile)

    def update_trajectory_plot(self):
        wire = self.measurement.wire
        detector = self.measurement.detector
        trajectory_plot = self.plots.trajectory_plot
        data = self._latest_result_for_wire(wire)
        if data is None:
            return
        self.suite.view.draw_trajectory(trajectory_plot.figure, data, wire, detector)
        trajectory_plot.draw()

    def update_profile_plot(self):
        wire = self.measurement.wire
        detector = self.measurement.detector
        profile_plot = self.plots.profile_plot
        data = self._latest_result_for_wire(wire)
        if data is None:
            return

        profile = self.plots.profile_control.profile.lower()
        if not profile or profile not in data.profiles:
            profile_plot.figure.clf()
            ax = profile_plot.figure.add_subplot(1, 1, 1)
            ax.text(
                0.5, 0.5, "Profile not measured",
                transform=ax.transAxes, ha="center", va="center",
                fontsize=14, color="gray",
            )
            ax.set_axis_off()
            profile_plot.draw()
            return
        self.suite.view.draw_profile(profile_plot.figure, data, wire, detector, profile)
        profile_plot.draw()

    def update_plots(self):
        if self._latest_result_for_wire(self.measurement.wire) is not None:
            self.update_trajectory_plot()
            self.update_profile_plot()
        else:
            self.suite.view.clear_figure(self.plots.trajectory_plot.figure)
            self.suite.view.clear_figure(self.plots.profile_plot.figure)
            self.plots.trajectory_plot.draw()
            self.plots.profile_plot.draw()
