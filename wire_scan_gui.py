import os
import pickle
import yaml
import numpy as np
from pydm import Display
from qtpy.QtWidgets import QVBoxLayout, QWidget
from PyQt5.QtCore import pyqtSignal, QThread
from lcls_tools.common.devices.reader import create_wire
from lcls_tools.common.measurements.wire_scan import WireBeamProfileMeasurement
from lcls_tools.common.measurements.wire_scan_results import (
    WireBeamProfileMeasurementResult,
)
from widgets.navigation import NavigationWidget
from widgets.measurement import MeasurementWidget, extract_measurement_data
from widgets.plots import PlotWidget
from widgets.text_logger import attach_logger_to_widget
import logging
from datetime import datetime


class WireScanThread(QThread):
    scan_complete = pyqtSignal(str, WireBeamProfileMeasurementResult)
    scan_failed = pyqtSignal(str, Exception)

    def __init__(self, wire_name, scan_obj, logger):
        super().__init__()
        self.logger = logger
        self.wire_name = wire_name
        self.scan_obj = scan_obj

    def run(self):
        try:
            result = self.scan_obj.measure()
        except Exception as e:
            self.scan_failed.emit(self.wire_name, e)
        self.scan_complete.emit(self.wire_name, result)


class WireScanGUI(Display):
    dataChanged = pyqtSignal()

    def __init__(self, parent=None, args=None, macros=None):
        super(WireScanGUI, self).__init__(parent=parent,
                                          args=args,
                                          macros=None)

        self.my_data = {}
        self.my_scans = {}

        filepath = "/usr/local/lcls/tools/python/hla/slacwire/"
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

        self.ui.statusUpdate.setReadOnly(True)
        self.logger = logging.getLogger("wire_scan_logger")
        attach_logger_to_widget(self.logger, self.ui.statusUpdate)

        self.plotLayout = QVBoxLayout()
        self.ui.plotFrame.setLayout(self.plotLayout)
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
                child.channel = pv_obj.pvname

    def start_scan_callback(self):
        self.ui.startButton.setEnabled(False)
        w = self.measurement.wire

        if w not in self.my_scans:
            self.my_scans[w] = WireBeamProfileMeasurement(
                my_wire=self.measurement.active_wire,
                beampath=self.nav.beampath)

            self.logger.info("Scan object made for %s", w)

        self.thread = WireScanThread(w, self.my_scans[w], self.logger)
        self.thread.scan_complete.connect(self.on_scan_complete)
        self.thread.scan_failed.connect(self.on_scan_failure)
        self.thread.start()

    def on_scan_complete(self, wire_name, data):
        self.ui.startButton.setEnabled(True)
        self.my_data[wire_name] = data
        self.update_plots()
        self.dataChanged.emit()
        self.logger.info(f"Scan complete for {wire_name}.")

    def on_scan_failure(self, wire_name, e):
        self.ui.startButton.setEnabled(True)
        self.logger.erorr(f"Scan failed for {wire_name}: {e}")

    def save_callback(self):
        w = self.measurement.wire
        filename = f"WireScan-{w}-{datetime.now():%Y-%m-%d-%H%M%S}.pkl"
        with open(filename, "wb") as f:
            pickle.dump(self.my_data[w], f)
        self.logger.info("Data pickled to {filename}")

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

        prof_x = self.my_data[w].profiles[profile].positions
        prof_y = self.my_data[w].profiles[profile].detectors[d]
        fr = self.my_data[w].fit_result.copy()
        fit_y = fr[profile][d].curve

        pp.axes.cla()
        pp.axes.plot(prof_x,
                     prof_y,
                     label="Measured",
                     linestyle="dotted",
                     color="blue")
        pp.axes.plot(prof_x,
                     fit_y,
                     label="Fit",
                     linestyle="-",
                     color="orange")

        pp.axes.set_xlabel("Wire Position (µm)")
        detector_label = "% Beam Loss" if d == "TMITLOSS" else f"{d} Counts"
        pp.axes.set_ylabel(detector_label)

        pp.axes.legend(loc="upper right")
        pp.axes.grid(True, which="both", linestyle="--", alpha=0.6)

        params_text = (
            f"Mean: {fr[profile][d].mean:.1f} µm\n"
            f"Sigma: {fr[profile][d].sigma:.1f} µm\n"
            f"Amplitude: {fr[profile][d].amplitude:.1f} %\n"
            f"Offset: {fr[profile][d].offset:.1f} %")

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
