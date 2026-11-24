"""The read tasks of the invented source ``example``.

``list_regions`` is a reference list with a cap of its own, ``get_series`` a series over a
region's periods that refuses an unknown code as a source does, and ``download_regions`` a
bulk task, Python-only and no tool. ``SERIES`` is the ceiling of ``get_series``, core's
``Ceiling``: 20 periods in Python, and 5 on the MCP server, whose ``--max-periods`` sets
another from 1 to 20. Its two methods are the module's option hooks, which the entry point
and a host apply, so a host that applies them at their defaults serves 5 (sdk-core ADR-0054).
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from xippios.core import Ceiling, InvalidRequestError, Result, ResultCap, ResultMeta
from xippios.example._client import SOURCE

__all__ = ["download_regions", "get_series", "list_regions"]

BULK_TASKS = frozenset({"download_regions"})

MCP_CAPS = {"list_regions": ResultCap(max_rows=400, max_bytes=100_000)}

MCP_INSTRUCTIONS = (
    "Example via xippios. Tools are read-only. Call example_list_regions first to find a "
    "region's code, then example_get_series."
)

SERIES = Ceiling(20, unit="periods", mcp=5, option="--max-periods", source=SOURCE)
"""The most periods one ``get_series`` call answers for: 20, and 5 once the hooks apply."""

mcp_add_options = SERIES.add_options  # the tool set's two hooks
mcp_apply_options = SERIES.apply_options

_RETRIEVED = datetime(2026, 11, 24, tzinfo=UTC)


class Region(BaseModel):
    """A region of the example source: its code and name."""

    code: str
    name: str


class Point(BaseModel):
    """One period of a region's series."""

    period: int
    value: float


_REGIONS = (Region(code="N", name="North"), Region(code="S", name="South"))


def _meta(endpoint: str, request: dict[str, Any]) -> ResultMeta:
    return ResultMeta(source=SOURCE, endpoint=endpoint, retrieved_at=_RETRIEVED, request=request)


def list_regions() -> Result[list[Region]]:
    """List the regions of the example source, each with its code and name.

    Call it first: get_series takes one of these codes.
    """
    return Result(data=list(_REGIONS), meta=_meta("listRegions", {}))


def get_series(region_code: str, periods: int = 3) -> Result[list[Point]]:
    """Get a region's series over its latest periods, oldest first.

    Args:
        region_code: The region's code, e.g. "N"; list_regions lists them.
        periods: How many periods, e.g. 3; at least 1 and at most the ceiling in force.
    """
    if region_code not in {region.code for region in _REGIONS}:
        raise InvalidRequestError(
            f"region_code {region_code!r}: no region of example; list_regions() lists the "
            "known values (over MCP, the tool example_list_regions).",
            source=SOURCE,
        )
    if periods < 1:
        raise InvalidRequestError(f"periods {periods}: at least 1", source=SOURCE)
    SERIES.check(periods)
    points = [Point(period=period, value=float(period)) for period in range(1, periods + 1)]
    request = {"region_code": region_code, "periods": periods}
    return Result(data=points, meta=_meta("getSeries", request))


def download_regions(dest: Path) -> Path:
    """Write the regions to ``dest`` as JSON: a bulk task, Python-only and no tool.

    Args:
        dest: The file to write, e.g. Path("regions.json").
    """
    dest.write_text(json.dumps([region.model_dump() for region in _REGIONS]), encoding="utf-8")
    return dest
