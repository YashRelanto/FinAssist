"""
graph/nodes.py
==============
All 9 node functions for the FinAssist LangGraph pipeline.

Each node:
  - Receives the full FinAssistState
  - Returns a PARTIAL dict of only the fields it modifies
  - Has no side-effects beyond logging and (in some cases) DB/API calls

Node inventory:
  1. input_guardrail_node      — Layer 1 security: prompt injection, length, profanity
  2. domain_scope_node         — Validates query is within supported financial domain
  3. intent_classifier_node    — Classifies intent + resolves multi-intent
  4. intent_router_node        — Pure Python routing hint (no LLM)
  5. nl2sql_node               — NL → SQL → Supabase → natural language answer
  6. workflow_relevance_node   — Checks if message continues an active HITL workflow
  7. rag_retrieval_node        — ChromaDB vector search
  8. workflow_slot_node        — HITL slot extraction + question generation
  9. advisor_node              — LLM answer generation with RAG context
 10. output_guardrail_node     — Layer 4 security: PII masking + secret leak prevention
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import openai

from app.core.config import settings
from app.graph.state import FinAssistState
from app.guardrails.input_guard import InputGuard
from app.guardrails.output_guard import OutputGuard
from app.utils.security_logger import log_security_event
from app.utils.prompts import (
    DOMAIN_SCOPE_SYSTEM,
    DOMAIN_SCOPE_USER,
    INTENT_CLASSIFIER_SYSTEM,
    INTENT_CLASSIFIER_USER,
    WORKFLOW_RELEVANCE_SYSTEM,
    WORKFLOW_RELEVANCE_USER,
    FINASSIST_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)

VALID_INTENTS = {"personal_transaction", "financial_knowledge", "financial_goal_planning"}
ROUTE_TO_NL2SQL_TOKEN = "ROUTE_TO_NL2SQL"

# Intent → ChromaDB collection mapping (mirrors AdvisorAgent)
INTENT_COLLECTION_MAP: Dict[str, List[str]] = {
    "financial_knowledge":    ["banking_data", "investment_data", "financial_tips"],
    "financial_goal_planning": ["financial_tips"],
    "personal_transaction":   [],
    "out_of_scope":           [],
}


def _get_client() -> openai.OpenAI:
    """Returns a configured OpenAI client using active settings."""
    return openai.OpenAI(
        api_key=settings.active_api_key,
        base_url=settings.active_base_url,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Node 1 — Input Guardrail
# ─────────────────────────────────────────────────────────────────────────────

def input_guardrail_node(state: FinAssistState) -> dict:
    """
    Layer 1 Security: validates the incoming user message.

    Uses InputGuard (regex-based, no LLM) to detect:
      - Prompt injection patterns (30+ rules)
      - Suspicious data-access phrases
      - Message length violations
      - Special character floods
      - Profanity

    On block → sets input_blocked=True and final_answer; graph routes to END.
    On pass  → sets input_blocked=False; graph continues to domain_scope.
    """
    user_id  = state["user_id"]
    thread_id = state["thread_id"]
    message  = state["user_message"]

    is_safe, error_message = InputGuard.validate(message, user_id)

    if not is_safe:
        log_security_event(
            user_id=user_id,
            thread_id=thread_id,
            event_type="prompt_injection_attempt" if "security" in error_message.lower() else "input_blocked",
            message=message,
            reason=error_message,
        )
        logger.warning("[Node:input_guardrail] BLOCKED | user=%s | reason=%s", user_id, error_message)
        return {
            "input_blocked": True,
            "input_error": error_message,
            "final_answer": error_message,
            "final_intent": "out_of_scope",
            "sources": ["Security Guardrails"],
        }

    logger.info("[Node:input_guardrail] PASSED | user=%s", user_id)
    return {"input_blocked": False}


# ─────────────────────────────────────────────────────────────────────────────
# Node 2 — Domain Scope Validator
# ─────────────────────────────────────────────────────────────────────────────

def domain_scope_node(state: FinAssistState) -> dict:
    """
    LLM call (temp=0, max_tokens=150, json_object) that determines whether
    the user's message falls within the supported financial domain.

    Supported: Banking, Investments, Personal Finance, Insurance, Tax, Retirement.
    Rejected:  Politics, Sports, Entertainment, Tech Support, Medical, Legal.

    On rejection → sets domain_supported=False and final_answer; routes to END.
    On approval  → sets domain_supported=True; routes to intent_classifier.
    """
    message = state["user_message"]
    lc_messages = state.get("messages", [])

    # Build history string from last 5 messages
    history_lines = []
    for m in lc_messages[-6:-1]:
        role = "User" if m.__class__.__name__ == "HumanMessage" else "Assistant"
        history_lines.append(f"{role}: {m.content}")
    history_str = "\n".join(history_lines) if history_lines else "None."

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=settings.active_chat_model,
            messages=[
                {"role": "system", "content": DOMAIN_SCOPE_SYSTEM},
                {"role": "user",   "content": DOMAIN_SCOPE_USER.format(history=history_str, message=message)},
            ],
            response_format={"type": "json_object"},
            max_tokens=150,
            temperature=0.0,
        )
        data = json.loads(response.choices[0].message.content.strip())
        supported = bool(data.get("supported", False))
        reason    = str(data.get("reason", ""))
        domain    = str(data.get("detected_domain", "unknown"))

        logger.info("[Node:domain_scope] supported=%s domain=%s", supported, domain)

        if not supported:
            out_msg = (
                "This assistant specialises in personal finance and financial planning. "
                "Please ask a finance-related question."
            )
            return {
                "domain_supported": False,
                "detected_domain":  domain,
                "domain_reason":    reason,
                "final_answer":     out_msg,
                "final_intent":     "out_of_scope",
                "sources":          ["Domain Scope Validator"],
            }

        return {
            "domain_supported": True,
            "detected_domain":  domain,
            "domain_reason":    reason,
        }

    except Exception as exc:
        logger.error("[Node:domain_scope] Failed: %s — proceeding safely", exc)
        return {"domain_supported": True, "detected_domain": "unknown"}


# ─────────────────────────────────────────────────────────────────────────────
# Node 3 — Intent Classifier
# ─────────────────────────────────────────────────────────────────────────────

def intent_classifier_node(state: FinAssistState) -> dict:
    """
    LLM call (temp=0, max_tokens=150, json_object) that:
      1. Classifies the message into 1–3 intents with confidence scores
      2. Filters candidates with confidence < 0.4
      3. Applies multi-intent resolution (Strategy A / Strategy B)

    Strategy A (dominant): top confidence ≥ 0.7 AND gap > 0.3 → route top intent
    Strategy B (ambiguous): both top-2 ≥ 0.6 AND gap ≤ 0.3   → ask for clarification

    Uses last 5 messages from LangGraph `messages` for context.
    """
    message   = state["user_message"]
    lc_messages = state.get("messages", [])

    # Build history string from last 5 LangChain messages (excluding the current one)
    history_lines = []
    for m in lc_messages[-6:-1]:  # -6 to -1 excludes the just-added HumanMessage
        role = "User" if m.__class__.__name__ == "HumanMessage" else "Assistant"
        history_lines.append(f"{role}: {m.content}")
    history_str = "\n".join(history_lines) if history_lines else "None."

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=settings.active_chat_model,
            messages=[
                {"role": "system", "content": INTENT_CLASSIFIER_SYSTEM},
                {"role": "user",   "content": INTENT_CLASSIFIER_USER.format(
                    message=message, history=history_str)},
            ],
            response_format={"type": "json_object"},
            max_tokens=150,
            temperature=0.0,
        )
        data = json.loads(response.choices[0].message.content.strip())
        raw_candidates = data.get("intent_candidates", [])

        # Normalise and filter
        candidates = []
        for c in raw_candidates:
            intent = str(c.get("intent", "financial_knowledge")).lower().strip()
            if intent not in VALID_INTENTS:
                intent = "financial_knowledge"
            c["intent"] = intent
            if float(c.get("confidence", 0.0)) >= 0.4:
                candidates.append(c)

        if not candidates:
            candidates = [{"intent": "financial_knowledge", "confidence": 1.0}]

        logger.info("[Node:intent_classifier] candidates=%s", candidates)

    except Exception as exc:
        logger.error("[Node:intent_classifier] Failed: %s", exc)
        candidates = [{"intent": "financial_knowledge", "confidence": 1.0}]

    # ── Single-Intent Resolution (always pick dominant) ───────────────────
    sorted_c = sorted(candidates, key=lambda x: x.get("confidence", 0.0), reverse=True)
    selected_intent = sorted_c[0]["intent"]

    return {
        "intent_candidates": candidates,
        "multi_intent_type": "route_dominant",
        "selected_intent":   selected_intent,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 4 — Intent Router  (pure Python, no LLM)
# ─────────────────────────────────────────────────────────────────────────────

def intent_router_node(state: FinAssistState) -> dict:
    """
    Pure routing node — reads selected_intent + workflow_active and determines
    the next branch.  This node sets no new state; the conditional edge
    function `route_after_intent_router` reads the same state fields.

    We keep this as an explicit node (rather than embedding logic in edges)
    so LangGraph Studio can display it as a visible step in the trace.
    """
    logger.info(
        "[Node:intent_router] intent=%s workflow_active=%s",
        state.get("selected_intent"),
        state.get("workflow_active", False),
    )
    return {}  # no state changes — edge function does the branching


# ─────────────────────────────────────────────────────────────────────────────
# Node 5a — NL2SQL Node
# ─────────────────────────────────────────────────────────────────────────────

async def nl2sql_node(state: FinAssistState) -> dict:
    """
    Translates the user's natural language question into a targeted
    Supabase query and returns a precise, fact-grounded answer.

    Delegates entirely to the existing NL2SQL pipeline:
      execute_nl2sql() → plan_query() → execute_query() → _generate_answer()
    (or fallback summary path if spec is degenerate)
    """
    from app.utils.nl2sql import execute_nl2sql

    user_id = state["user_id"]
    message = state["user_message"]

    logger.info("[Node:nl2sql] user=%s", user_id)

    try:
        answer = await execute_nl2sql(user_id, message)
    except Exception as exc:
        logger.error("[Node:nl2sql] Failed: %s", exc)
        answer = f"I encountered an error while looking up your transaction data: {exc}"

    return {
        "raw_answer":   answer,
        "sources":      ["Supabase Transactions"],
        "final_intent": "personal_transaction",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 5b — Workflow Relevance Node
# ─────────────────────────────────────────────────────────────────────────────

def workflow_relevance_node(state: FinAssistState) -> dict:
    """
    LLM call (temp=0, max_tokens=150, json_object) that decides whether the
    user's latest message is answering the active HITL workflow question or
    changing the subject to a different topic.

    workflow_related=True  → continue slot filling (route to workflow_slot)
    workflow_related=False → pause workflow, answer new question (route to intent_router)
    """
    message        = state["user_message"]
    workflow_state = state.get("workflow_state", {})

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=settings.active_chat_model,
            messages=[
                {"role": "system", "content": WORKFLOW_RELEVANCE_SYSTEM},
                {"role": "user",   "content": WORKFLOW_RELEVANCE_USER.format(
                    message=message,
                    workflow_state=json.dumps(workflow_state, indent=2),
                )},
            ],
            response_format={"type": "json_object"},
            max_tokens=150,
            temperature=0.0,
        )
        data = json.loads(response.choices[0].message.content.strip())
        related    = bool(data.get("workflow_related", False))
        confidence = float(data.get("confidence", 0.0))
        reason     = str(data.get("reason", ""))

        logger.info("[Node:workflow_relevance] related=%s conf=%.2f reason='%s'",
                    related, confidence, reason)

        if not related:
            # Pause the active workflow so it can resume later
            updated_wf = dict(workflow_state)
            updated_wf["workflow_status"] = "paused"
            updated_wf["last_updated"]    = datetime.now(timezone.utc).isoformat()
            return {
                "workflow_related": False,
                "workflow_state":   updated_wf,
                "workflow_active":  False,
            }

        return {"workflow_related": True}

    except Exception as exc:
        logger.error("[Node:workflow_relevance] Failed: %s — defaulting to not related", exc)
        return {"workflow_related": False}


# ─────────────────────────────────────────────────────────────────────────────
# Node 5c — RAG Retrieval Node
# ─────────────────────────────────────────────────────────────────────────────

def rag_retrieval_node(state: FinAssistState) -> dict:
    """
    Performs vector search on ChromaDB collections mapped to the selected intent.

    Collections searched per intent:
      financial_knowledge    → banking_data, investment_data, financial_tips
      financial_goal_planning → financial_tips

    Deduplicates results by exact text match (seen_texts set).
    Caps at 5 context blocks.
    Tracks minimum cosine distance to determine retrieval confidence.

    High confidence (distance ≤ 0.6) → context passed to advisor_node.
    Low confidence  (distance > 0.6) → advisor_node falls back to LLM general knowledge.
    """
    from app.utils.chroma_store import chroma_db

    intent  = state.get("selected_intent", "financial_knowledge")
    message = state["user_message"]

    collections = INTENT_COLLECTION_MAP.get(intent, ["financial_tips"])

    seen_texts:     set   = set()
    context_blocks: List  = []
    source_refs:    List  = []
    min_distance:   float = 1.0

    for collection_name in collections:
        try:
            results = chroma_db.search(collection_name=collection_name, query=message, n_results=3)
            for doc in results:
                text = (doc.get("text") or doc.get("document") or "").strip()
                if not text or text in seen_texts:
                    continue
                seen_texts.add(text)
                context_blocks.append(text)
                meta = doc.get("metadata") or {}
                source_refs.append(meta.get("source", meta.get("title", "FinAssist Knowledge Base")))
                dist = doc.get("distance", 1.0)
                if dist < min_distance:
                    min_distance = dist
        except Exception as exc:
            logger.warning("[Node:rag_retrieval] ChromaDB error for '%s': %s", collection_name, exc)

    # ── Hybrid Fallback: Live Web Search ──────────────────────────────────
    if not context_blocks or min_distance > 0.6:
        logger.info("[Node:rag_retrieval] Local RAG miss (min_dist=%.3f) — Triggering Live Web Search for: %s", min_distance, message)
        try:
            from app.utils.scrapers import live_web_search_and_scrape
            scraped_text, source_url = live_web_search_and_scrape(message, max_results=1)
            if scraped_text:
                context_blocks = [scraped_text]
                source_refs = [f"Live Web Search ({source_url})"]
                min_distance = 0.1  # Highly confident since it's a live direct search
                logger.info("[Node:rag_retrieval] Live Web Search succeeded: %s", source_url)
            else:
                logger.info("[Node:rag_retrieval] Live Web Search returned no usable text.")
        except Exception as e:
            logger.error("[Node:rag_retrieval] Live Web Search failed: %s", e)

    logger.info("[Node:rag_retrieval] intent=%s blocks=%d min_dist=%.3f",
                intent, len(context_blocks), min_distance)

    return {
        "retrieved_context": context_blocks[:5],
        "context_sources":   source_refs[:5],
        "rag_confidence":    min_distance,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 6a — Workflow Slot Node
# ─────────────────────────────────────────────────────────────────────────────

def workflow_slot_node(state: FinAssistState) -> dict:
    """
    Drives the HITL multi-turn slot-filling loop.
    Delegates to WorkflowAgent.process() — the slot extraction and question
    generation logic is unchanged from the original implementation.

    If slots remain missing:
      → sets final_answer to the next clarification question, routes to END

    If all slots are collected:
      → sets workflow_active=False, advisor_ready, routes to advisor_node
    """
    from app.utils.workflow_logic import WorkflowLogic
    from langchain_core.messages import HumanMessage, AIMessage

    message        = state["user_message"]
    workflow_state = state.get("workflow_state", {})
    lc_messages    = state.get("messages", [])

    # Convert LangChain messages → plain dicts for WorkflowAgent
    history = []
    for m in lc_messages[-10:]:
        if isinstance(m, HumanMessage):
            history.append({"role": "user", "content": m.content})
        elif isinstance(m, AIMessage):
            history.append({"role": "assistant", "content": m.content})

    logger.info("[Node:workflow_slot] workflow_type=%s collected=%s",
                workflow_state.get("workflow_type"), list(workflow_state.get("collected_information", {}).keys()))

    requires_clarification, next_question, updated_state = WorkflowLogic.process(
        message, history, workflow_state
    )

    if requires_clarification:
        # Still collecting slots — ask the next question
        return {
            "workflow_state":  updated_state,
            "workflow_active": True,
            "final_answer":    next_question,
            "final_intent":    "financial_goal_planning",
            "sources":         ["Clarification Planner"],
        }

    # All slots filled — hand off to advisor_node
    return {
        "workflow_state":  updated_state,
        "workflow_active": False,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 6b — Advisor Node (RAG Answer Generator)
# ─────────────────────────────────────────────────────────────────────────────

def advisor_node(state: FinAssistState) -> dict:
    """
    Generates the final LLM answer using:
      - Retrieved ChromaDB context (from rag_retrieval_node)
      - Workflow slot data (if coming from a completed HITL workflow)
      - User profile (income, segment, city, risk_profile, credit_score)
      - Last 10 conversation messages from LangGraph state

    If the LLM emits the ROUTE_TO_NL2SQL_TOKEN, sets route_to_nl2sql=True
    and returns an empty raw_answer — the conditional edge reroutes to nl2sql_node.

    LLM params: max_tokens=700, temperature=0.2 (slightly creative but factual)
    """
    from app.utils.workflow_logic import WorkflowLogic
    from langchain_core.messages import HumanMessage, AIMessage

    message         = state["user_message"]
    intent          = state.get("selected_intent", "financial_knowledge")
    profile         = state.get("user_profile", {})
    workflow_state  = state.get("workflow_state", {})
    context_blocks  = state.get("retrieved_context", [])
    source_refs     = state.get("context_sources", [])
    min_distance    = state.get("rag_confidence", 1.0)
    lc_messages     = state.get("messages", [])

    # ── Build context text ────────────────────────────────────────────────
    if context_blocks and min_distance <= 0.6:
        context_text = "\n\n---\n\n".join(context_blocks)
        sources = source_refs if source_refs else ["FinAssist Knowledge Base"]
    else:
        logger.info("[Node:advisor] Low RAG confidence (%.3f) — using LLM general knowledge", min_distance)
        context_text = (
            "No highly relevant documents found in the knowledge base. "
            "Use your general financial expertise to answer, while maintaining safety guidelines."
        )
        sources = ["FinAssist General Knowledge"]

    # ── Inject workflow slots if this is the final goal-planning answer ───
    if workflow_state and workflow_state.get("collected_information"):
        slots_str = WorkflowLogic.format_filled_slots(workflow_state["collected_information"])
        context_text = (
            f"User Scenario Details (ALL these details are already provided):\n{slots_str}\n\n{context_text}"
        )

    # ── Format user profile ───────────────────────────────────────────────
    income        = profile.get("income", "unknown")
    annual_income = profile.get("annual_income", income)
    segment       = profile.get("segment", "General")
    city          = profile.get("city", "India")
    risk_profile  = profile.get("risk_profile", "Moderate")
    credit_score  = profile.get("credit_score", "N/A")
    current_date  = datetime.now().strftime("%d %B %Y")
    income_display = f"₹{annual_income:,.0f} per annum" if isinstance(annual_income, (int, float)) else str(annual_income)
    real_time_balances = profile.get("real_time_balances", "N/A")
    monthly_net_flow = profile.get("monthly_net_flow", "N/A")

    system_prompt = FINASSIST_SYSTEM_PROMPT.format(
        current_date=current_date,
        income_display=income_display,
        segment=segment,
        city=city,
        risk_profile=risk_profile,
        credit_score=credit_score,
        real_time_balances=real_time_balances,
        monthly_net_flow=monthly_net_flow,
        context_text=context_text,
    )

    # ── Build messages list ───────────────────────────────────────────────
    recent_history = []
    for m in lc_messages[-11:-1]:   # last 10, excluding the current HumanMessage
        if isinstance(m, HumanMessage):
            recent_history.append({"role": "user",      "content": m.content})
        elif isinstance(m, AIMessage):
            recent_history.append({"role": "assistant", "content": m.content})

    messages_for_llm = [{"role": "system", "content": system_prompt}]
    messages_for_llm.extend(recent_history)
    messages_for_llm.append({"role": "user", "content": message})

    # ── LLM call ─────────────────────────────────────────────────────────
    answer         = ""
    route_to_nl2sql = False

    try:
        client = _get_client()
        completion = client.chat.completions.create(
            model=settings.active_chat_model,
            messages=messages_for_llm,
            max_tokens=700,
            temperature=0.2,
        )
        answer = completion.choices[0].message.content.strip()

        if answer.strip().upper().startswith(ROUTE_TO_NL2SQL_TOKEN):
            logger.info("[Node:advisor] LLM emitted ROUTE_TO_NL2SQL — rerouting to NL2SQL")
            route_to_nl2sql = True
            answer = ""

    except Exception as exc:
        logger.error("[Node:advisor] LLM call failed: %s", exc)
        answer = "I encountered a temporary issue generating your response. Please try again in a moment."

    logger.info("[Node:advisor] intent=%s route_to_nl2sql=%s", intent, route_to_nl2sql)

    return {
        "raw_answer":      answer,
        "sources":         sources,
        "route_to_nl2sql": route_to_nl2sql,
        "final_intent":    intent,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 7 — Output Guardrail
# ─────────────────────────────────────────────────────────────────────────────

def output_guardrail_node(state: FinAssistState) -> dict:
    """
    Layer 4 Security: validates the LLM-generated answer before delivery.

    Checks (in order):
      1. Sensitive credential leakage (API keys, JWT, DB connection strings, private keys)
         → Hard block: returns generic apology
      2. Raw SQL in response
         → Sanitise: replaces SQL fragments with [System Query Removed for Security]
      3. Residual PII (PAN, Aadhaar, phone, account numbers, UPI IDs, email, IFSC)
         → PIIMasker.mask_all() applied to cleaned response

    Sets final_answer to the cleaned (or blocked) response.
    """
    user_id   = state["user_id"]
    thread_id = state["thread_id"]
    message   = state["user_message"]
    raw       = state.get("raw_answer") or ""

    is_safe, cleaned = OutputGuard.validate_and_clean(raw, user_id)

    if not is_safe:
        log_security_event(
            user_id=user_id,
            thread_id=thread_id,
            event_type="output_blocked",
            message=message,
            reason="Sensitive credentials or system data detected in LLM output",
        )
        logger.error("[Node:output_guardrail] BLOCKED output | user=%s", user_id)
        return {
            "output_blocked": True,
            "final_answer":   cleaned,
            "sources":        ["Security Guardrails"],
        }

    logger.info("[Node:output_guardrail] PASSED | user=%s", user_id)
    return {
        "output_blocked": False,
        "final_answer":   cleaned,
    }
