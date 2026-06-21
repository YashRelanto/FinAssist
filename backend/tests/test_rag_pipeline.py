"""
Tests for the RAG & retrieval pipeline.

Test structure
==============
1. Unit — recursive_chunk()       : text splitting correctness, edge cases
2. Unit — ChromaStore             : CRUD operations on an ephemeral Chroma client
3. Unit — _mmr()                  : MMR selection logic with synthetic embeddings
4. Unit — _rerank()               : cross-encoder path + fallback
5. Smoke — knowledge_tool()       : end-to-end node with mocked ChromaDB + web fallback
6. Smoke — store_in_chroma()      : verifies scraper → Chroma storage roundtrip

All tests are offline — no network calls, no OpenAI key required.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

# ---------------------------------------------------------------------------
# Ensure the backend package is importable when running from repo root.
# ---------------------------------------------------------------------------
_BACKEND = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

# scrapers.py uses a bare `from chroma_store import chroma_db` import.
# That only resolves when `app/utils/` is on sys.path.  Add it here so
# the full import chain (knowledge_tool → scrapers → chroma_store) works
# when pytest runs from the backend/ directory.
_UTILS = os.path.normpath(os.path.join(_BACKEND, "app", "utils"))
if _UTILS not in sys.path:
    sys.path.insert(0, _UTILS)


# ===========================================================================
# 1. Unit tests — recursive_chunk()
# ===========================================================================

class TestRecursiveChunk(unittest.TestCase):
    """Verify the recursive text-splitter produces valid, bounded chunks."""

    @classmethod
    def setUpClass(cls):
        # Import here so sys.path fix above is in place.
        from app.utils.scrapers import recursive_chunk, MIN_CHUNK_LENGTH, MAX_CHUNK_WORDS
        cls.chunk = staticmethod(recursive_chunk)
        cls.MIN_CHUNK_LENGTH = MIN_CHUNK_LENGTH
        cls.MAX_CHUNK_WORDS = MAX_CHUNK_WORDS

    # ── edge cases ─────────────────────────────────────────────────────────

    def test_empty_string_returns_empty(self):
        self.assertEqual(self.chunk(""), [])

    def test_none_returns_empty(self):
        self.assertEqual(self.chunk(None), [])

    def test_whitespace_only_returns_empty(self):
        self.assertEqual(self.chunk("   \n\n   "), [])

    def test_short_text_below_min_returns_empty(self):
        """Text shorter than MIN_CHUNK_LENGTH should be discarded."""
        tiny = "A" * (self.MIN_CHUNK_LENGTH - 1)
        self.assertEqual(self.chunk(tiny), [])

    def test_single_paragraph_fits_in_one_chunk(self):
        text = "This is a reasonable financial paragraph. " * 5
        chunks = self.chunk(text, max_words=200)
        self.assertEqual(len(chunks), 1)

    # ── word-count ceiling ────────────────────────────────────────────────

    def test_no_chunk_exceeds_max_words(self):
        """Every chunk must honour the max_words ceiling (±overlap buffer)."""
        long_text = ("Fixed deposits offer guaranteed returns. " * 100
                     + "\n\n"
                     + "Mutual funds carry market risk. " * 100)
        max_w = 30
        overlap = 5
        chunks = self.chunk(long_text, max_words=max_w, overlap_words=overlap)
        self.assertGreater(len(chunks), 1)
        for i, c in enumerate(chunks):
            wc = len(c.split())
            # First chunk has no overlap prefix, so strict ceiling.
            # Subsequent chunks carry overlap_words extra.
            ceiling = max_w + overlap if i > 0 else max_w
            self.assertLessEqual(
                wc, ceiling + 2,   # +2 tolerance for sentence-boundary rounding
                f"Chunk {i} has {wc} words, ceiling={ceiling}: {c[:80]}…"
            )

    # ── overlap ───────────────────────────────────────────────────────────

    def test_overlap_prefix_present(self):
        """Chunk[i] should start with the tail words of chunk[i-1]."""
        long_text = "word " * 500
        overlap = 10
        chunks = self.chunk(long_text, max_words=40, overlap_words=overlap)
        self.assertGreater(len(chunks), 2, "Need multiple chunks to test overlap")
        for i in range(1, len(chunks)):
            prev_tail = " ".join(chunks[i - 1].split()[-overlap:])
            self.assertTrue(
                chunks[i].startswith(prev_tail),
                f"Chunk {i} does not start with overlap tail of chunk {i-1}",
            )

    def test_no_overlap_when_zero(self):
        """overlap_words=0 should yield independent chunks."""
        text = "Alpha bravo charlie. " * 50
        chunks = self.chunk(text, max_words=10, overlap_words=0)
        self.assertGreater(len(chunks), 2)
        # No chunk should end/start with a repeated sequence.
        for i in range(1, len(chunks)):
            tail = " ".join(chunks[i - 1].split()[-3:])
            self.assertFalse(chunks[i].startswith(tail))

    # ── separator hierarchy ──────────────────────────────────────────────

    def test_paragraph_splits_preferred(self):
        """Double-newlines should create chunk boundaries before sentence splits."""
        para1 = "Banking products include savings accounts and fixed deposits. " * 3
        para2 = "Mutual funds carry market risk but offer higher returns. " * 3
        text = para1 + "\n\n" + para2
        chunks = self.chunk(text, max_words=200)
        # Should split into 2 chunks (one per paragraph) if each fits.
        self.assertEqual(len(chunks), 2)


# ===========================================================================
# 2. Unit tests — ChromaStore CRUD
# ===========================================================================

class TestChromaStore(unittest.TestCase):
    """Test ChromaStore against an ephemeral (in-memory-like) temp directory."""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="chroma_test_")
        # Patch the module-level singleton before it's used in tests.
        from app.utils.chroma_store import ChromaStore, _build_embedding_function
        ef = _build_embedding_function()
        cls.store = ChromaStore(db_path=cls._tmpdir, embedding_function=ef)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def test_collection_creation(self):
        """get_or_create_collection should return a usable collection."""
        col = self.store.get_or_create_collection("test_rag_col")
        self.assertIsNotNone(col)
        self.assertTrue(self.store.collection_exists("test_rag_col"))

    def test_add_and_search_roundtrip(self):
        """Documents added should be retrievable via semantic search."""
        col_name = "test_roundtrip"
        docs = [
            {"id": "fd_1", "text": "Fixed deposits offer guaranteed returns with minimal risk.",
             "metadata": {"category": "banking", "source": "Test"}},
            {"id": "mf_1", "text": "Equity mutual funds invest in the stock market for higher returns.",
             "metadata": {"category": "mutual_funds", "source": "Test"}},
            {"id": "gold_1", "text": "Gold is considered a safe-haven asset during market uncertainty.",
             "metadata": {"category": "gold", "source": "Test"}},
        ]
        self.store.add_documents(col_name, docs)

        results = self.store.search(col_name, "safe investment with fixed returns", n_results=2)
        self.assertGreater(len(results), 0)
        self.assertLessEqual(len(results), 2)
        # Each result should have the expected shape.
        for r in results:
            self.assertIn("id", r)
            self.assertIn("text", r)
            self.assertIn("metadata", r)
            self.assertIn("distance", r)
            self.assertIsInstance(r["distance"], float)

    def test_search_with_embeddings_returns_vectors(self):
        """search_with_embeddings should return document embeddings + query embedding."""
        col_name = "test_embed_search"
        docs = [
            {"id": "e_1", "text": "PPF is a long-term savings scheme backed by the government.",
             "metadata": {"category": "retirement", "source": "Test"}},
            {"id": "e_2", "text": "NPS offers market-linked returns for retirement planning.",
             "metadata": {"category": "retirement", "source": "Test"}},
        ]
        self.store.add_documents(col_name, docs)

        results, q_emb = self.store.search_with_embeddings(
            col_name, "government savings", n_results=2,
        )
        self.assertGreater(len(results), 0)
        self.assertIsInstance(q_emb, list)
        self.assertGreater(len(q_emb), 0, "Query embedding should be non-empty")
        # Each doc result should carry an embedding vector.
        for r in results:
            self.assertIn("embedding", r)
            self.assertIsInstance(r["embedding"], list)
            self.assertGreater(len(r["embedding"]), 0)

    def test_search_empty_collection_returns_empty(self):
        """Searching an empty (but existing) collection should return []."""
        col_name = "test_empty_col"
        self.store.get_or_create_collection(col_name)
        results = self.store.search(col_name, "anything")
        self.assertEqual(results, [])

    def test_search_empty_query_returns_empty(self):
        """An empty query string should short-circuit to []."""
        self.assertEqual(self.store.search("test_roundtrip", ""), [])
        self.assertEqual(self.store.search("test_roundtrip", "   "), [])

    def test_get_collection_count(self):
        """Count should reflect the number of upserted documents."""
        col_name = "test_count"
        docs = [
            {"id": f"cnt_{i}", "text": f"Document number {i} with enough text to pass the filter.",
             "metadata": {"source": "count_test"}}
            for i in range(5)
        ]
        self.store.add_documents(col_name, docs)
        self.assertEqual(self.store.get_collection_count(col_name), 5)

    def test_delete_collection(self):
        """Deleting a collection should remove it."""
        col_name = "test_delete_me"
        self.store.get_or_create_collection(col_name)
        self.assertTrue(self.store.collection_exists(col_name))
        self.store.delete_collection(col_name)
        self.assertFalse(self.store.collection_exists(col_name))

    def test_upsert_idempotent(self):
        """Upserting the same IDs twice should not create duplicates."""
        col_name = "test_upsert_idem"
        doc = {"id": "idem_1", "text": "Recurring deposits allow small monthly investments.",
               "metadata": {"source": "Test"}}
        self.store.add_documents(col_name, [doc])
        self.store.add_documents(col_name, [doc])
        self.assertEqual(self.store.get_collection_count(col_name), 1)


# ===========================================================================
# 3. Unit tests — _mmr() (Maximal Marginal Relevance)
# ===========================================================================

class TestMMR(unittest.TestCase):
    """Test MMR selection with synthetic embedding vectors."""

    @classmethod
    def setUpClass(cls):
        from app.graph.tools.knowledge_tool import _mmr
        cls.mmr = staticmethod(_mmr)

    @staticmethod
    def _make_doc(idx: int, emb: list[float], dist: float = 0.1) -> dict:
        return {
            "id": f"doc_{idx}",
            "text": f"Document {idx}",
            "metadata": {"source": f"src_{idx}"},
            "distance": dist,
            "embedding": emb,
        }

    def test_empty_docs_returns_empty(self):
        self.assertEqual(self.mmr([], [], k=3), [])

    def test_returns_at_most_k(self):
        docs = [self._make_doc(i, [float(i), 0.0]) for i in range(10)]
        q_emb = [5.0, 0.0]
        result = self.mmr(q_emb, docs, k=3)
        self.assertLessEqual(len(result), 3)

    def test_most_relevant_selected_first(self):
        """With λ=1.0 (pure relevance), the most similar doc must come first."""
        d0 = self._make_doc(0, [1.0, 0.0])   # perfectly aligned with query
        d1 = self._make_doc(1, [0.0, 1.0])   # orthogonal
        d2 = self._make_doc(2, [0.7, 0.7])   # moderate
        result = self.mmr([1.0, 0.0], [d0, d1, d2], k=3, lambda_mult=1.0)
        self.assertEqual(result[0]["id"], "doc_0")

    def test_diversity_pushes_different_vectors(self):
        """With λ=0.0 (pure diversity), identical-direction docs should be penalised."""
        d0 = self._make_doc(0, [1.0, 0.0])
        d1 = self._make_doc(1, [0.99, 0.01])  # near-duplicate of d0
        d2 = self._make_doc(2, [0.0, 1.0])    # orthogonal — diverse
        result = self.mmr([1.0, 0.0], [d0, d1, d2], k=2, lambda_mult=0.0)
        # First pick: highest relevance → d0. Second pick: d2 (diverse) beats d1 (similar).
        selected_ids = [r["id"] for r in result]
        self.assertIn("doc_2", selected_ids, "Diverse doc should be selected over near-duplicate")

    def test_no_query_embedding_falls_back_to_distance(self):
        """When query embedding is empty, MMR should fall back to distance-based ranking."""
        d0 = self._make_doc(0, [1.0, 0.0], dist=0.5)
        d1 = self._make_doc(1, [0.0, 1.0], dist=0.1)  # closer
        result = self.mmr([], [d0, d1], k=2)
        self.assertEqual(result[0]["id"], "doc_1", "Closest doc by distance should be first")


# ===========================================================================
# 4. Unit tests — _rerank()
# ===========================================================================

class TestRerank(unittest.TestCase):
    """Test the cross-encoder reranking stage (mocked model)."""

    @classmethod
    def setUpClass(cls):
        from app.graph.tools.knowledge_tool import _rerank
        cls.rerank = staticmethod(_rerank)

    def _make_docs(self, n: int = 5) -> list[dict]:
        return [
            {"id": f"r_{i}", "text": f"Document about topic {i}", "metadata": {}}
            for i in range(n)
        ]

    def test_empty_docs_returns_empty(self):
        self.assertEqual(self.rerank("query", []), [])

    @patch("app.graph.tools.knowledge_tool._load_cross_encoder")
    def test_rerank_respects_top_k(self, mock_loader):
        """Reranking should keep exactly top_k docs."""
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.9, 0.1, 0.5, 0.3, 0.7]
        mock_loader.return_value = mock_model

        docs = self._make_docs(5)
        result = self.rerank("what is FD?", docs, top_k=3)
        self.assertEqual(len(result), 3)

    @patch("app.graph.tools.knowledge_tool._load_cross_encoder")
    def test_rerank_sorts_by_score_descending(self, mock_loader):
        """Highest-scoring doc should appear first after reranking."""
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.1, 0.9, 0.5]
        mock_loader.return_value = mock_model

        docs = self._make_docs(3)
        result = self.rerank("best mutual fund", docs, top_k=3)
        self.assertEqual(result[0]["id"], "r_1", "Highest-scoring doc should be first")

    @patch("app.graph.tools.knowledge_tool._load_cross_encoder")
    def test_rerank_fallback_when_model_none(self, mock_loader):
        """If cross-encoder is unavailable, should return docs in MMR order (truncated)."""
        mock_loader.return_value = None
        docs = self._make_docs(5)
        result = self.rerank("gold prices", docs, top_k=3)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["id"], "r_0", "Fallback should preserve input order")

    @patch("app.graph.tools.knowledge_tool._load_cross_encoder")
    def test_rerank_fallback_on_exception(self, mock_loader):
        """If the model.predict() throws, should gracefully fall back."""
        mock_model = MagicMock()
        mock_model.predict.side_effect = RuntimeError("GPU OOM")
        mock_loader.return_value = mock_model

        docs = self._make_docs(4)
        result = self.rerank("retirement", docs, top_k=2)
        self.assertEqual(len(result), 2)


# ===========================================================================
# 5. Smoke tests — knowledge_tool() end-to-end (mocked backends)
# ===========================================================================

class TestKnowledgeToolSmoke(unittest.TestCase):
    """
    End-to-end smoke tests for the knowledge_tool node.

    ChromaDB and web search are mocked so these tests run offline.
    """

    def _fake_candidates(self, n: int = 5, dist: float = 0.2) -> list[dict]:
        dim = 384
        return [
            {
                "id": f"cand_{i}",
                "text": f"Financial knowledge chunk {i} about banking and deposits. " * 3,
                "metadata": {"category": "banking", "source": f"Source_{i}"},
                "distance": dist + i * 0.02,
                "embedding": np.random.randn(dim).tolist(),
            }
            for i in range(n)
        ]

    @patch("app.graph.tools.knowledge_tool.live_web_search_and_scrape")
    @patch("app.graph.tools.knowledge_tool.chroma_db")
    def test_normal_rag_retrieval(self, mock_chroma, mock_web):
        """Good local match → returns context blocks, sources, and evidence."""
        from app.graph.tools.knowledge_tool import knowledge_tool

        candidates = self._fake_candidates(8, dist=0.15)
        q_emb = np.random.randn(384).tolist()
        mock_chroma.search_with_embeddings.return_value = (candidates, q_emb)

        state = {
            "brain_task": {"sub_question": "What are the best FD rates in India?"},
            "user_query": "Tell me about FD rates",
        }
        result = knowledge_tool(state)

        # Assertions on the returned state patch.
        self.assertIn("retrieved_context", result)
        self.assertIn("sources", result)
        self.assertIn("evidence", result)
        self.assertIsInstance(result["retrieved_context"], list)
        self.assertGreater(len(result["retrieved_context"]), 0)
        self.assertGreater(len(result["sources"]), 0)
        # Evidence should be a list with exactly one item.
        self.assertEqual(len(result["evidence"]), 1)
        ev = result["evidence"][0]
        self.assertEqual(ev["tool"], "knowledge")
        self.assertIn("min_distance", ev["data"])
        # Web fallback should NOT have been called.
        mock_web.assert_not_called()

    @patch("app.graph.tools.knowledge_tool.live_web_search_and_scrape")
    @patch("app.graph.tools.knowledge_tool.chroma_db")
    def test_web_fallback_on_high_distance(self, mock_chroma, mock_web):
        """When best_dist > threshold, should fall back to web search."""
        from app.graph.tools.knowledge_tool import knowledge_tool

        # Simulate a weak local match (distance above threshold).
        candidates = self._fake_candidates(3, dist=0.8)
        q_emb = np.random.randn(384).tolist()
        mock_chroma.search_with_embeddings.return_value = (candidates, q_emb)
        mock_web.return_value = ("Scraped web content about cryptocurrency", "https://example.com/crypto")

        state = {
            "brain_task": {"sub_question": "What is Bitcoin ETF?"},
            "user_query": "Bitcoin ETF",
        }
        result = knowledge_tool(state)

        mock_web.assert_called_once()
        self.assertIn("retrieved_context", result)
        self.assertGreater(len(result["retrieved_context"]), 0)
        self.assertTrue(
            any("Live Web Search" in s for s in result["sources"]),
            "Sources should mention live web search",
        )

    @patch("app.graph.tools.knowledge_tool.live_web_search_and_scrape")
    @patch("app.graph.tools.knowledge_tool.chroma_db")
    def test_empty_collection_triggers_web_fallback(self, mock_chroma, mock_web):
        """Empty ChromaDB collection (no candidates) should trigger web fallback."""
        from app.graph.tools.knowledge_tool import knowledge_tool

        mock_chroma.search_with_embeddings.return_value = ([], [])
        mock_web.return_value = ("Live content", "https://example.com/live")

        state = {
            "brain_task": {"sub_question": "What is P2P lending?"},
            "user_query": "P2P lending",
        }
        result = knowledge_tool(state)
        mock_web.assert_called_once()

    @patch("app.graph.tools.knowledge_tool.live_web_search_and_scrape")
    @patch("app.graph.tools.knowledge_tool.chroma_db")
    def test_both_local_and_web_fail(self, mock_chroma, mock_web):
        """When both local RAG and web search fail, return empty context gracefully."""
        from app.graph.tools.knowledge_tool import knowledge_tool

        mock_chroma.search_with_embeddings.return_value = ([], [])
        mock_web.return_value = ("", "")

        state = {
            "brain_task": {"sub_question": "obscure question nobody knows"},
            "user_query": "obscure question",
        }
        result = knowledge_tool(state)

        self.assertEqual(result["retrieved_context"], [])
        self.assertEqual(result["sources"], [])
        self.assertEqual(len(result["evidence"]), 1)
        self.assertIn("No results found", result["evidence"][0]["summary"])

    @patch("app.graph.tools.knowledge_tool.chroma_db")
    def test_empty_query_skips_retrieval(self, mock_chroma):
        """An empty or whitespace-only query should short-circuit immediately."""
        from app.graph.tools.knowledge_tool import knowledge_tool

        state = {"brain_task": {"sub_question": ""}, "user_query": ""}
        result = knowledge_tool(state)

        self.assertEqual(result["retrieved_context"], [])
        self.assertIn("Empty query", result["evidence"][0]["summary"])
        mock_chroma.search_with_embeddings.assert_not_called()

    @patch("app.graph.tools.knowledge_tool.live_web_search_and_scrape")
    @patch("app.graph.tools.knowledge_tool.chroma_db")
    def test_web_fallback_truncates_long_text(self, mock_chroma, mock_web):
        """Web fallback text should be capped at _MAX_WEB_CHARS."""
        from app.graph.tools.knowledge_tool import knowledge_tool, _MAX_WEB_CHARS

        mock_chroma.search_with_embeddings.return_value = ([], [])
        huge_text = "X" * 50_000
        mock_web.return_value = (huge_text, "https://example.com")

        state = {
            "brain_task": {"sub_question": "something"},
            "user_query": "something",
        }
        result = knowledge_tool(state)
        # The returned context should be capped.
        self.assertLessEqual(len(result["retrieved_context"][0]), _MAX_WEB_CHARS)


# ===========================================================================
# 6. Smoke tests — store_in_chroma() scraper → vector roundtrip
# ===========================================================================

class TestStoreInChroma(unittest.TestCase):
    """Verify that the scraper's store_in_chroma writes chunks to ChromaDB."""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="chroma_scraper_test_")
        from app.utils.chroma_store import ChromaStore, _build_embedding_function
        ef = _build_embedding_function()
        cls.store = ChromaStore(db_path=cls._tmpdir, embedding_function=ef)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    @patch("app.utils.scrapers.chroma_db")
    def test_store_in_chroma_adds_chunks(self, mock_chroma):
        """store_in_chroma should call add_documents with chunked text."""
        from app.utils.scrapers import store_in_chroma

        # Wire mock to capture the call.
        mock_chroma.get_or_create_collection.return_value = MagicMock()
        mock_chroma.add_documents = MagicMock()

        text = ("A fixed deposit is a financial product offered by banks. " * 30
                + "\n\n"
                + "Recurring deposits allow you to invest small amounts monthly. " * 30)

        store_in_chroma("banking", "https://example.com", "TestSource", text)

        # add_documents should have been called exactly once.
        mock_chroma.add_documents.assert_called_once()
        call_kwargs = mock_chroma.add_documents.call_args
        # Collection name should be the unified one.
        self.assertEqual(call_kwargs[1]["collection_name"], "finassist_knowledge")
        docs = call_kwargs[1]["documents"]
        self.assertGreater(len(docs), 0)
        # Each doc should have the right metadata shape.
        for d in docs:
            self.assertIn("id", d)
            self.assertIn("text", d)
            self.assertIn("metadata", d)
            self.assertEqual(d["metadata"]["category"], "banking")
            self.assertEqual(d["metadata"]["source"], "TestSource")
            self.assertIn("scraped_at", d["metadata"])

    @patch("app.utils.scrapers.chroma_db")
    def test_store_in_chroma_skips_short_text(self, mock_chroma):
        """Text shorter than MIN_TEXT_LENGTH should be skipped entirely."""
        from app.utils.scrapers import store_in_chroma

        mock_chroma.add_documents = MagicMock()
        store_in_chroma("banking", "https://x.com", "Short", "tiny")
        mock_chroma.add_documents.assert_not_called()

    @patch("app.utils.scrapers.chroma_db")
    def test_store_in_chroma_evicts_stale_chunks(self, mock_chroma):
        """Before inserting new chunks, stale chunks for the same source should be deleted."""
        from app.utils.scrapers import store_in_chroma

        mock_collection = MagicMock()
        mock_chroma.get_or_create_collection.return_value = mock_collection
        mock_chroma.add_documents = MagicMock()

        text = "Credit cards offer reward points and cashback benefits. " * 20

        store_in_chroma("banking", "https://example.com", "CreditCards", text)

        # The collection's .delete() should have been called to evict stale chunks.
        mock_collection.delete.assert_called_once_with(where={"source": "CreditCards"})


# ===========================================================================
# 7. Integration smoke — full ChromaStore add + search_with_embeddings + MMR
# ===========================================================================

class TestRAGPipelineIntegration(unittest.TestCase):
    """
    End-to-end integration: seed docs → search_with_embeddings → MMR → rerank.

    Uses a real ephemeral ChromaDB (local ONNX embeddings) so no mocks.
    """

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="chroma_integration_")
        from app.utils.chroma_store import ChromaStore, _build_embedding_function
        from app.graph.tools.knowledge_tool import _mmr

        ef = _build_embedding_function()
        cls.store = ChromaStore(db_path=cls._tmpdir, embedding_function=ef)
        cls.mmr = staticmethod(_mmr)

        # Seed with diverse financial documents.
        docs = [
            {"id": "int_fd",    "text": "Fixed deposits are a safe investment with guaranteed returns from banks. The interest rate is fixed for the tenure.",
             "metadata": {"category": "banking", "source": "FDGuide"}},
            {"id": "int_mf",    "text": "Equity mutual funds pool investor money to buy stocks. They carry market risk but can generate high returns over the long term.",
             "metadata": {"category": "mutual_funds", "source": "MFGuide"}},
            {"id": "int_gold",  "text": "Gold prices fluctuate with global demand and supply. Gold ETFs let you invest in gold without physical storage.",
             "metadata": {"category": "gold", "source": "GoldGuide"}},
            {"id": "int_ppf",   "text": "Public Provident Fund is a government-backed savings scheme with tax benefits under Section 80C.",
             "metadata": {"category": "retirement", "source": "PPFGuide"}},
            {"id": "int_nps",   "text": "National Pension System is a voluntary retirement savings scheme regulated by PFRDA.",
             "metadata": {"category": "retirement", "source": "NPSGuide"}},
            {"id": "int_cc",    "text": "Credit cards offer rewards, cashback, and purchase protection. Annual fees vary by card type and issuer.",
             "metadata": {"category": "banking", "source": "CCGuide"}},
        ]
        cls.store.add_documents("finassist_knowledge", docs)
        cls.col_name = "finassist_knowledge"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def test_semantic_search_relevance(self):
        """A query about FDs should rank the FD document highest (lowest distance)."""
        results = self.store.search(self.col_name, "What is a fixed deposit interest rate?", n_results=3)
        self.assertGreater(len(results), 0)
        top = results[0]
        self.assertIn("fixed", top["text"].lower())

    def test_search_with_embeddings_then_mmr(self):
        """search_with_embeddings → MMR should return diverse, relevant results."""
        docs, q_emb = self.store.search_with_embeddings(
            self.col_name, "retirement savings with tax benefits", n_results=6,
        )
        self.assertGreater(len(docs), 0)
        self.assertGreater(len(q_emb), 0)

        mmr_results = self.mmr(q_emb, docs, k=3, lambda_mult=0.7)
        self.assertLessEqual(len(mmr_results), 3)
        # The PPF document should be in the top results (most relevant to query).
        ids = [r["id"] for r in mmr_results]
        self.assertIn("int_ppf", ids, "PPF doc should be selected for retirement+tax query")

    def test_category_metadata_preserved(self):
        """Category metadata should survive the add → search roundtrip."""
        results = self.store.search(self.col_name, "credit card rewards cashback", n_results=1)
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["metadata"]["category"], "banking")
        self.assertEqual(results[0]["metadata"]["source"], "CCGuide")


if __name__ == "__main__":
    unittest.main()
