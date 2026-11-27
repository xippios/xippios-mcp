# Core's plugin keeps the default run offline (sdk-core ADR-0035), so nothing reaches an
# upstream though every source package is installed, and runs anyio tests on asyncio.
from collections.abc import Iterator

import pytest
from xippios.example import tasks as example_tasks

pytest_plugins = ["xippios.core.testing.plugin"]


@pytest.fixture(autouse=True)
def _python_ceiling() -> Iterator[None]:
    """Each test ends with the example's ceiling at its Python value, 20.

    An endpoint that the host builds applies the example's option hook at its default, which
    sets the ceiling of the whole process to 5, as the package's entry point does, so every
    test sets ``SERIES.most`` again after it, as core's ``Ceiling`` asks of a test.
    """
    yield
    example_tasks.SERIES.set(example_tasks.SERIES.most)
