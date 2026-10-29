"""The ``xippios-mcp`` entry point: the host's command line.

The host reads a config file that names its endpoints and groups (ADR-0026, decision 2).
The config loader, the transports and the bearer come in the next steps; until then
``--config`` stops with exit status 2, so nothing pretends to serve.
"""

import argparse
from collections.abc import Sequence
from pathlib import Path

__all__ = ["main"]


def _parser() -> argparse.ArgumentParser:
    """The command line ``main`` accepts."""
    parser = argparse.ArgumentParser(
        prog="xippios-mcp",
        description="Serve the MCP tools of the xippios packages by endpoint and group.",
    )
    parser.add_argument(
        "--config",
        required=True,
        type=Path,
        metavar="PATH",
        help="the config file that names the endpoints and groups",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Parse the command line; until the config loader lands, stop with exit status 2.

    ``--help`` exits 0 and a missing ``--config`` exits 2, as argparse does; with
    ``--config`` the host stops with exit status 2 too, since nothing is served yet.

    Args:
        argv: Arguments without the program name, e.g. ``["--config", "host.toml"]``;
            defaults to ``sys.argv[1:]``.
    """
    parser = _parser()
    parser.parse_args(argv)
    parser.error("nothing is served yet: the config loader lands with the next step")
