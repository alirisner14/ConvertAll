"""Background job runner.

Conversions run on a worker thread so the window never freezes; results are
handed back through a queue that the GUI drains on its own event loop.
"""

from __future__ import annotations

import queue
import threading
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .core.common import TaskResult


@dataclass
class JobSummary:
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    cancelled: bool = False
    bytes_in: int = 0
    bytes_out: int = 0
    outputs: list[Path] = field(default_factory=list)

    @property
    def saved_pct(self) -> float:
        if not self.bytes_in or not self.bytes_out:
            return 0.0
        return (1.0 - self.bytes_out / self.bytes_in) * 100.0


class JobRunner:
    """Runs `worker(path, **kwargs)` over a list of files, one at a time."""

    def __init__(self) -> None:
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def cancel(self) -> None:
        self._cancel.set()

    def start(
        self,
        files: list[Path],
        worker: Callable[..., TaskResult],
        **kwargs: Any,
    ) -> None:
        if self.busy:
            raise RuntimeError("A job is already running")
        self._cancel.clear()
        self._thread = threading.Thread(
            target=self._run, args=(list(files), worker, kwargs), daemon=True
        )
        self._thread.start()

    def _emit(self, kind: str, payload: Any = None) -> None:
        self.events.put((kind, payload))

    def _run(self, files: list[Path], worker: Callable[..., TaskResult], kwargs: dict) -> None:
        summary = JobSummary(total=len(files))
        self._emit("start", len(files))
        log = lambda text: self._emit("log", text)  # noqa: E731

        for index, path in enumerate(files, start=1):
            if self._cancel.is_set():
                summary.cancelled = True
                self._emit("log", "Cancelled by user.")
                break

            self._emit("progress", (index, len(files), Path(path).name))
            try:
                result = worker(Path(path), log=log, **kwargs)
            except Exception as exc:
                result = TaskResult(source=Path(path), ok=False, message=str(exc))
                self._emit("trace", traceback.format_exc())

            if result.ok:
                summary.succeeded += 1
                summary.bytes_in += result.bytes_in
                summary.bytes_out += result.bytes_out
                if result.output:
                    summary.outputs.append(result.output)
                summary.outputs.extend(result.extra_outputs)
            else:
                summary.failed += 1

            self._emit("result", result)

        self._emit("done", summary)
