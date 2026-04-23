from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QTextEdit, QApplication
import logging

FORMAT_STRING = "%(asctime)s - %(levelname)s - %(message)s"
DATE_FORMAT = "%H:%M:%S"


class QTextEditLogger(logging.Handler, QObject):
    flushOnClose = True
    append_text = pyqtSignal(str)

    def __init__(self, text_widget: QTextEdit, level=logging.INFO):
        QObject.__init__(self)
        logging.Handler.__init__(self)
        self.widget = text_widget
        self.setLevel(level)
        self.append_text.connect(self.widget.append)
        self.setFormatter(logging.Formatter(FORMAT_STRING, DATE_FORMAT))

    def emit(self, record):
        msg = self.format(record)
        self.append_text.emit(msg)
        QApplication.processEvents()


def attach_logger_to_widget(
    logger: logging.Logger, text_widget: QTextEdit, level=logging.INFO
):
    text_handler = QTextEditLogger(text_widget, level)
    logger.addHandler(text_handler)
    logger.propagate = False
