"""MCP server of the invented source ``example``, as core 0.5.0's package contract has it.

``build()`` returns the read tool set that core builds from ``tasks.py``, and ``server`` is
built from it; ``run`` is the entry point, which no test of the host runs.
"""

from xippios.core.mcp import ToolSet, build_server, main
from xippios.example import tasks
from xippios.example._client import ENV_VARS, SOURCE
from xippios.example._version import __version__

__all__ = ["ENV_VARS", "SOURCE", "build", "run", "server"]


def build() -> ToolSet:
    """The read tool set: the tasks with what ``tasks.py`` declares for the server."""
    return ToolSet.from_tasks(SOURCE, tasks, version=__version__)


server = build_server(build())


def run() -> None:
    """Run the server: stdio by default, ``--http`` for streamable HTTP."""
    main(build)
