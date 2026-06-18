"""
Knowledge Tool — RAG retrieval for general financial education / product info.

Pipeline (in order):
  1. Collection routing  — probe each collection with n=1; pick the one whose
                           best match has the lowest cosine distance to the query.
  2. Candidate fetch     — retrieve 15 candidates from the winning collection,
                           including their embedding vectors.
  3. MMR                 — filter 15 → 8 using Maximal Marginal Relevance
                           (λ=0.7 balances relevance vs diversity).
  4. Cross-encoder rerank— score the 8 MMR survivors with a bi-directional
                           cross-encoder and keep the top 3.
  5. Web fallback        — if the best ANN distance > 0.6 (weak local match),
                           discard local results and run a live DuckDuckGo search.
"""

from __future__ import annotations

import logging
import math
from typing import List

from app.graph.state import AgentState
from app.utils.chroma_store import chroma_db
from app.utils.scrapers import live_web_search_and_scrape

logger = logging.getLogger(__name__)

KNOWLEDGE_COLLECTIONS = ["banking_data", "investment_data", "financial_tips"]

# MMR: λ = 0.7 → 70% relevance, 30% diversity.  Lower → more diverse.
_MMR_LAMBDA = 0.7
_MMR_CANDIDATES = 15   # initial fetch from the single routed collection
_MMR_KEEP = 8          # MMR output (input to reranker)
_RERANK_TOP_K = 3      # final results returned to the Brain
_WEB_FALLBACK_DIST = 0.6   # cosine distance threshold; above this → web fallback

# Lazy-loaded cross-encoder (loaded once, reused across requests).
_cross_encoder = None

# ── Collection routing vocabulary ─────────────────────────────────────────────
# Each collection maps to a set of lowercase keyword tokens.
# Order matters only for the fallback: if nothing matches, _DEFAULT_COLLECTION is used.
_DEFAULT_COLLECTION = "financial_tips"

_ROUTING_RULES: list[tuple[str, set[str]]] = [
    ("banking_data", {
        "fd", "fixed deposit", "recurring deposit", "rd", "savings account",
        "current account", "interest rate", "bank", "credit card", "loan",
        "personal loan", "home loan", "car loan", "emi", "ifsc", "neft", "rtgs",
        "imps", "upi", "overdraft", "cheque", "kyc", "nominee", "account",
        "bankbazaar", "hdfc", "sbi", "icici", "axis", "kotak", "yes bank",
    }),
    ("investment_data", {
        "mutual fund", "sip", "nav", "equity", "stock", "share", "nifty",
        "sensex", "bse", "nse", "etf", "nps", "national pension", "elss",
        "gold", "sgb", "sovereign gold bond", "smallcap", "midcap", "largecap",
        "flexicap", "debt fund", "liquid fund", "index fund", "portfolio",
        "dividend", "folio", "amc", "sebi", "zerodha", "groww", "demat",
        "broker", "ipo", "listing", "returns", "cagr", "xirr",
    }),
    ("financial_tips", {
        "budget", "budgeting", "tax", "income tax", "itr", "tds", "80c", "80d",
        "hra", "insurance", "term insurance", "life insurance", "health insurance",
        "retire", "retirement", "fire", "financial independence", "emergency fund",
        "ppf", "epf", "provident fund", "savings", "saving tips", "expense",
        "spend", "cut costs", "frugal", "financial planning", "wealth", "net worth",
        "debt free", "credit score", "cibil", "loan repayment",
    }),
]


def _load_cross_encoder():
    global _cross_encoder
    if _cross_encoder is not None:
        return _cross_encoder
    try:
        from sentence_transformers import CrossEncoder
        _cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        logger.info("[knowledge] Cross-encoder loaded: ms-marco-MiniLM-L-6-v2")
    except Exception as exc:
        logger.warning("[knowledge] CrossEncoder unavailable (%s) — reranking disabled.", exc)
        _cross_encoder = None
    return _cross_encoder


# ── Math helpers ──────────────────────────────────────────────────────────────

def _cosine(a: list, b: list) -> float:
    """Cosine similarity between two equal-length vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na  = math.sqrt(sum(x * x for x in a))
    nb  = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb + 1e-9)


# ── Stage 1 — Collection routing (pure keyword, zero DB calls) ───────────────

def _route_collection(query: str) -> str:
    """
    Map a query to exactly one collection using keyword scoring.
    No DB is touched — this is pure string matching.

    Algorithm:
      - Lowercase the query once.
      - For each collection's keyword set, count how many keywords appear
        as substrings in the query.
      - Return the collection with the highest count.
      - Tie-break: earlier in _ROUTING_RULES wins (banking > investment > tips).
      - No match at all → _DEFAULT_COLLECTION ("financial_tips").

    Cost: O(total_keywords) substring checks — microseconds.
    """
    q = query.lower()
    best_name  = _DEFAULT_COLLECTION
    best_score = 0

    for collection_name, keywords in _ROUTING_RULES:
        score = sum(1 for kw in keywords if kw in q)
        if score > best_score:
            best_score = score
            best_name  = collection_name

    logger.info(
        "[knowledge] keyword routing → '%s' (score=%d, query='%.60s')",
        best_name, best_score, query,
    )
    return best_name


# ── Stage 2 — MMR ─────────────────────────────────────────────────────────────

def _mmr(
    query_emb: list,
    docs: List[dict],
    k: int = _MMR_KEEP,
    lambda_mult: float = _MMR_LAMBDA,
) -> List[dict]:
    """
    Maximal Marginal Relevance over `docs`.

    Each doc must have an "embedding" key (list[float]).
    Returns up to k docs that balance relevance to the query and
    diversity from each other.

    MMR score at each step:
        λ × sim(doc, query) − (1−λ) × max sim(doc, already_selected)
    """
    if not docs:
        return []
    if not isinstance(query_emb, list) or len(query_emb) == 0:
        # No query embedding available — fall back to distance ranking
        return sorted(docs, key=lambda d: d["distance"])[:k]

    embs = [d["embedding"] for d in docs]
    rel  = [_cosine(query_emb, e) for e in embs]  # relevance to query

    selected_idx: List[int] = []
    remaining    = list(range(len(docs)))

    while remaining and len(selected_idx) < k:
        if not selected_idx:
            # First pick: purely most relevant
            best = max(remaining, key=lambda i: rel[i])
        else:
            def _mmr_score(i: int) -> float:
                redundancy = max(_cosine(embs[i], embs[j]) for j in selected_idx)
                return lambda_mult * rel[i] - (1 - lambda_mult) * redundancy
            best = max(remaining, key=_mmr_score)

        selected_idx.append(best)
        remaining.remove(best)

    return [docs[i] for i in selected_idx]


# ── Stage 3 — Cross-encoder reranking ────────────────────────────────────────

def _rerank(query: str, docs: List[dict], top_k: int = _RERANK_TOP_K) -> List[dict]:
    """
    Score each (query, doc_text) pair with a cross-encoder and return the
    top_k by descending score.

    Falls back to distance order if the model is not installed.
    """
    if not docs:
        return []
    model = _load_cross_encoder()
    if model is None:
        return docs[:top_k]
    try:
        pairs  = [(query, d["text"]) for d in docs]
        scores = model.predict(pairs)
        ranked = sorted(zip(scores, docs), key=lambda x: x[0], reverse=True)
        logger.info(
            "[knowledge] rerank top scores: %s",
            [round(float(s), 3) for s, _ in ranked[:top_k]],
        )
        return [doc for _, doc in ranked[:top_k]]
    except Exception as exc:
        logger.warning("[knowledge] reranking failed (%s) — using MMR order", exc)
        return docs[:top_k]


# ── Main tool node ────────────────────────────────────────────────────────────

def knowledge_tool(state: AgentState) -> dict:
    """
    Retrieve knowledge-base / web context for the Brain's sub-question.

    Returns state keys:
      retrieved_context : list[str]   — text chunks passed to the answer LLM
      sources           : list[str]   — attribution strings
      evidence          : list[dict]  — structured evidence item for the Brain
    """
    task  = state.get("brain_task") or {}
    query = task.get("sub_question") or state.get("user_query") or ""

    if not query.strip():
        return {
            "retrieved_context": [],
            "sources": ["FinAssist Knowledge Base"],
            "evidence": [{"tool": "knowledge", "task": query,
                          "summary": "Empty query — skipped.", "data": {}}],
        }

    # ── Stage 1: route query to one collection — zero DB calls ───────────────
    collection_name = _route_collection(query)

    # ── Stage 2: fetch candidates with embeddings from that one collection ────
    candidates, query_emb = chroma_db.search_with_embeddings(
        collection_name=collection_name,
        query=query,
        n_results=_MMR_CANDIDATES,
    )
    best_dist = candidates[0]["distance"] if candidates else 1.0

    # ── Web fallback: local match too weak ────────────────────────────────────
    if not candidates or best_dist > _WEB_FALLBACK_DIST:
        logger.info(
            "[knowledge] Local RAG miss (dist=%.3f, col=%s) — live web search",
            best_dist, collection_name,
        )
        try:
            scraped_text, source_url = live_web_search_and_scrape(query, max_results=1)
            if scraped_text:
                summary = f"Web fallback: 1 chunk (local dist={best_dist:.3f})."
                return {
                    "retrieved_context": [scraped_text],
                    "sources": [f"Live Web Search ({source_url})"],
                    "evidence": [{"tool": "knowledge", "task": query,
                                  "summary": summary, "data": {"min_distance": best_dist}}],
                }
        except Exception as exc:
            logger.error("[knowledge] Live web search failed: %s", exc)
        return {
            "retrieved_context": [],
            "sources": ["FinAssist Knowledge Base"],
            "evidence": [{"tool": "knowledge", "task": query,
                          "summary": "No results found.", "data": {}}],
        }

    # ── Stage 3: MMR ─────────────────────────────────────────────────────────
    mmr_results = _mmr(query_emb, candidates, k=_MMR_KEEP, lambda_mult=_MMR_LAMBDA)
    logger.info(
        "[knowledge] MMR: %d candidates → %d diverse docs",
        len(candidates), len(mmr_results),
    )

    # ── Stage 4: cross-encoder rerank ────────────────────────────────────────
    final = _rerank(query, mmr_results, top_k=_RERANK_TOP_K)

    context_blocks = [d["text"] for d in final if d.get("text")]
    source_refs    = [
        (d.get("metadata") or {}).get("source")
        or (d.get("metadata") or {}).get("title")
        or "FinAssist Knowledge Base"
        for d in final
    ]

    summary = (
        f"Collection='{collection_name}' | "
        f"candidates={len(candidates)} | MMR={len(mmr_results)} | "
        f"reranked={len(final)} | best_dist={best_dist:.3f}"
    )
    logger.info("[knowledge] %s", summary)

    return {
        "retrieved_context": context_blocks,
        "sources": source_refs or ["FinAssist Knowledge Base"],
        "evidence": [{
            "tool":    "knowledge",
            "task":    query,
            "summary": summary,
            "data": {
                "collection":   collection_name,
                "chunks":       context_blocks,
                "sources":      source_refs,
                "min_distance": best_dist,
                "mmr_lambda":   _MMR_LAMBDA,
            },
        }],
    }
