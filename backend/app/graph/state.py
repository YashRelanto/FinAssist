"""
graph/state.py
==============
Defines the single typed state object that flows through the LangGraph
FinAssist pipeline.  Every node reads from and writes a subset of these fields.

The `messages` field uses LangGraph's `add_messages` reducer — messages are
automatically appended rather than replaced on each node update.
"""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Optional
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class FinAssistState(TypedDict, total=False):
    """
    Complete state object passed between every node in the FinAssist graph.

    Fields are grouped by pipeline stage:
      - Input         : values set once by the chatbot route before graph invocation
      - Messages      : LangGraph-managed conversation history (append-only)
      - Security      : results from input/output guardrail nodes
      - Domain Scope  : result of domain validation node
      - Intent        : result of intent classification + multi-intent resolution
      - Workflow/HITL : current HITL slot-filling state
      - RAG           : ChromaDB retrieval results
      - Answer        : raw and final answers
    """

    # ── Input (set once by the chatbot route) ─────────────────────────────
    user_id:      str          # Supabase user UUID
    thread_id:    str          # Conversation thread UUID
    user_message: str          # Latest user message text
    user_profile: Dict[str, Any]  # Income, segment, risk_profile, city, credit_score …

    # ── Conversation history (LangGraph-managed, append-only reducer) ─────
    messages: Annotated[List[BaseMessage], add_messages]

    # ── Security — Input Guard ────────────────────────────────────────────
    input_blocked: bool         # True when InputGuard blocks the message
    input_error:   Optional[str]  # Human-readable reason for the block

    # ── Domain Scope ──────────────────────────────────────────────────────
    domain_supported: Optional[bool]  # True = in-scope financial query
    detected_domain:  Optional[str]   # e.g. "banking", "investment"
    domain_reason:    Optional[str]   # Brief explanation from scope validator

    # ── Intent ────────────────────────────────────────────────────────────
    intent_candidates: List[Dict]     # [{"intent": str, "confidence": float}, …]
    selected_intent:   Optional[str]  # Winning intent after multi-intent resolution
    multi_intent_type: Optional[str]  # "route_dominant" | "clarification_required"

    # ── Workflow / HITL ───────────────────────────────────────────────────
    workflow_state:   Dict[str, Any]  # Full WorkflowAgent state dict
    workflow_active:  bool            # True when a HITL workflow is in progress
    workflow_related: Optional[bool]  # True if message answers an active workflow question

    # ── RAG Retrieval ─────────────────────────────────────────────────────
    retrieved_context: List[str]   # Text chunks from ChromaDB (deduplicated)
    context_sources:   List[str]   # Source labels for each chunk
    rag_confidence:    float       # Minimum cosine distance across retrieved chunks

    # ── Answer Production ─────────────────────────────────────────────────
    raw_answer:      Optional[str]  # LLM-generated answer before output guardrail
    sources:         List[str]      # Final source attribution list
    route_to_nl2sql: bool           # True when AdvisorAgent emits ROUTE_TO_NL2SQL

    # ── Output (after output guardrail) ───────────────────────────────────
    final_answer:  Optional[str]  # Cleaned and PII-masked answer
    final_intent:  Optional[str]  # Resolved intent sent in ChatResponse
    output_blocked: bool          # True when OutputGuard hard-blocks the response


def make_initial_state(
    user_id: str,
    thread_id: str,
    user_message: str,
    user_profile: Dict[str, Any],
    workflow_state: Optional[Dict[str, Any]] = None,
    workflow_active: bool = False,
) -> FinAssistState:
    """
    Build a clean initial FinAssistState dict for the start of each graph invocation.
    Called by the chatbot route before calling graph.ainvoke().
    """
    from langchain_core.messages import HumanMessage

    return FinAssistState(
        user_id=user_id,
        thread_id=thread_id,
        user_message=user_message,
        user_profile=user_profile,
        messages=[HumanMessage(content=user_message)],
        # Security
        input_blocked=False,
        input_error=None,
        # Domain
        domain_supported=None,
        detected_domain=None,
        domain_reason=None,
        # Intent
        intent_candidates=[],
        selected_intent=None,
        multi_intent_type=None,
        # Workflow
        workflow_state=workflow_state or {},
        workflow_active=workflow_active,
        workflow_related=None,
        # RAG
        retrieved_context=[],
        context_sources=[],
        rag_confidence=1.0,
        # Answer
        raw_answer=None,
        sources=[],
        route_to_nl2sql=False,
        # Output
        final_answer=None,
        final_intent=None,
        output_blocked=False,
    )
