"""RouterKing dock widget UI."""

try:
    from PySide2 import QtCore, QtWidgets
except ImportError:  # pragma: no cover - fallback for older FreeCAD builds
    from PySide import QtCore, QtWidgets

import FreeCADGui as Gui

from ..grbl.sender import GrblSender

_dock = None


def _find_main_window():
    for widget in QtWidgets.QApplication.topLevelWidgets():
        if widget.metaObject().className() == "Gui::MainWindow":
            return widget
    return None


def show_panel():
    global _dock

    main_window = _find_main_window()
    if not main_window:
        return

    if _dock is None:
        _dock = QtWidgets.QDockWidget("RouterKing", main_window)
        _dock.setObjectName("RouterKingDock")
        _dock.setWidget(RouterKingDockWidget())
        main_window.addDockWidget(QtCore.Qt.RightDockWidgetArea, _dock)

    _dock.show()
    _dock.raise_()


class RouterKingDockWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._sender = GrblSender()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        title = QtWidgets.QLabel("RouterKing GRBL Sender")
        title.setObjectName("RouterKingTitle")
        layout.addWidget(title)

        status = QtWidgets.QLabel("Status: disconnected")
        status.setObjectName("RouterKingStatus")
        layout.addWidget(status)

        connect_row = QtWidgets.QHBoxLayout()
        self._port = QtWidgets.QLineEdit()
        self._port.setPlaceholderText("/dev/ttyUSB0 or /dev/cu.wchusbserial...")
        self._connect_btn = QtWidgets.QPushButton("Connect")
        connect_row.addWidget(self._port)
        connect_row.addWidget(self._connect_btn)
        layout.addLayout(connect_row)

        jog_row = QtWidgets.QHBoxLayout()
        self._jog_xp = QtWidgets.QPushButton("X+")
        self._jog_xm = QtWidgets.QPushButton("X-")
        self._jog_yp = QtWidgets.QPushButton("Y+")
        self._jog_ym = QtWidgets.QPushButton("Y-")
        self._jog_zp = QtWidgets.QPushButton("Z+")
        self._jog_zm = QtWidgets.QPushButton("Z-")
        for btn in [self._jog_xm, self._jog_xp, self._jog_ym, self._jog_yp, self._jog_zm, self._jog_zp]:
            jog_row.addWidget(btn)
        layout.addLayout(jog_row)

        self._console = QtWidgets.QPlainTextEdit()
        self._console.setReadOnly(True)
        self._console.setPlaceholderText("GRBL console output will appear here.")
        layout.addWidget(self._console, 1)

        self._connect_btn.clicked.connect(self._on_connect)

    def _on_connect(self):
        # TODO: wire to GrblSender once implemented.
        self._console.appendPlainText("Connect requested (stub)")
        Gui.addStatusMessage("RouterKing: connect requested (stub)\n")
