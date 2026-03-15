"""Global GrblSender singleton, independent of the UI dock widget.

This allows MCP and other non-UI code paths to access the machine
connection without requiring the RouterKing dock panel to be open.
"""

from __future__ import annotations

import logging

LOG = logging.getLogger("routerking.grbl.manager")

_sender = None


def get_sender(create=False):
    """Return the global GrblSender singleton.

    Args:
        create: If True and no sender exists, create one lazily.
                If False (default), return None when no sender is registered.
                This prevents the manager from creating an unconnected sender
                that shadows the UI's connected one.
    """
    global _sender
    if _sender is None and create:
        try:
            from .sender import GrblSender
        except ImportError:
            from grbl.sender import GrblSender
        _sender = GrblSender()
        LOG.info("GrblSender singleton created by manager.")
    return _sender


def set_sender(sender):
    """Allow the UI to register its own sender instance as the global one.

    This ensures UI and MCP share the same connection.
    """
    global _sender
    _sender = sender
    LOG.info("GrblSender singleton set externally (from UI).")
