import unittest

from RouterKing.vendor import import_serial


class TestVendoredPyserial(unittest.TestCase):
    def test_import_serial(self):
        serial = import_serial()
        self.assertTrue(hasattr(serial, "Serial"))


if __name__ == "__main__":
    unittest.main()
