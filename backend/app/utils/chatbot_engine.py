"""
Core intelligence coordinator for the FinAssist Financial AI Advisor chatbot.

Responsibilities:
  - SessionManager  : thread-safe JSON-based conversation state persistence
  - classify_intent : 4-category LLM intent router with Domain Guard
  - run_dynamic_goal_planner : Dynamic Clarification Planner for financial goals
  - execute_rag     : ChromaDB multi-collection retrieval + FinAssist advisor generation
  - process_chat_message : top-level async orchestrator executing the 7-layer guardrails

Intent taxonomy (v4):
  personal_transaction | financial_knowledge | financial_goal_planning | out_of_scope
"""

import json
import os
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple, List, Dict, Any

import openai

# Import config first — this triggers dotenv loading before any os.getenv call
from app.core.config import settings
from app.utils.chroma_store import chroma_db
from app.utils.nl2sql import execute_nl2sql
from app.guardrails import Guardrails
from app.utils.security_logger import log_security_event
from app.utils.prompts import (
    INTENT_CLASSIFIER_SYSTEM,
    INTENT_CLASSIFIER_USER,
    GOAL_PLANNER_SYSTEM,
    GOAL_PLANNER_USER,
    FINASSIST_SYSTEM_PROMPT,
)

# ─── Logging ────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────────────

SESSIONS_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "sessions.json")
SESSIONS_FILE = os.path.normpath(SESSIONS_FILE)

# 4-category intent taxonomy
VALID_INTENTS = {
    "personal_transaction",
    "financial_knowledge",
    "financial_goal_planning",
    "out_of_scope",
}

# Map each intent to one or more ChromaDB collection names.
INTENT_COLLECTION_MAP: dict[str, list[str]] = {
    "financial_knowledge":     ["banking_data", "investment_data", "financial_tips"],
    "financial_goal_planning":  ["financial_tips"],
    "personal_transaction":    [],
    "out_of_scope":            [],
}

# Token the LLM can emit when it detects personal-data intent mid-turn
ROUTE_TO_NL2SQL_TOKEN = "ROUTE_TO_NL2SQL"

# ── Active LLM settings (resolved from LLM_PROVIDER env var) ────────────────
OPENAI_MODEL = settings.active_chat_model

logger.info(
    "[ChatbotEngine] LLM Provider: %s | Model: %s | Base URL: %s",
    settings.LLM_PROVIDER.upper(),
    settings.active_chat_model,
    settings.active_base_url,
)


# ─── SessionManager ──────────────────────────────────────────────────────────

class SessionManager:
    """
    Manages per-user, per-thread conversation history stored in a local
    sessions.json file.
    """

    def __init__(self, sessions_file: str = SESSIONS_FILE):
        self.sessions_file = sessions_file
        self._ensure_file()

    def _ensure_file(self) -> None:
        """Create the sessions file and its parent directory if absent."""
        os.makedirs(os.path.dirname(self.sessions_file), exist_ok=True)
        if not os.path.exists(self.sessions_file):
            with open(self.sessions_file, "w", encoding="utf-8") as fh:
                json.dump({}, fh, indent=2)

    def _load(self) -> dict:
        try:
            with open(self.sessions_file, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            logger.warning("sessions.json unreadable or corrupt — resetting.")
            return {}

    def _save(self, data: dict) -> None:
        try:
            with open(self.sessions_file, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
        except OSError as exc:
            logger.error("Failed to persist sessions.json: %s", exc)

    def get_state(self, user_id: str, thread_id: str) -> list[dict]:
        """Return the ordered message list for a specific user/thread pair."""
        data = self._load()
        thread_data = data.get(user_id, {}).get(thread_id, [])
        if isinstance(thread_data, list):
            return thread_data
        elif isinstance(thread_data, dict):
            return thread_data.get("messages", [])
        return []

    def get_clarification_state(self, user_id: str, thread_id: str) -> dict:
        """Return the persistent clarification state for a specific user/thread pair."""
        data = self._load()
        thread_data = data.get(user_id, {}).get(thread_id, {})
        if isinstance(thread_data, dict):
            return thread_data.get("clarification_state", {})
        return {}

    def update_state(
        self,
        user_id: str,
        thread_id: str,
        messages: list[dict],
    ) -> None:
        """Persist the full updated message list for a user/thread pair."""
        data = self._load()
        if user_id not in data:
            data[user_id] = {}
            
        thread_data = data[user_id].get(thread_id, {})
        if isinstance(thread_data, list):
            thread_data = {
                "messages": messages,
                "clarification_state": {}
            }
        elif isinstance(thread_data, dict):
            thread_data["messages"] = messages
        else:
            thread_data = {
                "messages": messages,
                "clarification_state": {}
            }
        data[user_id][thread_id] = thread_data
        self._save(data)

    def update_clarification_state(
        self,
        user_id: str,
        thread_id: str,
        state: dict,
    ) -> None:
        """Persist the updated clarification state for a user/thread pair."""
        data = self._load()
        if user_id not in data:
            data[user_id] = {}
            
        thread_data = data[user_id].get(thread_id, {})
        if isinstance(thread_data, list):
            thread_data = {
                "messages": thread_data,
                "clarification_state": state
            }
        elif isinstance(thread_data, dict):
            thread_data["clarification_state"] = state
        else:
            thread_data = {
                "messages": [],
                "clarification_state": state
            }
        data[user_id][thread_id] = thread_data
        self._save(data)

    def append_turn(
        self,
        user_id: str,
        thread_id: str,
        user_message: str,
        assistant_message: str,
    ) -> list[dict]:
        """Append a user+assistant turn to the thread history and persist."""
        history = self.get_state(user_id, thread_id)
        ts = datetime.now(timezone.utc).isoformat()
        history.append({"role": "user", "content": user_message, "ts": ts})
        history.append({"role": "assistant", "content": assistant_message, "ts": ts})
        self.update_state(user_id, thread_id, history)
        return history


# Module-level singleton
session_manager = SessionManager()


# ─── Intent Classifier & Domain Guard (Layer 0 & Layer 2) ──────────────────

def classify_intent(user_message: str, history: list[dict] = None) -> Tuple[str, bool]:
    """
    Classifies the user's message into 6 intents:
      PERSONAL_DATA, BANKING, INVESTING, GENERAL_FINANCE, GOAL_PLANNING, OUT_OF_SCOPE.
    Also returns whether it is out of scope.
    """
    try:
        # Build history context
        history_lines = []
        if history:
            for msg in history[-5:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                history_lines.append(f"{role.capitalize()}: {content}")
        history_str = "\n".join(history_lines) if history_lines else "None."

        client = openai.OpenAI(
            api_key=settings.active_api_key,
            base_url=settings.active_base_url,
        )
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": INTENT_CLASSIFIER_SYSTEM},
                {
                    "role": "user",
                    "content": INTENT_CLASSIFIER_USER.format(
                        message=user_message,
                        history=history_str
                    )
                },
            ],
            response_format={"type": "json_object"},
            max_tokens=150,
            temperature=0.0,
        )
        raw = response.choices[0].message.content.strip()
        data = json.loads(raw)
        
        intent = str(data.get("intent", "general_finance")).lower().strip()
        out_of_scope = bool(data.get("out_of_scope", False))

        if intent not in VALID_INTENTS:
            intent = "financial_knowledge"

        if intent == "out_of_scope":
            out_of_scope = True

        logger.info("[IntentClassifier] '%s' → intent=%s, out_of_scope=%s", user_message[:60], intent, out_of_scope)
        return intent, out_of_scope

    except Exception as exc:
        logger.error("[IntentClassifier] Failed: %s", exc)
        return "financial_knowledge", False


# ─── Clarification Engine (Layer 3) ──────────────────────────────────────────

def call_dynamic_planner_llm(user_message: str, history: list[dict], state_json: str) -> dict:
    """
    Calls the Dynamic Goal Planner LLM to analyze the user message and history,
    and returns the slot/planning state updates.
    """
    try:
        history_lines = []
        for msg in history[-10:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            history_lines.append(f"{role.capitalize()}: {content}")
        history_str = "\n".join(history_lines) if history_lines else "None."

        client = openai.OpenAI(
            api_key=settings.active_api_key,
            base_url=settings.active_base_url,
        )
        
        from app.utils.prompts import GOAL_PLANNER_SYSTEM, GOAL_PLANNER_USER

        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": GOAL_PLANNER_SYSTEM},
                {
                    "role": "user",
                    "content": GOAL_PLANNER_USER.format(
                        state_json=state_json,
                        history=history_str,
                        message=user_message
                    )
                },
            ],
            response_format={"type": "json_object"},
            max_tokens=300,
            temperature=0.0,
        )
        raw = response.choices[0].message.content.strip()
        data = json.loads(raw)
        return data
    except Exception as exc:
        logger.error("[DynamicPlanner] LLM call failed: %s", exc)
        return {}

def run_dynamic_goal_planner(
    user_id: str,
    thread_id: str,
    user_message: str,
    history: list[dict]
) -> Tuple[bool, str, dict]:
    """
    Executes the dynamic, domain-agnostic goal planner state machine.
    Merges newly collected details, updates the generic state, and saves to session.
    Returns (requires_clarification, next_question, updated_state)
    """
    state = session_manager.get_clarification_state(user_id, thread_id)
    if not isinstance(state, dict) or not state.get("intent") or state.get("intent") != "financial_goal_planning":
        state = {
            "intent": "financial_goal_planning",
            "goal_detected": False,
            "goal_description": "",
            "collected_information": {},
            "missing_information": [],
            "clarification_required": False,
            "next_question": "",
            "advisor_ready": False
        }

    input_state = {
        "goal_description": state.get("goal_description", ""),
        "collected_information": state.get("collected_information", {})
    }
    state_json = json.dumps(input_state, indent=2)

    planner_output = call_dynamic_planner_llm(user_message, history, state_json)

    state["goal_detected"] = bool(planner_output.get("goal_detected", state.get("goal_detected", False)))
    
    desc = planner_output.get("goal_description")
    if desc:
        state["goal_description"] = str(desc)

    new_info = planner_output.get("newly_collected_information")
    if isinstance(new_info, dict):
        for k, v in new_info.items():
            if v is not None:
                state["collected_information"][k] = v

    missing_info = planner_output.get("missing_information")
    if isinstance(missing_info, list):
        state["missing_information"] = missing_info
    else:
        state["missing_information"] = []

    advisor_ready = bool(planner_output.get("advisor_ready", False))
    state["advisor_ready"] = advisor_ready
    state["clarification_required"] = not advisor_ready
    state["next_question"] = str(planner_output.get("next_question", ""))

    session_manager.update_clarification_state(user_id, thread_id, state)

    return state["clarification_required"], state["next_question"], state
    
    session_manager.update_clarification_state(user_id, thread_id, updated_state)
    
    # Build list of questions only for the missing slots
    questions = []
    questions_dict = SLOT_QUESTIONS.get(intent, {})
    for slot in missing_slots:
        if slot in questions_dict:
            questions.append(questions_dict[slot])
            
    return requires_clarification, questions, updated_state


# ─── ChromaDB Multi-Collection Retriever with Cosine Distance check ──────────

def _retrieve_context(intent: str, user_message: str, n_per_collection: int = 3) -> tuple[list[str], list[str], float]:
    """
    Search one or more ChromaDB collections based on intent and return
    (context_blocks, source_refs, min_distance) tuples.
    """
    collections = INTENT_COLLECTION_MAP.get(intent, ["financial_tips"])
    seen_texts: set[str] = set()
    context_blocks: list[str] = []
    source_refs: list[str] = []
    min_distance = 1.0

    for collection_name in collections:
        try:
            results = chroma_db.search(
                collection_name=collection_name,
                query=user_message,
                n_results=n_per_collection,
            )
            for doc in results:
                text = (doc.get("text") or doc.get("document") or "").strip()
                if not text or text in seen_texts:
                    continue
                seen_texts.add(text)
                context_blocks.append(text)
                meta = doc.get("metadata") or {}
                source_refs.append(
                    meta.get("source", meta.get("title", "FinAssist Knowledge Base"))
                )
                dist = doc.get("distance", 1.0)
                if dist < min_distance:
                    min_distance = dist
        except Exception as exc:
            logger.warning(
                "[RAG] ChromaDB search failed for collection '%s': %s",
                collection_name, exc
            )

    # Cap at 5 total chunks to keep prompt size reasonable
    return context_blocks[:5], source_refs[:5], min_distance


def format_filled_slots(slots: dict) -> str:
    lines = []
    for k, v in slots.items():
        if k == "car_model":
            lines.append(f"- Car Model: {v}")
        elif k == "budget":
            if isinstance(v, (int, float)):
                lines.append(f"- Budget: Rs. {v:,.0f}")
            else:
                lines.append(f"- Budget: Rs. {v}")
        elif k == "loan_required":
            status = "Yes (Loan required)" if v is True else "No (Cash/Outright purchase)" if v is False else str(v)
            lines.append(f"- Loan Required: {status}")
        elif k == "timeline":
            lines.append(f"- Timeline: {v}")
        elif k == "bank_preference":
            lines.append(f"- Preferred Bank(s): {v}")
        elif k == "investment_amount":
            if isinstance(v, (int, float)):
                lines.append(f"- Investment Amount: Rs. {v:,.0f}")
            else:
                lines.append(f"- Investment Amount: Rs. {v}")
        elif k == "fd_duration":
            lines.append(f"- FD Duration/Tenure: {v}")
        elif k == "senior_citizen":
            status = "Yes" if v is True else "No" if v is False else str(v)
            lines.append(f"- Senior Citizen: {status}")
        elif k == "risk_profile":
            lines.append(f"- Risk Profile/Appetite: {v}")
        elif k == "goal":
            lines.append(f"- Investment Goal/Purpose: {v}")
        elif k == "investment_horizon":
            lines.append(f"- Investment Horizon/Duration: {v}")
        else:
            key_display = str(k).replace('_', ' ').title()
            lines.append(f"- {key_display}: {v}")
    return "\n".join(lines)


# ─── RAG Answer Generator (Layer 4A) ─────────────────────────────────────────

def execute_rag(
    user_message: str,
    intent: str,
    history: list[dict],
    profile: dict,
    clarification_state: Optional[dict] = None,
) -> dict:
    """
    Retrieval-Augmented Generation pipeline using the FinAssist advisor persona.
    Includes confidence scoring check (minimum similarity distance <= 0.6).
    """
    # ── 1. Retrieve context & check confidence ────────────────────────────
    context_blocks, source_refs, min_distance = _retrieve_context(intent, user_message)

    if (not context_blocks or min_distance > 0.6) and intent == "financial_knowledge":
        logger.info("[RAG] Confidence score low (min_distance=%s > 0.6) for intent %s — returning safe rejection", min_distance, intent)
        return {
            "answer": "I couldn't find reliable information to answer that accurately.",
            "sources": ["FinAssist Knowledge Base"],
            "route_to_nl2sql": False,
        }

    context_text = "\n\n---\n\n".join(context_blocks)

    # Inject persistent user slots context to RAG so it can make custom recommendations
    if clarification_state and clarification_state.get("collected_information"):
        slots_str = format_filled_slots(clarification_state["collected_information"])
        context_text = f"User Scenario Details (ALL these details are already provided/filled):\n{slots_str}\n\n{context_text}"

    # ── 2. Build system prompt with all slots filled ──────────────────────
    income = profile.get("income", "unknown")
    annual_income = profile.get("annual_income", income)
    segment = profile.get("segment", "General")
    city = profile.get("city", "India")
    risk_profile = profile.get("risk_profile", "Moderate")
    credit_score = profile.get("credit_score", "N/A")
    current_date = datetime.now().strftime("%d %B %Y")

    income_display = (
        f"₹{annual_income:,.0f} per annum"
        if isinstance(annual_income, (int, float))
        else str(annual_income)
    )

    system_prompt = FINASSIST_SYSTEM_PROMPT.format(
        current_date=current_date,
        income_display=income_display,
        segment=segment,
        city=city,
        risk_profile=risk_profile,
        credit_score=credit_score,
        context_text=context_text,
    )

    # ── 3. Build message list (last 10 turns for HITL slot recall) ────────
    recent_history = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in history[-10:]
        if msg.get("role") in {"user", "assistant"} and msg.get("content")
    ]
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(recent_history)
    messages.append({"role": "user", "content": user_message})

    # ── 4. Call LLM ───────────────────────────────────────────────────────
    answer = ""
    route_to_nl2sql = False

    try:
        client = openai.OpenAI(
            api_key=settings.active_api_key,
            base_url=settings.active_base_url,
        )
        completion = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            max_tokens=700,
            temperature=0.2,
        )
        answer = completion.choices[0].message.content.strip()

        # Detect ROUTE_TO_NL2SQL token
        if answer.strip().upper().startswith(ROUTE_TO_NL2SQL_TOKEN):
            logger.info(
                "[RAG] LLM emitted ROUTE_TO_NL2SQL for message: '%s'",
                user_message[:80],
            )
            route_to_nl2sql = True
            answer = ""

    except Exception as exc:
        logger.error("[RAG] LLM call failed: %s", exc)
        answer = (
            "I encountered a temporary issue generating your response. "
            "Please try again in a moment."
        )

    return {
        "answer": answer,
        "sources": source_refs if source_refs else ["FinAssist Knowledge Base"],
        "route_to_nl2sql": route_to_nl2sql,
    }


# ─── Main Orchestrator ───────────────────────────────────────────────────────

async def process_chat_message(
    user_id: str,
    message: str,
    thread_id: str,
    user_profile: dict,
) -> dict:
    """
    Top-level async orchestrator for a single chat turn implementing all layers.
    """
    if not thread_id or thread_id.strip() == "":
        thread_id = str(uuid.uuid4())

    # ── Layer 1: Input Guardrails ──────────────────────────────────────────
    is_safe, error_message = Guardrails.validate_input(message, user_id)
    if not is_safe:
        log_security_event(
            user_id=user_id,
            thread_id=thread_id,
            event_type="prompt_injection_attempt" if "flagged" in error_message or "security" in error_message else "input_blocked",
            message=message,
            reason=error_message,
        )
        return {
            "answer": error_message,
            "intent": "out_of_scope",
            "sources": ["Security Guardrails"],
            "thread_id": thread_id,
            "user_id": user_id,
        }

    # Load conversation history
    history = session_manager.get_state(user_id, thread_id)

    # ── Layer 0 & Layer 2: Domain Guard & Intent Classification ────────────
    intent, out_of_scope = classify_intent(message, history)

    if out_of_scope or intent == "out_of_scope":
        log_security_event(
            user_id=user_id,
            thread_id=thread_id,
            event_type="out_of_scope_request",
            message=message,
            reason="User query is out of the financial advisor domains.",
        )
        
        out_of_scope_response = (
            "I am a Financial Advisor and can assist with:\n\n"
            "• Banking\n"
            "• Investments\n"
            "• Insurance\n"
            "• Tax Planning\n"
            "• Budgeting\n"
            "• Financial Goal Planning\n"
            "• Personal Spending Analysis\n\n"
            "Please ask a finance-related question."
        )

        session_manager.append_turn(
            user_id=user_id,
            thread_id=thread_id,
            user_message=message,
            assistant_message=out_of_scope_response,
        )

        return {
            "answer": out_of_scope_response,
            "intent": "out_of_scope",
            "sources": ["Domain Guard"],
            "thread_id": thread_id,
            "user_id": user_id,
        }

    # ── Load persistent clarification state ──────────────────────────────────
    clarification_state = session_manager.get_clarification_state(user_id, thread_id)

    # ── Layer 3: Clarification Engine ──────────────────────────────────────
    is_clarifying_active = clarification_state.get("clarification_required", False)

    if intent == "financial_goal_planning" or is_clarifying_active:
        if is_clarifying_active:
            intent = "financial_goal_planning"

        requires_clarification, next_question, clarification_state = run_dynamic_goal_planner(
            user_id=user_id,
            thread_id=thread_id,
            user_message=message,
            history=history
        )
        
        if requires_clarification and next_question:
            session_manager.append_turn(
                user_id=user_id,
                thread_id=thread_id,
                user_message=message,
                assistant_message=next_question,
            )

            return {
                "answer": next_question,
                "intent": intent,
                "sources": ["Clarification Planner"],
                "thread_id": thread_id,
                "user_id": user_id,
            }

    # ── Layer 4A & 4B: Execution Routing ────────────────────────────────────
    sources: list[str] = []

    if intent == "personal_transaction":
        # 4b. Direct NL2SQL path (User scoping is strictly enforced via user_id)
        logger.info("[ChatbotEngine] Direct route → NL2SQL (intent=personal_transaction)")
        answer = await execute_nl2sql(user_id, message)
        sources = ["Supabase Transactions"]

    else:
        # 4a. RAG path
        rag_result = execute_rag(
            user_message=message,
            intent=intent,
            history=history,
            profile=user_profile,
            clarification_state=clarification_state,
        )
        sources = rag_result.get("sources", [])

        if rag_result.get("route_to_nl2sql"):
            # Failsafe: LLM detected personal-data query mid-turn
            logger.info(
                "[ChatbotEngine] Failsafe route → NL2SQL "
                "(LLM emitted ROUTE_TO_NL2SQL, classified intent=%s)", intent
            )
            answer = await execute_nl2sql(user_id, message)
            sources = ["Supabase Transactions"]
            intent = "personal_transaction"
        else:
            answer = rag_result.get("answer", "")

    # ── Layer 6: Output Guardrails ──────────────────────────────────────────
    logger.info("[ChatbotEngine] Raw LLM Answer before Output Guard: %s", answer)
    is_output_safe, cleaned_answer = Guardrails.validate_output(answer, user_id)
    if not is_output_safe:
        log_security_event(
            user_id=user_id,
            thread_id=thread_id,
            event_type="output_blocked",
            message=message,
            reason="Sensitive credentials leaked in response",
        )
        return {
            "answer": cleaned_answer,
            "intent": intent,
            "sources": ["Security Guardrails"],
            "thread_id": thread_id,
            "user_id": user_id,
        }

    answer = cleaned_answer

    # Persist the turn
    session_manager.append_turn(
        user_id=user_id,
        thread_id=thread_id,
        user_message=message,
        assistant_message=answer,
    )

    return {
        "answer": answer,
        "intent": intent,
        "sources": sources,
        "thread_id": thread_id,
        "user_id": user_id,
    }
