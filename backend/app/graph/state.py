"""
graph/state.py
==============
Defines the AgentState TypedDict that flows through the FinAssist LangGraph v2
pipeline. Every node reads from and writes a subset of these fields.

The `messages` field uses LangGraph's `add_messages` reducer — messages are
automatically appended rather than replaced on each node update.
"""

from __future__ import annotations

import time
from typing import Annotated, Any, Dict, List, Optional
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph.message import add_messages

from app.utils.temporal_context import get_time_context


class AgentState(TypedDict, total=False):
    """
    Complete state object passed between every node in the FinAssist v2 graph.

    Fields are grouped by pipeline stage:
      - Input           : set once by chatbot route before graph invocation
      - Messages        : LangGraph-managed conversation history (append-only)
      - Guardrail       : input/output security check results
      - Intent          : classification result
      - Context         : follow-up query resolution
      - Entities        : structured extraction from query
      - Semantic        : DB-normalized entities
      - Clarification   : ambiguity detection
      - Agent Routing   : which agent handles the query
      - Goal Planning   : HITL slot-filling workflow state
      - SQL Pipeline    : AST → validated SQL → execution results
      - Analytics       : computed aggregates, trends, anomalies
      - RAG             : ChromaDB retrieval results (for knowledge queries)
      - Answer          : raw and final answers
      - Observability   : execution metrics
    """

    # ── Input (set once by the chatbot route) ─────────────────────────
    user_id:      str               # Supabase user UUID
    session_id:   str               # Conversation thread UUID (from frontend)
    user_query:   str               # Latest user message text (raw)
    user_profile: Dict[str, Any]    # Income, segment, risk_profile, city, etc.

    # ── Conversation history (LangGraph-managed, append-only reducer) ─
    messages: Annotated[List[BaseMessage], add_messages]

    # ── Security — Input Guard ────────────────────────────────────────
    input_blocked: bool              # True when InputGuard blocks the message
    input_error:   Optional[str]     # Human-readable reason for the block
    validated_query: str             # Normalized query after input guard (FR-1)

    # ── Intent Classification ─────────────────────────────────────────
    intent:     str                  # TRANSACTION_QUERY, SPENDING_SUMMARY, etc.
    confidence: float                # Classification confidence score

    # ── Context Resolution (follow-up handling) ───────────────────────
    rewritten_query: str             # Resolved query after follow-up merging
    standalone_query: str            # BRD alias for rewritten_query

    # ── Entity Extraction ─────────────────────────────────────────────
    entities: Dict[str, Any]         # Structured: merchant, category, dates, metric, etc.

    # ── Semantic Resolution ───────────────────────────────────────────
    resolved_entities: Dict[str, Any]  # DB-normalized entities (fuzzy → exact names)

    # ── Clarification ─────────────────────────────────────────────────
    clarification_needed:   bool
    clarification_question: str
    clarification_options:  List[str]
    clarification_history:  List[Dict[str, Any]]
    clarification_complete: bool

    # ── Semantic Reasoning (Brain prep) ───────────────────────────────
    semantic_context: Dict[str, Any]

    # ── Brain Orchestration ───────────────────────────────────────────
    execution_plan: Dict[str, Any]
    rag_results: Dict[str, Any]
    agent_results: List[Dict[str, Any]]
    portfolio_results: Dict[str, Any]
    final_context: Dict[str, Any]

    # ── Agent Routing (legacy + tool execution) ───────────────────────
    selected_agent: str              # transaction, comparison, trend, anomaly, knowledge
    agent_context:  Dict[str, Any]   # Agent-specific parameters / instructions

    # ── Goal Planning / HITL Workflow ─────────────────────────────────
    workflow_state:   Dict[str, Any]   # Slot-filling state (type, collected_info, missing)
    workflow_active:  bool             # True when HITL workflow is in progress
    workflow_related: Optional[bool]   # True if message continues active workflow

    # ── SQL Pipeline ──────────────────────────────────────────────────
    sql_ast:               Dict[str, Any]   # Structured query specification (AST)
    sql_query:             str              # Generated SQL string
    sql_valid:             bool             # Whether SQL passed validation
    sql_validation_errors: List[str]        # Validation error messages
    sql_results:           List[Dict]       # Raw Supabase query results
    sql_error:             Optional[str]    # Execution error message

    # ── Analytics ─────────────────────────────────────────────────────
    analytics_results: Dict[str, Any]  # Computed aggregates, trends, anomalies

    # ── RAG Retrieval (preserved for knowledge queries) ───────────────
    retrieved_context: List[str]    # Text chunks from ChromaDB (deduplicated)
    context_sources:   List[str]   # Source labels for each chunk
    rag_confidence:    float       # Minimum cosine distance across retrieved chunks

    # ── Answer Production ─────────────────────────────────────────────
    raw_answer:     Optional[str]   # LLM-generated answer before output guardrail
    final_answer:   Optional[str]   # Cleaned and PII-masked answer
    final_intent:   Optional[str]   # Resolved intent sent in ChatResponse
    sources:        List[str]       # Source attribution list
    output_blocked: bool            # True when OutputGuard hard-blocks the response

    # ── Observability ─────────────────────────────────────────────────
    metadata: Dict[str, Any]        # execution_time, token_usage, node timings


def make_initial_state(
    user_id: str,
    session_id: str,
    user_query: str,
    user_profile: Dict[str, Any],
    workflow_state: Optional[Dict[str, Any]] = None,
    workflow_active: bool = False,
) -> AgentState:
    """
    Build a clean initial AgentState dict for the start of each graph invocation.
    Called by the chatbot route before calling graph.ainvoke().
    """
    return AgentState(
        # Input
        user_id=user_id,
        session_id=session_id,
        user_query=user_query,
        user_profile=user_profile,
        messages=[HumanMessage(content=user_query)],

        # Security
        input_blocked=False,
        input_error=None,
        validated_query="",

        # Intent
        intent="",
        confidence=0.0,

        # Context
        rewritten_query="",
        standalone_query="",

        # Entities
        entities={},
        resolved_entities={},

        # Clarification
        clarification_needed=False,
        clarification_question="",
        clarification_options=[],
        clarification_history=[],
        clarification_complete=True,

        # Semantic / Brain
        semantic_context={},
        execution_plan={},
        rag_results={},
        agent_results=[],
        portfolio_results={},
        final_context={},

        # Routing
        selected_agent="",
        agent_context={},

        # Workflow
        workflow_state=workflow_state or {},
        workflow_active=workflow_active,
        workflow_related=None,

        # SQL
        sql_ast={},
        sql_query="",
        sql_valid=False,
        sql_validation_errors=[],
        sql_results=[],
        sql_error=None,

        # Analytics
        analytics_results={},

        # RAG
        retrieved_context=[],
        context_sources=[],
        rag_confidence=1.0,

        # Answer
        raw_answer=None,
        final_answer=None,
        final_intent=None,
        sources=[],
        output_blocked=False,

        # Observability
        metadata={"start_time": time.time(), "time_context": get_time_context()},
    )
