"""GRBL sender stub for RouterKing."""

from ..vendor import import_serial


class GrblSender:
    def __init__(self):
        self._connected = False
        self._serial = import_serial()

    def connect(self, port, baudrate=115200):
        """Connect to the GRBL controller (stub)."""
        raise NotImplementedError("GRBL streaming not implemented yet")

    def disconnect(self):
        """Disconnect from the controller (stub)."""
        self._connected = False

    def is_connected(self):
        return self._connected
