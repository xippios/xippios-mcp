"""The write tasks of the invented source ``example``: each previews unless ``confirm``.

Nothing is written anywhere: a confirmed call answers as if the upstream had done it.
"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel
from xippios.core import Result, ResultMeta
from xippios.example._client import SOURCE

__all__ = ["create_thing", "delete_thing"]

MCP_INSTRUCTIONS = (
    "Example write tools via xippios. Every tool returns a preview and changes nothing unless "
    "confirm=true is passed. Call it once without confirm, show the preview, then confirm."
)

_RETRIEVED = datetime(2026, 11, 24, tzinfo=UTC)


class Preview(BaseModel):
    """What a write would send, not sent."""

    performed: Literal[False] = False
    action: str
    reads: list[str] = []


class Done(BaseModel):
    """A write the upstream did."""

    performed: Literal[True] = True
    action: str


def _answer(action: str, endpoint: str, confirm: bool) -> Result[Preview | Done]:
    meta = ResultMeta(source=SOURCE, endpoint=endpoint, retrieved_at=_RETRIEVED)
    data: Preview | Done = Done(action=action) if confirm else Preview(action=action)
    return Result(data=data, meta=meta)


def create_thing(name: str, confirm: bool = False) -> Result[Preview | Done]:
    """Create a thing: a preview of the create unless confirm is true.

    Args:
        name: The thing's name, e.g. "first".
        confirm: True to create it; False, the default, previews it.
    """
    return _answer(f"create thing {name}", "createThing", confirm)


def delete_thing(name: str, confirm: bool = False) -> Result[Preview | Done]:
    """Delete a thing: a preview of the delete unless confirm is true.

    Args:
        name: The thing's name, e.g. "first".
        confirm: True to delete it; False, the default, previews it.
    """
    return _answer(f"delete thing {name}", "deleteThing", confirm)
