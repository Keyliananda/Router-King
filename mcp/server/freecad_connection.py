"""Connection layer between MCP-facing tools and the RouterKing bridge."""

from __future__ import annotations

import json
import logging
import os
import socket
from dataclasses import dataclass
from typing import Any, Callable, Dict

from mcp.server.schemas import make_response

from RouterKing.mcp.bridge import RouterKingBridge

LOG = logging.getLogger("routerking.mcp.connection")

SUPPORTED_MODES = {"embedded", "socket"}


@dataclass(frozen=True)
class FreeCADConnectionConfig:
    mode: str = "embedded"
    host: str = "127.0.0.1"
    port: int = 4400

    @classmethod
    def from_env(cls) -> "FreeCADConnectionConfig":
        return cls(
            mode=os.getenv("ROUTERKING_MCP_MODE", "embedded"),
            host=os.getenv("ROUTERKING_MCP_HOST", "127.0.0.1"),
            port=int(os.getenv("ROUTERKING_MCP_PORT", "4400")),
        )


class FreeCADConnection:
    """Unified connection to FreeCAD supporting embedded and socket modes.

    Embedded mode: calls the RouterKingBridge directly in-process.
    Socket mode: sends JSON-RPC requests to a running FreeCAD instance
    listening on host:port.
    """

    def __init__(
        self,
        config: FreeCADConnectionConfig | None = None,
        *,
        bridge_factory: Callable[[], RouterKingBridge] | None = None,
    ) -> None:
        self.config = config or FreeCADConnectionConfig.from_env()
        self._bridge_factory = bridge_factory or RouterKingBridge
        self._bridge = None

    def ping(self) -> Dict[str, Any]:
        if self.config.mode == "embedded":
            return self._ping_embedded()
        if self.config.mode == "socket":
            return self._ping_socket()
        return self._unsupported_mode_response("ping")

    def invoke(self, operation: str, /, **kwargs: Any) -> Dict[str, Any]:
        if self.config.mode == "embedded":
            return self._invoke_embedded(operation, **kwargs)
        if self.config.mode == "socket":
            return self._invoke_socket(operation, **kwargs)
        return self._unsupported_mode_response(operation)

    # -- embedded mode ---------------------------------------------------------

    def _ping_embedded(self) -> Dict[str, Any]:
        bridge = self._get_bridge()
        status = bridge.healthcheck()
        success = bool(status.get("freecad_available"))
        message = "FreeCAD bridge reachable." if success else "FreeCAD bridge unavailable."
        return make_response(success, message, data=status, errors=status.get("errors") or [])

    def _invoke_embedded(self, operation: str, **kwargs: Any) -> Dict[str, Any]:
        bridge = self._get_bridge()
        handler = getattr(bridge, operation, None)
        if handler is None:
            message = f"Unknown FreeCAD bridge operation: {operation}"
            return make_response(False, message, data={"operation": operation}, errors=[message])
        return handler(**kwargs)

    def _get_bridge(self) -> RouterKingBridge:
        if self._bridge is None:
            self._bridge = self._bridge_factory()
        return self._bridge

    # -- socket mode -----------------------------------------------------------

    def _ping_socket(self) -> Dict[str, Any]:
        try:
            result = self._rpc_call("ping")
        except ConnectionError as exc:
            message = f"FreeCAD socket unreachable at {self.config.host}:{self.config.port}: {exc}"
            return make_response(
                False,
                message,
                data={"mode": "socket", "host": self.config.host, "port": self.config.port},
                errors=[message],
            )
        success = bool(result.get("freecad_available", result.get("success", False)))
        message = "FreeCAD socket reachable." if success else "FreeCAD socket ping failed."
        return make_response(success, message, data=result, errors=result.get("errors") or [])

    def _invoke_socket(self, operation: str, **kwargs: Any) -> Dict[str, Any]:
        try:
            return self._rpc_call(operation, **kwargs)
        except ConnectionError as exc:
            message = f"Socket call '{operation}' failed: {exc}"
            return make_response(
                False,
                message,
                data={"mode": "socket", "operation": operation},
                errors=[message],
            )

    def _rpc_call(self, method: str, **params: Any) -> Dict[str, Any]:
        """Send a JSON-RPC-style request over a TCP socket and return the parsed response."""
        request = json.dumps({"method": method, "params": params}).encode("utf-8")
        try:
            sock = socket.create_connection(
                (self.config.host, self.config.port),
                timeout=10.0,
            )
        except OSError as exc:
            raise ConnectionError(f"Cannot connect to {self.config.host}:{self.config.port}: {exc}") from exc

        try:
            # Length-prefixed framing: 4-byte big-endian length + payload.
            sock.sendall(len(request).to_bytes(4, "big") + request)

            # Read response length.
            length_bytes = _recv_exact(sock, 4)
            if length_bytes is None:
                raise ConnectionError("Connection closed before response length was received.")
            response_length = int.from_bytes(length_bytes, "big")
            if response_length <= 0 or response_length > 16 * 1024 * 1024:
                raise ConnectionError(f"Invalid response length: {response_length}")

            # Read response body.
            body = _recv_exact(sock, response_length)
            if body is None:
                raise ConnectionError("Connection closed before full response was received.")
        finally:
            sock.close()

        try:
            response = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ConnectionError(f"Malformed response from FreeCAD: {exc}") from exc

        if not isinstance(response, dict):
            raise ConnectionError(f"Expected dict response, got {type(response).__name__}.")

        return response

    # -- helpers ---------------------------------------------------------------

    def _unsupported_mode_response(self, operation: str) -> Dict[str, Any]:
        message = (
            f"FreeCAD connection mode '{self.config.mode}' is not supported. "
            f"Supported modes: {', '.join(sorted(SUPPORTED_MODES))}."
        )
        return make_response(
            False,
            message,
            data={"mode": self.config.mode, "operation": operation},
            errors=[message],
        )


def _recv_exact(sock: socket.socket, n: int) -> bytes | None:
    """Read exactly *n* bytes from *sock*, or return None on premature EOF."""
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)

