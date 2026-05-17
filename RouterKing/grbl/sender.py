"""GRBL sender for RouterKing."""

import collections
import queue
import re
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
        # Separate queue for $-setting and $I info responses
        self._settings_queue = queue.Queue()
        self._collecting_settings = False

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
            self.stop_stream(reset_progress=True)
            self._stop_event.set()
            reader_thread = self._reader_thread
            self._reader_thread = None
            self._status_line = None
            self._status_data = None
            self._last_error = None
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

    def cancel_jog(self):
        """Cancel an active GRBL jog motion."""
        self.send_realtime_command(b"\x85")

    def request_status(self):
        """Request a GRBL status report."""
        self.send_realtime_command("?")

    def send_and_collect(self, command, timeout=2.0):
        """Send a command (like $$ or $I) and collect all response lines.

        Returns a list of response lines.  Blocks up to *timeout* seconds
        waiting for the final ``ok`` that GRBL sends after the output.
        """
        effective_timeout = float(timeout)
        probe_timeout = self._calculate_probe_timeout(command)
        if probe_timeout is not None:
            effective_timeout = max(effective_timeout, probe_timeout)

        # Drain any stale settings
        while not self._settings_queue.empty():
            try:
                self._settings_queue.get_nowait()
            except queue.Empty:
                break

        self._collecting_settings = True
        try:
            self.send_line(command)
            lines = []
            deadline = time.time() + effective_timeout
            while time.time() < deadline:
                try:
                    item = self._settings_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                if item == "__SETTINGS_OK__":
                    break
                if item.startswith("__SETTINGS_ERROR__:"):
                    lines.append(item.replace("__SETTINGS_ERROR__:", ""))
                    break
                lines.append(item)
            return lines
        finally:
            self._collecting_settings = False

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
        """Drain received lines for UI/consumer use.

        Note: _handle_line is already called in the reader thread, so we
        only drain the queue here without re-processing.
        """
        return self.drain_lines()

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

    def stop_stream(self, reset_progress=False):
        self._stream_queue.clear()
        self._streaming = False
        self._paused = False
        self._awaiting_ok = False
        if reset_progress:
            self._total_lines = 0
            self._sent_lines = 0
            self._acked_lines = 0

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
        # Route $-settings and $I info lines to the settings queue
        if self._collecting_settings:
            if self._is_collect_response_line(line):
                self._settings_queue.put(line)
                return
            if line.lower().startswith("ok"):
                # End of settings block
                self._settings_queue.put("__SETTINGS_OK__")
                if self._streaming:
                    self._acked_lines += 1
                    self._awaiting_ok = False
                    self._send_next_line()
                return
        if line.lower().startswith("ok"):
            if self._streaming:
                self._acked_lines += 1
                self._awaiting_ok = False
                self._send_next_line()
            return
        if line.lower().startswith("error") or line.lower().startswith("alarm"):
            self._last_error = line
            if self._collecting_settings:
                self._settings_queue.put(f"__SETTINGS_ERROR__:{line}")
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
                # Process streaming-critical lines immediately in the reader
                # thread so streaming doesn't stall waiting for poll().
                # The line is still queued for UI/poll consumers.
                self._handle_line(line)
                self._rx_queue.put(line)

    def _mark_connection_lost(self, exc):
        message = f"[serial error] {exc}"
        with self._lock:
            self.stop_stream(reset_progress=True)
            self._status_line = None
            self._status_data = None
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
    def _is_collect_response_line(line):
        if line.startswith("$") or line.startswith("Grbl"):
            return True
        if line.startswith("[PRB:"):
            return True
        if line.startswith("["):
            return True
        return False

    @staticmethod
    def _calculate_probe_timeout(command):
        text = str(command or "")
        if not re.search(r"\bG38(?:\.\d+)?\b", text, flags=re.IGNORECASE):
            return None

        axis_values = [abs(float(value)) for value in re.findall(r"\b[XYZ]\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))", text, flags=re.IGNORECASE)]
        feed_matches = re.findall(r"\bF\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))", text, flags=re.IGNORECASE)
        if not axis_values or not feed_matches:
            return None
        try:
            distance = max(axis_values)
            feed = abs(float(feed_matches[-1]))
        except Exception:
            return None
        if distance <= 0.0 or feed <= 0.0:
            return None
        return (distance / feed) * 60.0 + 10.0

    @staticmethod
    def _contains_grbl_signature(lines):
        for line in lines:
            if "grbl" in line.lower():
                return True
            if line.startswith("<") and line.endswith(">"):
                return True
        return False
