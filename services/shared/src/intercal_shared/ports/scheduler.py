"""SchedulerPort — provider-agnostic job scheduling interface.

Design note
-----------
The scheduler port is intentionally thin.  In deployed environments (GitHub
Actions, Modal, VPS cron) the *scheduler* is the external system — it simply
invokes the CLI entrypoint (`python -m intercal_ingest ingest_source ...`).

The `local` adapter (the only one needed for dev and testing) calls the job
callable directly.  There is no need for a heavy scheduler abstraction.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any, Protocol, runtime_checkable

# A job callable is any async function that accepts keyword arguments and
# returns None (or something that will be ignored).
JobCallable = Callable[..., Coroutine[Any, Any, None]]


@runtime_checkable
class SchedulerPort(Protocol):
    """Job scheduler port.

    The primary use-case in dev is `run_now` for inline execution during tests
    and local CLI runs.  Deployed schedulers (GitHub Actions, Modal, cron) call
    the same worker entrypoints directly; the port adapter stays 'local'.
    """

    async def run_now(
        self,
        job: JobCallable,
        **kwargs: Any,
    ) -> None:
        """Run *job* immediately with *kwargs*.

        In the 'local' adapter this is a direct ``await job(**kwargs)``.

        Raises:
            SchedulerError: if the job raises an unhandled exception (the
                adapter may re-raise or wrap; callers should handle both).
        """
        ...


class SchedulerError(Exception):
    """Raised by scheduler adapters on execution failures."""
