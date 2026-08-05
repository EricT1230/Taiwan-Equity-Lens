from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any


def run_bounded_loaders(
    loaders: dict[str, Callable[[], Any]],
    *,
    timeout_seconds: float,
    capacity: threading.BoundedSemaphore,
) -> tuple[dict[str, Any], dict[str, BaseException]]:
    """Run independent loaders concurrently without an unbounded work queue.

    A timed-out loader may still finish its in-flight network call, but it keeps
    one shared capacity slot until then. Later snapshots fail fast instead of
    queuing behind stuck work and consuming request workers.
    """

    results: dict[str, Any] = {}
    failures: dict[str, BaseException] = {}
    completed: dict[str, threading.Event] = {}
    lock = threading.Lock()

    def run(name: str, loader: Callable[[], Any], done: threading.Event) -> None:
        try:
            value = loader()
        except BaseException as exc:  # keep worker failures inside the component
            with lock:
                failures[name] = exc
        else:
            with lock:
                results[name] = value
        finally:
            capacity.release()
            done.set()

    for name, loader in loaders.items():
        done = threading.Event()
        completed[name] = done
        if not capacity.acquire(blocking=False):
            failures[name] = TimeoutError("component loader capacity is busy")
            done.set()
            continue
        threading.Thread(
            target=run,
            args=(name, loader, done),
            name=f"market-component-{name}",
            daemon=True,
        ).start()

    deadline = time.monotonic() + max(0.01, float(timeout_seconds))
    for name, done in completed.items():
        remaining = deadline - time.monotonic()
        if remaining > 0:
            done.wait(remaining)
        if not done.is_set() and name not in failures:
            failures[name] = TimeoutError("component snapshot deadline exceeded")
    return results, failures
