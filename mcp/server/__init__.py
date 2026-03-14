"""RouterKing MCP server modules.

The initial implementation keeps transport and domain logic separate:

- ``mcp.server.*`` contains tool schemas, safety checks, and server-facing adapters.
- ``RouterKing.mcp.*`` contains the FreeCAD/RouterKing bridge that can run inside
  the FreeCAD Python environment.

This first slice uses an embedded connection mode. A later RPC/socket layer can
replace the connection backend without changing the tool modules.
"""

