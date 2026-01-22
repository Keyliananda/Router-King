"""Logging helpers for RouterKing AI tools."""

import logging

try:  # FreeCAD may not be available during tests or linting.
    import FreeCAD as App
except Exception:  # pragma: no cover - FreeCAD not available in CI
    App = None


class _FreeCADLogHandler(logging.Handler):
    def emit(self, record):
        if App is None or not hasattr(App, "Console"):
            return
        message = self.format(record)
        if record.levelno >= logging.ERROR:
            App.Console.PrintError(message + "\n")
        elif record.levelno >= logging.WARNING:
            App.Console.PrintWarning(message + "\n")
        else:
            App.Console.PrintMessage(message + "\n")


def get_logger(name):
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("[%(levelname)s] %(name)s: %(message)s")
    if App is None:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    else:
        handler = _FreeCADLogHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger
