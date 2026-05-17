import importlib
import unittest


class TestGrblManager(unittest.TestCase):
    def test_sender_singleton_is_process_global(self):
        manager = importlib.import_module("RouterKing.grbl.manager")
        original = manager.get_sender(create=False)
        sender = object()
        try:
            manager.set_sender(sender)
            reloaded = importlib.reload(manager)
            self.assertIs(reloaded.get_sender(create=False), sender)
        finally:
            manager.set_sender(original)


if __name__ == "__main__":
    unittest.main()
