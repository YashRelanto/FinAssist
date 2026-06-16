"""
Knowledge Tool — RAG retrieval for general financial education / product info.

Retrieves context from ChromaDB and falls back to live web search, writing the
retrieved chunks to `retrieved_context` and an `evidence` item for the Brain.
"""

from __future__ import annotations

import logging
from typing import List

from app.graph.state import AgentState
from app.utils.chroma_store import chroma_db
from app.utils.scrapers import live_web_search_and_scrape

logger = logging.getLogger(__name__)

# Knowledge collections searched for general (non-personal) financial queries.
KNOWLEDGE_COLLECTIONS = ["banking_data", "investment_data", "financial_tips"]


def knowledge_tool(state: AgentState) -> dict:
    """Retrieve knowledge-base / web context for the Brain's sub-question."""
    task = state.get("brain_task") or {}
    query = task.get("sub_question") or state.get("user_query") or ""

    seen: set = set()
    context_blocks: List[str] = []
    source_refs: List[str] = []
    min_distance = 1.0

    for collection_name in KNOWLEDGE_COLLECTIONS:
        try:
            for doc in chroma_db.search(collection_name=collection_name, query=query, n_results=3):
                text = (doc.get("text") or doc.get("document") or "").strip()
                if not text or text in seen:
                    continue
                seen.add(text)
                context_blocks.append(text)
                meta = doc.get("metadata") or {}
                source_refs.append(meta.get("source") or meta.get("title") or "FinAssist Knowledge Base")
                dist = doc.get("distance", 1.0)
                min_distance = min(min_distance, dist)
        except Exception as exc:
            logger.warning("[knowledge] ChromaDB error for '%s': %s", collection_name, exc)

    # Hybrid fallback: live web search when local retrieval is weak.
    if not context_blocks or min_distance > 0.6:
        logger.info("[knowledge] Local RAG miss (min_dist=%.3f) — live web search for: %s", min_distance, query)
        try:
            scraped_text, source_url = live_web_search_and_scrape(query, max_results=1)
            if scraped_text:
                context_blocks = [scraped_text]
                source_refs = [f"Live Web Search ({source_url})"]
                min_distance = 0.1
        except Exception as exc:
            logger.error("[knowledge] Live web search failed: %s", exc)

    context_blocks = context_blocks[:5]
    source_refs = source_refs[:5]
    summary = f"Retrieved {len(context_blocks)} knowledge chunk(s) (min_dist={min_distance:.3f})."
    logger.info("[knowledge] %s", summary)

    return {
        "retrieved_context": context_blocks,
        "sources": source_refs or ["FinAssist Knowledge Base"],
        "evidence": [{
            "tool": "knowledge",
            "task": query,
            "summary": summary,
            "data": {"chunks": context_blocks, "sources": source_refs, "min_distance": min_distance},
        }],
    }
