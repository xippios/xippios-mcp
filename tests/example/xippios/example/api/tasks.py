"""The read tasks of the invented nested source ``example-api``: two, without caps."""

from datetime import UTC, datetime

from pydantic import BaseModel
from xippios.core import NotFoundError, Result, ResultMeta
from xippios.example.api._client import SOURCE

__all__ = ["get_record", "list_kinds"]

MCP_INSTRUCTIONS = "Example API via xippios. Tools are read-only."

_RETRIEVED = datetime(2026, 11, 24, tzinfo=UTC)
_KINDS = ("alpha", "beta")


class Record(BaseModel):
    """A record of the nested source."""

    record_id: str
    kind: str


def list_kinds() -> Result[list[str]]:
    """List the kinds of record the nested source holds."""
    meta = ResultMeta(source=SOURCE, endpoint="listKinds", retrieved_at=_RETRIEVED)
    return Result(data=list(_KINDS), meta=meta)


def get_record(record_id: str) -> Result[Record]:
    """Get one record by its id.

    Args:
        record_id: The record's id, e.g. "a1": a kind's first letter and a number.
    """
    kind = next((kind for kind in _KINDS if record_id.startswith(kind[0])), None)
    if kind is None:
        raise NotFoundError(f"record_id {record_id!r}: no record", source=SOURCE)
    meta = ResultMeta(
        source=SOURCE, endpoint="getRecord", retrieved_at=_RETRIEVED, request={"id": record_id}
    )
    return Result(data=Record(record_id=record_id, kind=kind), meta=meta)
