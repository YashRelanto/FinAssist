"""
graph/state.py
==============
Minimal AgentState for the FinAssist Brain (Supervisor) + tool-loop graph.

The Brain is a supervisor node that decides, each pass, which tool to call
(nl2sql / goal_planner / investment / knowledge) — accumulating results into
`evidence` — until it has enough information to `finish`, at which point the
answer node synthesises the final structured response. Clarification is handled
inside the Brain via LangGraph `interrupt` (HITL pause/resume), so it is not a
state machine of its own.

The `messages` field uses LangGraph's `add_messages` reducer and `evidence`
uses an additive reducer — both append rather than replace across nodes.
"""

from __future__ import annotations

import time
from typing import Annotated, Any, Dict, List, Optional
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph.message import add_messages


def merge_evidence(current: List[Dict[str, Any]] | None,
                   update: List[Dict[str, Any]] | None) -> List[Dict[str, Any]]:
    """
    Reducer for `evidence`.

    Tools append one or more non-empty items during a turn, so those accumulate.
    An empty (or None) update is the per-turn RESET signal — only
    `make_initial_state` sends `evidence=[]`, which must CLEAR last turn's evidence
    rather than merge with it (the checkpointer persists state across turns, and a
    plain `operator.add` reducer would otherwise keep stale evidence forever).
    """
    if not update:
        return []
    return (current or []) + list(update)


def keep_last_goal(current: Dict[str, Any] | None,
                   update: Dict[str, Any] | None) -> Dict[str, Any]:
    """Reducer for `last_goal`. A NON-EMPTY update REPLACES it (goal_planner stored a fresh goal);
    an EMPTY update — `make_initial_state`'s per-turn reset — KEEPS the persisted goal so a what-if
    in a LATER turn can still build on the original plan (carrying target_amount, timeline, etc.)."""
    return update if update else (current or {})


class AgentState(TypedDict, total=False):
    """Lean state passed between nodes in the supervisor graph."""

    # ── Input (set once per turn by the chatbot route) ────────────────
    user_id:      str               # Supabase user UUID
    session_id:   str               # Conversation thread UUID
    user_query:   str               # Latest user message text
    user_profile: Dict[str, Any]    # Income, balances, net flow, etc.

    # ── Conversation history (append-only reducer) ───────────────────
    messages: Annotated[List[BaseMessage], add_messages]

    # ── Input Guardrail ──────────────────────────────────────────────
    input_blocked: bool

    # ── Brain supervisor loop ────────────────────────────────────────
    next_action: str                # nl2sql | goal_planner | investment | knowledge | out_of_scope | finish
    brain_task:  Dict[str, Any]     # instruction for the chosen tool
    # Persists across turns (kept by `keep_last_goal` when reset) so what-ifs can build on it.
    last_goal:   Annotated[Dict[str, Any], keep_last_goal]
    iterations:  int                # number of Brain passes this turn
    evidence:    Annotated[List[Dict[str, Any]], merge_evidence]  # [{tool, task, summary, data}]

    # ── NL2SQL scratch (consumed by the reused SQL chain) ────────────
    sql_ast:       Dict[str, Any]
    sql_query:     Any                  # str, or {"query_a","query_b"} for comparisons
    sql_valid:     bool
    sql_results:   List[Dict[str, Any]]
    sql_error:     Optional[str]
    analysis_type: str                  # basic | trend | comparison | anomaly

    # ── Knowledge tool scratch ───────────────────────────────────────
    retrieved_context: List[str]

    # ── Output ───────────────────────────────────────────────────────
    final_answer:   Optional[str]
    artifacts:      List[Dict[str, Any]]   # visualization specs for the frontend
    scenario_cards: List[Dict[str, Any]]   # per-scenario cards (goal planning) for the frontend
    sources:        List[str]
    final_intent:   Optional[str]
    output_blocked: bool

    # ── Observability ────────────────────────────────────────────────
    metadata: Dict[str, Any]            # iterations, tools_used, token usage


def make_initial_state(
    user_id: str,
    session_id: str,
    user_query: str,
    user_profile: Dict[str, Any],
) -> AgentState:
    """Build a clean initial AgentState for the start of each graph invocation."""
    return AgentState(
        # Input
        user_id=user_id,
        session_id=session_id,
        user_query=user_query,
        user_profile=user_profile,
        messages=[HumanMessage(content=user_query)],

        # Guardrail
        input_blocked=False,

        # Brain loop
        next_action="",
        brain_task={},
        last_goal={},
        iterations=0,
        evidence=[],

        # SQL scratch
        sql_ast={},
        sql_query="",
        sql_valid=False,
        sql_results=[],
        sql_error=None,
        analysis_type="basic",

        # Knowledge scratch
        retrieved_context=[],

        # Output
        final_answer=None,
        artifacts=[],
        scenario_cards=[],
        sources=[],
        final_intent=None,
        output_blocked=False,

        # Observability
        metadata={"start_time": time.time()},
    )
