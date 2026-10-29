# Core's plugin keeps the default run offline (ADR-0013), so nothing reaches an upstream
# though every source package is installed, and runs anyio tests on asyncio.
pytest_plugins = ["xippios.core.testing.plugin"]
