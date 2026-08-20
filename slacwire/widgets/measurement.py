from qtpy.QtWidgets import (
    QVBoxLayout, QComboBox, QGroupBox, QListWidget, QCheckBox, QPushButton,
)
from PyQt5.QtCore import pyqtSignal
from collections import defaultdict

from slacwire.config import WireConfig, get_wire_config, set_wire_config
from slacwire.config.wire_config import FittingMethod, VALID_FIT_METHODS


def extract_measurement_data(yaml_data):
    area_to_wires = defaultdict(set)
    wire_to_area = {}

    for areas in yaml_data.values():
        for area, entries in areas.items():
            for entry in entries:
                if ":" in entry:
                    wire = entry
                    area_to_wires[area].add(wire)
                    wire_to_area[wire] = area

    # Convert sets to sorted lists
    area_to_wires = {area: sorted(wires) for area, wires in area_to_wires.items()}

    return area_to_wires


class MeasurementWidget(QGroupBox):
    wireChanged = pyqtSignal(str)
    detectorChanged = pyqtSignal(str)

    def __init__(self, area_to_wires, create_wire_fn, parent=None):
        super().__init__("Measurement Settings", parent)
        self.area_to_wires = area_to_wires
        self.create_wire = create_wire_fn
        self.current_area = None
        self.my_wire = None
        self._beampath = "CU_HXR"

        # UI Elements
        self.wire_combo = QComboBox()
        self.detector_combo = QComboBox()
        self.fitting_method_combo = QComboBox()
        self.fitting_method_combo.addItems(VALID_FIT_METHODS)
        self.bpm_list = QListWidget()
        self.bpm_list.setSelectionMode(QListWidget.MultiSelection)
        self.jitter_checkbox = QCheckBox("Apply Jitter Correction")
        self.charge_checkbox = QCheckBox("Normalize by Charge")
        self.save_config_btn = QPushButton("Save Config")

        layout = QVBoxLayout()
        layout.addWidget(self.wire_combo)
        layout.addWidget(self.detector_combo)
        layout.addWidget(self.fitting_method_combo)
        layout.addWidget(self.bpm_list)
        layout.addWidget(self.jitter_checkbox)
        layout.addWidget(self.charge_checkbox)
        layout.addWidget(self.save_config_btn)
        self.setLayout(layout)

        # Signals
        self.wire_combo.currentTextChanged.connect(self._on_wire_selected)
        self.wire_combo.currentTextChanged.connect(self.wireChanged)
        self.detector_combo.currentTextChanged.connect(self.detectorChanged)
        self.wireChanged.connect(self.update_detectors)
        self.wireChanged.connect(self.update_bpms)
        self.save_config_btn.clicked.connect(self.save_config)

        self.update_area("HTR")

    def update_area(self, area: str):
        """Call this from NavigationWidget when area changes."""
        self.current_area = area
        self.wire_combo.blockSignals(True)
        self.wire_combo.clear()

        wires = []
        wire_strings = self.area_to_wires.get(area, [])
        for string in wire_strings:
            wire, area = string.split(":")
            wires.append(wire)
            self.wire_combo.addItem(wire, area)

        self.wire_combo.blockSignals(False)

        if wires:
            self._on_wire_selected(self.wire_combo.currentText())

    def update_detectors(self):
        self.detector_combo.blockSignals(True)
        self.detector_combo.clear()

        if self.my_wire is None:
            self.detector_combo.blockSignals(False)
            return

        detectors = getattr(self.my_wire.metadata, "detectors", [])
        for detector_string in detectors:
            detector, area = detector_string.split(":")
            self.detector_combo.addItem(detector, area)

        self.detector_combo.blockSignals(False)

    def update_bpms(self):
        self.bpm_list.blockSignals(True)
        self.bpm_list.clear()

        if self.my_wire is None:
            self.bpm_list.blockSignals(False)
            return

        jitter_bpms = getattr(self.my_wire.metadata, "jitter_bpms", None)
        if jitter_bpms:
            for bpm in jitter_bpms:
                self.bpm_list.addItem(bpm)

        self.bpm_list.blockSignals(False)

    def set_beampath(self, beampath: str):
        """Update the current beampath (called when NavigationWidget changes)."""
        self._beampath = beampath
        if self.wire_combo.currentText():
            self._apply_config()

    def _on_wire_selected(self, wire: str):
        if not wire or not self.current_area:
            return

        try:
            self.my_wire = self.create_wire(
                area=self.wire_combo.currentData(), name=wire
            )
        except Exception as e:
            print(f"Failed to create wire {wire} in area {self.current_area}: {e}")
            return

        self._apply_config()
        self.wireChanged.emit(wire)

    def _apply_config(self):
        """Read per-wire config from SQLite and set widget states."""
        wire = self.wire_combo.currentText()
        if not wire:
            return

        config = get_wire_config(wire, self._beampath)

        self.jitter_checkbox.setChecked(config.jitter_correction)
        self.charge_checkbox.setChecked(config.charge_normalization)

        idx = self.fitting_method_combo.findText(config.fitting_method)
        if idx >= 0:
            self.fitting_method_combo.setCurrentIndex(idx)

        if config.detector:
            det_idx = self.detector_combo.findText(config.detector)
            if det_idx >= 0:
                self.detector_combo.setCurrentIndex(det_idx)

        if config.jitter_bpms:
            for i in range(self.bpm_list.count()):
                item = self.bpm_list.item(i)
                item.setSelected(item.text() in config.jitter_bpms)

    def save_config(self):
        """Write current widget state to SQLite config database."""
        wire = self.wire_combo.currentText()
        if not wire:
            return

        selected_bpms = [item.text() for item in self.bpm_list.selectedItems()]

        set_wire_config(
            wire=wire,
            beampath=self._beampath,
            fitting_method=self.fitting_method_combo.currentText(),
            detector=self.detector_combo.currentText() or None,
            charge_normalization=self.charge_checkbox.isChecked(),
            jitter_correction=self.jitter_checkbox.isChecked(),
            jitter_bpms=selected_bpms or None,
        )

    @property
    def wire(self) -> str:
        return self.wire_combo.currentText()

    @property
    def active_wire(self):
        return self.my_wire

    @property
    def detector(self) -> str:
        return self.detector_combo.currentText()

    @property
    def selected_bpms(self) -> list[str]:
        return [item.text() for item in self.bpm_list.selectedItems()]

    @property
    def jitter_enabled(self) -> bool:
        return self.jitter_checkbox.isChecked()

    @property
    def charge_normalized(self) -> bool:
        return self.charge_checkbox.isChecked()
