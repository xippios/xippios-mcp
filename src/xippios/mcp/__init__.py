"""Public API: ``__version__``; the host is run through its entry point, ``xippios-mcp``.

The self-hosted MCP host of the xippios SDK family: the packages' tools on one server, by
endpoint and group (ADR-0026).
"""

from xippios.mcp._version import __version__

__all__ = ["__version__"]
