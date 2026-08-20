from qtpy.QtWidgets import (
    QComboBox,
    QRadioButton,
    QHBoxLayout,
    QWidget,
    QGroupBox,
    QButtonGroup,
    QVBoxLayout,
)
from PyQt5.QtCore import pyqtSignal

from slacwire.config.wire_config import VALID_FIT_METHODS
import matplotlib

matplotlib.use("Qt5Agg")
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure


class MplCanvas(FigureCanvasQTAgg):
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = fig.add_subplot(1, 1, 1)
        super(MplCanvas, self).__init__(fig)


class ProfileControl(QGroupBox):
    profileChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent=None)

        self.x_button = QRadioButton("X")
        self.x_button.setChecked(True)
        self.y_button = QRadioButton("Y")
        self.u_button = QRadioButton("U")

        self.button_group = QButtonGroup(self)
        self.button_group.addButton(self.x_button, 0)
        self.button_group.addButton(self.y_button, 1)
        self.button_group.addButton(self.u_button, 2)

        layout = QHBoxLayout()
        layout.addWidget(self.x_button)
        layout.addWidget(self.y_button)
        layout.addWidget(self.u_button)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        self.button_group.buttonClicked.connect(self.on_button_clicked)

    def on_button_clicked(self, button):
        self.profileChanged.emit(button.text())

    def selected_profile(self) -> str:
        for btn in (self.x_button, self.y_button, self.u_button):
            if btn.isChecked():
                return btn.text()
        return ""

    @property
    def profile(self) -> str:
        return self.selected_profile()


class FitControl(QGroupBox):
    fitMethodChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent=None)

        self.fit_combo = QComboBox()
        self.fit_combo.addItems(VALID_FIT_METHODS)

        layout = QHBoxLayout()
        layout.addWidget(self.fit_combo)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        self.fit_combo.currentTextChanged.connect(self.fitMethodChanged)

    @property
    def fitting_method(self) -> str:
        return self.fit_combo.currentText()

    def set_fitting_method(self, method: str):
        idx = self.fit_combo.findText(method)
        if idx >= 0:
            self.fit_combo.setCurrentIndex(idx)


class PlotWidget(QWidget):
    wireChanged = pyqtSignal(str)
    detectorChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.trajectory_plot = MplCanvas()
        self.profile_plot = MplCanvas()
        self.profile_control = ProfileControl()
        self.fit_control = FitControl()

        controls_row = QHBoxLayout()
        controls_row.addWidget(self.profile_control)
        controls_row.addWidget(self.fit_control)

        layout = QVBoxLayout()
        layout.addWidget(self.trajectory_plot)
        layout.addWidget(self.profile_plot)
        layout.addLayout(controls_row)

        self.setLayout(layout)
