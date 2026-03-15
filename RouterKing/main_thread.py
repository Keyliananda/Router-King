"""Main-thread dispatcher for FreeCAD thread safety.

FreeCAD GUI objects (``App.newDocument``, ``doc.addObject``, ``doc.recompute``,
etc.) may only be touched from the Qt main thread.  The MCP socket server
handles requests on plain ``threading.Thread`` workers, so we need a way to
marshal callables back to the main thread.

``QTimer.singleShot`` cannot be used from a non-QThread, so we use a
polling-based approach instead: a ``QTimer`` on the main thread drains a
``queue.Queue`` every 50 ms.

**CRITICAL**: ``init_dispatcher()`` (or ``get_dispatcher()``) must be called
on the Qt main thread — typically from ``InitGui.py`` during plugin load.
"""

from __future__ import annotations

import builtins
import logging
import queue
import sys
import threading
from typing import Any, Callable, TypeVar

LOG = logging.getLogger("routerking.main_thread")

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Qt imports — PySide2 (FreeCAD ≤0.21) or PySide6 (≥1.0).
# When neither is available (tests / CI) the dispatcher is not created and
# ``run_on_main_thread`` falls back to direct inline execution.
# ---------------------------------------------------------------------------

QtCore: Any = None
try:
    from PySide2 import QtCore  # type: ignore[no-redef]
except ImportError:
    try:
        from PySide6 import QtCore  # type: ignore[no-redef]
    except ImportError:
        pass


class MainThreadDispatcher(QtCore.QObject if QtCore is not None else object):
    """QObject that lives on the main thread and drains a work queue.

    Worker threads submit callables via :meth:`dispatch`.  A ``QTimer``
    fires every 50 ms on the main thread, picks up pending items, executes
    them, and signals completion back to the waiting worker.
    """

    _POLL_INTERVAL_MS = 50

    def __init__(self) -> None:
        super().__init__()
        self._queue: queue.Queue[
            tuple[Callable[[], Any], list, threading.Event]
        ] = queue.Queue()
        # Timer remains as a safety net if queued invoke fails.
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._drain)
        self._timer.start(self._POLL_INTERVAL_MS)

    # -- main-thread side ----------------------------------------------------

    if QtCore is not None:
        @QtCore.Slot()
        def _drain_slot(self) -> None:
            self._drain()
    else:  # pragma: no cover - only used when Qt is unavailable
        def _drain_slot(self) -> None:
            self._drain()

    def _drain(self) -> None:
        """Execute all pending callables (runs on the main thread)."""
        while True:
            try:
                fn, result_holder, event = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                result_holder[0] = fn()
            except Exception as exc:
                result_holder[1] = exc
            finally:
                event.set()

    def _schedule_drain(self) -> None:
        """Schedule queue draining on the Qt main event loop."""
        if QtCore is None:
            return

        invoked = False
        try:
            connection = QtCore.Qt.QueuedConnection
            invoked = bool(
                QtCore.QMetaObject.invokeMethod(self, "_drain_slot", connection)
            )
        except Exception:
            invoked = False

        # Safety fallback: ensure periodic polling remains active.
        if not invoked:
            try:
                if not self._timer.isActive():
                    self._timer.start(self._POLL_INTERVAL_MS)
            except Exception:
                pass

    # -- worker-thread side --------------------------------------------------

    def dispatch(self, fn: Callable[[], T], timeout: float = 60.0) -> T:
        """Submit *fn* for execution on the main thread and block until done.

        Parameters
        ----------
        fn:
            Zero-argument callable to execute on the main thread.
        timeout:
            Maximum seconds to wait.  Raises ``TimeoutError`` on expiry.

        Returns
        -------
        Whatever *fn* returns.

        Raises
        ------
        TimeoutError
            If the main thread does not complete *fn* within *timeout*.
        Exception
            Any exception raised by *fn* is re-raised in the caller.
        """
        result: list = [None, None]  # [return_value, exception]
        done = threading.Event()
        self._queue.put((fn, result, done))
        self._schedule_drain()
        if not done.wait(timeout=timeout):
            raise TimeoutError(
                f"Main-thread dispatch timed out after {timeout:.0f} s"
            )
        if result[1] is not None:
            raise result[1]
        return result[0]

    def _is_current_thread_main(self) -> bool:
        """Return True when called from the dispatcher's owning Qt thread."""
        if QtCore is None:
            return True
        try:
            owner_thread = self.thread()
            if owner_thread is not None:
                return QtCore.QThread.currentThread() == owner_thread
        except Exception:
            pass
        return False

    def run_on_main(self, fn: Callable[[], T], timeout: float = 60.0) -> T:
        """Execute *fn* on the main thread, inline when already on main.

        This is the preferred API for FreeCAD/Qt callers to avoid deadlocking
        when a call originates from the main thread itself.
        """
        if self._is_current_thread_main():
            return fn()
        return self.dispatch(fn, timeout=timeout)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_dispatcher: MainThreadDispatcher | None = None
_GLOBAL_DISPATCHER_KEY = "_routerking_main_thread_dispatcher_singleton"

# Ensure both import names resolve to the same module object.
# This avoids split singletons when code imports either:
# - RouterKing.main_thread
# - main_thread
if __name__ == "RouterKing.main_thread":
    sys.modules.setdefault("main_thread", sys.modules[__name__])
elif __name__ == "main_thread":
    sys.modules.setdefault("RouterKing.main_thread", sys.modules[__name__])


def _get_global_dispatcher() -> MainThreadDispatcher | None:
    value = getattr(builtins, _GLOBAL_DISPATCHER_KEY, None)
    if value is None:
        return None
    return value


def _set_global_dispatcher(dispatcher: MainThreadDispatcher | None) -> None:
    setattr(builtins, _GLOBAL_DISPATCHER_KEY, dispatcher)


def init_dispatcher() -> MainThreadDispatcher | None:
    """Create the global dispatcher.  **Must be called on the main thread.**

    Returns ``None`` when Qt is unavailable (tests / headless).
    """
    global _dispatcher
    if QtCore is None:
        return None
    if _dispatcher is None:
        _dispatcher = _get_global_dispatcher()
    if _dispatcher is None:
        _dispatcher = MainThreadDispatcher()
        _set_global_dispatcher(_dispatcher)
        LOG.debug("MainThreadDispatcher initialised on main thread")
    else:
        _set_global_dispatcher(_dispatcher)
    return _dispatcher


def get_dispatcher() -> MainThreadDispatcher | None:
    """Return the global dispatcher, or ``None`` if not yet initialised."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = _get_global_dispatcher()
    return _dispatcher


def run_on_main_thread(fn: Callable[[], T], timeout: float = 60.0) -> T:
    """Execute *fn* on the Qt main thread, blocking until complete.

    * If no dispatcher exists (tests / CLI / headless) → runs inline.
    * If already on the main thread → runs inline.
    * Otherwise → submits to the :class:`MainThreadDispatcher` queue and waits.
    """
    dispatcher = get_dispatcher()

    if dispatcher is None:
        # No Qt / not initialised — direct call (safe in tests & CLI).
        return fn()

    return dispatcher.run_on_main(fn, timeout=timeout)
