"""Write server of the invented source ``example``, as core 0.5.0's package contract has it.

``build()`` returns the write tool set that core builds from ``tasks_write.py``, whose every
task takes ``confirm: bool = False``, and ``server`` is built from it.
"""

from xippios.core.mcp import ToolSet, build_server, main
from xippios.example import tasks_write
from xippios.example._client import ENV_VARS, SOURCE
from xippios.example._version import __version__

__all__ = ["ENV_VARS", "SOURCE", "build", "run", "server"]


def build() -> ToolSet:
    """The write tool set: the write tasks with what ``tasks_write.py`` declares."""
    return ToolSet.from_tasks(SOURCE, tasks_write, version=__version__, read_only=False)


server = build_server(build())


def run() -> None:
    """Run the write server: stdio by default, ``--http`` on loopback."""
    main(build)
