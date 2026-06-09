"""
Workflow relevance node — Checks if user message continues active goal-planning workflow.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from app.core.config import settings
from app.graph.logging_utils import graph_chat_completion
from app.graph.state import AgentState
from app.utils.prompts import WORKFLOW_RELEVANCE_SYSTEM, WORKFLOW_RELEVANCE_USER

logger = logging.getLogger(__name__)


def workflow_relevance_node(state: AgentState) -> dict:
    """
    Determines whether the user's message continues the active workflow or changes topic.
    Sets workflow_related.
    """
    message = state.get("user_query") or ""
    workflow_state = state.get("workflow_state") or {}

    try:
        response = graph_chat_completion(
            node="workflow_relevance_node",
            purpose="workflow_relevance",
            model=settings.active_chat_model,
            messages=[
                {"role": "system", "content": WORKFLOW_RELEVANCE_SYSTEM},
                {"role": "user", "content": WORKFLOW_RELEVANCE_USER.format(
                    message=message,
                    workflow_state=json.dumps(workflow_state, indent=2),
                )},
            ],
            response_format={"type": "json_object"},
            max_tokens=150,
            temperature=0.0,
        )
        data = json.loads(response.choices[0].message.content.strip())
        related = bool(data.get("workflow_related", False))
        confidence = float(data.get("confidence", 0.0))
        reason = str(data.get("reason", ""))

        logger.info("[Node:workflow_relevance] related=%s conf=%.2f reason='%s'",
                    related, confidence, reason)

        if not related:
            # Pause the active workflow
            updated_wf = dict(workflow_state)
            updated_wf["workflow_status"] = "paused"
            updated_wf["last_updated"] = datetime.now(timezone.utc).isoformat()
            return {
                "workflow_related": False,
                "workflow_state": updated_wf,
                "workflow_active": False,
            }

        return {"workflow_related": True}

    except Exception as exc:
        logger.error("[Node:workflow_relevance] Failed: %s — defaulting to not related", exc)
        return {"workflow_related": False}
