"""GRBL sender for RouterKing."""

import collections
import queue
import threading
import time

try:
    from ..vendor import import_serial
except ImportError:
    from vendor import import_serial


class GrblSender:
    def __init__(self):
        self._connected = False
        self._serial_module = import_serial()
        self._serial = None
        self._rx_queue = queue.Queue()
        self._stop_event = threading.Event()
        self._reader_thread = None
        self._lock = threading.Lock()
        self._stream_queue = collections.deque()
        self._streaming = False
        self._paused = False
        self._awaiting_ok = False
        self._total_lines = 0
        self._sent_lines = 0
        self._acked_lines = 0
        self._last_error = None
        self._status_line = None
        self._status_data = None
        self._disconnect_reason = None

    def connect(self, port, baudrate=115200, timeout=0.1, handshake_timeout=1.0):
        """Connect to the GRBL controller over serial."""
        if not port:
            raise ValueError("Port is required")
        with self._lock:
            if self._connected:
                return
            try:
                self._serial = self._serial_module.Serial(
                    port=port,
                    baudrate=baudrate,
                    timeout=timeout,
                    write_timeout=timeout,
                )
                initial_lines = self._perform_handshake(handshake_timeout)
            except Exception:
                self._close_serial_unlocked()
                raise
            self._disconnect_reason = None
            self._last_error = None
            self._status_line = None
            self._status_data = None
            self._stop_event.clear()
            self._reader_thread = threading.Thread(
                target=self._reader_loop,
                name="RouterKingGrblReader",
                daemon=True,
            )
            self._connected = True
            self._reader_thread.start()
            for line in initial_lines:
                self._rx_queue.put(line)

    def disconnect(self):
        """Disconnect from the controller."""
        with self._lock:
            if not self._connected:
                return
            self.stop_stream()
            self._stop_event.set()
            reader_thread = self._reader_thread
            self._reader_thread = None
            self._close_serial_unlocked()
            self._connected = False
            self._disconnect_reason = None
        if reader_thread is not None and reader_thread is not threading.current_thread():
            reader_thread.join(timeout=1.0)

    def send_line(self, line):
        """Send a single line of G-code or a GRBL command."""
        if not line:
            return
        payload = f"{line.rstrip()}\n".encode("ascii", errors="replace")
        self._write(payload)

    def send_realtime_command(self, command):
        """Send a GRBL realtime command without newline."""
        if isinstance(command, str):
            payload = command.encode("ascii", errors="replace")
        else:
            payload = command
        self._write(payload)

    def send_soft_reset(self):
        """Send GRBL soft reset."""
        self.send_realtime_command(b"\x18")

    def request_status(self):
        """Request a GRBL status report."""
        self.send_realtime_command("?")

    def drain_lines(self, limit=None):
        """Return any received lines without blocking."""
        lines = []
        while limit is None or len(lines) < limit:
            try:
                lines.append(self._rx_queue.get_nowait())
            except queue.Empty:
                break
        return lines

    def poll(self):
        """Drain received lines and update sender state."""
        lines = self.drain_lines()
        for line in lines:
            self._handle_line(line)
        return lines

    def is_connected(self):
        return self._connected

    def is_streaming(self):
        return self._streaming

    def is_paused(self):
        return self._paused

    def get_progress(self):
        return {
            "streaming": self._streaming,
            "paused": self._paused,
            "awaiting_ok": self._awaiting_ok,
            "sent": self._sent_lines,
            "acked": self._acked_lines,
            "total": self._total_lines,
            "last_error": self._last_error,
        }

    def get_status(self):
        return self._status_data

    def get_disconnect_reason(self):
        return self._disconnect_reason

    def start_stream(self, lines):
        """Start streaming a list of G-code lines."""
        if not self._connected or self._serial is None:
            raise RuntimeError("Not connected")
        self._stream_queue.clear()
        self._stream_queue.extend(line for line in lines if line)
        self._total_lines = len(self._stream_queue)
        self._sent_lines = 0
        self._acked_lines = 0
        self._last_error = None
        self._paused = False
        self._streaming = self._total_lines > 0
        self._awaiting_ok = False
        if self._streaming:
            self._send_next_line()

    def pause_stream(self):
        if self._streaming:
            self.send_realtime_command("!")
            self._paused = True

    def resume_stream(self):
        if self._streaming:
            self.send_realtime_command("~")
            self._paused = False
            self._send_next_line()

    def stop_stream(self):
        self._stream_queue.clear()
        self._streaming = False
        self._paused = False
        self._awaiting_ok = False

    def abort_stream(self):
        self.stop_stream()
        if self._connected:
            self.send_soft_reset()

    def _write(self, payload):
        with self._lock:
            if not self._connected or self._serial is None:
                raise RuntimeError("Not connected")
            self._serial.write(payload)
            self._serial.flush()

    def _perform_handshake(self, handshake_timeout):
        if self._serial is None:
            raise RuntimeError("Serial device not available")
        try:
            if hasattr(self._serial, "reset_input_buffer"):
                self._serial.reset_input_buffer()
        except Exception:
            pass
        self._serial.write(b"\r\n\r\n")
        self._serial.flush()
        time.sleep(0.1)
        self._serial.write(b"?")
        self._serial.flush()

        deadline = time.time() + max(handshake_timeout, 0.1)
        buffer = b""
        initial_lines = []
        while time.time() < deadline:
            chunk = self._serial.read(128)
            if not chunk:
                continue
            buffer += chunk
            decoded = buffer.decode("utf-8", errors="replace")
            initial_lines = [line.strip() for line in decoded.splitlines() if line.strip()]
            if self._contains_grbl_signature(initial_lines):
                return initial_lines
        raise RuntimeError("No GRBL response detected on serial port")

    def _handle_line(self, line):
        if line.startswith("<") and line.endswith(">"):
            self._status_line = line
            self._status_data = self._parse_status_line(line)
            return
        if line.lower().startswith("ok"):
            if self._streaming:
                self._acked_lines += 1
                self._awaiting_ok = False
                self._send_next_line()
            return
        if line.lower().startswith("error") or line.lower().startswith("alarm"):
            self._last_error = line
            self._streaming = False
            self._paused = False
            self._awaiting_ok = False
            return

    def _send_next_line(self):
        if not self._streaming or self._paused or self._awaiting_ok:
            return
        if not self._stream_queue:
            self._streaming = False
            return
        line = self._stream_queue.popleft()
        if not line:
            self._send_next_line()
            return
        self.send_line(line)
        self._sent_lines += 1
        self._awaiting_ok = True

    @staticmethod
    def _parse_status_line(line):
        if not (line.startswith("<") and line.endswith(">")):
            return None
        body = line[1:-1]
        parts = body.split("|")
        data = {"state": parts[0]} if parts else {"state": "?"}
        for part in parts[1:]:
            if ":" not in part:
                continue
            key, value = part.split(":", 1)
            data[key] = value
        return data

    def _reader_loop(self):
        while not self._stop_event.is_set():
            try:
                if self._serial is None:
                    break
                raw = self._serial.readline()
            except Exception as exc:
                self._mark_connection_lost(exc)
                break
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").strip()
            if line:
                self._rx_queue.put(line)

    def _mark_connection_lost(self, exc):
        message = f"[serial error] {exc}"
        with self._lock:
            self._stream_queue.clear()
            self._streaming = False
            self._paused = False
            self._awaiting_ok = False
            self._connected = False
            self._disconnect_reason = message
            self._last_error = message
            self._stop_event.set()
            self._close_serial_unlocked()
        self._rx_queue.put(message)

    def _close_serial_unlocked(self):
        if self._serial is None:
            return
        try:
            self._serial.close()
        finally:
            self._serial = None

    @staticmethod
    def _contains_grbl_signature(lines):
        for line in lines:
            if "grbl" in line.lower():
                return True
            if line.startswith("<") and line.endswith(">"):
                return True
        return False
