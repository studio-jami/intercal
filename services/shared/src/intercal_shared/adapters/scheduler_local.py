"""Local (inline) scheduler adapter.

Runs job callables directly in the current event loop.  This is the only
required scheduler adapter: deployed schedulers (GitHub Actions, Modal, cron)
invoke the same CLI entrypoints and never need a remote scheduling SDK.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any

from intercal_shared.ports.scheduler import SchedulerError

_log = logging.getLogger(__name__)


class LocalSchedulerAdapter:
    """SchedulerPort implementation that runs jobs inline.

    Design note: deployed schedulers (GitHub Actions scheduled workflows, Modal
    cron triggers, VPS cron) call ``python -m intercal_ingest <job>`` directly.
    The scheduler port therefore only needs to support local/inline execution.
    """

    async def run_now(
        self,
        job: Callable[..., Coroutine[Any, Any, None]],
        **kwargs: Any,
    ) -> None:
        """Run *job* immediately with *kwargs*.

        Raises:
            SchedulerError: if the job raises an unhandled exception.
        """
        _log.debug("LocalScheduler: running %s", getattr(job, "__name__", repr(job)))
        try:
            await job(**kwargs)
        except Exception as exc:
            raise SchedulerError(
                f"Job {getattr(job, '__name__', repr(job))} failed: {exc}"
            ) from exc
