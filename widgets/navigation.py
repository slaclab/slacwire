from qtpy.QtWidgets import QComboBox, QGroupBox, QHBoxLayout
from PyQt5.QtCore import pyqtSignal


def parse_yaml(yaml_data):
    parsed = {}
    for beampath, areas in yaml_data.items():
        parsed[beampath] = {}
        for area, wire_strings in areas.items():
            wires = [ws.split(":")[0] for ws in wire_strings]
            parsed[beampath][area] = wires
    return parsed


class NavigationWidget(QGroupBox):
    beampathChanged = pyqtSignal(str)
    areaChanged = pyqtSignal(str)

    def __init__(self, yaml_data: dict, parent=None):
        super().__init__("Navigation Control", parent)

        self.data = parse_yaml(yaml_data)

        self.layout = QHBoxLayout()
        self.setLayout(self.layout)

        self.beampath_combo = QComboBox()
        self.area_combo = QComboBox()

        self.layout.addWidget(self.beampath_combo)
        self.layout.addWidget(self.area_combo)

        self.beampath_combo.addItems(self.data.keys())
        self.beampath_combo.currentTextChanged.connect(self._update_areas)
        self.area_combo.currentTextChanged.connect(self.areaChanged)
        self.beampath_combo.currentTextChanged.connect(self.beampathChanged)

        self._update_areas(self.beampath_combo.currentText())

    def _update_areas(self, beampath):
        self.area_combo.blockSignals(True)
        self.area_combo.clear()
        areas = self.data.get(beampath, {}).keys()
        self.area_combo.addItems(areas)
        self.area_combo.blockSignals(False)
        self.areaChanged.emit(self.area_combo.currentText())

    @property
    def beampath(self) -> str:
        return self.beampath_combo.currentText()

    @property
    def area(self) -> str:
        return self.area_combo.currentText()

    def get_wires(self) -> list[str]:
        return self.data.get(self.beampath, {}).get(self.area, [])
