"""Tab-scoped logging gated by config flags (LOG_TAB_*)."""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings

TAB_NAMES = frozenset({"analytics", "dashboard", "chat", "forecasting"})


def is_tab_logging_enabled(tab: str) -> bool:
    return settings.is_tab_log_enabled(tab)


def tab_logger(tab: str) -> logging.Logger:
    key = tab.strip().lower()
    return logging.getLogger(f"finassist.tab.{key}")


def tab_log(tab: str, level: int, msg: str, *args: Any, **kwargs: Any) -> None:
    if not is_tab_logging_enabled(tab):
        return
    tab_logger(tab).log(level, msg, *args, **kwargs)


def tab_info(tab: str, msg: str, *args: Any, **kwargs: Any) -> None:
    tab_log(tab, logging.INFO, msg, *args, **kwargs)


def tab_debug(tab: str, msg: str, *args: Any, **kwargs: Any) -> None:
    tab_log(tab, logging.DEBUG, msg, *args, **kwargs)


def tab_warning(tab: str, msg: str, *args: Any, **kwargs: Any) -> None:
    tab_log(tab, logging.WARNING, msg, *args, **kwargs)


def tab_error(tab: str, msg: str, *args: Any, **kwargs: Any) -> None:
    tab_log(tab, logging.ERROR, msg, *args, **kwargs)


def mask_user_id(user_id: str | None) -> str:
    if not user_id:
        return "unknown"
    uid = user_id.strip()
    return uid[:8] if len(uid) > 8 else uid
