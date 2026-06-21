"""Shared OpenAI-compatible client factory."""

from __future__ import annotations

import openai

from app.core.config import settings


def create_openai_client() -> openai.OpenAI:
    return openai.OpenAI(
        api_key=settings.active_api_key,
        base_url=settings.active_base_url,
    )
