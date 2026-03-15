"""Tests for socket transport in FreeCADConnection."""

import json
import socket
import threading
import unittest

from mcp.server.freecad_connection import FreeCADConnection, FreeCADConnectionConfig, _recv_exact


class TestSocketTransportConfig(unittest.TestCase):
    def test_unsupported_mode_returns_error(self):
        config = FreeCADConnectionConfig(mode="magic")
        conn = FreeCADConnection(config)
        result = conn.ping()
        self.assertFalse(result["success"])
        self.assertIn("not supported", result["message"])

    def test_unsupported_mode_invoke_returns_error(self):
        config = FreeCADConnectionConfig(mode="magic")
        conn = FreeCADConnection(config)
        result = conn.invoke("list_actions")
        self.assertFalse(result["success"])
        self.assertIn("not supported", result["message"])

    def test_embedded_mode_still_works(self):
        """Embedded mode should still dispatch to the bridge factory."""
        class StubBridge:
            def healthcheck(self):
                return {"freecad_available": True, "active_document": "Test", "errors": []}

        config = FreeCADConnectionConfig(mode="embedded")
        conn = FreeCADConnection(config, bridge_factory=StubBridge)
        result = conn.ping()
        self.assertTrue(result["success"])
        self.assertEqual(result["message"], "FreeCAD bridge reachable.")


class TestSocketTransportConnection(unittest.TestCase):
    """Test socket mode with a real local TCP server."""

    def _start_server(self, response_payload):
        """Start a TCP server that replies with a length-prefixed JSON payload."""
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(("127.0.0.1", 0))
        server_sock.listen(1)
        port = server_sock.getsockname()[1]

        def handler():
            conn, _ = server_sock.accept()
            try:
                # Read request length + body (we don't need to parse it).
                length_bytes = conn.recv(4)
                if length_bytes:
                    req_length = int.from_bytes(length_bytes, "big")
                    conn.recv(req_length)

                # Send response.
                body = json.dumps(response_payload).encode("utf-8")
                conn.sendall(len(body).to_bytes(4, "big") + body)
            finally:
                conn.close()
                server_sock.close()

        thread = threading.Thread(target=handler, daemon=True)
        thread.start()
        return port, thread

    def test_ping_socket_success(self):
        port, thread = self._start_server({"freecad_available": True, "errors": []})
        config = FreeCADConnectionConfig(mode="socket", host="127.0.0.1", port=port)
        conn = FreeCADConnection(config)
        result = conn.ping()
        thread.join(timeout=2)
        self.assertTrue(result["success"])
        self.assertEqual(result["message"], "FreeCAD socket reachable.")

    def test_ping_socket_failure(self):
        port, thread = self._start_server({"freecad_available": False, "errors": ["not ready"]})
        config = FreeCADConnectionConfig(mode="socket", host="127.0.0.1", port=port)
        conn = FreeCADConnection(config)
        result = conn.ping()
        thread.join(timeout=2)
        self.assertFalse(result["success"])

    def test_invoke_socket_returns_response(self):
        expected = {"success": True, "message": "ok", "data": {"actions": []}, "errors": []}
        port, thread = self._start_server(expected)
        config = FreeCADConnectionConfig(mode="socket", host="127.0.0.1", port=port)
        conn = FreeCADConnection(config)
        result = conn.invoke("list_actions")
        thread.join(timeout=2)
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["actions"], [])

    def test_invoke_socket_connection_refused(self):
        # Use a port that nothing is listening on.
        config = FreeCADConnectionConfig(mode="socket", host="127.0.0.1", port=1)
        conn = FreeCADConnection(config)
        result = conn.invoke("list_actions")
        self.assertFalse(result["success"])
        self.assertIn("failed", result["message"])


class TestRecvExact(unittest.TestCase):
    def test_recv_exact_returns_none_on_empty(self):
        # Create a socket pair to test _recv_exact.
        a, b = socket.socketpair()
        b.close()  # Close writer so reader gets EOF.
        result = _recv_exact(a, 4)
        a.close()
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
