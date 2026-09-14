"""Background job runner.

Conversions run on a worker thread so the window never freezes; results are
handed back through a queue that the GUI drains on its own event loop.
"""

from __future__ import annotations

import inspect
import queue
import threading
import time
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


def _accepts_progress(worker: Callable) -> bool:
    """Only some pipelines can report sub-file progress; FFmpeg-backed ones can."""
    try:
        return "progress" in inspect.signature(worker).parameters
    except (TypeError, ValueError):  # pragma: no cover - builtins and partials
        return False


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
        total = len(files)
        started = time.monotonic()
        self._emit("start", total)
        log = lambda text: self._emit("detail", text)  # noqa: E731
        wants_progress = _accepts_progress(worker)

        def tick(fraction: float, index: int) -> None:
            """Overall completion, plus what it implies about time remaining."""
            overall = min(1.0, max(0.0, (index - 1 + fraction) / total))
            elapsed = time.monotonic() - started
            # Only guess once there is enough signal to be worth showing.
            remaining = (elapsed / overall - elapsed) if overall > 0.02 else None
            self._emit("tick", (overall, elapsed, remaining))

        for index, path in enumerate(files, start=1):
            if self._cancel.is_set():
                summary.cancelled = True
                self._emit("cancelled", None)
                break

            self._emit("file_start", (index, total, Path(path).name))
            tick(0.0, index)

            call = dict(kwargs)
            if wants_progress:
                call["progress"] = lambda fraction, i=index: tick(fraction, i)

            try:
                result = worker(Path(path), log=log, **call)
            except Exception as exc:
                result = TaskResult(source=Path(path), ok=False, message=str(exc))
                self._emit("detail", traceback.format_exc())
            tick(1.0, index)

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
