"""Structured logging for the LangGraph pipeline and LLM calls."""

from __future__ import annotations

import logging
import time
from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable

import openai

from app.core.config import settings

logger = logging.getLogger("app.graph")

_run_context: ContextVar[dict[str, str]] = ContextVar("graph_run_context", default={})


def set_graph_run_context(*, user_id: str, thread_id: str) -> None:
    _run_context.set({"user_id": user_id, "thread_id": thread_id})


def clear_graph_run_context() -> None:
    _run_context.set({})


def _ctx_prefix() -> str:
    ctx = _run_context.get()
    if not ctx:
        return ""
    uid = ctx.get("user_id", "?")
    tid = ctx.get("thread_id", "?")
    return f"user={uid[:8]} thread={tid[:8]} "


def truncate(text: str | None, max_len: int = 200) -> str:
    if not text:
        return ""
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= max_len:
        return cleaned
    return f"{cleaned[: max_len - 3]}..."


def summarize_messages(messages: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "?")
        content = truncate(str(msg.get("content", "")), 120)
        parts.append(f"{role}={content!r}")
    return "; ".join(parts)


def summarize_state_snapshot(state: dict[str, Any]) -> str:
    fields = {
        "intent": state.get("intent"),
        "selected_agent": state.get("selected_agent"),
        "workflow_active": state.get("workflow_active"),
        "clarification_needed": state.get("clarification_needed"),
        "input_blocked": state.get("input_blocked"),
        "output_blocked": state.get("output_blocked"),
    }
    query = state.get("rewritten_query") or state.get("user_query")
    if query:
        fields["query"] = truncate(str(query), 120)
    return ", ".join(f"{k}={v!r}" for k, v in fields.items() if v is not None)


def summarize_node_updates(updates: dict[str, Any] | None) -> str:
    if not updates:
        return "none"
    parts: list[str] = []
    for key, value in updates.items():
        if key in {"entities", "resolved_entities", "sql_ast", "sql_results", "analytics_results"}:
            parts.append(f"{key}=<{type(value).__name__}>")
        elif key in {"raw_answer", "final_answer", "clarification_question", "rewritten_query"}:
            parts.append(f"{key}={truncate(str(value), 100)!r}")
        elif key == "retrieved_context":
            count = len(value) if isinstance(value, list) else 0
            parts.append(f"retrieved_context_blocks={count}")
        else:
            parts.append(f"{key}={value!r}")
    return ", ".join(parts)


def create_openai_client() -> openai.OpenAI:
    return openai.OpenAI(
        api_key=settings.active_api_key,
        base_url=settings.active_base_url,
    )


def graph_chat_completion(
    *,
    node: str,
    purpose: str,
    client: openai.OpenAI | None = None,
    **kwargs: Any,
):
    """Log and execute an OpenAI chat completion used inside the graph."""
    model = kwargs.get("model", settings.active_chat_model)
    messages = kwargs.get("messages", [])
    started = time.perf_counter()

    logger.info(
        "[%s] LLM start | %spurpose=%s model=%s | %s",
        node,
        _ctx_prefix(),
        purpose,
        model,
        summarize_messages(messages),
    )

    if client is None:
        client = create_openai_client()

    response = client.chat.completions.create(**kwargs)
    elapsed_ms = (time.perf_counter() - started) * 1000

    usage = getattr(response, "usage", None)
    token_info = ""
    if usage is not None:
        token_info = (
            f" prompt_tokens={usage.prompt_tokens}"
            f" completion_tokens={usage.completion_tokens}"
            f" total_tokens={usage.total_tokens}"
        )

    content = ""
    if response.choices:
        content = truncate(response.choices[0].message.content or "", 240)

    logger.info(
        "[%s] LLM done | %spurpose=%s elapsed_ms=%.0f%s | response=%r",
        node,
        _ctx_prefix(),
        purpose,
        elapsed_ms,
        token_info,
        content,
    )
    return response


def wrap_graph_node(node_name: str, fn: Callable[[Any], dict[str, Any]]) -> Callable[[Any], dict[str, Any]]:
    """Decorator/wrapper that logs node entry, exit, duration, and state updates."""

    @wraps(fn)
    def wrapper(state: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        logger.info(
            "[%s] enter | %sstate=%s",
            node_name,
            _ctx_prefix(),
            summarize_state_snapshot(state),
        )
        try:
            result = fn(state)
        except Exception:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.exception(
                "[%s] failed | %selapsed_ms=%.0f",
                node_name,
                _ctx_prefix(),
                elapsed_ms,
            )
            raise

        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "[%s] exit | %selapsed_ms=%.0f updates=%s",
            node_name,
            _ctx_prefix(),
            elapsed_ms,
            summarize_node_updates(result),
        )
        if isinstance(result, dict):
            meta = dict(state.get("metadata") or {})
            meta.update(result.get("metadata") or {})
            timings = dict(meta.get("node_timings") or {})
            timings[node_name] = round(elapsed_ms, 1)
            meta["node_timings"] = timings
            result = {**result, "metadata": meta}
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
