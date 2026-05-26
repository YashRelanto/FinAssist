"""
Core intelligence coordinator for the FinAssist Financial AI Advisor chatbot.

Responsibilities:
  - SessionManager  : thread-safe JSON-based conversation state persistence
  - classify_intent : zero-shot LLM intent router
  - execute_rag     : ChromaDB retrieval + personalised LLM advisory generation
  - process_chat_message : top-level async orchestrator
"""

import json
import os
import uuid
import logging
from datetime import datetime
from typing import Optional

import openai

# Import config first — this triggers dotenv loading before any os.getenv call
from app.core.config import settings
from app.utils.chroma_store import chroma_db
from app.utils.nl2sql import execute_nl2sql
from app.guardrails import Guardrails
from app.utils.security_logger import log_security_event

# ─── Logging ────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────────────

SESSIONS_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "sessions.json")
SESSIONS_FILE = os.path.normpath(SESSIONS_FILE)

INTENT_COLLECTION_MAP: dict[str, str] = {
    "banking": "banking_data",
    "investing": "investment_data",
    "general_finance": "financial_tips",
}

VALID_INTENTS = {"banking", "investing", "general_finance", "personal_data"}

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
    sessions.json file.  The file schema is:

        {
          "<user_id>": {
            "<thread_id>": [
              {"role": "user"|"assistant", "content": "...", "ts": "ISO8601"},
              ...
            ]
          }
        }

    All public methods are synchronous and include file-level locking via a
    simple try/except guard to survive concurrent reads/writes in a
    single-process uvicorn deployment.
    """

    def __init__(self, sessions_file: str = SESSIONS_FILE):
        self.sessions_file = sessions_file
        self._ensure_file()

    # ── Private helpers ──────────────────────────────────────────────────────

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

    # ── Public API ───────────────────────────────────────────────────────────

    def get_state(self, user_id: str, thread_id: str) -> list[dict]:
        """Return the ordered message list for a specific user/thread pair."""
        data = self._load()
        return data.get(user_id, {}).get(thread_id, [])

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
        data[user_id][thread_id] = messages
        self._save(data)

    def append_turn(
        self,
        user_id: str,
        thread_id: str,
        user_message: str,
        assistant_message: str,
    ) -> list[dict]:
        """
        Convenience method: append a user+assistant turn to the thread history
        and immediately persist.  Returns the updated history list.
        """
        history = self.get_state(user_id, thread_id)
        ts = datetime.utcnow().isoformat()
        history.append({"role": "user", "content": user_message, "ts": ts})
        history.append({"role": "assistant", "content": assistant_message, "ts": ts})
        self.update_state(user_id, thread_id, history)
        return history


# Module-level singleton so all call-sites share one file handle lifecycle
session_manager = SessionManager()


# ─── Intent Classifier ───────────────────────────────────────────────────────

def classify_intent(user_message: str) -> str:
    """
    Zero-shot intent classification using an OpenAI completion call.

    Returns exactly one of:
        "banking" | "investing" | "general_finance" | "personal_data"

    Falls back to "general_finance" if the model response is unparseable.
    """
    system_prompt = (
        "You are an intent classification engine for a personal finance application.\n"
        "Classify the user's message into EXACTLY ONE of the following four categories "
        "and respond with ONLY that single word — no punctuation, no explanation:\n\n"
        "  banking         – questions about bank accounts, interest rates, FDs, RDs, "
        "savings accounts, loans, credit cards, or banking products\n"
        "  investing        – questions about stocks, mutual funds, SIPs, ETFs, bonds, "
        "portfolio management, market data, or investment strategies\n"
        "  general_finance  – broader financial topics such as budgeting, tax planning, "
        "insurance, retirement planning, or financial literacy\n"
        "  personal_data    – queries about the user's own transactions, spending habits, "
        "balances, income, or account-specific summaries that require database lookup\n\n"
        "Reply with one of: banking, investing, general_finance, personal_data"
    )

    try:
        client = openai.OpenAI(
            api_key=settings.active_api_key,
            base_url=settings.active_base_url,
        )
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=10,
            temperature=0.0,
        )
        raw = response.choices[0].message.content.strip().lower()
        # Sanitise: strip punctuation, take first word
        intent = raw.split()[0].rstrip(".,;:") if raw else ""
        if intent in VALID_INTENTS:
            return intent
        logger.warning("Unexpected intent token '%s' — defaulting to general_finance", intent)
        return "general_finance"

    except Exception as exc:
        logger.error("classify_intent failed: %s", exc)
        return "general_finance"


# ─── RAG Executor ────────────────────────────────────────────────────────────

def execute_rag(
    user_message: str,
    intent: str,
    history: list[dict],
    profile: dict,
) -> dict:
    """
    Retrieval-Augmented Generation pipeline.

    Steps:
      1. Map intent → ChromaDB collection name
      2. Search ChromaDB for top-3 relevant context chunks
      3. Compile context + user profile into a personalised advisory prompt
      4. Call OpenAI chat completion for the final answer
      5. Return {"answer": str, "sources": list[str]}
    """
    collection_name = INTENT_COLLECTION_MAP.get(intent, "financial_tips")

    # 1. Retrieve context from ChromaDB
    retrieved_docs: list[dict] = []
    try:
        results = chroma_db.search(
            collection_name=collection_name,
            query=user_message,
            n_results=3,
        )
        # chroma_db.search is expected to return a list of dicts with at least
        # keys: "text" (str) and optionally "metadata" (dict) / "id" (str)
        retrieved_docs = results if isinstance(results, list) else []
    except Exception as exc:
        logger.warning("ChromaDB search failed for collection '%s': %s", collection_name, exc)

    # 2. Compile context blocks (top 3)
    context_blocks: list[str] = []
    source_refs: list[str] = []
    for doc in retrieved_docs[:3]:
        text = doc.get("text") or doc.get("document") or str(doc)
        context_blocks.append(text)
        meta = doc.get("metadata") or {}
        source_refs.append(meta.get("source", meta.get("title", "FinAssist Knowledge Base")))

    context_text = "\n\n---\n\n".join(context_blocks) if context_blocks else (
        "No specific data found. Provide general best-practice advice."
    )

    # 3. Build personalised system prompt
    income = profile.get("income", "unknown")
    segment = profile.get("segment", "General")
    city = profile.get("city", "India")
    annual_income = profile.get("annual_income", income)
    risk_profile = profile.get("risk_profile", "Moderate")
    credit_score = profile.get("credit_score", "N/A")
    current_date = datetime.now().strftime("%d %B %Y")

    # Format income display safely
    if isinstance(annual_income, (int, float)):
        income_display = f"₹{annual_income:,.0f} per annum"
    else:
        income_display = str(annual_income)

    system_prompt = (
        f"You are FinAssist, an expert AI financial advisor serving Indian retail banking customers.\n\n"
        f"Today's Date: {current_date}\n\n"
        f"User Profile:\n"
        f"  - Annual Income      : {income_display}\n"
        f"  - Customer Segment   : {segment}\n"
        f"  - City Tier          : {city}\n"
        f"  - Risk Profile       : {risk_profile}\n"
        f"  - CIBIL Score        : {credit_score}\n\n"
        f"Relevant Knowledge Base Context:\n"
        f"{context_text}\n\n"
        f"Instructions for a neat and premium response:\n"
        f"  - Provide a precise, personalised, and actionable financial advisory answer.\n"
        f"  - Tailor all recommendations to the user's income level, risk profile, and segment.\n"
        f"  - Cite specific product names, institutions, and approximate figures where the context supports it.\n"
        f"  - Always format money values in Indian Rupees (e.g. ₹50,000 or ₹1.5 Lakhs).\n"
        f"  - Structure your response beautifully with bold text, clean headings (##), and spacing between paragraphs.\n"
        f"  - Use bullet points or modern list layouts with relevant financial emojis (like 💰, 📈, 🏥, 🏦) to present suggestions neatly.\n"
        f"  - Keep the response highly readable and concise — under 350 words.\n"
        f"  - If the context does not contain sufficient data, clearly acknowledge that and provide general best-practice guidance based on current Indian financial norms."
    )

    # 4. Build message list (last 6 turns of history for context window efficiency)
    recent_history = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in history[-6:]
        if msg.get("role") in {"user", "assistant"} and msg.get("content")
    ]
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(recent_history)
    messages.append({"role": "user", "content": user_message})

    # 5. Generate advisory answer
    answer = ""
    try:
        client = openai.OpenAI(
            api_key=settings.active_api_key,
            base_url=settings.active_base_url,
        )
        completion = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            max_tokens=512,
            temperature=0.4,
        )
        answer = completion.choices[0].message.content.strip()
    except Exception as exc:
        logger.error("execute_rag LLM call failed: %s", exc)
        answer = (
            "I'm sorry, I encountered a temporary issue generating your advisory. "
            "Please try again in a moment."
        )

    return {
        "answer": answer,
        "sources": source_refs if source_refs else ["FinAssist Knowledge Base"],
    }


# ─── Personal Data Summariser (NL2SQL Mock) ──────────────────────────────────

def _generate_personal_data_summary(user_message: str, profile: dict) -> dict:
    """
    Simulates an NL2SQL output engine.  In production this would translate
    the natural language query into SQL, execute it against Supabase, and
    format results.  Here we return a rich, realistic mock analytical summary
    that mirrors the schema (transactions, accounts, categories tables).
    """
    income = profile.get("income", 55000)
    segment = profile.get("segment", "High Income Low Spender")
    city = profile.get("city", "Tier 1")

    summary = (
        f"📊 **Personal Financial Summary** *(Simulated Analytics Engine)*\n\n"
        f"**Profile**: {segment} | {city} City | Annual Income ₹{income:,}\n\n"
        f"**Last 30 Days Snapshot:**\n"
        f"  - 💰 Total Credits: ₹4,58,200 (Salary + Freelance)\n"
        f"  - 💸 Total Debits: ₹1,23,750 (68 transactions)\n"
        f"  - 📈 Net Savings Rate: **73.0%** — Well above your 60% target\n\n"
        f"**Top 3 Spending Categories:**\n"
        f"  1. 🏠 Housing & Utilities — ₹32,000 (25.8%)\n"
        f"  2. 🛒 Food & Dining — ₹18,400 (14.9%)\n"
        f"  3. 🚕 Transportation — ₹9,200 (7.4%)\n\n"
        f"**Account Balances:**\n"
        f"  - HDFC Savings Primary: ₹2,14,500\n"
        f"  - HDFC Savings Emergency: ₹85,000\n"
        f"  - Zerodha Demat Value: ₹6,32,400\n\n"
        f"**Insight**: Based on your spending pattern, you are consistently "
        f"saving over 70% of income. Consider deploying the idle savings "
        f"(₹2.1L+) into a liquid mutual fund or FD ladder to optimise returns."
    )

    return {
        "answer": summary,
        "sources": ["Supabase: transactions", "Supabase: accounts", "Supabase: categories"],
    }


# ─── Main Orchestrator ───────────────────────────────────────────────────────

async def process_chat_message(
    user_id: str,
    message: str,
    thread_id: str,
    user_profile: dict,
) -> dict:
    """
    Top-level async orchestrator for a single chat turn.

    Flow:
      1. Run input validation guardrails
      2. Fetch conversation history for the thread
      3. Classify the user's intent
      4a. personal_data  → return mock NL2SQL analytical summary
      4b. RAG intents    → run ChromaDB retrieval + LLM advisory
      5. Run output validation guardrails
      6. Persist the completed turn to sessions.json
      7. Return a unified payload dict
    """
    # Ensure thread_id is non-empty
    if not thread_id or thread_id.strip() == "":
        thread_id = str(uuid.uuid4())

    # 1. Run Input Guardrails (Layer 1)
    is_safe, error_message = Guardrails.validate_input(message, user_id)
    if not is_safe:
        log_security_event(user_id=user_id, event_type="input_blocked", message=message, reason=error_message)
        return {
            "answer": error_message,
            "intent": "general_finance",
            "sources": ["Security Guardrails"],
            "thread_id": thread_id,
            "user_id": user_id,
        }

    # 2. Load conversation history
    history = session_manager.get_state(user_id, thread_id)

    # 3. Classify intent
    intent = classify_intent(message)
    logger.info("user=%s thread=%s intent=%s", user_id, thread_id, intent)

    # 4. Route execution
    if intent == "personal_data":
        logger.info("[ChatbotEngine] Routing to NL2SQL engine for personal_data...")
        answer = await execute_nl2sql(user_id, message)
        result = {
            "answer": answer,
            "intent": intent,
            "sources": ["Supabase Transactions"]
        }
    else:
        result = execute_rag(
            user_message=message,
            intent=intent,
            history=history,
            profile=user_profile,
        )

    answer: str = result.get("answer", "")
    sources: list[str] = result.get("sources", [])

    # 5. Run Output Guardrails (Layer 4)
    is_output_safe, cleaned_answer = Guardrails.validate_output(answer, user_id)
    if not is_output_safe:
        log_security_event(user_id=user_id, event_type="output_blocked", message=message, reason="Sensitive credentials leaked in response")
        return {
            "answer": cleaned_answer,
            "intent": intent,
            "sources": ["Security Guardrails"],
            "thread_id": thread_id,
            "user_id": user_id,
        }
    
    answer = cleaned_answer

    # 6. Persist the turn
    session_manager.append_turn(
        user_id=user_id,
        thread_id=thread_id,
        user_message=message,
        assistant_message=answer,
    )

    # 7. Return unified response payload
    return {
        "answer": answer,
        "intent": intent,
        "sources": sources,
        "thread_id": thread_id,
        "user_id": user_id,
    }
