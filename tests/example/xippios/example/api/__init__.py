"""The invented nested source ``example-api`` (``xippios.example.api``), for a group.

A second, smaller read source beside ``example``, its slug with a hyphen as a nested source's
is, so its tools are named ``example_api_<task>``. It has no write server.
"""

from xippios.example.api._version import __version__

__all__ = ["__version__"]
