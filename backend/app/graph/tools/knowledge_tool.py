"""
Knowledge Tool — RAG retrieval for general financial education / product info.

Pipeline (in order):
  1. Collection routing  — pure keyword scoring; maps the query to exactly one
                           ChromaDB collection in O(keywords) time, zero DB calls.
                           Single-word keywords use exact token matching to prevent
                           false positives ("rd" in "word", "nse" in "expenses").
  2. Candidate fetch     — retrieve _MMR_CANDIDATES docs + embedding vectors from
                           the routed collection via chroma_db.search_with_embeddings.
  3. MMR                 — filter candidates → _MMR_KEEP using Maximal Marginal
                           Relevance (λ=0.7 balances relevance vs diversity).
                           All similarities are precomputed with numpy in one pass.
  4. Cross-encoder rerank— score the _MMR_KEEP survivors with a bi-directional
                           cross-encoder and keep the top _RERANK_TOP_K.
  5. Web fallback        — if best ANN distance > _WEB_FALLBACK_DIST (weak local
                           match), discard local results and run a live DuckDuckGo
                           search instead. Text is capped at _MAX_WEB_CHARS.
"""

from __future__ import annotations

import logging
import re
import threading

import numpy as np

from app.graph.state import AgentState
from app.utils.chroma_store import chroma_db
from app.utils.scrapers import live_web_search_and_scrape

logger = logging.getLogger(__name__)

KNOWLEDGE_COLLECTIONS = ["banking_data", "investment_data", "financial_tips"]

# ── Retrieval hyper-parameters ─────────────────────────────────────────────────
_MMR_LAMBDA        = 0.7    # λ: 70 % relevance, 30 % diversity
_MMR_CANDIDATES    = 15     # initial fetch from the routed collection
_MMR_KEEP          = 8      # MMR survivors fed to the reranker
_RERANK_TOP_K      = 3      # final chunks returned to the Brain
_WEB_FALLBACK_DIST = 0.6    # cosine distance threshold: above this → web fallback
_MAX_WEB_CHARS     = 4_000  # FIX: raw scraped text can be 50k+ chars; cap it here
                             #      to prevent downstream LLM context-window overflow

# ── Cross-encoder: lazy singleton, thread-safe ────────────────────────────────
# FIX: original had no lock — concurrent requests raced to load the model.
#      A failed load left _cross_encoder=None so every call retried the import.
#      Now: one lock + a boolean flag ensure exactly one load attempt, ever.
_cross_encoder        = None
_cross_encoder_loaded = False  # True once a load attempt has completed (pass or fail)
_cross_encoder_lock   = threading.Lock()

# ── Routing ────────────────────────────────────────────────────────────────────
_DEFAULT_COLLECTION = "financial_tips"

# Compile a reusable word-tokeniser once
# FIX: original used `kw in query_string` which is a raw substring check.
#      "rd" matches "word"/"record"/"third"; "nse" matches "expenses";
#      "nav" matches "navigate". Single-word keywords now use token-set lookup.
_WORD_TOKEN_RE = re.compile(r"\b\w+\b")

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


# ── Cross-encoder loader ───────────────────────────────────────────────────────

def _load_cross_encoder() -> object | None:
    global _cross_encoder, _cross_encoder_loaded

    # Fast path: a load attempt already happened (success or failure)
    if _cross_encoder_loaded:
        return _cross_encoder

    # Slow path: first call — serialize with a lock so concurrent requests
    # don't each try to load the model independently.
    with _cross_encoder_lock:
        if _cross_encoder_loaded:          # double-checked inside the lock
            return _cross_encoder
        try:
            from sentence_transformers import CrossEncoder
            _cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
            logger.info("[knowledge] Cross-encoder loaded: ms-marco-MiniLM-L-6-v2")
        except Exception as exc:
            logger.warning("[knowledge] CrossEncoder unavailable (%s) — reranking disabled.", exc)
            _cross_encoder = None
        finally:
            _cross_encoder_loaded = True   # never retry after first attempt, pass or fail

    return _cross_encoder


# ── Stage 1 — Collection routing (zero DB calls) ──────────────────────────────

def _route_collection(query: str) -> str:
    """
    Map a query to exactly one collection using keyword scoring.

    Algorithm
    ---------
    - Lowercase the query and extract word tokens via regex.
    - Multi-word keywords (e.g. "mutual fund", "fixed deposit"):
        substring match on the lowercased query — specific enough to be safe.
    - Single-word keywords (e.g. "rd", "nse", "nav"):
        exact token match against the word-token set — prevents false positives
        like "rd" in "word"/"third", "nse" in "expenses", "nav" in "navigate".
    - Return the collection with the highest hit count.
    - Tie-break: earlier in _ROUTING_RULES wins (banking > investment > tips).
    - Zero hits → _DEFAULT_COLLECTION.

    Cost: O(total_keywords) — microseconds, zero DB calls.
    """
    q_lower  = query.lower()
    q_tokens = set(_WORD_TOKEN_RE.findall(q_lower))  # {"what", "is", "the", "rd", ...}

    best_name  = _DEFAULT_COLLECTION
    best_score = 0

    for collection_name, keywords in _ROUTING_RULES:
        score = 0
        for kw in keywords:
            if " " in kw:
                score += kw in q_lower    # multi-word: substring is specific enough
            else:
                score += kw in q_tokens   # single-word: exact token to avoid false hits
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
    query_emb:   list,
    docs:        list[dict],
    k:           int   = _MMR_KEEP,
    lambda_mult: float = _MMR_LAMBDA,
) -> list[dict]:
    """
    Maximal Marginal Relevance over *docs*.

    FIX: original called a pure-Python _cosine() O(k × n) times inside the
    selection loop over 384-768-dim vectors — extremely slow.
    Now: numpy precomputes ALL relevance scores and pairwise similarities in
    one matrix multiply before the loop, so the loop itself does only
    arithmetic on scalars.

    MMR score at each step:
        λ × sim(doc, query) − (1−λ) × max sim(doc, already_selected)
    """
    if not docs:
        return []
    if not isinstance(query_emb, list) or not query_emb:
        # No query embedding available — fall back to distance ranking
        return sorted(docs, key=lambda d: d.get("distance", 1.0))[:k]

    # ── Precompute all similarities in one numpy pass ──────────────────────
    emb_matrix = np.array([d["embedding"] for d in docs], dtype=np.float32)  # (n, dim)
    q_vec      = np.array(query_emb, dtype=np.float32)  # (dim,)

    # L2-normalise so dot product == cosine similarity
    emb_unit = emb_matrix / (np.linalg.norm(emb_matrix, axis=1, keepdims=True) + 1e-9)
    q_unit   = q_vec      / (np.linalg.norm(q_vec)                            + 1e-9)

    rel = (emb_unit @ q_unit).tolist()      # (n,)   — cosine sim to query
    sim = (emb_unit @ emb_unit.T).tolist()  # (n, n) — pairwise cosine sim

    # ── Greedy MMR selection ───────────────────────────────────────────────
    selected_idx: list[int] = []
    remaining = list(range(len(docs)))

    while remaining and len(selected_idx) < k:
        if not selected_idx:
            best = max(remaining, key=lambda i: rel[i])
        else:
            # FIX: original defined _mmr_score() inside this loop, recompiling
            # it and re-running pure-Python _cosine on every iteration.
            # Now: sim[i][j] is a pre-computed scalar lookup — O(1) per pair.
            # Snapshot selected_idx via default arg to make the capture explicit.
            sel  = selected_idx
            best = max(
                remaining,
                key=lambda i, _sel=sel: (
                    lambda_mult * rel[i]
                    - (1 - lambda_mult) * max(sim[i][j] for j in _sel)
                ),
            )
        selected_idx.append(best)
        remaining.remove(best)

    return [docs[i] for i in selected_idx]


# ── Stage 3 — Cross-encoder reranking ────────────────────────────────────────

def _rerank(query: str, docs: list[dict], top_k: int = _RERANK_TOP_K) -> list[dict]:
    """
    Score each (query, doc_text) pair with a cross-encoder; keep top_k.
    Falls back to MMR order when the model is unavailable.
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
            "sources":           ["FinAssist Knowledge Base"],
            "evidence": [{"tool": "knowledge", "task": query,
                          "summary": "Empty query — skipped.", "data": {}}],
        }

    # ── Stage 1: route to one collection — zero DB calls ─────────────────────
    collection_name = _route_collection(query)

    # ── Stage 2: fetch candidates + embedding vectors ─────────────────────────
    candidates, query_emb = chroma_db.search_with_embeddings(
        collection_name=collection_name,
        query=query,
        n_results=_MMR_CANDIDATES,
    )
    # FIX: original did candidates[0]["distance"] — KeyError if the key is absent.
    best_dist = candidates[0].get("distance", 1.0) if candidates else 1.0

    # ── Web fallback: local match too weak ────────────────────────────────────
    if not candidates or best_dist > _WEB_FALLBACK_DIST:
        logger.info(
            "[knowledge] Local RAG miss (dist=%.3f, col=%s) — live web search",
            best_dist, collection_name,
        )
        try:
            scraped_text, source_url = live_web_search_and_scrape(query, max_results=1)
            if scraped_text:
                # FIX: raw scraped text is 10k-50k chars; passing it whole to the
                # downstream LLM blows the context window.  Cap at _MAX_WEB_CHARS.
                context = scraped_text[:_MAX_WEB_CHARS]
                summary = (
                    f"Web fallback: {len(context):,} chars returned "
                    f"(local dist={best_dist:.3f})."
                )
                return {
                    "retrieved_context": [context],
                    "sources":           [f"Live Web Search ({source_url})"],
                    "evidence": [{"tool": "knowledge", "task": query,
                                  "summary": summary,
                                  "data": {"min_distance": best_dist}}],
                }
        except Exception as exc:
            logger.error("[knowledge] Live web search failed: %s", exc)

        # Both local AND web failed — return empty, not a misleading source name.
        # FIX: original still said sources=["FinAssist Knowledge Base"] here,
        # implying we found something when we found nothing.
        return {
            "retrieved_context": [],
            "sources":           [],
            "evidence": [{"tool": "knowledge", "task": query,
                          "summary": "No results found locally or via web search.",
                          "data": {}}],
        }

    # ── Stage 3: MMR ──────────────────────────────────────────────────────────
    mmr_results = _mmr(query_emb, candidates, k=_MMR_KEEP, lambda_mult=_MMR_LAMBDA)
    logger.info(
        "[knowledge] MMR: %d candidates → %d diverse docs",
        len(candidates), len(mmr_results),
    )

    # ── Stage 4: cross-encoder rerank ─────────────────────────────────────────
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
        "sources":           source_refs or ["FinAssist Knowledge Base"],
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