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
import re
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import interrupt

from app.core.config import settings
from app.graph.logging_utils import graph_chat_completion
from app.graph.state import AgentState
from app.utils.prompts import BRAIN_SYSTEM, BRAIN_USER

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 15         # max tool-calling passes per turn

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


def _build_brain_messages(state: AgentState, clarifs: List[Dict[str, str]], iteration: int) -> List[Dict]:
    return [
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
    ]


def _decide(state: AgentState, clarifs: List[Dict[str, str]], iteration: int) -> Dict[str, Any]:
    """One LLM call returning the Brain's decision JSON. Falls back to active_chat_model on 404."""
    messages = _build_brain_messages(state, clarifs, iteration)
    common_kwargs = dict(response_format={"type": "json_object"}, max_tokens=600, temperature=0.0)

    response = None
    try:
        response = graph_chat_completion(
            node="brain", purpose="supervisor_decision",
            model=settings.brain_model, messages=messages, **common_kwargs,
        )
    except Exception as exc:
        err = str(exc)
        # brain_model may not be available on this NIM account tier — retry with the
        # confirmed-working model before giving up.
        if ("404" in err or "not found" in err.lower()) and settings.brain_model != settings.active_chat_model:
            logger.warning("[brain] brain_model '%s' returned %s — retrying with active_chat_model",
                           settings.brain_model, err[:80])
            try:
                response = graph_chat_completion(
                    node="brain", purpose="supervisor_decision",
                    model=settings.active_chat_model, messages=messages, **common_kwargs,
                )
            except Exception as exc2:
                logger.error("[brain] fallback also failed: %s — defaulting to knowledge", exc2)
        else:
            logger.error("[brain] Decision failed: %s — defaulting to knowledge", exc)

    if response is None:
        return {"next_action": "knowledge", "task": {"sub_question": state.get("user_query")}}

    try:
        decision = json.loads(response.choices[0].message.content.strip())
    except Exception as exc:
        logger.error("[brain] JSON parse failed: %s — defaulting to knowledge", exc)
        decision = {"next_action": "knowledge", "task": {"sub_question": state.get("user_query")}}

    action = str(decision.get("next_action", "")).lower().strip()
    if action not in VALID_ACTIONS:
        action = "finish" if (state.get("evidence")) else "knowledge"
    decision["next_action"] = action
    return decision


def _parse_bulk_answers(questions: List[str], raw: Any) -> List[Dict[str, str]]:
    """
    Parse the bulk answer JSON string returned by the frontend after a clarification_batch
    interrupt into the internal clarifs list format [{q, a}].

    The frontend sends answers as: '{"q0": "iPhone 17 Pro", "q1": "6 months", "q2": "skip"}'
    Answers that are empty or explicitly skipped are omitted (the Brain proceeds without them).
    """
    SKIP_VALUES = {"skip", "s", "idk", "i don't know", "i dont know",
                   "don't know", "dont know", "na", "n/a", "not sure", "unsure", ""}

    data: Dict[str, Any] = {}
    if raw is not None:
        raw_str = str(raw).strip()
        if raw_str.startswith("{"):
            try:
                data = json.loads(raw_str)
            except Exception:
                # Fallback: treat whole string as answer to first question
                data = {"q0": raw_str}
        else:
            data = {"q0": raw_str}

    result: List[Dict[str, str]] = []
    for i, q in enumerate(questions):
        ans = str(data.get(f"q{i}", "")).strip()
        if ans.lower() not in SKIP_VALUES:
            result.append({"q": q, "a": ans})
    return result


def _classify_clarification(q: str) -> str:
    """
    Map a clarification question to the single goal field it asks about. Order matters —
    most specific first — so e.g. a down-payment question ("...the car's PRICE...as a down
    payment") is classified as down_payment, NOT target_amount.
    """
    if "down payment" in q or ("down" in q and "pay" in q):
        return "down_payment_pct"
    if any(kw in q for kw in ("timeline", "timeframe", "time frame", "how long",
                              "by when", "when do", "how soon", "duration")):
        return "timeline"
    if "financ" in q or ("cash" in q and "loan" in q):
        return "financing_preference"
    if any(kw in q for kw in ("saved", "saving", "set aside", "already have")):
        return "existing_savings"
    if "cover" in q or "emergency" in q:
        return "target_months_coverage"
    if "retire" in q or "target age" in q:
        return "target_age"
    if "age" in q:
        return "current_age"
    if any(kw in q for kw in ("budget", "price", "cost", "worth", "how expensive", "range", "amount")):
        return "target_amount"
    return ""


def _backfill_goal_from_clarifs(task: Dict[str, Any], clarifs: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    The routing model frequently mis-extracts structured values (e.g. "1-1.5 years" -> 1).
    The user's clarification answer is ground truth, so this deterministic post-process
    OVERRIDES the model's goal fields with values parsed from the matching Q&A.
    """
    from app.graph.tools.goal_planner_tool import _parse_amount

    goal = dict(task.get("goal") or {})
    SKIP = {"skip", "no", "none", "n/a", "na", "not sure", "idk", ""}

    for c in clarifs:
        q = c.get("q", "").lower()
        a = str(c.get("a", "")).strip()
        if a.lower() in SKIP:
            # An explicit "no savings" answer still means existing_savings = 0.
            if _classify_clarification(q) == "existing_savings":
                goal["existing_savings"] = 0.0
            continue

        field = _classify_clarification(q)
        if not field:
            continue

        if field == "target_amount":
            amt = _parse_amount(a)
            if amt:
                goal["target_amount"] = amt
        elif field == "timeline":
            # Keep the raw answer string — goal_planner parses "1-1.5 years" robustly.
            goal["timeline"] = a
        elif field == "existing_savings":
            amt = _parse_amount(a)
            goal["existing_savings"] = amt if amt is not None else 0.0
        elif field == "financing_preference":
            al = a.lower()
            if any(w in al for w in ("cash", "full", "outright")) and "loan" not in al:
                goal["financing_preference"] = "cash"
            elif "loan" in al or "emi" in al or "borrow" in al or "financ" in al:
                # "30% down, rest loan" etc. → hybrid; pure loan otherwise.
                goal["financing_preference"] = "hybrid" if ("down" in al or "%" in al) else "loan"
            elif "hybrid" in al or "both" in al:
                goal["financing_preference"] = "hybrid"
        elif field == "down_payment_pct":
            m = re.search(r"(\d+(?:\.\d+)?)", a)
            if m:
                goal["down_payment_pct"] = float(m.group(1))
        elif field == "target_months_coverage":
            m = re.search(r"(\d+)", a)
            if m:
                goal["target_months_coverage"] = float(m.group(1))
        elif field == "current_age":
            m = re.search(r"\b(\d{1,2})\b", a)
            if m:
                goal["current_age"] = float(m.group(1))
        elif field == "target_age":
            m = re.search(r"\b(\d{2})\b", a)
            if m:
                goal["target_age"] = float(m.group(1))

    task = dict(task)
    task["goal"] = goal
    return task


def brain_node(state: AgentState) -> dict:
    """Supervisor decision node with HITL bulk clarification via a single interrupt()."""
    iteration = (state.get("iterations") or 0) + 1
    clarifs: List[Dict[str, str]] = []

    # Short-circuit: goal_planner is terminal in our flow — once it has produced evidence,
    # finish immediately WITHOUT another (slow) supervisor LLM call.
    _existing = {e.get("tool") for e in (state.get("evidence") or [])}
    if "goal_planner" in _existing:
        logger.info("[brain] iter=%d goal_planner already ran -> finish (no LLM call)", iteration)
        return {"next_action": "finish", "brain_task": state.get("brain_task") or {}, "iterations": iteration}

    # Short-circuit: a single successful nl2sql answer to a BASIC data question is terminal.
    # Re-invoking the supervisor LLM (a ~40s call) only to re-run the same query — or to finally
    # decide "finish" — wastes time and can DUPLICATE the query when the model rephrases the
    # sub-question (defeating the exact-match repeat guard below). Mirror the goal_planner
    # short-circuit: once basic nl2sql has returned data with no error, finish with no LLM call.
    _prev_task = state.get("brain_task") or {}
    if str(_prev_task.get("analysis_type") or "").lower() == "basic":
        _nl_evs = [e for e in (state.get("evidence") or []) if e.get("tool") == "nl2sql"]
        if _nl_evs and not ((_nl_evs[-1].get("data") or {}).get("sql_error")):
            logger.info("[brain] iter=%d basic nl2sql already answered -> finish (no LLM call)", iteration)
            return {"next_action": "finish", "brain_task": _prev_task, "iterations": iteration}

    # First decision pass — no clarifications gathered yet this turn.
    decision = _decide(state, [], iteration)
    action = decision["next_action"]

    # Guard: a tool already ran this turn but the model wants to clarify again — it's stuck.
    # If a goal is in flight and goal_planner hasn't run, go straight to goal_planner;
    # otherwise just finish. Never re-open clarification mid-turn.
    _evidence_so_far = state.get("evidence") or []
    _tools_so_far = {e.get("tool") for e in _evidence_so_far}
    if action == "clarify" and _tools_so_far:
        _goal_type = ((decision.get("task") or {}).get("goal") or {}).get("goal_type")
        if "goal_planner" not in _tools_so_far and _goal_type:
            action = "goal_planner"
        else:
            action = "finish"
        logger.info("[brain] iter=%d tool already ran, suppressing re-clarify -> %s", iteration, action)
        decision = {**decision, "next_action": action}

    if action == "clarify" and iteration < MAX_ITERATIONS:
        # Collect ALL questions the brain wants to ask, then issue a SINGLE interrupt.
        # The frontend presents them one-at-a-time with a Skip option; when all are
        # answered it sends ONE resume payload with all answers as a JSON string.
        raw_questions: List[str] = decision.get("clarification_questions") or []
        if not raw_questions:
            # Backward-compat: single-question form from older prompt version
            single = decision.get("clarification_question") or "Could you clarify your request?"
            raw_questions = [single]

        logger.info("[brain] iter=%d clarify batch: %d question(s)", iteration, len(raw_questions))

        questions_payload = [{"id": f"q{i}", "question": q} for i, q in enumerate(raw_questions)]
        raw_answers = interrupt({
            "type": "clarification_batch",
            "questions": questions_payload,
        })

        # On resume the node re-executes from the top, so the questions above were
        # regenerated and may differ from what the user actually saw (the routing LLM is
        # not perfectly deterministic). The route passes the ORIGINAL questions back in the
        # resume payload — use them so answers map to the right questions by index.
        if isinstance(raw_answers, dict) and raw_answers.get("questions"):
            raw_questions = [q.get("question", "") for q in raw_answers["questions"]]
            raw_answers = raw_answers.get("answers")

        # Parse answers and re-decide once with full context.
        clarifs = _parse_bulk_answers(raw_questions, raw_answers)
        logger.info("[brain] clarification answered: %d/%d non-skipped", len(clarifs), len(raw_questions))
        decision = _decide(state, clarifs, iteration)
        action = decision["next_action"]

        # Always backfill goal fields from clarification answers — the model may have
        # failed to extract amounts/timelines into the structured task.goal.
        if clarifs:
            decision = {**decision, "task": _backfill_goal_from_clarifs(dict(decision.get("task") or {}), clarifs)}

        # Guard: if the model STILL wants to clarify after we already have answers, it's
        # confused. If a goal is present, go straight to goal_planner (it fetches its own
        # financial data); otherwise fall back to nl2sql for a general query.
        if action == "clarify":
            task_patch = dict(decision.get("task") or {})
            if (task_patch.get("goal") or {}).get("goal_type"):
                forced = "goal_planner"
            else:
                forced = "nl2sql"
                task_patch.setdefault("sub_question", state.get("user_query") or "")
            decision = {**decision, "next_action": forced, "task": task_patch}
            action = forced
            logger.warning("[brain] iter=%d still clarify after answers — forcing %s", iteration, forced)

    task = decision.get("task") or {}

    # Deterministic guards against runaway loops the prompt may miss:
    #  - knowledge / investment run at most once per turn;
    #  - goal_planner runs at most once per turn;
    #  - nl2sql may repeat for genuinely distinct sub-questions, capped at 4 per turn.
    evidence = state.get("evidence") or []
    existing_tools = {e.get("tool") for e in evidence}
    if action in ("knowledge", "investment", "goal_planner") and action in existing_tools:
        logger.info("[brain] iter=%d single-shot '%s' already ran -> finish", iteration, action)
        action = "finish"
    elif action == "nl2sql":
        nl2sql_evs = [e for e in evidence if e.get("tool") == "nl2sql"]
        sub_q = (task.get("sub_question") or "").strip().lower()
        repeated = any(str(e.get("task") or "").strip().lower() == sub_q for e in nl2sql_evs)
        if repeated or len(nl2sql_evs) >= 4:
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
