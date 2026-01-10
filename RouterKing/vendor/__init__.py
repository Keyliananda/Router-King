"""Vendored dependencies for RouterKing."""

import importlib
import os
import sys


def import_serial():
    """Import pyserial, falling back to the vendored copy."""
    try:
        return importlib.import_module("serial")
    except Exception:
        vendor_root = os.path.join(os.path.dirname(__file__), "pyserial")
        if vendor_root not in sys.path:
            sys.path.insert(0, vendor_root)
        return importlib.import_module("serial")
