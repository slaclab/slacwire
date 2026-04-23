from qtpy.QtWidgets import (
    QRadioButton,
    QHBoxLayout,
    QWidget,
    QGroupBox,
    QButtonGroup,
    QVBoxLayout,
)
from PyQt5.QtCore import pyqtSignal
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


class PlotWidget(QWidget):
    wireChanged = pyqtSignal(str)
    detectorChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.trajectory_plot = MplCanvas()
        self.profile_plot = MplCanvas()
        self.profile_control = ProfileControl()

        layout = QVBoxLayout()
        layout.addWidget(self.trajectory_plot)
        layout.addWidget(self.profile_plot)
        layout.addWidget(self.profile_control)

        self.setLayout(layout)
