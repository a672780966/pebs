"""当前执行中的动态节点（§39 per-skill model_calls）。

并行调度下不能用"调用计数差分"（共享的 run 级计数器会被同批节点的调用污染），
所以用一个线程局部的 step 上下文，让 `store.bump_calls` 能精确记到发起调用的节点上。
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

_local = threading.local()


def current_step() -> str:
    return str(getattr(_local, "step_id", "") or "")


@contextmanager
def step_scope(step_id: str) -> Iterator[None]:
    previous = getattr(_local, "step_id", "")
    _local.step_id = step_id
    try:
        yield
    finally:
        _local.step_id = previous
