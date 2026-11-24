"""The variables the invented source names for a host; no task of it reads one."""

from xippios.core import EnvVar

__all__ = ["ENV_VARS", "SOURCE"]

SOURCE = "example"

ENV_VARS: tuple[EnvVar, ...] = (EnvVar("EXAMPLE_API_KEY", secret=True, required=True),)
