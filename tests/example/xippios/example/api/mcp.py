"""MCP server of the invented nested source ``example-api``, as core 0.5.0's contract has it."""

from xippios.core.mcp import ToolSet, build_server, main
from xippios.example.api import tasks
from xippios.example.api._client import ENV_VARS, SOURCE
from xippios.example.api._version import __version__

__all__ = ["ENV_VARS", "SOURCE", "build", "run", "server"]


def build() -> ToolSet:
    """The read tool set: the tasks with what ``tasks.py`` declares for the server."""
    return ToolSet.from_tasks(SOURCE, tasks, version=__version__)


server = build_server(build())


def run() -> None:
    """Run the server: stdio by default, ``--http`` for streamable HTTP."""
    main(build)
