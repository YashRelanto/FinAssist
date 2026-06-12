"""
RAG Retrieval Node — local ChromaDB vector search + live web search fallback.
"""

from __future__ import annotations

import logging
from typing import Dict, List

from app.graph.state import AgentState
from app.utils.chroma_store import chroma_db
from app.utils.scrapers import live_web_search_and_scrape

logger = logging.getLogger(__name__)

INTENT_COLLECTION_MAP: Dict[str, List[str]] = {
    "FINANCIAL_KNOWLEDGE":    ["banking_data", "investment_data", "financial_tips"],
    "GOAL_PLANNING":          ["financial_tips"],
}


def run_rag_retrieval(query: str, intent: str = "FINANCIAL_KNOWLEDGE") -> dict:
    """
    Core RAG retrieval logic — usable as a Brain tool or graph node.
    """
    collections = INTENT_COLLECTION_MAP.get(intent, ["financial_tips"])

    seen_texts = set()
    context_blocks = []
    source_refs = []
    min_distance = 1.0

    for collection_name in collections:
        try:
            results = chroma_db.search(collection_name=collection_name, query=query, n_results=3)
            for doc in results:
                text = (doc.get("text") or doc.get("document") or "").strip()
                if not text or text in seen_texts:
                    continue
                seen_texts.add(text)
                context_blocks.append(text)
                meta = doc.get("metadata") or {}
                source_refs.append(meta.get("source") or meta.get("title") or "FinAssist Knowledge Base")
                dist = doc.get("distance", 1.0)
                if dist < min_distance:
                    min_distance = dist
        except Exception as exc:
            logger.warning("[Node:rag] ChromaDB error for '%s': %s", collection_name, exc)

    # Hybrid Fallback: Live Web Search
    # Check distance: ChromaDB distance <= 0.6 is typically good quality (or whatever was configured)
    if not context_blocks or min_distance > 0.6:
        logger.info("[Node:rag] Local RAG miss (min_dist=%.3f) — Triggering Live Web Search for: %s", min_distance, query)
        try:
            scraped_text, source_url = live_web_search_and_scrape(query, max_results=1)
            if scraped_text:
                context_blocks = [scraped_text]
                source_refs = [f"Live Web Search ({source_url})"]
                min_distance = 0.1  # Highly confident
                logger.info("[Node:rag] Live Web Search succeeded: %s", source_url)
            else:
                logger.info("[Node:rag] Live Web Search returned no usable text.")
        except Exception as e:
            logger.error("[Node:rag] Live Web Search failed: %s", e)

    logger.info("[Node:rag] intent=%s blocks=%d min_dist=%.3f",
                intent, len(context_blocks), min_distance)

    return {
        "retrieved_context": context_blocks[:5],
        "context_sources": source_refs[:5],
        "rag_confidence": min_distance,
    }


def rag_node(state: AgentState) -> dict:
    """Graph node wrapper around run_rag_retrieval."""
    intent = state.get("intent") or "FINANCIAL_KNOWLEDGE"
    query = state.get("standalone_query") or state.get("rewritten_query") or state.get("user_query") or ""
    return run_rag_retrieval(query=query, intent=intent)
