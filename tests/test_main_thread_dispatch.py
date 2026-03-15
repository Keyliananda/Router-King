"""Tests for MainThreadDispatcher and FreeCAD action main-thread dispatch."""

import builtins
import queue
import threading
import unittest
from unittest.mock import patch

from RouterKing.ai.actions import (
    _FREECAD_ACTIONS,
    execute_actions,
    run_on_main_thread,
)
from RouterKing.main_thread import (
    MainThreadDispatcher,
    get_dispatcher,
    init_dispatcher,
)


class TestRunOnMainThread(unittest.TestCase):
    """run_on_main_thread without Qt falls back to direct execution."""

    def test_inline_when_no_qt(self):
        """Without Qt (CI), fn runs synchronously on the calling thread."""
        result = run_on_main_thread(lambda: 42)
        self.assertEqual(result, 42)

    def test_propagates_exception(self):
        def _boom():
            raise ValueError("kaboom")

        with self.assertRaises(ValueError):
            run_on_main_thread(_boom)

    def test_inline_from_worker_thread(self):
        """Even from a worker thread, without Qt it still runs inline."""
        results = []

        def _task():
            results.append(run_on_main_thread(lambda: threading.current_thread().name))

        t = threading.Thread(target=_task, name="test-worker")
        t.start()
        t.join(timeout=5.0)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], "test-worker")

    def test_uses_dispatcher_run_on_main_when_available(self):
        """When a dispatcher exists, run_on_main_thread delegates to run_on_main."""
        import RouterKing.main_thread as main_thread

        class StubDispatcher:
            def __init__(self):
                self.calls = 0

            def run_on_main(self, fn, timeout=60.0):
                self.calls += 1
                return fn()

        dispatcher = StubDispatcher()
        with patch.object(main_thread, "get_dispatcher", return_value=dispatcher):
            result = main_thread.run_on_main_thread(lambda: 42)

        self.assertEqual(result, 42)
        self.assertEqual(dispatcher.calls, 1)


class TestMainThreadDispatcherUnit(unittest.TestCase):
    """Test MainThreadDispatcher queue/event logic without Qt."""

    def test_no_dispatcher_without_qt(self):
        """init_dispatcher returns None when Qt is unavailable."""
        # In CI without Qt, init_dispatcher should return None.
        result = init_dispatcher()
        self.assertIsNone(result)
        self.assertIsNone(get_dispatcher())

    def test_dispatch_queue_protocol(self):
        """Verify the queue protocol: (fn, result_holder, event)."""
        q = queue.Queue()
        result = [None, None]
        done = threading.Event()

        q.put((lambda: 99, result, done))

        # Simulate what _drain does:
        fn, holder, event = q.get_nowait()
        try:
            holder[0] = fn()
        except Exception as exc:
            holder[1] = exc
        event.set()

        self.assertTrue(done.is_set())
        self.assertEqual(result[0], 99)
        self.assertIsNone(result[1])

    def test_dispatch_queue_exception_protocol(self):
        """Verify exceptions propagate through the queue protocol."""
        q = queue.Queue()
        result = [None, None]
        done = threading.Event()

        def _boom():
            raise RuntimeError("boom")

        q.put((_boom, result, done))

        fn, holder, event = q.get_nowait()
        try:
            holder[0] = fn()
        except Exception as exc:
            holder[1] = exc
        event.set()

        self.assertTrue(done.is_set())
        self.assertIsNone(result[0])
        self.assertIsInstance(result[1], RuntimeError)
        self.assertEqual(str(result[1]), "boom")

    def test_get_dispatcher_reads_global_store(self):
        """get_dispatcher should recover dispatcher from process-global store."""
        import RouterKing.main_thread as main_thread

        sentinel = object()
        old_local = main_thread._dispatcher
        key = main_thread._GLOBAL_DISPATCHER_KEY
        had_old_global = hasattr(builtins, key)
        old_global = getattr(builtins, key, None)
        try:
            main_thread._dispatcher = None
            setattr(builtins, key, sentinel)
            self.assertIs(main_thread.get_dispatcher(), sentinel)
        finally:
            main_thread._dispatcher = old_local
            if had_old_global:
                setattr(builtins, key, old_global)
            elif hasattr(builtins, key):
                delattr(builtins, key)


class TestFreecadActionsSet(unittest.TestCase):
    """Verify _FREECAD_ACTIONS is consistent with the handler registry."""

    def test_all_freecad_actions_have_handlers(self):
        from RouterKing.ai.actions import _ACTION_HANDLERS

        for action_type in _FREECAD_ACTIONS:
            self.assertIn(
                action_type,
                _ACTION_HANDLERS,
                f"{action_type} in _FREECAD_ACTIONS but not in _ACTION_HANDLERS",
            )

    def test_machine_actions_not_in_freecad_set(self):
        """Machine/GRBL actions should NOT be dispatched to the main thread."""
        from RouterKing.ai.actions import _ACTION_HANDLERS

        for action_type in _ACTION_HANDLERS:
            if action_type.startswith("machine_"):
                self.assertNotIn(
                    action_type,
                    _FREECAD_ACTIONS,
                    f"{action_type} is a machine action but listed in _FREECAD_ACTIONS",
                )


class TestExecuteActionsDispatch(unittest.TestCase):
    """execute_actions dispatches FreeCAD actions through run_on_main_thread."""

    def test_unknown_action_still_reports_error(self):
        results, errors = execute_actions([{"type": "not_a_real_action"}])
        self.assertEqual(results, [])
        self.assertIn("Unsupported action: not_a_real_action", errors)

    def test_empty_actions(self):
        results, errors = execute_actions([])
        self.assertEqual(results, [])
        self.assertEqual(errors, [])

    def test_invalid_payload(self):
        results, errors = execute_actions(["not_a_dict"])
        self.assertEqual(results, [])
        self.assertEqual(len(errors), 1)


if __name__ == "__main__":
    unittest.main()
