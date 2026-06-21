"""Structured logging and observability for the LangGraph pipeline."""

from __future__ import annotations

import logging
import threading
import time
from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable

from langgraph.errors import GraphInterrupt

logger = logging.getLogger("app.graph")

_run_context: ContextVar[dict[str, str]] = ContextVar("graph_run_context", default={})

# Per-request token accumulator. LangGraph runs sync nodes in worker threads that
# receive a COPY of the contextvars — so a ContextVar can't accumulate across the
# thread boundary (mutations in the worker copy don't propagate back). Instead we
# keep a shared, lock-guarded dict keyed by thread_id; workers can still read the
# thread_id from the (copied) run context. Reads/resets happen in the request
# coroutine, writes happen in the node workers — both keyed by the same thread_id.
_token_usage: dict[str, dict[str, int]] = {}
_token_lock = threading.Lock()


def _run_key() -> str:
    return _run_context.get().get("thread_id", "") or "_default"


def set_graph_run_context(*, user_id: str, thread_id: str) -> None:
    _run_context.set({"user_id": user_id, "thread_id": thread_id})


def clear_graph_run_context() -> None:
    _run_context.set({})


def reset_token_usage() -> None:
    """Clear the per-request token accumulator (call at the start of each turn)."""
    with _token_lock:
        _token_usage[_run_key()] = {}


def get_token_usage() -> dict[str, int]:
    """Return per-node token usage and the total for the current request."""
    with _token_lock:
        usage = dict(_token_usage.get(_run_key(), {}))
    usage["total"] = sum(usage.values())
    return usage


def record_token_usage(node: str, total_tokens: int) -> None:
    """Add a completion's token count to the per-node accumulator."""
    if not total_tokens:
        return
    with _token_lock:
        bucket = _token_usage.setdefault(_run_key(), {})
        bucket[node] = bucket.get(node, 0) + int(total_tokens)


def truncate(text: str | None, max_len: int = 200) -> str:
    if not text:
        return ""
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= max_len:
        return cleaned
    return f"{cleaned[: max_len - 3]}..."


def _summarize_output(updates: dict[str, Any] | None) -> str:
    """Full output of a node's return dict — no truncation."""
    if not updates:
        return "no updates"
    import json
    try:
        return json.dumps(updates, default=str, ensure_ascii=False)
    except Exception:
        return str(updates)


def wrap_graph_node(node_name: str, fn: Callable[[Any], dict[str, Any]]) -> Callable[[Any], dict[str, Any]]:
    """Decorator/wrapper that logs node entry, exit, and a compact output summary."""

    @wraps(fn)
    def wrapper(state: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        logger.info("[%s] enter", node_name)
        try:
            result = fn(state)
        except GraphInterrupt:
            logger.info("[%s] interrupt — awaiting user input", node_name)
            raise
        except Exception:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.exception("[%s] failed | elapsed_ms=%.0f", node_name, elapsed_ms)
            raise

        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "[%s] exit | elapsed_ms=%.0f | %s",
            node_name, elapsed_ms, _summarize_output(result),
        )
        return result

    return wrapper


def log_graph_run_start(*, user_id: str, thread_id: str, message: str) -> None:
    logger.info(
        "[Graph] run start | user=%s thread=%s message=%r",
        user_id[:8],
        thread_id[:8],
        truncate(message, 240),
    )


def log_graph_run_end(
    *,
    user_id: str,
    thread_id: str,
    intent: str,
    elapsed_ms: float,
    answer_preview: str,
) -> None:
    logger.info(
        "[Graph] run end | user=%s thread=%s intent=%s elapsed_ms=%.0f answer=%r",
        user_id[:8],
        thread_id[:8],
        intent,
        elapsed_ms,
        truncate(answer_preview, 240),
    )
