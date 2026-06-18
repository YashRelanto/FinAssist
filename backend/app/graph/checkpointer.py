"""
graph/checkpointer.py
=====================
Environment-aware checkpointer factory.

Checkpointer provides LangGraph with a persistence backend for conversation
state.  It replaces the sessions.json file used by the old StateManager.

Upgrade path:
  Development  → MemorySaver      (in-memory, lost on restart, zero setup)
  Production   → AsyncPostgresSaver (same Supabase PostgreSQL, fully persistent + multi-process)

The active checkpointer is determined by the APP_ENV environment variable:
  APP_ENV=development  → MemorySaver  (default)
  APP_ENV=staging      → SqliteSaver
  APP_ENV=production   → AsyncPostgresSaver (requires SUPABASE_DB_URL in .env)
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def get_checkpointer():
    """
    Returns the appropriate LangGraph checkpointer for the current environment.

    Called once at module load time in graph.py — the result is reused for
    the lifetime of the process.
    """
    env = os.getenv("APP_ENV", "development").lower()

    if env == "production":
        db_url = os.getenv("SUPABASE_DB_URL")
        if db_url:
            try:
                from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
                checkpointer = AsyncPostgresSaver.from_conn_string(db_url)
                logger.info("[Checkpointer] Using AsyncPostgresSaver (production)")
                return checkpointer
            except Exception as exc:
                logger.error("[Checkpointer] AsyncPostgresSaver failed: %s — falling back to MemorySaver", exc)
        else:
            logger.warning("[Checkpointer] APP_ENV=production but SUPABASE_DB_URL not set — using MemorySaver")


    # Default: MemorySaver (development / fallback)
    from langgraph.checkpoint.memory import MemorySaver
    logger.info("[Checkpointer] Using MemorySaver (development)")
    return MemorySaver()
