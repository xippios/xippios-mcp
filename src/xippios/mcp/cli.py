"""The ``xippios-mcp`` entry point: the host's command line.

The host reads a config file that names its endpoints and groups (ADR-0026, decision 2;
``xippios.mcp.config``) and builds every endpoint's server (``xippios.mcp.servers``).
Then it serves them, or checks and lists them (gap, row 310 (e)):

- ``--stdio ENDPOINT`` serves that one endpoint on stdio, without auth and without
  reading a token variable: stdio is the client's own child process.
- ``--http`` serves every endpoint over streamable HTTP at ``/<name>/mcp`` on ``--host``
  (default ``127.0.0.1``) and ``--port`` (default 8000), each with its own auth
  (``xippios.mcp.app``).
- Without either it stops after the build: it prints one line per endpoint, its name,
  read or write, its tool count and its packages, and exits 0, so an operator checks a
  config before serving it (gap, row 309 (b)).

A refusal ends the process like an argparse error: the message on stderr, exit status
2, nothing served (ADR-0014, decision 8).
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from xippios.core import ConfigError

# Outside core's public surface: queue row 297 decides whether core 0.4.0 exports
# quiet_request_logging from xippios.core.mcp.
from xippios.core.mcp.server import quiet_request_logging

from xippios.mcp.app import build_app, serve_http
from xippios.mcp.config import HostConfig, load_config
from xippios.mcp.servers import BuildError, Built, build_all

__all__ = ["main"]

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def _parser() -> argparse.ArgumentParser:
    """The command line ``main`` accepts."""
    parser = argparse.ArgumentParser(
        prog="xippios-mcp",
        description=(
            "Serve the MCP tools of the xippios packages by endpoint and group. Without "
            "--stdio or --http, check the config and list one line per endpoint."
        ),
    )
    parser.add_argument(
        "--config",
        required=True,
        type=Path,
        metavar="PATH",
        help="the TOML file that names the endpoints and groups",
    )
    transport = parser.add_mutually_exclusive_group()
    transport.add_argument(
        "--stdio",
        metavar="ENDPOINT",
        help="serve this one endpoint on stdio, without auth",
    )
    transport.add_argument(
        "--http",
        action="store_true",
        help="serve every endpoint over streamable HTTP at /<endpoint>/mcp",
    )
    parser.add_argument("--host", help=f"bind address for --http (default {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, help=f"port for --http (default {DEFAULT_PORT})")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Parse the command line, load and build the config, then serve or list it.

    ``--help`` exits 0, and a missing ``--config``, ``--stdio`` with ``--http``, or
    ``--host`` or ``--port`` without ``--http`` exit 2, as argparse does; a config the
    host refuses exits 2 as well, the refusal on stderr. Without ``--stdio`` or
    ``--http`` a good config prints one line per endpoint and returns.

    Args:
        argv: Arguments without the program name, e.g.
            ``["--config", "host.toml", "--stdio", "agriculture"]``; defaults to
            ``sys.argv[1:]``.
    """
    parser = _parser()
    args = parser.parse_args(argv)
    if not args.http and (args.host is not None or args.port is not None):
        parser.error("--host and --port apply to --http only")
    host = DEFAULT_HOST if args.host is None else args.host
    port = DEFAULT_PORT if args.port is None else args.port
    try:
        config = load_config(args.config)
        if args.stdio is not None and args.stdio not in config.endpoints:
            raise ConfigError(
                f"{config.path}: --stdio {args.stdio}: no endpoint of the config; the "
                f"configured ones: {', '.join(config.endpoints)}"
            )
        built = build_all(config)
        app = build_app(config, built, host=host) if args.http else None
    except (ConfigError, BuildError) as exc:
        parser.error(str(exc))
    if args.stdio is not None:
        server = built[args.stdio].server
        quiet_request_logging()
        server.run(transport="stdio")
    elif app is not None:
        quiet_request_logging()
        serve_http(app, host, port)
    else:
        _list(config, built)


def _list(config: HostConfig, built: dict[str, Built]) -> None:
    """Print one line per endpoint: its name, read or write, its tools and packages."""
    for name, endpoint in config.endpoints.items():
        server = built[name]
        kind = "write" if server.write else "read"
        slugs = ", ".join(ref.slug for ref in endpoint.packages)
        sys.stdout.write(f"{name}: {kind}, {len(server.tools)} tools of {slugs}\n")
