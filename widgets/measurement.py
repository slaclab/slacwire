from qtpy.QtWidgets import QVBoxLayout, QComboBox, QGroupBox, QListWidget, QCheckBox
from PyQt5.QtCore import pyqtSignal
from collections import defaultdict


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

        # UI Elements
        self.wire_combo = QComboBox()
        self.detector_combo = QComboBox()
        self.bpm_list = QListWidget()
        self.jitter_checkbox = QCheckBox("Apply Jitter Correction")
        self.charge_checkbox = QCheckBox("Normalize by Charge")

        layout = QVBoxLayout()
        layout.addWidget(self.wire_combo)
        layout.addWidget(self.detector_combo)
        layout.addWidget(self.bpm_list)
        layout.addWidget(self.jitter_checkbox)
        layout.addWidget(self.charge_checkbox)
        self.setLayout(layout)

        # Signals
        self.wire_combo.currentTextChanged.connect(self._on_wire_selected)
        self.wire_combo.currentTextChanged.connect(self.wireChanged)
        self.detector_combo.currentTextChanged.connect(self.detectorChanged)
        self.wireChanged.connect(self.update_detectors)
        self.wireChanged.connect(self.update_bpms)

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

        lblms = getattr(self.my_wire.metadata, "lblms", [])
        for detector_string in lblms:
            detector, area = detector_string.split(":")
            self.detector_combo.addItem(detector, area)

        self.detector_combo.blockSignals(False)

    def update_bpms(self):
        self.bpm_list.blockSignals(True)
        self.bpm_list.clear()

        bpms = getattr(self.my_wire.metadata, "bpms_before_wire", [])
        for bpm in bpms:
            self.bpm_list.addItem(bpm)

        self.bpm_list.blockSignals(False)

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

        self.wireChanged.emit(wire)

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
