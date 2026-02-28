import os
import pickle
import yaml
import numpy as np
from pydm import Display
from qtpy.QtWidgets import QVBoxLayout, QWidget, QFileDialog
from PyQt5.QtCore import pyqtSignal, QThread
from lcls_tools.common.devices.reader import create_wire
from lcls_tools.common.measurements.ws_collection import WireMeasurementCollection
from lcls_tools.common.measurements.ws_analysis import WireMeasurementAnalysis
from lcls_tools.common.measurements.wire_scan_results import (
    WireBeamProfileMeasurementResult,
)
from widgets.navigation import NavigationWidget
from widgets.measurement import MeasurementWidget, extract_measurement_data
from widgets.plots import PlotWidget
from widgets.text_logger import attach_logger_to_widget
from save_util import dated_dir
import logging
from lcls_tools.common.logger.file_logger import custom_logger
from datetime import datetime
import physicselog as elog
from lcls_tools.common.measurements.ws_analysis_results import load_from_h5


class WireScanThread(QThread):
    scan_complete = pyqtSignal(str, WireBeamProfileMeasurementResult)
    scan_failed = pyqtSignal(str, Exception)

    def __init__(self, wire_name, scan_obj, logger):
        super().__init__()
        self.logger = logger
        self.logger.propagte = False
        self.wire_name = wire_name
        self.scan_obj = scan_obj

    def run(self):
        try:
            beam_rate = self.scan_obj.beam_profile_device.beam_rate
            if beam_rate <= 120:
                data = self.scan_obj.measure(scan_type="step")
            elif beam_rate > 16000:
                raise ValueError(f"Beam rate {beam_rate} is too high for on-the-fly scanning.")
            else:
                data = self.scan_obj.measure(scan_type="on_the_fly")
            self.scan_complete.emit(self.wire_name, data)
        except Exception as e:
            self.scan_failed.emit(self.wire_name, e)


class WireScanGUI(Display):
    dataChanged = pyqtSignal()

    def __init__(self, parent=None, args=None, macros=None):
        super(WireScanGUI, self).__init__(parent=parent,
                                          args=args,
                                          macros=None)

        self.my_scans = {}
        self.my_data = {}
        self.my_analysis = {}
        self.my_results = {}
        self.my_save_files = {}

        filepath = "/usr/local/lcls/tools/python/hla/slacwire"
        filename = "wire_scan_gui.yaml"
        full_path = os.path.join(filepath, filename)
        with open(full_path, "r") as f:
            yaml_data = yaml.safe_load(f)

        area_to_wires = extract_measurement_data(yaml_data)

        self.nav = NavigationWidget(yaml_data)
        self.measurement = MeasurementWidget(area_to_wires, create_wire)
        self.plots = PlotWidget()

        self.nav.areaChanged.connect(self.measurement.update_area)
        self.measurement.wireChanged.connect(self.update_parameters)
        self.measurement.wireChanged.connect(self.update_plots)
        self.measurement.detectorChanged.connect(self.update_plots)
        self.dataChanged.connect(self.update_plots)
        self.plots.profile_control.profileChanged.connect(self.update_profile_plot)

        self.init_ui()

    def ui_filename(self):
        # Point to our UI file
        return "wire_scan_gui.ui"

    def ui_filepath(self):
        # Return the full path to the UI file
        return os.path.join("/usr/local/lcls/tools/python/hla/slacwire",
                            self.ui_filename())

    def init_ui(self):
        self.ControlsLayout.insertWidget(0, self.nav)
        self.ControlsLayout.insertWidget(1, self.measurement)
        self.measurement.wireChanged.emit(self.measurement.wire)

        self.ui.startButton.clicked.connect(self.start_scan_callback)
        self.ui.saveDataButton.clicked.connect(self.save_callback)
        self.ui.loadDataButton.clicked.connect(self.load_callback)
        self.ui.logBookButton.clicked.connect(self.logbook_callback)

        self.ui.statusUpdate.setReadOnly(True)
        out_dir = dated_dir()
        dest = out_dir / f"WireScanLog-{datetime.now():%Y-%m-%d}.txt"
        self.logger = custom_logger(log_file=dest, name="wire_scan_logger")
        self.logger.setLevel(logging.INFO)
        attach_logger_to_widget(self.logger, self.ui.statusUpdate)

        self.plotLayout = QVBoxLayout()
        self.ui.plotFrame.setLayout(self.plotLayout)
        self.plotLayout.addWidget(self.ui.logBookButton)
        self.plotLayout.addWidget(self.plots)

    def update_parameters(self):
        children = self.ui.ParametersGroupBox.findChildren(QWidget)
        for child in children:
            name = child.objectName()
            if not name.endswith("Label"):
                pv_obj = getattr(
                    self.measurement.active_wire.controls_information.PVs,
                    name,
                    None)
                if pv_obj is not None:
                    child.channel = pv_obj.pvname

    def start_scan_callback(self):
        self.ui.startButton.setEnabled(False)
        w = self.measurement.wire

        if w not in self.my_scans:
            self.my_scans[w] = WireMeasurementCollection(
                beam_profile_device=self.measurement.active_wire,
                beampath=self.nav.beampath
            )

            self.logger.info("Scan object made for %s", w)

        self.thread = WireScanThread(w, self.my_scans[w], self.logger)
        self.thread.scan_complete.connect(self.on_scan_complete)
        self.thread.scan_failed.connect(self.on_scan_failure)
        self.thread.start()

    def on_scan_complete(self, wire_name, data):
        # Re-enable the start button
        self.ui.startButton.setEnabled(True)

        # Store the data
        self.my_data[wire_name] = data

        # Analyze the data
        analysis = WireMeasurementAnalysis(collection_result=data)
        self.my_analysis[wire_name] = analysis
        self.my_results[wire_name] = self.my_analysis[wire_name].analyze()

        # Prepare the save file path
        out_dir = dated_dir()
        dest = out_dir / f"WireScan-{wire_name}-{datetime.now():%Y-%m-%d-%H%M%S}.hdf5"
        self.my_save_files[wire_name] = dest
        self.update_plots()
        self.dataChanged.emit()
        self.logger.info(f"Scan complete for {wire_name}.")

    def on_scan_failure(self, wire_name, e):
        self.ui.startButton.setEnabled(True)
        self.logger.exception(f"Scan failed for {wire_name}: {e}", exc_info=True)
        raise e

    def save_callback(self):
        w = self.measurement.wire
        if w in self.my_results:
            dest = self.my_save_files[w]
            self.my_results[w].save_to_h5(dest)
            self.logger.info(f"Data saved to {dest}")
        else:
            self.logger.info(f"No data for {w} to save!")

    def load_callback(self):
        def open_file_browser():
            file_path, _ = QFileDialog.getOpenFileName(self, "Select a file")
            if file_path:
                try:
                    return load_from_h5(file_path)
                except Exception as e:
                    self.logger.info(f"Failed to load data: {e}")
                    return None
        result = open_file_browser()
        if result is not None:
            w = result.metadata.wire_name
            data = result
            self.my_data[w] = data
            if w == self.measurement.wire:
                self.update_plots()
            self.logger.info(f"Successfully loaded data for {w}")
        else:
            self.logger.info("Failed to load data.")

    def logbook_callback(self):
        w = self.measurement.wire
        d = self.measurement.detector
        p = self.plots.profile_control.profile
        username = "Wire Scan GUI"
        title = f"{w} Scan v. {d} - {p} Profile"

        if self.nav.beampath.startswith("SC"):
            logbook = "lcls2"
        elif self.nav.beampath.startswith("CU"):
            logbook = "lcls"

        entry_text = ""
        fig = self.plots.profile_plot
        floc = "/tmp/profile_plot.png"
        fig.figure.savefig(floc, dpi=150)
        elog.submit_entry(logbook, username, title, entry_text, floc)
        self.save_callback()

    def update_trajectory_plot(self):
        w = self.measurement.wire
        d = self.measurement.detector
        tp = self.plots.trajectory_plot

        traj_wire = self.my_data[w].raw_data[w]
        scan_points = np.arange(len(traj_wire))
        traj_detector = self.my_data[w].raw_data[d]
        detector_label = "% Beam Loss" if d == "TMITLOSS" else f"{d} Counts"

        tp.figure.clf()
        ax1 = tp.figure.add_subplot(1, 1, 1)
        ax2 = ax1.twinx()
        tp.axes = ax1
        tp.secondary_axes = ax2

        # Plot wire position
        ax1.plot(scan_points, traj_wire, label="Wire Position (µm)",
                 color="#1f77b4")
        ax1.set_ylabel("Wire Position (µm)", color="#1f77b4")
        ax1.tick_params(axis="y", labelcolor="#1f77b4")

        ax2.plot(scan_points, traj_detector, label=detector_label,
                 color="#d95f02")
        ax2.set_ylabel(detector_label, color="#d95f02")
        ax2.tick_params(axis="y", labelcolor="#d95f02")

        tp.draw()

    def update_profile_plot(self):
        w = self.measurement.wire
        d = self.measurement.detector
        pp = self.plots.profile_plot
        profile = self.plots.profile_control.profile.lower()
        result = self.my_results[w]

        p = result.profiles[profile]
        x_stage = np.asarray(p.positions)
        y_meas = np.asarray(p.detectors[d].values)

        fr = result.fit_result[profile].detectors[d]
        fit_y = fr.curve

        pp.axes.cla()
        pp.axes.plot(x_stage,
                     y_meas,
                     label="Measured",
                     linestyle="dotted",
                     color="blue")
        pp.axes.set_xlabel("Wire Position (stage, µm)")
        detector_label = "% Beam Loss" if d == "TMITLOSS" else f"{d} Counts"
        pp.axes.set_ylabel(detector_label)

        scale = 1 if profile == "u" else np.cos(np.deg2rad(45))
        def stage_to_beam(x):
            return x * scale

        def beam_to_stage(x):
            return x / scale

        x_beam_fit = np.asarray(fr.positions)
        y_fit = np.asarray(fr.curve)
        pp.axes.plot(beam_to_stage(x_beam_fit),
                     y_fit,
                     label="Fitted",
                     linestyle="-")

        secax = pp.axes.secondary_xaxis(
            "top",
            functions=(stage_to_beam, beam_to_stage),
        )

        pp.axes.set_title(f"{w} {profile.upper()} Profile for {d}")

        pp.axes.legend(loc="upper right")
        pp.axes.grid(True, which="both", linestyle="--", alpha=0.6)

        amp_off_units = "%" if d == "TMITLOSS" else "Counts"

        params_text = (
            f"Mean: {fr.mean:.1f} µm\n"
            f"Sigma: {fr.sigma:.1f} µm\n"
            f"Amplitude: {fr.amplitude:.1f} {amp_off_units}\n"
            f"Offset: {fr.offset:.1f} {amp_off_units}")

        pp.axes.tick_params(axis='both', which='major')
        pp.axes.text(
            0.95, 0.15, params_text,
            transform=pp.axes.transAxes,
            verticalalignment="bottom",
            horizontalalignment="right",
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.8)
        )

        pp.figure.tight_layout()
        pp.draw()

    def update_plots(self):
        if self.measurement.wire in self.my_data:
            self.update_trajectory_plot()
            self.update_profile_plot()
        else:
            self.plots.trajectory_plot.axes.cla()
            if hasattr(self.plots.trajectory_plot, "secondary_axes"):
                self.plots.trajectory_plot.secondary_axes.cla()
            self.plots.profile_plot.axes.cla()
            self.plots.trajectory_plot.draw()
            self.plots.profile_plot.draw()
