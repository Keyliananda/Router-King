"""Connection layer between MCP-facing tools and the RouterKing bridge."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Dict

from mcp.server.schemas import make_response

from RouterKing.mcp.bridge import RouterKingBridge


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
        if self.config.mode != "embedded":
            message = (
                f"FreeCAD connection mode '{self.config.mode}' is not implemented yet. "
                "Use embedded mode for the current MVP slice."
            )
            return make_response(
                False,
                message,
                data={"mode": self.config.mode, "host": self.config.host, "port": self.config.port},
                errors=[message],
            )

        bridge = self._get_bridge()
        status = bridge.healthcheck()
        success = bool(status.get("freecad_available"))
        message = "FreeCAD bridge reachable." if success else "FreeCAD bridge unavailable."
        return make_response(success, message, data=status, errors=status.get("errors") or [])

    def invoke(self, operation: str, /, **kwargs: Any) -> Dict[str, Any]:
        if self.config.mode != "embedded":
            message = (
                f"FreeCAD connection mode '{self.config.mode}' cannot execute '{operation}'. "
                "Only embedded mode is available in this implementation."
            )
            return make_response(
                False,
                message,
                data={"mode": self.config.mode, "operation": operation},
                errors=[message],
            )

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

