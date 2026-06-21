"""LLM chat completions for LangGraph nodes."""

from __future__ import annotations

import logging
import time
from typing import Any

import openai

from app.core.config import settings
from app.core.llm_client import create_openai_client
from app.graph.logging_utils import record_token_usage

logger = logging.getLogger("app.graph")


def graph_chat_completion(
    *,
    node: str,
    purpose: str,
    client: openai.OpenAI | None = None,
    **kwargs: Any,
):
    """Execute a chat completion and record tokens/timing for graph observability."""
    model = kwargs.get("model", settings.active_chat_model)
    started = time.perf_counter()

    if client is None:
        client = create_openai_client()

    response = client.chat.completions.create(**kwargs)
    elapsed_ms = (time.perf_counter() - started) * 1000

    usage = getattr(response, "usage", None)
    tokens = getattr(usage, "total_tokens", 0) or 0
    if tokens:
        record_token_usage(node, tokens)

    logger.info(
        "[%s] LLM | purpose=%s model=%s elapsed_ms=%.0f tokens=%d",
        node,
        purpose,
        model,
        elapsed_ms,
        tokens,
    )
    return response
