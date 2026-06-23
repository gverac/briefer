"""Serialize all printing through a single worker thread.

The printer is one physical device. Opening it from two threads at once — the
scheduler firing a brief while the GPIO button reprints, or the web console's
"Print now" landing mid-email — makes libusb raise ``[Errno 16] Resource busy``
(EBUSY) and corrupts whichever job loses the race. To prevent that, every print
path submits a job here instead of touching the printer directly; the worker
runs them strictly one at a time, in submission order (a FIFO print queue).

Callers that need the old synchronous behaviour (a return value, "mark the email
read only once it actually printed", "print the goodbye before powering off")
submit and then ``.wait()``. Fire-and-forget callers (the button) just submit.

When no worker is running (the one-shot CLI, tests) ``submit`` runs the job
inline, so those single-threaded paths keep working unchanged.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Any, Callable

log = logging.getLogger("daily_brief.printqueue")

# Bound the backlog so a wedged printer can't grow the queue without limit; a
# day's worth of briefs + email is tiny, so this is really just a safety valve.
MAX_PENDING = 32


class PrintJob:
    """A single queued print, with a handle to wait for its completion."""

    def __init__(self, name: str, fn: Callable[[], Any]):
        self.name = name
        self.fn = fn
        self.result: Any = None
        self.error: BaseException | None = None
        self._done = threading.Event()

    def run(self) -> None:
        """Execute the job, capturing its result or exception. Never raises."""
        try:
            self.result = self.fn()
        except BaseException as exc:  # noqa: BLE001 - a bad job must not kill the worker
            self.error = exc
            log.error("print job %r failed: %s", self.name, exc)
        finally:
            self._done.set()

    def wait(self, timeout: float | None = None) -> bool:
        """Block until the job has run. Returns True if it finished without error.

        Returns False on timeout or if the job raised — so callers can decide
        whether to retry (e.g. leave an email unread for the next poll).
        """
        if not self._done.wait(timeout):
            return False
        return self.error is None


class PrintQueue:
    """A FIFO queue of print jobs drained by one dedicated worker thread."""

    def __init__(self, maxsize: int = MAX_PENDING):
        self._q: queue.Queue[PrintJob | None] = queue.Queue(maxsize=maxsize)
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start the worker thread (idempotent)."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._run, name="print-queue", daemon=True
            )
            self._thread.start()

    def _running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def submit(self, name: str, fn: Callable[[], Any]) -> PrintJob:
        """Enqueue a print job and return its handle.

        With no worker running the job runs inline (single-threaded CLI/tests).
        If the queue is full the job also runs inline rather than being dropped,
        so a print is never silently lost.
        """
        job = PrintJob(name, fn)
        if not self._running():
            job.run()
            return job
        try:
            self._q.put_nowait(job)
        except queue.Full:
            log.warning("print queue full; running %r inline", name)
            job.run()
        return job

    def _run(self) -> None:
        while True:
            job = self._q.get()
            try:
                if job is None:  # stop sentinel
                    return
                pending = self._q.qsize()
                if pending:
                    log.info("printing %r (%d more queued)", job.name, pending)
                else:
                    log.info("printing %r", job.name)
                job.run()
            finally:
                self._q.task_done()

    def stop(self, timeout: float | None = 5.0) -> None:
        """Signal the worker to exit after draining and join it."""
        if not self._running():
            return
        self._q.put(None)
        if self._thread is not None:
            self._thread.join(timeout)


# Process-wide singleton. The daemon starts it; every print path submits to it.
QUEUE = PrintQueue()


def submit(name: str, fn: Callable[[], Any]) -> PrintJob:
    """Submit a job to the process-wide print queue (see ``PrintQueue.submit``)."""
    return QUEUE.submit(name, fn)
