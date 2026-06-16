"""Shared SQL generation prompt kwargs."""

from __future__ import annotations

from app.utils.temporal_context import get_time_context


def sql_prompt_kwargs() -> dict[str, str]:
    return get_time_context()
