import collections
import time
import unittest

from RouterKing.grbl.sender import GrblSender


class FakeSerial:
    def __init__(self, handshake_chunks=None, fail_on_read=False):
        self._handshake_chunks = collections.deque(handshake_chunks or [])
        self._fail_on_read = fail_on_read
        self.writes = []
        self.closed = False

    def reset_input_buffer(self):
        return None

    def write(self, payload):
        self.writes.append(payload)
        return len(payload)

    def flush(self):
        return None

    def read(self, _size):
        if self.closed:
            raise OSError("port closed")
        if self._handshake_chunks:
            return self._handshake_chunks.popleft()
        return b""

    def readline(self):
        if self.closed:
            raise OSError("port closed")
        if self._fail_on_read:
            raise OSError("serial lost")
        time.sleep(0.01)
        return b""

    def close(self):
        self.closed = True


class FakeSerialModule:
    def __init__(self, serial_instance):
        self._serial_instance = serial_instance
        self.kwargs = None

    def Serial(self, **kwargs):
        self.kwargs = kwargs
        return self._serial_instance


class TestGrblSender(unittest.TestCase):
    def make_sender(self, serial_instance):
        sender = GrblSender()
        sender._serial_module = FakeSerialModule(serial_instance)
        return sender

    def test_connect_requires_grbl_signature(self):
        serial_instance = FakeSerial([b"Grbl 1.1h ['$' for help]\n"])
        sender = self.make_sender(serial_instance)

        sender.connect("/dev/ttyUSB0")

        self.assertTrue(sender.is_connected())
        self.assertEqual(sender._serial_module.kwargs["port"], "/dev/ttyUSB0")
        sender.disconnect()

    def test_connect_rejects_non_grbl_device(self):
        serial_instance = FakeSerial([b"hello from something else\n"])
        sender = self.make_sender(serial_instance)

        with self.assertRaisesRegex(RuntimeError, "No GRBL response detected"):
            sender.connect("/dev/ttyUSB0", handshake_timeout=0.2)

        self.assertFalse(sender.is_connected())

    def test_pause_resume_use_realtime_commands(self):
        serial_instance = FakeSerial([b"<Idle|MPos:0.000,0.000,0.000>\n"])
        sender = self.make_sender(serial_instance)
        sender.connect("/dev/ttyUSB0")

        sender.start_stream(["G1 X1", "G1 X2"])
        self.assertIn(b"G1 X1\n", serial_instance.writes)

        sender.pause_stream()
        self.assertTrue(sender.is_paused())
        self.assertEqual(serial_instance.writes[-1], b"!")

        sender._rx_queue.put("ok")
        sender.poll()
        self.assertNotIn(b"G1 X2\n", serial_instance.writes)

        sender.resume_stream()
        self.assertFalse(sender.is_paused())
        self.assertEqual(serial_instance.writes[-2:], [b"~", b"G1 X2\n"])

        sender.disconnect()

    def test_abort_stream_sends_soft_reset(self):
        serial_instance = FakeSerial([b"<Idle|MPos:0.000,0.000,0.000>\n"])
        sender = self.make_sender(serial_instance)
        sender.connect("/dev/ttyUSB0")

        sender.start_stream(["G1 X1", "G1 X2"])
        sender.abort_stream()

        self.assertFalse(sender.is_streaming())
        self.assertIn(b"\x18", serial_instance.writes)
        sender.disconnect()

    def test_disconnect_clears_status_and_progress(self):
        serial_instance = FakeSerial([b"<Idle|MPos:0.000,0.000,0.000>\n"])
        sender = self.make_sender(serial_instance)
        sender.connect("/dev/ttyUSB0")

        sender.poll()
        sender.start_stream(["G1 X1", "G1 X2"])
        sender.disconnect()

        progress = sender.get_progress()
        self.assertFalse(sender.is_connected())
        self.assertIsNone(sender.get_status())
        self.assertEqual(progress["total"], 0)
        self.assertEqual(progress["sent"], 0)
        self.assertEqual(progress["acked"], 0)
        self.assertIsNone(progress["last_error"])

    def test_serial_failure_marks_sender_disconnected(self):
        serial_instance = FakeSerial([b"<Idle|MPos:0.000,0.000,0.000>\n"], fail_on_read=True)
        sender = self.make_sender(serial_instance)
        sender.connect("/dev/ttyUSB0")
        sender.poll()
        sender.start_stream(["G1 X1", "G1 X2"])

        deadline = time.time() + 1.0
        while sender.is_connected() and time.time() < deadline:
            time.sleep(0.02)

        self.assertFalse(sender.is_connected())
        self.assertIsNone(sender.get_status())
        self.assertIn("serial lost", sender.get_disconnect_reason())
        progress = sender.get_progress()
        self.assertEqual(progress["total"], 0)
        self.assertEqual(progress["sent"], 0)
        self.assertEqual(progress["acked"], 0)
        self.assertIn("serial lost", progress["last_error"])
        lines = sender.poll()
        self.assertTrue(any("serial error" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
