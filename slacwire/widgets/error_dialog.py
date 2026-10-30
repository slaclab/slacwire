from qtpy.QtCore import Qt
from qtpy.QtGui import QFontDatabase
from qtpy.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QStyle,
    QVBoxLayout,
)


class ErrorDialog(QDialog):
    """Resizable error dialog with a scrollable traceback view.

    QMessageBox enforces a fixed size, which makes long tracebacks hard
    to read, so this dialog is used in its place.
    """

    def __init__(self, title: str, text: str, message: str, tb: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setSizeGripEnabled(True)

        icon = QLabel()
        icon.setPixmap(
            self.style().standardIcon(QStyle.SP_MessageBoxCritical).pixmap(48, 48)
        )

        heading = QLabel(f"<b>{text}</b>")
        summary = QLabel(message)
        summary.setWordWrap(True)
        summary.setTextInteractionFlags(Qt.TextSelectableByMouse)

        text_layout = QVBoxLayout()
        text_layout.addWidget(heading)
        text_layout.addWidget(summary)

        header = QHBoxLayout()
        header.addWidget(icon, 0)
        header.addLayout(text_layout, 1)

        layout = QVBoxLayout(self)
        layout.addLayout(header, 0)

        if tb:
            details = QPlainTextEdit(tb)
            details.setReadOnly(True)
            details.setLineWrapMode(QPlainTextEdit.NoWrap)
            details.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
            layout.addWidget(details, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons, 0)

        self.resize(800, 500 if tb else 150)
