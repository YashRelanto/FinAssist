"""
Brain (Supervisor) node.

The Brain is the central orchestrator. On each pass it inspects the user request,
conversation history, profile, and accumulated evidence, then decides ONE next
action: ask a clarification (HITL via `interrupt`), call a tool, reject as
out-of-scope, or finish. Tools return their results as `evidence` and control comes
back to the Brain until it has enough information to `finish`.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import interrupt

from app.core.config import settings
from app.graph.logging_utils import graph_chat_completion
from app.graph.state import AgentState
from app.utils.prompts import BRAIN_SYSTEM, BRAIN_USER

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 5          # max tool-calling passes per turn
MAX_CLARIFICATIONS = 3      # max clarification questions per turn

VALID_ACTIONS = {
    "clarify", "nl2sql", "goal_planner", "investment",
    "knowledge", "out_of_scope", "finish",
}

OUT_OF_SCOPE_MESSAGE = (
    "This assistant specialises in personal finance and financial planning. "
    "Please ask a finance-related question."
)


def _format_profile(profile: Dict[str, Any]) -> str:
    if not profile:
        return "Not available."
    keys = ["income", "city", "real_time_balances", "monthly_net_flow", "risk_profile"]
    lines = [f"- {k}: {profile[k]}" for k in keys if profile.get(k) is not None]
    return "\n".join(lines) or "Not available."


def _format_history(messages: List[Any], limit: int = 8) -> str:
    lines = []
    for m in messages[-(limit + 1):-1]:  # exclude the latest (passed separately)
        role = "User" if isinstance(m, HumanMessage) or m.__class__.__name__ == "HumanMessage" else "Assistant"
        lines.append(f"{role}: {m.content}")
    return "\n".join(lines) if lines else "None."


def _format_evidence(evidence: List[Dict[str, Any]]) -> str:
    if not evidence:
        return "None yet."
    return "\n".join(f"- [{e.get('tool')}] {e.get('summary')}" for e in evidence)


def _format_clarifications(clarifs: List[Dict[str, str]]) -> str:
    if not clarifs:
        return "None."
    return "\n".join(f"- Asked: {c['q']} | User answered: {c['a']}" for c in clarifs)


def _decide(state: AgentState, clarifs: List[Dict[str, str]], iteration: int) -> Dict[str, Any]:
    """One LLM call returning the Brain's decision JSON."""
    try:
        response = graph_chat_completion(
            node="brain",
            purpose="supervisor_decision",
            model=settings.active_chat_model,
            messages=[
                {"role": "system", "content": BRAIN_SYSTEM},
                {"role": "user", "content": BRAIN_USER.format(
                    profile=_format_profile(state.get("user_profile") or {}),
                    history=_format_history(state.get("messages") or []),
                    clarifications=_format_clarifications(clarifs),
                    evidence=_format_evidence(state.get("evidence") or []),
                    iteration=iteration,
                    max_iterations=MAX_ITERATIONS,
                    message=state.get("user_query") or "",
                )},
            ],
            response_format={"type": "json_object"},
            max_tokens=500,
            temperature=0.0,
        )
        decision = json.loads(response.choices[0].message.content.strip())
    except Exception as exc:
        logger.error("[brain] Decision failed: %s — defaulting to knowledge", exc)
        decision = {"next_action": "knowledge", "task": {"sub_question": state.get("user_query")}}

    action = str(decision.get("next_action", "")).lower().strip()
    if action not in VALID_ACTIONS:
        action = "finish" if (state.get("evidence")) else "knowledge"
    decision["next_action"] = action
    return decision


def brain_node(state: AgentState) -> dict:
    """Supervisor decision node with HITL clarification via interrupt()."""
    iteration = (state.get("iterations") or 0) + 1
    clarifs: List[Dict[str, str]] = []

    while True:
        decision = _decide(state, clarifs, iteration)
        action = decision["next_action"]

        if action == "clarify" and iteration < MAX_ITERATIONS and len(clarifs) < MAX_CLARIFICATIONS:
            question = decision.get("clarification_question") or "Could you clarify your request?"
            logger.info("[brain] iter=%d clarify -> interrupt: %s", iteration, question)
            answer = interrupt({"type": "clarification", "question": question})
            clarifs.append({"q": question, "a": str(answer)})
            continue
        break

    task = decision.get("task") or {}

    # Deterministic guards against runaway loops the prompt may miss:
    #  - single-shot tools (knowledge / investment / goal_planner) run at most once;
    #  - nl2sql may repeat for distinct sub-questions, but never the identical one.
    evidence = state.get("evidence") or []
    existing_tools = {e.get("tool") for e in evidence}
    if action in ("knowledge", "investment", "goal_planner") and action in existing_tools:
        logger.info("[brain] iter=%d single-shot '%s' already ran -> finish", iteration, action)
        action = "finish"
    elif action == "nl2sql":
        nl2sql_evs = [e for e in evidence if e.get("tool") == "nl2sql"]
        sub_q = (task.get("sub_question") or "").strip().lower()
        repeated = any(str(e.get("task") or "").strip().lower() == sub_q for e in nl2sql_evs)
        if repeated or len(nl2sql_evs) >= 2:   # identical re-query, or enough data gathered
            logger.info("[brain] iter=%d nl2sql cap/repeat -> finish", iteration)
            action = "finish"

    # Force completion if we've exhausted the loop budget.
    if iteration >= MAX_ITERATIONS and action != "out_of_scope":
        logger.info("[brain] iter=%d max iterations reached -> finish", iteration)
        action = "finish"

    logger.info("[brain] iter=%d decision=%s reason=%s", iteration, action, decision.get("reasoning", ""))

    result: dict = {
        "next_action": action,
        "brain_task": task,
        "iterations": iteration,
    }

    # Persist any clarification exchange into the conversation so later Brain
    # passes (and future turns) retain the answer and don't re-ask it.
    new_messages = []
    for c in clarifs:
        new_messages.append(AIMessage(content=c["q"]))
        new_messages.append(HumanMessage(content=c["a"]))

    if action == "out_of_scope":
        result["final_answer"] = OUT_OF_SCOPE_MESSAGE
        result["final_intent"] = "OUT_OF_SCOPE"
        result["sources"] = ["Domain Scope Validator"]
        new_messages.append(AIMessage(content=OUT_OF_SCOPE_MESSAGE))

    if new_messages:
        result["messages"] = new_messages

    return result
