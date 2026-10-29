"""The ``xippios-mcp`` entry point: the host's command line.

The host reads a config file that names its endpoints and groups (ADR-0026, decision 2;
``xippios.mcp.config``) and builds every endpoint's server (``xippios.mcp.servers``).
Without a transport flag it stops there: it prints one line per endpoint, its name,
read or write, its tool count and its packages, and exits 0, so an operator checks a
config before serving it (gap, row 309). A refusal ends the process like an argparse
error: the message on stderr, exit status 2, nothing served (ADR-0014, decision 8). The
transports come with the next step.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from xippios.core import ConfigError

from xippios.mcp.config import load_config
from xippios.mcp.servers import build_all

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
        help=(
            "the TOML file that names the endpoints and groups; checked, built and listed, "
            "one line per endpoint"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Parse the command line, load the config and build every endpoint.

    Args:
        argv: Arguments without the program name, e.g. ``["--config", "host.toml"]``;
            defaults to ``sys.argv[1:]``.
    """
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        built = build_all(config)
    except (ConfigError, ValueError) as exc:
        parser.error(str(exc))
    for name, endpoint in config.endpoints.items():
        server = built[name]
        kind = "write" if server.write else "read"
        slugs = ", ".join(ref.slug for ref in endpoint.packages)
        sys.stdout.write(f"{name}: {kind}, {len(server.tools)} tools of {slugs}\n")
