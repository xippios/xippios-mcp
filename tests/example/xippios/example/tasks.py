"""The read tasks of the invented source ``example``.

``list_regions`` is a reference list with a cap of its own, ``get_series`` a series over a
region's periods that refuses an unknown code as a source does, and ``download_regions`` a
bulk task, Python-only and no tool. ``MAX_PERIODS`` is the ceiling the module holds.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from xippios.core import InvalidRequestError, Result, ResultCap, ResultMeta
from xippios.example._client import SOURCE

__all__ = ["download_regions", "get_series", "list_regions"]

BULK_TASKS = frozenset({"download_regions"})

MCP_CAPS = {"list_regions": ResultCap(max_rows=400, max_bytes=100_000)}

MCP_INSTRUCTIONS = (
    "Example via xippios. Tools are read-only. Call example_list_regions first to find a "
    "region's code, then example_get_series."
)

MAX_PERIODS = 20
"""The most periods ``get_series`` answers for."""

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
        periods: How many periods, e.g. 3; at least 1 and at most the source's ceiling.
    """
    if region_code not in {region.code for region in _REGIONS}:
        raise InvalidRequestError(
            f"region_code {region_code!r}: no region of example; list_regions() lists the "
            "known values (over MCP, the tool example_list_regions).",
            source=SOURCE,
        )
    if not 1 <= periods <= MAX_PERIODS:
        raise InvalidRequestError(f"periods {periods}: from 1 to {MAX_PERIODS}", source=SOURCE)
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
