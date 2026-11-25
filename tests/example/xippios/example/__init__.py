"""The invented source ``example``, which the host's tests serve in place of a real one.

It has the files of a source that the host reads, as core 0.5.0's package contract has them:
``_client.py`` with ``SOURCE`` and ``ENV_VARS``, ``tasks.py`` and ``tasks_write.py``, and
``mcp.py`` and ``mcp_write.py``, whose ``build()`` returns the tool set. No task sends a
request: each answers from the module's own table, so a test needs no fixture and no key.
pytest finds it by the ``pythonpath`` of ``pyproject.toml``; it ships in no distribution.
"""

from xippios.example._version import __version__

__all__ = ["__version__"]
