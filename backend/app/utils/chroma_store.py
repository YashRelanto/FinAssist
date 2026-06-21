"""
ChromaDB persistent client wrapper for the FinAssist vector knowledge base.

Provides a module-level singleton `chroma_db` that is imported by:
  - app.graph.nodes.rag_node  (search)
  - app.utils.scrapers        (add_documents)

Storage location: backend/chroma_db/   (auto-created on first run)

Collections managed:
  - finassist_knowledge : All scraped financial data (banking, investments, tips)
                          Category is preserved in per-chunk metadata.

Embedding strategy (priority order):
  1. OpenAI text-embedding-3-small  — if OPENAI_API_KEY is set (best quality)
  2. ChromaDB DefaultEmbeddingFunction — local ONNX mini-model (no API needed)

IMPORTANT: The embedding function chosen at collection creation time must be
           consistent for all subsequent searches on that collection.
           This module pins the chosen function at startup for the process lifetime.
"""

from __future__ import annotations

import logging
import os
from typing import Any

# ── Bootstrap: ensure .env is loaded before reading env-vars ──────────────────
try:
    from dotenv import load_dotenv
    _env_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env")
    )
    load_dotenv(dotenv_path=_env_path, override=False)
except ImportError:
    pass

import chromadb
from chromadb.config import Settings as _ChromaSettings

logger = logging.getLogger(__name__)

# ─── Storage path ─────────────────────────────────────────────────────────────

_CHROMA_DB_PATH: str = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "chroma_db")
)

# ─── Known collections (auto-created on first access) ─────────────────────────

KNOWN_COLLECTIONS: list[str] = [
    "finassist_knowledge",
]


# ─── Embedding function factory ───────────────────────────────────────────────

def _build_embedding_function():
    """
    Returns the best available embedding function for this runtime.

    Default strategy: LOCAL — uses ChromaDB's built-in ONNX mini-LM model.
    No API key or internet connection required.  Fully offline capable.

    To opt into OpenAI embeddings (better quality, requires billing):
        Set CHROMA_USE_OPENAI_EMBED=true in your .env file.

    Priority when CHROMA_USE_OPENAI_EMBED=true:
      1. OpenAI text-embedding-3-small  (requires funded OPENAI_API_KEY)
      2. ChromaDB DefaultEmbeddingFunction (fallback if OpenAI fails)
    """
    use_openai_embed = os.getenv("CHROMA_USE_OPENAI_EMBED", "false").strip().lower() == "true"

    if use_openai_embed:
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        if openai_key:
            try:
                from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
                ef = OpenAIEmbeddingFunction(
                    api_key=openai_key,
                    model_name="text-embedding-3-small",
                )
                logger.info("[ChromaStore] Embedding: OpenAI text-embedding-3-small ✅")
                return ef
            except Exception as exc:
                logger.warning(
                    "[ChromaStore] OpenAI embedding function unavailable (%s). "
                    "Falling back to local default.", exc
                )

    # ── Local ONNX default — always works, no quota ───────────────────────────
    try:
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
        ef = DefaultEmbeddingFunction()
        logger.info("[ChromaStore] Embedding: Local ONNX DefaultEmbeddingFunction ✅")
        return ef
    except Exception as exc:
        logger.critical(
            "[ChromaStore] No embedding function available (%s). "
            "Searches will fail. Install chromadb[default] or onnxruntime.", exc
        )
        return None


# ─── ChromaStore class ────────────────────────────────────────────────────────

class ChromaStore:
    """
    Thin wrapper around a persistent ChromaDB client.

    Public API
    ----------
    search(collection_name, query, n_results=3) -> list[dict]
        Semantic search; returns up to n_results documents.
        Each result dict: {"id": str, "text": str, "metadata": dict, "distance": float}

    add_documents(collection_name, documents) -> None
        Upsert a list of documents into a collection.
        Each document dict must have: {"id": str, "text": str, "metadata": dict}

    delete_collection(collection_name) -> None
        Permanently delete a collection and all its vectors.

    collection_exists(collection_name) -> bool
        Returns True if the named collection has been created.

    get_collection_count(collection_name) -> int
        Returns the number of documents in a collection (0 if absent).

    list_collections() -> list[str]
        Returns the names of all existing collections.
    """

    def __init__(self, db_path: str, embedding_function) -> None:
        self._db_path = db_path
        self._ef = embedding_function
        self._client: chromadb.PersistentClient | None = None
        self._collection_cache: dict[str, chromadb.Collection] = {}
        self._initialise()

    # ── Initialisation ────────────────────────────────────────────────────────

    def _initialise(self) -> None:
        """Create persistent client and pre-warm all known collections."""
        os.makedirs(self._db_path, exist_ok=True)
        try:
            self._client = chromadb.PersistentClient(
                path=self._db_path,
                settings=_ChromaSettings(
                    anonymized_telemetry=False,
                    allow_reset=True,
                ),
            )
            logger.info("[ChromaStore] Persistent client initialised at: %s", self._db_path)
        except Exception as exc:
            logger.critical("[ChromaStore] Failed to create PersistentClient: %s", exc)
            raise RuntimeError(f"ChromaDB initialisation failed: {exc}") from exc

        # Pre-create all known collections so they're ready without seeding
        for name in KNOWN_COLLECTIONS:
            self._get_or_create_collection(name)

    def _get_or_create_collection(self, name: str) -> chromadb.Collection:
        """Return (creating if necessary) the named collection with the shared EF."""
        if name in self._collection_cache:
            return self._collection_cache[name]

        try:
            kwargs: dict[str, Any] = {"name": name}
            if self._ef is not None:
                kwargs["embedding_function"] = self._ef

            collection = self._client.get_or_create_collection(
                **kwargs,
                metadata={"hnsw:space": "cosine"},
            )
            self._collection_cache[name] = collection
            logger.debug("[ChromaStore] Collection ready: %s (%d docs)", name, collection.count())
            return collection
        except Exception as exc:
            logger.error("[ChromaStore] Cannot get/create collection '%s': %s", name, exc)
            raise

    def get_or_create_collection(self, name: str) -> chromadb.Collection:
        """Public wrapper around _get_or_create_collection."""
        return self._get_or_create_collection(name)

    # ── Public API ────────────────────────────────────────────────────────────

    def search(
        self,
        collection_name: str,
        query: str,
        n_results: int = 3,
    ) -> list[dict]:
        """
        Perform a semantic similarity search against the named collection.

        Parameters
        ----------
        collection_name : str   One of KNOWN_COLLECTIONS (or any custom name)
        query           : str   Natural language query string
        n_results       : int   Maximum number of results to return (default 3)

        Returns
        -------
        list[dict]  Each item: {"id": str, "text": str, "metadata": dict, "distance": float}
                    Returns [] on any error or if the collection is empty.
        """
        if not query or not query.strip():
            logger.warning("[ChromaStore] search() called with empty query — skipping.")
            return []

        try:
            collection = self._get_or_create_collection(collection_name)
            count = collection.count()

            if count == 0:
                logger.info(
                    "[ChromaStore] Collection '%s' is empty. "
                    "Run scrapers.py to seed the vector store.", collection_name
                )
                return []

            # Cap n_results to the number of available documents
            safe_n = min(n_results, count)

            results = collection.query(
                query_texts=[query],
                n_results=safe_n,
                include=["documents", "metadatas", "distances"],
            )

            # Unpack chromadb response structure
            ids        = results.get("ids",        [[]])[0]
            documents  = results.get("documents",  [[]])[0]
            metadatas  = results.get("metadatas",  [[]])[0]
            distances  = results.get("distances",  [[]])[0]

            output: list[dict] = []
            for doc_id, text, meta, dist in zip(ids, documents, metadatas, distances):
                output.append({
                    "id":       doc_id,
                    "text":     text or "",
                    "metadata": meta or {},
                    "distance": round(float(dist), 6),
                })

            logger.info(
                "[ChromaStore] search('%s', n=%d) → %d results",
                collection_name, safe_n, len(output)
            )
            return output

        except Exception as exc:
            logger.error(
                "[ChromaStore] search() failed on collection '%s': %s",
                collection_name, exc
            )
            return []

    def search_with_embeddings(
        self,
        collection_name: str,
        query: str,
        n_results: int = 15,
    ) -> tuple[list[dict], list[float]]:
        """
        Like search() but also returns document embeddings and the query embedding.
        Used by the knowledge tool for MMR + reranking.

        Returns
        -------
        (docs, query_embedding)
          docs            : list[dict] — same shape as search(), plus key "embedding": list[float]
          query_embedding : list[float] — embedding of the query string (empty list on failure)
        """
        if not query or not query.strip():
            return [], []
        try:
            collection = self._get_or_create_collection(collection_name)
            count = collection.count()
            if count == 0:
                return [], []

            safe_n = min(n_results, count)
            results = collection.query(
                query_texts=[query],
                n_results=safe_n,
                include=["documents", "metadatas", "distances", "embeddings"],
            )

            ids        = results.get("ids",        [[]])[0]
            documents  = results.get("documents",  [[]])[0]
            metadatas  = results.get("metadatas",  [[]])[0]
            distances  = results.get("distances",  [[]])[0]
            embeddings = results.get("embeddings", [[]])[0]  # list of list[float]

            def _to_list(v) -> list:
                # ChromaDB returns numpy arrays; convert to plain Python list so callers
                # can safely do `if not emb`, boolean checks, and JSON serialisation.
                if v is None:
                    return []
                if hasattr(v, "tolist"):
                    return v.tolist()
                return list(v)

            docs = []
            for doc_id, text, meta, dist, emb in zip(ids, documents, metadatas, distances, embeddings):
                docs.append({
                    "id":        doc_id,
                    "text":      text or "",
                    "metadata":  meta or {},
                    "distance":  round(float(dist), 6),
                    "embedding": _to_list(emb),
                })

            # Compute query embedding so the caller can do MMR without a second round-trip.
            query_emb: list[float] = []
            if self._ef is not None:
                try:
                    query_emb = _to_list(self._ef([query])[0])
                except Exception as exc:
                    logger.warning("[ChromaStore] query embedding failed: %s", exc)

            logger.info(
                "[ChromaStore] search_with_embeddings('%s', n=%d) → %d results",
                collection_name, safe_n, len(docs),
            )
            return docs, query_emb

        except Exception as exc:
            logger.error(
                "[ChromaStore] search_with_embeddings() failed on '%s': %s",
                collection_name, exc,
            )
            return [], []

    def add_documents(
        self,
        collection_name: str,
        documents: list[dict],
    ) -> None:
        """
        Upsert documents into the named collection.

        Parameters
        ----------
        collection_name : str
        documents       : list[dict]
            Each dict must contain:
              - "id"       : str   Unique document identifier (UUID recommended)
              - "text"     : str   Content to embed and store
              - "metadata" : dict  Arbitrary key-value provenance metadata

        Notes
        -----
        Uses `upsert` (not `add`) so repeated seeding runs are idempotent.
        Documents are batched in groups of 100 to avoid payload size limits.
        """
        if not documents:
            logger.warning("[ChromaStore] add_documents() called with empty list — skipping.")
            return

        try:
            collection = self._get_or_create_collection(collection_name)

            ids:   list[str]  = []
            texts: list[str]  = []
            metas: list[dict] = []

            for doc in documents:
                doc_id = str(doc.get("id", ""))
                text   = str(doc.get("text", "")).strip()
                meta   = doc.get("metadata", {}) or {}

                if not doc_id or not text:
                    logger.warning(
                        "[ChromaStore] Skipping document with missing id or text: %s",
                        doc
                    )
                    continue

                ids.append(doc_id)
                texts.append(text)
                metas.append(meta)

            if not ids:
                logger.warning("[ChromaStore] No valid documents to upsert after filtering.")
                return

            # Batch upsert in groups of 100
            batch_size = 100
            total_upserted = 0
            for i in range(0, len(ids), batch_size):
                batch_ids   = ids[i : i + batch_size]
                batch_texts = texts[i : i + batch_size]
                batch_metas = metas[i : i + batch_size]

                collection.upsert(
                    ids=batch_ids,
                    documents=batch_texts,
                    metadatas=batch_metas,
                )
                total_upserted += len(batch_ids)

            logger.info(
                "[ChromaStore] Upserted %d documents into '%s'. "
                "Collection now has %d total.",
                total_upserted, collection_name, collection.count()
            )

        except Exception as exc:
            logger.error(
                "[ChromaStore] add_documents() failed on collection '%s': %s",
                collection_name, exc
            )
            raise

    def delete_collection(self, collection_name: str) -> None:
        """Permanently delete a collection and all its vectors."""
        try:
            self._client.delete_collection(collection_name)
            self._collection_cache.pop(collection_name, None)
            logger.info("[ChromaStore] Collection '%s' deleted.", collection_name)
        except Exception as exc:
            logger.warning(
                "[ChromaStore] delete_collection('%s') failed: %s", collection_name, exc
            )

    def collection_exists(self, collection_name: str) -> bool:
        """Returns True if the named collection has been created in this client."""
        try:
            existing = [c.name for c in self._client.list_collections()]
            return collection_name in existing
        except Exception:
            return False

    def get_collection_count(self, collection_name: str) -> int:
        """Returns the number of documents in the collection, or 0 if absent/empty."""
        try:
            collection = self._get_or_create_collection(collection_name)
            return collection.count()
        except Exception:
            return 0

    def list_collections(self) -> list[str]:
        """Returns the names of all collections in this client."""
        try:
            return [c.name for c in self._client.list_collections()]
        except Exception as exc:
            logger.error("[ChromaStore] list_collections() failed: %s", exc)
            return []

    def reset_all(self) -> None:
        """
        ⚠️  DESTRUCTIVE: Delete every collection and all vectors.
        Use only in development / re-seeding workflows.
        """
        try:
            self._client.reset()
            self._collection_cache.clear()
            logger.warning("[ChromaStore] reset_all() executed — all data wiped.")
        except Exception as exc:
            logger.error("[ChromaStore] reset_all() failed: %s", exc)


# ─── Module-level singleton ───────────────────────────────────────────────────

_embedding_function = _build_embedding_function()

chroma_db = ChromaStore(
    db_path=_CHROMA_DB_PATH,
    embedding_function=_embedding_function,
)
"""
Module-level ChromaStore singleton.  Import and use like:

    from app.utils.chroma_store import chroma_db

    results = chroma_db.search("finassist_knowledge", "best FD rates", n_results=3)
    chroma_db.add_documents("finassist_knowledge", documents)
"""
