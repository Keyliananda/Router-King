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
MACHINE_ACTION_PREFIX = "machine_"
STANDALONE_MACHINE_ENV = "ROUTERKING_MCP_ALLOW_STANDALONE_MACHINE"


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
            machine_action = _extract_machine_action(operation, kwargs)
            if machine_action is not None and not _standalone_machine_allowed():
                return self._route_machine_action_to_socket(operation, machine_action, **kwargs)
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

    def _route_machine_action_to_socket(self, operation: str, machine_action: str, **kwargs: Any) -> Dict[str, Any]:
        """Keep real machine ownership in the FreeCAD/RouterKing process.

        Embedded MCP servers run in their own Python process, so their
        GrblSender singleton is not shared with the RouterKing dock/socket
        process.  Opening serial from embedded mode can therefore steal the
        controller port from the UI.  Machine actions are routed to the
        FreeCAD socket owner unless standalone mode is explicitly enabled for
        low-level debugging.
        """
        socket_config = FreeCADConnectionConfig(
            mode="socket",
            host=self.config.host,
            port=self.config.port,
        )
        socket_connection = FreeCADConnection(socket_config, bridge_factory=self._bridge_factory)
        result = socket_connection.invoke(operation, **kwargs)
        if result.get("success") or not _is_socket_transport_failure(result, operation):
            return result

        message = (
            f"{machine_action}: embedded MCP machine control is disabled to avoid "
            "opening a second GRBL serial connection. Start/use the RouterKing "
            f"FreeCAD socket at {self.config.host}:{self.config.port}, or set "
            f"{STANDALONE_MACHINE_ENV}=1 only for explicit low-level debugging."
        )
        errors = [message]
        errors.extend(str(item) for item in (result.get("errors") or []) if str(item))
        return make_response(
            False,
            message,
            data={
                "mode": self.config.mode,
                "operation": operation,
                "machine_action": machine_action,
                "socket_result": result,
            },
            errors=errors,
        )

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


def _standalone_machine_allowed() -> bool:
    return os.getenv(STANDALONE_MACHINE_ENV, "").lower() in {"1", "true", "yes", "on"}


def _extract_machine_action(operation: str, kwargs: Dict[str, Any]) -> str | None:
    if operation.startswith(MACHINE_ACTION_PREFIX):
        return operation

    if operation != "apply_actions":
        return None

    payload = kwargs.get("payload") or {}
    if not isinstance(payload, dict):
        return None

    for raw_action in payload.get("actions") or []:
        if not isinstance(raw_action, dict):
            continue
        action_type = str(raw_action.get("type") or raw_action.get("action") or "").strip()
        if action_type.startswith(MACHINE_ACTION_PREFIX):
            return action_type
    return None


def _is_socket_transport_failure(result: Dict[str, Any], operation: str) -> bool:
    data = result.get("data") or {}
    if not isinstance(data, dict):
        return False
    return data.get("mode") == "socket" and data.get("operation") == operation
