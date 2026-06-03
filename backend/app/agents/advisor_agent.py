import logging
from datetime import datetime
from typing import Dict, Any, Tuple, List, Optional
import openai

from app.core.config import settings
from app.utils.chroma_store import chroma_db
from app.utils.prompts import FINASSIST_SYSTEM_PROMPT
from app.agents.workflow_agent import WorkflowAgent

logger = logging.getLogger(__name__)

# Map each intent to one or more ChromaDB collection names.
INTENT_COLLECTION_MAP: dict[str, list[str]] = {
    "financial_knowledge":     ["banking_data", "investment_data", "financial_tips"],
    "financial_goal_planning":  ["financial_tips"],
    "personal_transaction":    [],
    "out_of_scope":            [],
}

ROUTE_TO_NL2SQL_TOKEN = "ROUTE_TO_NL2SQL"

class AdvisorAgent:
    """
    Handles general financial knowledge and applies RAG.
    Does not gate generation on RAG results. Uses LLM base knowledge as fallback.
    """

    @staticmethod
    def _retrieve_context(intent: str, user_message: str, n_per_collection: int = 3) -> Tuple[List[str], List[str], float]:
        collections = INTENT_COLLECTION_MAP.get(intent, ["financial_tips"])
        seen_texts: set[str] = set()
        context_blocks: List[str] = []
        source_refs: List[str] = []
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
                logger.warning("[RAG] ChromaDB search failed for collection '%s': %s", collection_name, exc)

        return context_blocks[:5], source_refs[:5], min_distance

    @staticmethod
    def process(user_message: str, intent: str, history: List[Dict], profile: Dict[str, Any], workflow_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Executes Retrieval-Augmented Generation pipeline.
        Returns a dict with 'answer', 'sources', and 'route_to_nl2sql'.
        """
        context_blocks, source_refs, min_distance = AdvisorAgent._retrieve_context(intent, user_message)

        # Do NOT gate on low confidence RAG. Use retrieved context if confidence is decent, otherwise fall back to LLM general knowledge.
        if context_blocks and min_distance <= 0.6:
            context_text = "\n\n---\n\n".join(context_blocks)
            sources = source_refs
        else:
            logger.info("[RAG] Confidence score low or no docs found for intent %s. Using LLM base knowledge.", intent)
            context_text = "No highly relevant documents found in the exact knowledge base. Use your general financial expertise to answer, while maintaining safety guidelines."
            sources = ["FinAssist General Knowledge"]

        if workflow_state and workflow_state.get("collected_information"):
            slots_str = WorkflowAgent.format_filled_slots(workflow_state["collected_information"])
            context_text = f"User Scenario Details (ALL these details are already provided/filled):\n{slots_str}\n\n{context_text}"

        income = profile.get("income", "unknown")
        annual_income = profile.get("annual_income", income)
        segment = profile.get("segment", "General")
        city = profile.get("city", "India")
        risk_profile = profile.get("risk_profile", "Moderate")
        credit_score = profile.get("credit_score", "N/A")
        current_date = datetime.now().strftime("%d %B %Y")

        income_display = f"₹{annual_income:,.0f} per annum" if isinstance(annual_income, (int, float)) else str(annual_income)

        system_prompt = FINASSIST_SYSTEM_PROMPT.format(
            current_date=current_date,
            income_display=income_display,
            segment=segment,
            city=city,
            risk_profile=risk_profile,
            credit_score=credit_score,
            context_text=context_text,
        )

        recent_history = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in history[-10:]
            if msg.get("role") in {"user", "assistant"} and msg.get("content")
        ]
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(recent_history)
        messages.append({"role": "user", "content": user_message})

        answer = ""
        route_to_nl2sql = False

        try:
            client = openai.OpenAI(
                api_key=settings.active_api_key,
                base_url=settings.active_base_url,
            )
            completion = client.chat.completions.create(
                model=settings.active_chat_model,
                messages=messages,
                max_tokens=700,
                temperature=0.2,
            )
            answer = completion.choices[0].message.content.strip()

            if answer.strip().upper().startswith(ROUTE_TO_NL2SQL_TOKEN):
                logger.info("[AdvisorAgent] LLM emitted ROUTE_TO_NL2SQL for message: '%s'", user_message[:80])
                route_to_nl2sql = True
                answer = ""

        except Exception as exc:
            logger.error("[AdvisorAgent] LLM call failed: %s", exc)
            answer = "I encountered a temporary issue generating your response. Please try again in a moment."

        return {
            "answer": answer,
            "sources": sources,
            "route_to_nl2sql": route_to_nl2sql,
        }
