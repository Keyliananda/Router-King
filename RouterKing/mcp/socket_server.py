"""TCP socket server that runs inside FreeCAD and serves MCP bridge requests.

This server is started automatically when the RouterKing workbench is loaded.
It listens on 127.0.0.1:4400 (configurable via ROUTERKING_MCP_PORT env var)
and accepts length-prefixed JSON-RPC requests from the external MCP stdio
server process launched by Claude Desktop.

Protocol (matches FreeCADConnection._rpc_call):
  -> 4-byte big-endian length + JSON request  {"method": "...", "params": {...}}
  <- 4-byte big-endian length + JSON response  {...}
"""

from __future__ import annotations

import json
import logging
import os
import socket
import struct
import threading
import traceback
from typing import Any, Dict

LOG = logging.getLogger("routerking.mcp.socket_server")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4400


class FreeCADSocketServer:
    """Lightweight TCP server that dispatches to the RouterKingBridge."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
    ) -> None:
        self.host = host or os.getenv("ROUTERKING_MCP_HOST", DEFAULT_HOST)
        self.port = port or int(os.getenv("ROUTERKING_MCP_PORT", str(DEFAULT_PORT)))
        self._server_socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._bridge = None

    def _get_bridge(self):
        """Lazy-init the bridge so FreeCAD modules are available."""
        if self._bridge is None:
            try:
                from RouterKing.mcp.bridge import RouterKingBridge
            except ImportError:
                from mcp.bridge import RouterKingBridge
            self._bridge = RouterKingBridge()
        return self._bridge

    def start(self) -> None:
        """Start the socket server in a background daemon thread."""
        if self._running:
            LOG.warning("Socket server already running on %s:%s", self.host, self.port)
            return

        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._server_socket.bind((self.host, self.port))
        except OSError as exc:
            LOG.error("Cannot bind to %s:%s: %s", self.host, self.port, exc)
            self._server_socket.close()
            self._server_socket = None
            return

        self._server_socket.listen(4)
        self._server_socket.settimeout(1.0)  # allow periodic shutdown checks
        self._running = True

        self._thread = threading.Thread(
            target=self._accept_loop,
            name="RouterKing-MCP-SocketServer",
            daemon=True,
        )
        self._thread.start()
        LOG.info("RouterKing MCP socket server listening on %s:%s", self.host, self.port)

        try:
            import FreeCAD as App
            App.Console.PrintMessage(
                f"RouterKing MCP socket server started on {self.host}:{self.port}\n"
            )
        except Exception:
            pass

    def stop(self) -> None:
        """Stop the socket server."""
        self._running = False
        if self._server_socket is not None:
            try:
                self._server_socket.close()
            except Exception:
                pass
            self._server_socket = None
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        LOG.info("RouterKing MCP socket server stopped.")

    @property
    def is_running(self) -> bool:
        return self._running

    # -- internal ------------------------------------------------------------

    def _accept_loop(self) -> None:
        """Accept connections in a loop until stopped."""
        while self._running:
            try:
                client, addr = self._server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                if self._running:
                    LOG.exception("Accept error")
                break

            # Handle each connection in a separate thread
            handler = threading.Thread(
                target=self._handle_client,
                args=(client, addr),
                name=f"RouterKing-MCP-Client-{addr}",
                daemon=True,
            )
            handler.start()

    def _handle_client(self, client: socket.socket, addr: tuple) -> None:
        """Handle a single client connection."""
        try:
            client.settimeout(30.0)

            # Read 4-byte length prefix
            length_bytes = _recv_exact(client, 4)
            if length_bytes is None:
                return
            request_length = struct.unpack(">I", length_bytes)[0]
            if request_length <= 0 or request_length > 16 * 1024 * 1024:
                LOG.warning("Invalid request length from %s: %s", addr, request_length)
                return

            # Read request body
            body = _recv_exact(client, request_length)
            if body is None:
                LOG.warning("Connection from %s closed before full request received", addr)
                return

            # Parse and dispatch
            try:
                request = json.loads(body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                LOG.warning("Malformed request from %s: %s", addr, exc)
                response = {"success": False, "message": f"Malformed request: {exc}"}
                _send_response(client, response)
                return

            method = request.get("method", "")
            params = request.get("params", {})

            response = self._dispatch(method, params)
            _send_response(client, response)

        except Exception:
            LOG.exception("Error handling client %s", addr)
        finally:
            try:
                client.close()
            except Exception:
                pass

    def _dispatch(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch a method call to the bridge."""
        bridge = self._get_bridge()

        # Special methods
        if method == "ping":
            return bridge.healthcheck()

        # Map method names to bridge methods
        handler = getattr(bridge, method, None)
        if handler is None:
            return {
                "success": False,
                "message": f"Unknown method: {method}",
                "data": {},
                "errors": [f"Unknown method: {method}"],
            }

        try:
            return handler(**params)
        except Exception as exc:
            LOG.exception("Bridge method %s raised", method)
            return {
                "success": False,
                "message": str(exc),
                "data": {},
                "errors": [traceback.format_exc()],
            }


def _recv_exact(sock: socket.socket, n: int) -> bytes | None:
    """Read exactly *n* bytes from *sock*, or return None on premature EOF."""
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


def _send_response(client: socket.socket, response: Dict[str, Any]) -> None:
    """Send a length-prefixed JSON response."""
    payload = json.dumps(response, default=str).encode("utf-8")
    client.sendall(struct.pack(">I", len(payload)) + payload)


# -- Module-level singleton --------------------------------------------------

_server_instance: FreeCADSocketServer | None = None


def get_server() -> FreeCADSocketServer:
    """Get or create the global server instance."""
    global _server_instance
    if _server_instance is None:
        _server_instance = FreeCADSocketServer()
    return _server_instance


def start_server() -> FreeCADSocketServer:
    """Start the global server instance."""
    # Defensive init: the dispatcher should exist before socket worker threads
    # can execute FreeCAD/CAM actions.
    try:
        if threading.current_thread() is threading.main_thread():
            try:
                from RouterKing.main_thread import get_dispatcher, init_dispatcher
            except ImportError:
                from main_thread import get_dispatcher, init_dispatcher
            if get_dispatcher() is None:
                init_dispatcher()
        else:
            LOG.warning(
                "start_server called off main thread; cannot safely init MainThreadDispatcher"
            )
    except Exception as exc:
        LOG.warning("MainThreadDispatcher init check failed: %s", exc)

    server = get_server()
    if not server.is_running:
        server.start()
    return server


def stop_server() -> None:
    """Stop the global server instance."""
    global _server_instance
    if _server_instance is not None:
        _server_instance.stop()
        _server_instance = None
