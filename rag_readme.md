# 🧠 FinAssist — RAG (Retrieval-Augmented Generation) System

> **Full technical reference for the FinAssist RAG pipeline.**
> Covers every stage from raw data ingestion through vector storage, semantic retrieval, LLM-powered generation, multi-layer guardrails, session persistence, and scheduled data refresh.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [High-Level Data Flow](#2-high-level-data-flow)
3. [Component Deep-Dive](#3-component-deep-dive)
   - 3.1 [Data Ingestion Layer — `scrapers.py`](#31-data-ingestion-layer--scraperspy)
   - 3.2 [Vector Store Layer — `chroma_store.py`](#32-vector-store-layer--chroma_storepy)
   - 3.3 [Intent Classification — `chatbot_engine.py :: classify_intent()`](#33-intent-classification--chatbot_enginepy--classify_intent)
   - 3.4 [RAG Executor — `chatbot_engine.py :: execute_rag()`](#34-rag-executor--chatbot_enginepy--execute_rag)
   - 3.5 [NL2SQL Branch — `nl2sql.py`](#35-nl2sql-branch--nl2sqlpy)
   - 3.6 [Session Management — `chatbot_engine.py :: SessionManager`](#36-session-management--chatbot_enginepy--sessionmanager)
   - 3.7 [Security Guardrails Layer](#37-security-guardrails-layer)
   - 3.8 [API Layer — `routes/chatbot.py`](#38-api-layer--routeschatbotpy)
   - 3.9 [Scheduled Data Refresh — `tasks/scheduler.py`](#39-scheduled-data-refresh--tasksschedulerpy)
4. [Step-by-Step Request Lifecycle](#4-step-by-step-request-lifecycle)
5. [ChromaDB Collection Schema](#5-chromadb-collection-schema)
6. [Embedding Strategy](#6-embedding-strategy)
7. [Configuration & Environment Variables](#7-configuration--environment-variables)
8. [File Reference Map](#8-file-reference-map)
9. [Utility Scripts](#9-utility-scripts)
10. [Sequence Diagram — Full Chat Turn](#10-sequence-diagram--full-chat-turn)

---

## 1. Architecture Overview

The FinAssist RAG system is a **production-grade Retrieval-Augmented Generation pipeline** designed for Indian retail banking advisory. It combines:

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Data Ingestion** | Playwright + BeautifulSoup | Headless browser scraping of 8 financial data sources |
| **Chunking Engine** | Custom NLP chunker | 800-char sliding-window chunks with 100-char overlap |
| **Vector Database** | ChromaDB (PersistentClient) | Cosine-similarity semantic search over 3 domain collections |
| **Embeddings** | Local ONNX mini-LM (default) / OpenAI `text-embedding-3-small` (optional) | Document & query vectorization |
| **Intent Router** | LLM zero-shot classifier | Routes queries to the correct ChromaDB collection or NL2SQL |
| **LLM Provider** | NVIDIA NIM (`meta/llama-3.1-8b-instruct`) via OpenAI-compatible API | Advisory answer generation |
| **Guardrails** | 4-layer custom security system | Input validation, authorization, PII masking, output sanitization |
| **Session Store** | JSON file-based persistence | Multi-turn conversation history per user per thread |
| **Scheduler** | Celery + Redis | Automated periodic data refresh (daily/weekly/monthly scrapes) |
| **API** | FastAPI | RESTful endpoint at `POST /api/chat/message` |

---

## 2. High-Level Data Flow

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        DATA INGESTION PIPELINE                          │
│                                                                         │
│  8 Financial URLs ──► Playwright Headless Browser ──► BeautifulSoup     │
│       │                      │                            │              │
│       │                      ▼                            ▼              │
│       │              Raw HTML Content            Clean Text Extraction   │
│       │                                                   │              │
│       │                                                   ▼              │
│       │                                     chunk_text() — 800/100      │
│       │                                         sliding window          │
│       │                                                   │              │
│       │                                                   ▼              │
│       │                                    store_in_chroma()            │
│       │                                         │                        │
│       ▼                                         ▼                        │
│  ┌─────────────────────────────────────────────────────┐                │
│  │              ChromaDB Persistent Store               │                │
│  │  ┌───────────────┬──────────────────┬──────────────┐ │                │
│  │  │ banking_data  │ investment_data  │financial_tips│ │                │
│  │  │               │                  │              │ │                │
│  │  │ FD/RD rates   │ Stocks, MF, Gold │ Budgeting    │ │                │
│  │  │ Savings accts │ SIP, ETF, NPS    │ Tax planning │ │                │
│  │  │ Loans, Cards  │ SGB, Portfolio   │ Insurance    │ │                │
│  │  └───────────────┴──────────────────┴──────────────┘ │                │
│  └─────────────────────────────────────────────────────┘                │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│                         QUERY-TIME PIPELINE                             │
│                                                                         │
│  User Message ──► Input Guardrails ──► Intent Classifier (LLM)         │
│                        │                       │                        │
│                   [Block if unsafe]            │                        │
│                                                ▼                        │
│                              ┌─────────────────────────────┐            │
│                              │   Intent Router              │            │
│                              │                              │            │
│                              │  banking ──► banking_data    │            │
│                              │  investing ──► investment_data│           │
│                              │  general_finance ──►          │           │
│                              │         financial_tips        │           │
│                              │  personal_data ──► NL2SQL    │            │
│                              └─────────┬───────────────────┘            │
│                                        │                                │
│              ┌─────────────────────────┼────────────────────┐           │
│              │  RAG Path               │ NL2SQL Path        │           │
│              ▼                         ▼                    │           │
│    ChromaDB.search()         Supabase transactions          │           │
│    (top-3 cosine)              + PII masking                │           │
│         │                         │                         │           │
│         ▼                         ▼                         │           │
│  Context Compilation       LLM Summarizer                   │           │
│  + User Profile                                             │           │
│         │                                                   │           │
│         ▼                                                   │           │
│  System Prompt Assembly                                     │           │
│  + History (last 6 turns)                                   │           │
│         │                                                   │           │
│         ▼                                                   │           │
│  LLM Chat Completion                                        │           │
│  (NVIDIA NIM / OpenAI)                                      │           │
│         │                                                   │           │
│         ▼                                                   │           │
│  Output Guardrails                                          │           │
│    ├─ Credential leak detection                             │           │
│    ├─ SQL sanitization                                      │           │
│    └─ PII masking                                           │           │
│         │                                                   │           │
│         ▼                                                   │           │
│  Session Persistence (sessions.json)                        │           │
│         │                                                   │           │
│         ▼                                                   │           │
│  ┌──────────────────────────────────┐                       │           │
│  │  ChatResponse                    │                       │           │
│  │  {answer, intent, sources,       │                       │           │
│  │   thread_id, user_id}            │                       │           │
│  └──────────────────────────────────┘                       │           │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Component Deep-Dive

### 3.1 Data Ingestion Layer — `scrapers.py`

**File**: `backend/app/utils/scrapers.py`

This is the **data acquisition engine** that populates ChromaDB with real-world financial data. It uses Playwright (headless Chromium) to render JavaScript-heavy financial websites and BeautifulSoup for HTML parsing.

#### 3.1.1 Data Sources (8 URLs across 6 categories)

| Category | Source Name | URL | Target Collection |
|----------|-----------|-----|-------------------|
| **Banking** | BankBazaar Savings | `bankbazaar.com/savings-account.html` | `banking_data` |
| **Banking** | BankBazaar FD | `bankbazaar.com/fixed-deposit-rate.html` | `banking_data` |
| **Banking** | BankBazaar RD | `bankbazaar.com/recurring-deposit.html` | `banking_data` |
| **Banking** | Groww FD | `groww.in/fixed-deposit` | `banking_data` |
| **Banking** | Groww RD | `groww.in/recurring-deposit` | `banking_data` |
| **Banking** | BankBazaar Credit Cards | `bankbazaar.com/credit-card.html` | `banking_data` |
| **Banking** | BankBazaar Personal Loan | `bankbazaar.com/personal-loan.html` | `banking_data` |
| **Stocks** | MoneyControl Top Gainers | `moneycontrol.com/.../nsegainer/` | `investment_data` |
| **Stocks** | MoneyControl Top Losers | `moneycontrol.com/.../nseloser/` | `investment_data` |
| **Stocks** | Screener All Stocks | `screener.in/screens/71064/all-stocks/` | `investment_data` |
| **Mutual Funds** | Groww Top MF | `groww.in/mutual-funds/top-mutual-funds` | `investment_data` |
| **Mutual Funds** | MC Large Cap | `moneycontrol.com/.../large-cap-fund.html` | `investment_data` |
| **Mutual Funds** | MC ELSS | `moneycontrol.com/.../tax-saving-fund.html` | `investment_data` |
| **Gold** | GoodReturns Gold | `goodreturns.in/gold-rates/` | `investment_data` |
| **Gold** | BankBazaar Gold | `bankbazaar.com/gold-rate-today.html` | `investment_data` |
| **Retirement** | BankBazaar PPF | `bankbazaar.com/ppf.html` | `financial_tips` |
| **Financial Tips** | ET Wealth | `economictimes.indiatimes.com/wealth` | `financial_tips` |
| **Financial Tips** | MC Personal Finance | `moneycontrol.com/.../personal-finance/` | `financial_tips` |

#### 3.1.2 Scraping Workflow (per URL)

```
URL Input
    │
    ▼
scrape_url_playwright(url, source_name)
    │
    ├── 1. Launch headless Chromium via Playwright
    │       ├── Custom User-Agent (Chrome 120)
    │       ├── Viewport: 1920×1080
    │       └── Timeout: 45 seconds
    │
    ├── 2. Navigate to URL (wait_until="domcontentloaded")
    │
    ├── 3. Wait 3 seconds for React/JS tables to render
    │       └── Critical for dynamic content (Groww, MoneyControl)
    │
    ├── 4. Extract full page HTML via page.content()
    │
    ├── 5. BeautifulSoup HTML cleaning:
    │       ├── Remove: <script>, <style>, <nav>, <footer>,
    │       │          <header>, <aside>, <iframe>
    │       ├── Attempt targeted extraction:
    │       │   <main> → <article> → .content/.article/.post/.table
    │       └── Fallback: full page get_text()
    │
    ├── 6. Whitespace normalization: collapse all \s+ into single space
    │
    └── Returns: clean text string
```

#### 3.1.3 Chunking Algorithm — `chunk_text()`

The chunker implements a **sliding window with overlap** strategy to preserve semantic coherence across chunk boundaries:

```python
def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list:
```

| Parameter | Value | Explanation |
|-----------|-------|-------------|
| `chunk_size` | 800 characters | ~160 words per chunk — fits within embedding model context |
| `overlap` | 100 characters | ~20 words of overlap to avoid splitting sentences mid-thought |
| `words_per_chunk` | `800 // 5 = 160` | Estimated words per chunk (avg 5 chars/word) |
| `words_overlap` | `100 // 5 = 20` | Overlapping words between consecutive chunks |
| Min chunk length | 50 characters | Chunks shorter than 50 chars are discarded as noise |

**Sliding window mechanics:**

```
Document: [w1 w2 w3 ... w160 w161 ... w300 w301 ...]

Chunk 1: [w1   ─────────────── w160]
Chunk 2:              [w141 ──────────────── w300]    ← 20-word overlap
Chunk 3:                           [w281 ────────── w440]
```

#### 3.1.4 Storage Pipeline — `store_in_chroma()`

Once text is chunked, each chunk is stored in ChromaDB as a document with full provenance metadata:

```
store_in_chroma(category, url, source_name, text)
    │
    ├── 1. Validation: skip if text < 100 chars
    │
    ├── 2. chunk_text(text, chunk_size=800, overlap=100)
    │
    ├── 3. Build document list:
    │       [{
    │           "id": "{source_name}_{uuid_hex[:8]}",
    │           "text": chunk_content,
    │           "metadata": {
    │               "category": "banking",
    │               "source": "BankBazaar FD",
    │               "url": "https://...",
    │               "scraped_at": "2026-06-01T02:00:00.000000"
    │           }
    │       }, ...]
    │
    ├── 4. Category → Collection routing:
    │       banking        → banking_data
    │       stocks         → investment_data
    │       mutual_funds   → investment_data
    │       gold           → investment_data
    │       retirement     → financial_tips
    │       financial_tips → financial_tips
    │
    ├── 5. CLEANUP: Delete existing chunks for this source
    │       collection.delete(where={"source": source_name})
    │       └── Prevents stale/duplicate data across re-scrapes
    │
    └── 6. chroma_db.add_documents(collection_name, documents)
            └── Upserts in batches of 100
```

**Source-specific cleanup** (step 5) is a critical design choice. Before inserting new chunks, the pipeline deletes all existing chunks from the **same source** using ChromaDB's metadata filter. This ensures:
- No stale data remains from previous scrape runs
- No duplicate chunks accumulate
- Each source's data is atomically replaced

---

### 3.2 Vector Store Layer — `chroma_store.py`

**File**: `backend/app/utils/chroma_store.py`

This module provides a **singleton `ChromaStore` wrapper** around ChromaDB's `PersistentClient`. It is the single source of truth for all vector operations in the system.

#### 3.2.1 Singleton Pattern

```python
# Module-level — executed once at import time
_embedding_function = _build_embedding_function()

chroma_db = ChromaStore(
    db_path=_CHROMA_DB_PATH,         # backend/chroma_db/
    embedding_function=_embedding_function,
)
```

The `chroma_db` singleton is imported by:
- `app.utils.chatbot_engine` → for `search()` during RAG retrieval
- `app.utils.scrapers` → for `add_documents()` during data ingestion

#### 3.2.2 Storage Location

```
backend/
  └── chroma_db/
      ├── chroma.sqlite3          ← SQLite metadata store (~3.5 MB)
      ├── 5ba341a4-.../           ← HNSW index shard (collection 1)
      ├── 5c8f25b8-.../           ← HNSW index shard (collection 2)
      └── 7b677dc7-.../           ← HNSW index shard (collection 3)
```

#### 3.2.3 Collections

Three domain-specific collections are pre-created at startup:

| Collection Name | Domain | Sources |
|----------------|--------|---------|
| `banking_data` | Bank rates, FD/RD, loans, credit cards | BankBazaar, Groww |
| `investment_data` | Equities, mutual funds, gold, NPS, SGB | MoneyControl, Groww, Screener, GoodReturns |
| `financial_tips` | Budgeting, tax, insurance, retirement | ET Wealth, MoneyControl, BankBazaar PPF |

Each collection is configured with `metadata={"hnsw:space": "cosine"}` — meaning the HNSW index uses **cosine distance** for similarity computation.

#### 3.2.4 Initialization Sequence

```
ChromaStore.__init__(db_path, embedding_function)
    │
    ├── 1. os.makedirs(db_path, exist_ok=True)
    │
    ├── 2. chromadb.PersistentClient(
    │       path=db_path,
    │       settings=Settings(
    │           anonymized_telemetry=False,
    │           allow_reset=True,
    │       )
    │   )
    │
    └── 3. Pre-warm all 3 known collections:
            for name in ["banking_data", "investment_data", "financial_tips"]:
                _get_or_create_collection(name)
                    │
                    └── client.get_or_create_collection(
                            name=name,
                            embedding_function=ef,
                            metadata={"hnsw:space": "cosine"}
                        )
```

#### 3.2.5 Search API — `search()`

```python
def search(collection_name, query, n_results=3) -> list[dict]
```

**Step-by-step execution:**

```
search("banking_data", "best FD rates in India", n_results=3)
    │
    ├── 1. Validate: reject empty/whitespace-only queries
    │
    ├── 2. Get collection handle (from cache or create)
    │
    ├── 3. Check collection count
    │       └── If count == 0: return [] (log: "run scrapers.py to seed")
    │
    ├── 4. Cap n_results: safe_n = min(n_results, count)
    │       └── Prevents ChromaDB error when requesting more results than exist
    │
    ├── 5. collection.query(
    │       query_texts=["best FD rates in India"],
    │       n_results=3,
    │       include=["documents", "metadatas", "distances"]
    │   )
    │   ┌─────────────────────────────────────────────────┐
    │   │ INTERNAL: ChromaDB query execution              │
    │   │  a. Embed the query text using the same EF      │
    │   │  b. HNSW approximate nearest neighbor search    │
    │   │  c. Rank by cosine distance (lower = closer)    │
    │   │  d. Return top-N results with metadata          │
    │   └─────────────────────────────────────────────────┘
    │
    ├── 6. Unpack nested response structure:
    │       ids       = results["ids"][0]        # [str, str, str]
    │       documents = results["documents"][0]  # [str, str, str]
    │       metadatas = results["metadatas"][0]  # [dict, dict, dict]
    │       distances = results["distances"][0]  # [float, float, float]
    │
    └── 7. Return normalized output:
            [
                {
                    "id": "BankBazaar_FD_a1b2c3d4",
                    "text": "SBI FD rates: 7.25% for 1-year...",
                    "metadata": {
                        "category": "banking",
                        "source": "BankBazaar FD",
                        "url": "https://...",
                        "scraped_at": "2026-06-01T02:00:00"
                    },
                    "distance": 0.142857
                },
                ...
            ]
```

#### 3.2.6 Upsert API — `add_documents()`

```python
def add_documents(collection_name, documents) -> None
```

| Feature | Detail |
|---------|--------|
| **Idempotency** | Uses `upsert` (not `add`) — safe to run multiple times |
| **Batching** | Documents are processed in batches of 100 |
| **Validation** | Documents with missing `id` or empty `text` are skipped with a warning |
| **Schema** | Each document: `{"id": str, "text": str, "metadata": dict}` |

#### 3.2.7 Additional APIs

| Method | Signature | Purpose |
|--------|-----------|---------|
| `delete_collection(name)` | `-> None` | Permanently delete a collection and all vectors |
| `collection_exists(name)` | `-> bool` | Check if a collection has been created |
| `get_collection_count(name)` | `-> int` | Count documents in a collection (0 if absent) |
| `list_collections()` | `-> list[str]` | Return names of all collections |
| `reset_all()` | `-> None` | ⚠️ **DESTRUCTIVE**: Wipe all collections and vectors |

---

### 3.3 Intent Classification — `chatbot_engine.py :: classify_intent()`

**File**: `backend/app/utils/chatbot_engine.py` (lines 149–197)

Before any retrieval happens, the user's message must be routed to the correct knowledge domain. This is done via **zero-shot LLM classification**.

#### 3.3.1 How It Works

```
User Message: "What are the best FD rates right now?"
    │
    ▼
classify_intent(user_message)
    │
    ├── 1. Build system prompt:
    │       "You are an intent classification engine...
    │        Classify into EXACTLY ONE of:
    │          banking | investing | general_finance | personal_data
    │        Reply with ONLY that single word."
    │
    ├── 2. LLM call:
    │       model     = meta/llama-3.1-8b-instruct (via NVIDIA NIM)
    │       messages  = [system_prompt, user_message]
    │       max_tokens = 10
    │       temperature = 0.0   ← deterministic, no sampling randomness
    │
    ├── 3. Parse response:
    │       raw = "banking"
    │       intent = raw.split()[0].rstrip(".,;:")  ← sanitize punctuation
    │
    ├── 4. Validate against VALID_INTENTS:
    │       {"banking", "investing", "general_finance", "personal_data"}
    │
    └── 5. Return intent string
            └── Fallback: "general_finance" if unparseable or on error
```

#### 3.3.2 Intent Categories & What They Trigger

| Intent | Description | Collection | Handler |
|--------|------------|------------|---------|
| `banking` | Bank accounts, FDs, RDs, savings, loans, credit cards | `banking_data` | `execute_rag()` |
| `investing` | Stocks, MFs, SIPs, ETFs, bonds, portfolio, market data | `investment_data` | `execute_rag()` |
| `general_finance` | Budgeting, tax planning, insurance, retirement, literacy | `financial_tips` | `execute_rag()` |
| `personal_data` | User's own transactions, spending, balances, income | *(none — uses Supabase)* | `execute_nl2sql()` |

#### 3.3.3 Intent → Collection Mapping

Defined as a constant dictionary in `chatbot_engine.py`:

```python
INTENT_COLLECTION_MAP = {
    "banking":          "banking_data",
    "investing":        "investment_data",
    "general_finance":  "financial_tips",
}
```

If the intent is `personal_data`, the pipeline bypasses ChromaDB entirely and routes to the NL2SQL engine.

---

### 3.4 RAG Executor — `chatbot_engine.py :: execute_rag()`

**File**: `backend/app/utils/chatbot_engine.py` (lines 202–318)

This is the **heart of the RAG pipeline** — it combines retrieved context with user profile data to generate personalised financial advisory answers.

#### 3.4.1 Function Signature

```python
def execute_rag(
    user_message: str,     # The user's natural language query
    intent: str,           # Classified intent (banking/investing/general_finance)
    history: list[dict],   # Conversation history for this thread
    profile: dict,         # User profile (income, segment, risk, city, etc.)
) -> dict:                 # Returns {"answer": str, "sources": list[str]}
```

#### 3.4.2 Step-by-Step Execution

```
execute_rag("What are the best FD rates?", "banking", history=[], profile={...})
    │
    │ ╔══════════════════════════════════════════════════════════╗
    │ ║  STEP 1: MAP INTENT → COLLECTION                       ║
    │ ╚══════════════════════════════════════════════════════════╝
    │
    ├── collection_name = INTENT_COLLECTION_MAP.get("banking", "financial_tips")
    │                    = "banking_data"
    │
    │ ╔══════════════════════════════════════════════════════════╗
    │ ║  STEP 2: RETRIEVE CONTEXT FROM CHROMADB                ║
    │ ╚══════════════════════════════════════════════════════════╝
    │
    ├── results = chroma_db.search(
    │       collection_name = "banking_data",
    │       query           = "What are the best FD rates?",
    │       n_results       = 3,
    │   )
    │   │
    │   └── Returns list of dicts:
    │       [
    │           {"text": "SBI FD: 7.25% for 1yr...", "metadata": {"source": "BankBazaar FD"}, ...},
    │           {"text": "HDFC FD: 7.10% for 1yr...", "metadata": {"source": "Groww FD"}, ...},
    │           {"text": "Post Office TD: 7.50%...", "metadata": {"source": "BankBazaar FD"}, ...},
    │       ]
    │
    │ ╔══════════════════════════════════════════════════════════╗
    │ ║  STEP 3: COMPILE CONTEXT BLOCKS                        ║
    │ ╚══════════════════════════════════════════════════════════╝
    │
    ├── For each retrieved doc (top 3):
    │       a. Extract text: doc["text"] or doc["document"] or str(doc)
    │       b. Build context_blocks list
    │       c. Extract source references from metadata:
    │          meta.get("source") → "BankBazaar FD"
    │          or meta.get("title") → fallback
    │          or "FinAssist Knowledge Base" → default
    │
    ├── Compile context_text:
    │       "SBI FD: 7.25% for 1yr..."
    │       ---
    │       "HDFC FD: 7.10% for 1yr..."
    │       ---
    │       "Post Office TD: 7.50%..."
    │
    │   If NO context found:
    │       context_text = "No specific data found. Provide general best-practice advice."
    │
    │ ╔══════════════════════════════════════════════════════════╗
    │ ║  STEP 4: BUILD PERSONALISED SYSTEM PROMPT              ║
    │ ╚══════════════════════════════════════════════════════════╝
    │
    ├── Extract user profile fields:
    │       income       = profile.get("income", "unknown")
    │       segment      = profile.get("segment", "General")
    │       city         = profile.get("city", "India")
    │       annual_income = profile.get("annual_income", income)
    │       risk_profile = profile.get("risk_profile", "Moderate")
    │       credit_score = profile.get("credit_score", "N/A")
    │
    ├── Format income safely:
    │       If numeric → "₹660,000 per annum"
    │       Else → str(annual_income)
    │
    ├── Assemble system prompt:
    │   ┌─────────────────────────────────────────────────────────┐
    │   │ "You are FinAssist, an expert AI financial advisor     │
    │   │  serving Indian retail banking customers.               │
    │   │                                                         │
    │   │  Today's Date: 01 June 2026                            │
    │   │                                                         │
    │   │  User Profile:                                          │
    │   │    - Annual Income: ₹660,000 per annum                 │
    │   │    - Customer Segment: High Income Low Spender         │
    │   │    - City Tier: Tier 1                                  │
    │   │    - Risk Profile: Moderate                             │
    │   │    - CIBIL Score: 780                                   │
    │   │                                                         │
    │   │  Relevant Knowledge Base Context:                       │
    │   │    [... retrieved chunks inserted here ...]              │
    │   │                                                         │
    │   │  Instructions:                                          │
    │   │    - Provide precise, personalised, actionable advice  │
    │   │    - Tailor to income, risk profile, and segment       │
    │   │    - Cite product names and institutions               │
    │   │    - Format money in Indian Rupees (₹)                 │
    │   │    - Use bold, headings, bullet points, emojis         │
    │   │    - Keep under 350 words                               │
    │   │    - Acknowledge data gaps if context insufficient     │
    │   └─────────────────────────────────────────────────────────┘
    │
    │ ╔══════════════════════════════════════════════════════════╗
    │ ║  STEP 5: BUILD LLM MESSAGE LIST                        ║
    │ ╚══════════════════════════════════════════════════════════╝
    │
    ├── recent_history = history[-6:]    ← last 6 messages for context efficiency
    │       Filter: only "user"/"assistant" roles with non-empty content
    │
    ├── messages = [
    │       {"role": "system", "content": system_prompt},
    │       ...recent_history...,
    │       {"role": "user", "content": "What are the best FD rates?"},
    │   ]
    │
    │ ╔══════════════════════════════════════════════════════════╗
    │ ║  STEP 6: GENERATE LLM RESPONSE                        ║
    │ ╚══════════════════════════════════════════════════════════╝
    │
    ├── client = openai.OpenAI(
    │       api_key  = NVIDIA_API_KEY,
    │       base_url = "https://integrate.api.nvidia.com/v1",
    │   )
    │
    ├── completion = client.chat.completions.create(
    │       model       = "meta/llama-3.1-8b-instruct",
    │       messages    = messages,
    │       max_tokens  = 512,
    │       temperature = 0.4,    ← slightly creative but mostly factual
    │   )
    │
    ├── answer = completion.choices[0].message.content.strip()
    │
    │   On error → fallback message:
    │       "I'm sorry, I encountered a temporary issue..."
    │
    └── Return:
            {
                "answer": "## 🏦 Best FD Rates for You...",
                "sources": ["BankBazaar FD", "Groww FD", "BankBazaar FD"]
            }
```

---

### 3.5 NL2SQL Branch — `nl2sql.py`

**File**: `backend/app/utils/nl2sql.py`

When the intent is `personal_data`, the pipeline **bypasses ChromaDB entirely** and instead queries the user's own transactional data from Supabase.

#### 3.5.1 Workflow

```
execute_nl2sql(user_id, user_question)
    │
    ├── 1. Fetch from Supabase:
    │       supabase.table('transactions')
    │           .select('*')
    │           .eq('user_id', user_id)       ← strict user isolation
    │           .order('transaction_date', desc=True)
    │           .limit(100)                    ← last 100 transactions
    │           .execute()
    │
    ├── 2. Guardrails Layer 3 — PII Masking:
    │       Guardrails.mask_context_data(transactions_data, user_id)
    │           ├── Filter: only rows where row.user_id == user_id
    │           └── PIIMasker.mask_transaction_data(rows)
    │               ├── Mask phone numbers: ******1234
    │               ├── Mask account numbers: ****5678
    │               ├── Mask credit cards: XXXX-XXXX-XXXX-1234
    │               ├── Mask emails: ya***@gmail.com
    │               ├── Delete: bank_txn_ref, ifsc_code, ref_num
    │               └── Mask descriptions for PAN, Aadhaar, UPI
    │
    ├── 3. Serialize to JSON
    │
    ├── 4. LLM summarization:
    │       model       = settings.active_chat_model
    │       temperature = 0.3     ← low creativity for data analysis
    │       max_tokens  = 700
    │       system      = "You are a highly analytical financial advisor AI...
    │                      Answer ONLY based on this transaction data...
    │                      Format beautifully with bold, tables, emojis..."
    │       user        = "User Question: {question}\n\nTransaction Data: {json}"
    │
    └── Return: LLM-generated analytical summary string
```

---

### 3.6 Session Management — `chatbot_engine.py :: SessionManager`

**File**: `backend/app/utils/chatbot_engine.py` (lines 57–144)

The `SessionManager` provides **thread-safe, file-based conversation persistence** enabling multi-turn conversations.

#### 3.6.1 Storage Schema

```json
// backend/sessions.json
{
  "<user_id>": {
    "<thread_id>": [
      {"role": "user", "content": "What are FD rates?", "ts": "2026-06-01T05:30:00"},
      {"role": "assistant", "content": "## 🏦 Best FD Rates...", "ts": "2026-06-01T05:30:00"},
      {"role": "user", "content": "Compare SBI vs HDFC", "ts": "2026-06-01T05:31:00"},
      {"role": "assistant", "content": "## SBI vs HDFC FD...", "ts": "2026-06-01T05:31:00"}
    ]
  }
}
```

#### 3.6.2 API

| Method | Purpose |
|--------|---------|
| `get_state(user_id, thread_id)` | Load conversation history for a specific thread |
| `update_state(user_id, thread_id, messages)` | Persist full message list for a thread |
| `append_turn(user_id, thread_id, user_msg, assistant_msg)` | Convenience: append a user+assistant turn pair and persist |

#### 3.6.3 How History Feeds into RAG

In `execute_rag()`, the **last 6 messages** from history are included in the LLM prompt to provide conversational context:

```python
recent_history = [
    {"role": msg["role"], "content": msg["content"]}
    for msg in history[-6:]
    if msg.get("role") in {"user", "assistant"} and msg.get("content")
]
```

This gives the LLM awareness of previous turns without exceeding context limits.

---

### 3.7 Security Guardrails Layer

**Directory**: `backend/app/guardrails/`

The guardrails system implements a **4-layer security architecture** that wraps the entire RAG pipeline:

```
┌──────────────────────────────────────────────────────────────────────┐
│                    GUARDRAILS ARCHITECTURE                           │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ LAYER 1: INPUT GUARDRAILS (input_guard.py)                    │  │
│  │   Runs BEFORE intent classification                            │  │
│  │   ├── Prompt injection detection (17 regex patterns)          │  │
│  │   ├── Suspicious phrase detection (7 patterns)                │  │
│  │   ├── Profanity filter (18 words)                             │  │
│  │   ├── Excessive length check (max 2000 chars)                 │  │
│  │   └── Special character flood detection (>50% threshold)      │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                            │                                         │
│                            ▼                                         │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ LAYER 2: AUTHORIZATION (authorization.py)                     │  │
│  │   Validates SQL query context for NL2SQL branch               │  │
│  │   ├── Ensures user_id filter matches authenticated user       │  │
│  │   └── Blocks multi-user operators (IN, <>, !=)                │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                            │                                         │
│                            ▼                                         │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ LAYER 3: DATA RETRIEVAL / CONTEXT MASKING (pii_masking.py)    │  │
│  │   Applied to transaction data BEFORE it reaches the LLM       │  │
│  │   ├── Row-level filtering: only user_id-matching rows         │  │
│  │   ├── Indian PII masking:                                     │  │
│  │   │     Phone: 9876543210 → ******3210                        │  │
│  │   │     PAN: ABCDE1234F → ***MASKED***                        │  │
│  │   │     Aadhaar: 1234 5678 9012 → ***MASKED***                │  │
│  │   │     Account: 12345678901234 → ****1234                    │  │
│  │   │     Credit Card: 4111-1111-1111-1234 → XXXX-XXXX-XXXX-1234│ │
│  │   │     Email: yash@gmail.com → ya***@gmail.com               │  │
│  │   │     UPI: yash@upi → ya***@upi                             │  │
│  │   ├── IFSC code detection                                      │  │
│  │   └── Sensitive field deletion: bank_txn_ref, ifsc_code,      │  │
│  │       ref_num                                                  │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                            │                                         │
│                            ▼                                         │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ LAYER 4: OUTPUT GUARDRAILS (output_guard.py)                  │  │
│  │   Runs AFTER LLM response generation                          │  │
│  │   ├── Credential leak detection:                              │  │
│  │   │     API keys, passwords, connection strings, JWTs,        │  │
│  │   │     private keys                                           │  │
│  │   ├── SQL code sanitization in response text                  │  │
│  │   └── Residual PII masking (final sweep via PIIMasker)        │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ SECURITY EVENT LOGGING (security_logger.py)                   │  │
│  │   Records all blocked/flagged events to:                      │  │
│  │   ├── Python logger (console/files)                           │  │
│  │   └── backend/security_events.json (last 1000 events)         │  │
│  └────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

#### 3.7.1 Guardrails Unified Interface

**File**: `backend/app/guardrails/guardrails.py`

The `Guardrails` class provides a clean static interface used by the chatbot engine:

```python
# Layer 1 — Input validation (called in process_chat_message)
is_safe, error_message = Guardrails.validate_input(message, user_id)

# Layer 2 — SQL authorization (called in NL2SQL context)
is_valid = Guardrails.validate_sql_query(sql_query, user_id)

# Layer 3 — Context data PII masking (called in nl2sql.py)
masked_data = Guardrails.mask_context_data(transactions, user_id)

# Layer 4 — Output validation (called in process_chat_message)
is_safe, cleaned_answer = Guardrails.validate_output(answer, user_id)
```

---

### 3.8 API Layer — `routes/chatbot.py`

**File**: `backend/app/routes/chatbot.py`

The FastAPI router exposes a single endpoint that serves as the entry point for the entire RAG system.

#### 3.8.1 Endpoint

```
POST /api/chat/message
```

#### 3.8.2 Request Schema — `ChatRequest`

```json
{
    "user_id":   "550e8400-e29b-41d4-a716-446655440000",   // 1–128 chars, required
    "message":   "What are the best FD rates available?",    // 1–4096 chars, required
    "thread_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"    // 1–128 chars, required
}
```

#### 3.8.3 Response Schema — `ChatResponse`

```json
{
    "answer":    "## 🏦 Best FD Rates for You\n\n...",
    "intent":    "banking",
    "sources":   ["BankBazaar FD", "Groww FD"],
    "thread_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "user_id":   "550e8400-e29b-41d4-a716-446655440000"
}
```

#### 3.8.4 User Profile Loading

Currently, a **mock user profile** is returned by `_get_default_user_profile()`:

```python
{
    "income": 55000,                          # Monthly INR
    "annual_income": 660000,
    "segment": "High Income Low Spender",
    "city": "Tier 1",
    "age": 32,
    "risk_profile": "Moderate",
    "primary_bank": "HDFC Bank",
    "existing_investments": ["Mutual Funds (SIP ₹10,000/mo)", "PPF", "EPF"],
    "outstanding_loans": [],
    "credit_score": 780,
    "preferred_language": "English",
}
```

> **Production note**: This should be replaced with a Supabase lookup by `user_id`.

#### 3.8.5 Error Handling

| HTTP Status | Condition | Detail |
|-------------|-----------|--------|
| `200` | Success | Full `ChatResponse` payload |
| `422` | `ValueError` from engine | Invalid input feedback |
| `503` | `ConnectionError` | Downstream service (OpenAI/ChromaDB) unavailable |
| `500` | Unhandled exception | Generic error; exception logged with full traceback |

---

### 3.9 Scheduled Data Refresh — `tasks/scheduler.py`

**File**: `backend/tasks/scheduler.py`

The system uses **Celery with Redis** as the message broker to automate periodic scraping. This ensures the ChromaDB knowledge base stays fresh with current financial data.

#### 3.9.1 Schedule

| Task | Frequency | Time | Categories Scraped |
|------|-----------|------|-------------------|
| `scheduled_weekly_scrape` | Every Sunday | 2:00 AM | `banking` |
| `scheduled_daily_morning_scrape` | Mon–Fri | 9:15 AM | `stocks` |
| `scheduled_daily_evening_scrape` | Daily | 6:00 PM | `mutual_funds`, `gold`, `financial_tips` |
| `scheduled_monthly_scrape` | 1st of month | 3:00 AM | `retirement` |

#### 3.9.2 Rationale for Schedule Design

- **Stocks at 9:15 AM**: Indian stock markets open at 9:15 AM IST — scrape captures opening data
- **MF + Gold at 6:00 PM**: NAVs and gold prices are finalized by EOD
- **Banking weekly**: Bank rates change infrequently (weekly is sufficient)
- **Retirement monthly**: PPF/NPS rates change quarterly at most

---

## 4. Step-by-Step Request Lifecycle

A complete trace of what happens when a user sends: **"What are the best FD rates right now?"**

```
┌──────────────────────────────────────────────────────────────────┐
│  STEP 1: HTTP Request Received                                   │
│  POST /api/chat/message                                          │
│  Body: {user_id, message, thread_id}                            │
│  Handler: routes/chatbot.py :: post_chat_message()               │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 2: Load User Profile                                       │
│  _get_default_user_profile() → mock profile dict                │
│  (Production: Supabase fetch by user_id)                        │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 3: Enter Core Engine                                       │
│  chatbot_engine.py :: process_chat_message()                     │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 4: INPUT GUARDRAILS (Layer 1)                              │
│  Guardrails.validate_input(message, user_id)                    │
│  ├── Prompt injection check     → PASS                          │
│  ├── Length check (≤2000)       → PASS                          │
│  ├── Special char flood check   → PASS                          │
│  └── Profanity check            → PASS                          │
│                                                                  │
│  If FAIL → return error response, log to security_events.json   │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 5: Load Conversation History                               │
│  session_manager.get_state(user_id, thread_id)                  │
│  → Load from sessions.json                                       │
│  → Returns: [] (new thread) or [prev messages]                   │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 6: Intent Classification                                   │
│  classify_intent("What are the best FD rates right now?")       │
│  → LLM call (max_tokens=10, temp=0.0)                           │
│  → Returns: "banking"                                            │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 7: Route by Intent                                         │
│  intent == "banking" → RAG path (not personal_data)             │
│  → Call execute_rag(message, "banking", history, profile)       │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 8: ChromaDB Retrieval                                      │
│  chroma_db.search("banking_data", query, n_results=3)           │
│  ├── Embed query via ONNX mini-LM (or OpenAI)                  │
│  ├── HNSW cosine nearest-neighbor search                        │
│  └── Return top-3 document chunks with metadata & distances     │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 9: Context Compilation                                     │
│  ├── Extract text from each result                              │
│  ├── Join with "---" separator                                  │
│  └── Extract source references from metadata                    │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 10: System Prompt Assembly                                 │
│  ├── Inject user profile (income, segment, risk, CIBIL)        │
│  ├── Inject retrieved context blocks                            │
│  ├── Inject formatting instructions                              │
│  └── Build message list: [system, history[-6:], user_message]   │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 11: LLM Generation                                        │
│  NVIDIA NIM API (OpenAI-compatible)                              │
│  Model: meta/llama-3.1-8b-instruct                              │
│  max_tokens=512, temperature=0.4                                │
│  → Returns: Formatted advisory answer with emojis & headings   │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 12: OUTPUT GUARDRAILS (Layer 4)                            │
│  Guardrails.validate_output(answer, user_id)                    │
│  ├── Scan for API keys, passwords, JWTs, private keys           │
│  ├── Sanitize any raw SQL in output                             │
│  └── Final PII masking sweep                                    │
│                                                                  │
│  If credentials detected → block & return safe fallback          │
│  If SQL detected → replace with "[System Query Removed]"        │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 13: Session Persistence                                    │
│  session_manager.append_turn(user_id, thread_id, msg, answer)   │
│  → Append both user + assistant messages to sessions.json       │
│  → Each message tagged with ISO8601 timestamp                   │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│  STEP 14: Return Response                                        │
│  ChatResponse {                                                  │
│      answer:    "## 🏦 Best FD Rates For Your Profile...",      │
│      intent:    "banking",                                       │
│      sources:   ["BankBazaar FD", "Groww FD"],                  │
│      thread_id: "a1b2c3d4-...",                                 │
│      user_id:   "550e8400-..."                                  │
│  }                                                               │
└──────────────────────────────────────────────────────────────────┘
```

---

## 5. ChromaDB Collection Schema

### Document Structure (as stored)

Each document in ChromaDB has the following structure:

```
┌─────────────────────────────────────────────────────────┐
│  ChromaDB Document                                       │
├─────────────────────────────────────────────────────────┤
│  id         │ "BankBazaar_FD_a1b2c3d4"                  │
│  document   │ "SBI offers 7.25% on 1-year FDs. The      │
│             │  minimum deposit is ₹10,000. Senior        │
│             │  citizens get an additional 0.50%..."       │
│  metadata   │ {                                          │
│             │     "category":   "banking",               │
│             │     "source":     "BankBazaar FD",         │
│             │     "url":        "https://bankbazaar..",  │
│             │     "scraped_at": "2026-06-01T02:00:00"    │
│             │ }                                          │
│  embedding  │ [0.023, -0.145, 0.089, ...]  (384-dim)    │
│             │ (auto-generated by embedding function)     │
└─────────────────────────────────────────────────────────┘
```

### Collection Metrics

| Metric | Value |
|--------|-------|
| Distance metric | Cosine |
| Index type | HNSW (Hierarchical Navigable Small World) |
| Storage format | SQLite + UUID-named shards |
| Storage path | `backend/chroma_db/` |
| Total DB size | ~3.5 MB (chroma.sqlite3) |

---

## 6. Embedding Strategy

The system supports two embedding backends with automatic fallback:

### Priority Resolution

```
_build_embedding_function()
    │
    ├── Check: CHROMA_USE_OPENAI_EMBED == "true"?
    │       │
    │       ├── YES + OPENAI_API_KEY available:
    │       │       → OpenAI text-embedding-3-small
    │       │         ├── 1536-dimensional vectors
    │       │         ├── Requires funded API key
    │       │         ├── Best semantic quality
    │       │         └── Internet required
    │       │
    │       └── NO or API key missing/failed:
    │               ↓ (fallback)
    │
    └── Default: ChromaDB DefaultEmbeddingFunction
                  ├── Local ONNX mini-LM model
                  ├── 384-dimensional vectors
                  ├── No API key needed
                  ├── Fully offline capable
                  └── Good-enough quality for most use cases
```

### Critical Consistency Rule

> **⚠️ The embedding function chosen at collection creation time MUST be consistent for all subsequent searches on that collection.**
> Switching embedding functions after data has been indexed will produce meaningless search results because the query vector dimensions won't match the stored document vectors.

The module pins the chosen function at startup as a module-level singleton, ensuring consistency for the entire process lifetime.

---

## 7. Configuration & Environment Variables

**File**: `backend/app/core/config.py`

| Variable | Default | Used By |
|----------|---------|---------|
| `NVIDIA_API_KEY` | *(required)* | LLM calls (intent classification + RAG generation) |
| `NVIDIA_CHAT_MODEL` | `meta/llama-3.1-8b-instruct` | Chat model for completions |
| `NVIDIA_BASE_URL` | `https://integrate.api.nvidia.com/v1` | NVIDIA NIM API endpoint |
| `SUPABASE_URL` | *(required for NL2SQL)* | Supabase project URL |
| `SUPABASE_KEY` | *(required for NL2SQL)* | Supabase anon/service key |
| `OPENAI_API_KEY` | *(optional)* | Only if using OpenAI embeddings |
| `CHROMA_USE_OPENAI_EMBED` | `false` | Toggle OpenAI embeddings |
| `CHROMA_DB_PATH` | `backend/chroma_db` | ChromaDB storage directory |
| `SESSIONS_FILE` | `backend/sessions.json` | Session persistence file |

The `Settings` class exposes computed properties that abstract the LLM provider:

```python
settings.active_api_key    → NVIDIA_API_KEY
settings.active_chat_model → NVIDIA_CHAT_MODEL
settings.active_base_url   → NVIDIA_BASE_URL
```

---

## 8. File Reference Map

| File | Role in RAG Pipeline |
|------|---------------------|
| `backend/app/routes/chatbot.py` | API entry point — receives HTTP requests, returns responses |
| `backend/app/utils/chatbot_engine.py` | Core orchestrator — intent classification, RAG execution, session management |
| `backend/app/utils/chroma_store.py` | ChromaDB wrapper — singleton client, search, upsert, collection management |
| `backend/app/utils/scrapers.py` | Data ingestion — Playwright scraping, chunking, ChromaDB storage |
| `backend/app/utils/nl2sql.py` | Personal data branch — Supabase query + LLM summarization |
| `backend/app/utils/supabase_client.py` | Supabase client initializer |
| `backend/app/utils/security_logger.py` | Security event persistence to JSON file |
| `backend/app/core/config.py` | Centralized settings — all env vars and LLM provider config |
| `backend/app/guardrails/__init__.py` | Guardrails module entry — exports `Guardrails` class |
| `backend/app/guardrails/guardrails.py` | Unified 4-layer guardrails facade |
| `backend/app/guardrails/input_guard.py` | Layer 1 — input validation (injection, length, profanity) |
| `backend/app/guardrails/authorization.py` | Layer 2 — SQL authorization (user_id enforcement) |
| `backend/app/guardrails/pii_masking.py` | Layer 3 — Indian PII masking (phone, PAN, Aadhaar, etc.) |
| `backend/app/guardrails/output_guard.py` | Layer 4 — output sanitization (credential leaks, SQL removal) |
| `backend/tasks/scheduler.py` | Celery periodic task scheduler for automated scraping |
| `backend/dump_chroma.py` | Debug utility — dump all ChromaDB collections to console |
| `backend/sessions.json` | Persistent conversation state (per user, per thread) |
| `backend/chroma_db/` | ChromaDB persistent storage directory |

---

## 9. Utility Scripts

### `dump_chroma.py` — ChromaDB Inspector

**File**: `backend/dump_chroma.py`

A diagnostic utility that dumps all documents from all three ChromaDB collections to the console. Useful for verifying that scraping and indexing worked correctly.

**Usage:**
```bash
cd backend
python dump_chroma.py
```

**Output format:**
```
======================================================================
COLLECTION: BANKING_DATA  (47 documents)
======================================================================
  [1] Title   : N/A
       Source  : BankBazaar FD
       Ingested: N/A
       Preview : SBI FD rates: General customers can earn up to 7.25% interest...

  [2] Title   : N/A
       Source  : Groww FD
       ...
```

### Manual Scraper Execution

```bash
cd backend
python -m app.utils.scrapers
```

This runs `scrape_all()` which iterates through all 6 categories and all 18 URLs, scraping and indexing everything into ChromaDB.

---

## 10. Sequence Diagram — Full Chat Turn

```
Frontend          API Router          Engine              Guardrails         ChromaDB         LLM (NVIDIA)
   │                  │                  │                    │                  │                 │
   │  POST /message   │                  │                    │                  │                 │
   │ ────────────────►│                  │                    │                  │                 │
   │                  │  load profile    │                    │                  │                 │
   │                  │ ────────────────►│                    │                  │                 │
   │                  │                  │                    │                  │                 │
   │                  │                  │  validate_input()  │                  │                 │
   │                  │                  │ ──────────────────►│                  │                 │
   │                  │                  │    (is_safe, "")   │                  │                 │
   │                  │                  │ ◄──────────────────│                  │                 │
   │                  │                  │                    │                  │                 │
   │                  │                  │  load history      │                  │                 │
   │                  │                  │  (sessions.json)   │                  │                 │
   │                  │                  │                    │                  │                 │
   │                  │                  │  classify_intent() │                  │                 │
   │                  │                  │ ─────────────────────────────────────────────────────► │
   │                  │                  │                    │                  │    "banking"    │
   │                  │                  │ ◄───────────────────────────────────────────────────── │
   │                  │                  │                    │                  │                 │
   │                  │                  │  search("banking_data", query, 3)    │                 │
   │                  │                  │ ────────────────────────────────────►│                 │
   │                  │                  │                    │    [top-3 docs]  │                 │
   │                  │                  │ ◄────────────────────────────────────│                 │
   │                  │                  │                    │                  │                 │
   │                  │                  │  build system prompt                 │                 │
   │                  │                  │  (profile + context + history)       │                 │
   │                  │                  │                    │                  │                 │
   │                  │                  │  chat.completions.create()           │                 │
   │                  │                  │ ─────────────────────────────────────────────────────► │
   │                  │                  │                    │                  │   answer text   │
   │                  │                  │ ◄───────────────────────────────────────────────────── │
   │                  │                  │                    │                  │                 │
   │                  │                  │  validate_output() │                  │                 │
   │                  │                  │ ──────────────────►│                  │                 │
   │                  │                  │  (True, cleaned)   │                  │                 │
   │                  │                  │ ◄──────────────────│                  │                 │
   │                  │                  │                    │                  │                 │
   │                  │                  │  persist turn      │                  │                 │
   │                  │                  │  (sessions.json)   │                  │                 │
   │                  │                  │                    │                  │                 │
   │                  │  ChatResponse    │                    │                  │                 │
   │                  │ ◄────────────────│                    │                  │                 │
   │   JSON response  │                  │                    │                  │                 │
   │ ◄────────────────│                  │                    │                  │                 │
   │                  │                  │                    │                  │                 │
```

---

## LLM Parameters Summary

| Call Site | Model | max_tokens | temperature | Purpose |
|-----------|-------|-----------|-------------|---------|
| `classify_intent()` | `meta/llama-3.1-8b-instruct` | 10 | 0.0 | Deterministic single-word intent classification |
| `execute_rag()` | `meta/llama-3.1-8b-instruct` | 512 | 0.4 | Advisory answer generation (slightly creative) |
| `execute_nl2sql()` | `meta/llama-3.1-8b-instruct` | 700 | 0.3 | Transaction data analysis (mostly factual) |

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **3 collections (not 1)** | Domain separation improves retrieval precision — banking queries don't pollute investment results |
| **Cosine distance** | Standard for text similarity; normalized, direction-based comparison works well with embeddings |
| **Top-3 retrieval** | Balances context quality (more = more noise) vs. coverage (fewer = might miss relevant info) |
| **800-char chunks with 100-char overlap** | Fits within embedding model context; overlap prevents losing information at chunk boundaries |
| **Last 6 messages in history** | Enough for multi-turn coherence without exceeding LLM context window |
| **Source-level cleanup before re-index** | Atomic replacement prevents stale data accumulation across scrape cycles |
| **Local ONNX as default embedding** | Zero-cost, offline-capable; production can opt into OpenAI for better quality |
| **NVIDIA NIM over direct OpenAI** | Cost-effective; Llama 3.1 8B via NVIDIA's inference API is free-tier eligible |
| **Batch upsert (100/batch)** | Prevents ChromaDB payload size limits on large scrapes |
| **Temperature 0.0 for intent, 0.4 for RAG** | Intent must be deterministic; advisory benefits from slight creativity |

---

*Last updated: 01 June 2026*
