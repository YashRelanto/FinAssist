# FinAssist AI — Finance Advisor: Architecture & Technical Documentation

> A comprehensive guide to the AI-powered financial advisory engine behind FinAssist.
> Covers every component from user input to final response — guardrails, routing, NL2SQL, hybrid RAG, scraping, chunking, and prompt engineering.

---

## 1. System Architecture

```
                             ┌──────────────────────┐
                             │      User Query      │
                             └──────────┬───────────┘
                                        │
                                        ▼
                          ┌──────────────────────────┐
                          │   Input Guardrails       │
                          │ • Prompt Injection Check │
                          │ • Profanity (library)    │
                          │ • Length & Char Flood    │
                          └──────────┬───────────────┘
                                     │
                                     ▼
                          ┌──────────────────────────┐
                          │   Domain Scope Validator  │
                          │ (LLM: is this finance?)   │
                          └──────────┬───────────────┘
                                     │
                                     ▼
                          ┌──────────────────────────┐
                          │    Intent Classifier     │
                          │ (LLM: multi-intent)      │
                          └──────────┬───────────────┘
                                     │
                                     ▼
                          ┌──────────────────────────┐
                          │      Intent Router       │
                          │  (Pure Python, no LLM)   │
                          └──────────┬───────────────┘
                                     │
           ┌─────────────────────────┼─────────────────────────┐
           │                         │                         │
           ▼                         ▼                         ▼
┌────────────────────┐  ┌────────────────────────┐  ┌────────────────────┐
│ Personal Finance   │  │ Financial Knowledge    │  │ Goal Planning      │
│ Transaction Query  │  │ (Market/Rates/Tips)    │  │ (HITL Workflow)    │
└─────────┬──────────┘  └────────────┬───────────┘  └─────────┬──────────┘
          │                          │                         │
          ▼                          ▼                         ▼
┌────────────────────┐  ┌────────────────────────┐  ┌────────────────────┐
│   NL2SQL Engine    │  │ Hybrid Retrieval Layer │  │ Workflow Slot Node │
│ (2-Phase Planner)  │  └────────────┬───────────┘  │ (Clarification     │
└─────────┬──────────┘               │              │  Questions)        │
          │              ┌───────────┴───────────┐  └─────────┬──────────┘
          ▼              ▼                       ▼            │
┌────────────────┐ ┌──────────────┐ ┌──────────────────┐      │
│   Supabase     │ │ ChromaDB     │ │ Live Web Search  │      │
│   PostgreSQL   │ │ (MMR Vector  │ │ & Scraping       │      │
│                │ │  Retrieval)  │ │ (DuckDuckGo)     │      │
└───────┬────────┘ └──────┬───────┘ └────────┬─────────┘      │
        │                 │                  │                │
        │                 └────────┬─────────┘                │
        │                          │                          │
        │                          ▼                          │
        │              ┌────────────────────────┐             │
        │              │ Knowledge Aggregation  │             │
        │              └────────────┬───────────┘             │
        │                          │                          │
        │                          ▼                          │
        │              ┌────────────────────────┐             │
        └─────────────▶│  Advisor Agent (LLM)   │◀────────────┘
                       │ • Profile Injection    │
                       │ • Context Synthesis    │
                       │ • Markdown Formatting  │
                       └────────────┬───────────┘
                                    │
                                    ▼
                       ┌────────────────────────┐
                       │  Output Guardrails     │
                       │ • PII Masking          │
                       │ • Credential Leak Check│
                       │ • SQL Sanitization     │
                       └────────────┬───────────┘
                                    │
                                    ▼
                           ┌──────────────┐
                           │ Final Answer │
                           └──────────────┘
```

---

## 2. LangGraph Implementation

### 2.1 Why LangGraph?
We use **LangGraph** (by LangChain) to model the entire chatbot as a **compiled state machine**. Each "agent" is a Python function (a "node") that reads from and writes to a shared typed state dictionary. Conditional "edges" route the state to the next node based on the results of the previous one.

### 2.2 State Object (`app/graph/state.py`)
The `FinAssistState` is a `TypedDict` containing **23 typed fields** grouped by pipeline stage:

| Field Group       | Key Fields                                          | Purpose                                    |
|-------------------|-----------------------------------------------------|--------------------------------------------|
| **Input**         | `user_id`, `thread_id`, `user_message`, `user_profile` | Immutable inputs set once per invocation |
| **Messages**      | `messages` (append-only via `add_messages` reducer)  | Full conversation history for multi-turn   |
| **Security**      | `input_blocked`, `output_blocked`, `input_error`     | Guardrail gate results                     |
| **Domain**        | `domain_supported`, `detected_domain`                | Domain scope validation result             |
| **Intent**        | `intent_candidates`, `selected_intent`, `multi_intent_type` | Classification + resolution          |
| **Workflow**      | `workflow_state`, `workflow_active`, `workflow_related` | HITL slot-filling state                  |
| **RAG**           | `retrieved_context`, `context_sources`, `rag_confidence` | ChromaDB retrieval results              |
| **Answer**        | `raw_answer`, `final_answer`, `sources`, `route_to_nl2sql` | Generated response pipeline            |

### 2.3 Node Inventory (`app/graph/nodes.py`)
The graph contains **10 registered nodes**, each a standalone Python function:

| #  | Node                     | Type              | What It Does                                                        |
|----|--------------------------|-------------------|---------------------------------------------------------------------|
| 1  | `input_guardrail_node`   | Regex (no LLM)    | Prompt injection, profanity (`better_profanity`), length & char flood |
| 2  | `domain_scope_node`      | LLM (temp=0)      | Decides if query is finance-related; rejects sports, politics, etc. |
| 3  | `intent_classifier_node` | LLM (temp=0)      | Classifies into 1–3 intents with confidence scores                  |
| 4  | `intent_router_node`     | Pure Python       | Reads `selected_intent` and routes to the correct action branch     |
| 5  | `nl2sql_node`            | Async Python+LLM  | Converts NL → SQL spec → Supabase query → human-readable answer     |
| 6  | `workflow_relevance_node`| LLM (temp=0)      | Checks if user is answering an active HITL question or changing topic |
| 7  | `rag_retrieval_node`     | Vector DB + Scraper| Searches ChromaDB; falls back to live web scraping on low confidence |
| 8  | `workflow_slot_node`     | Python + LLM      | Multi-turn slot-filling: asks clarification questions one by one    |
| 9  | `advisor_node`           | LLM (temp=0.2)    | Final answer synthesis with profile injection and context blending  |
| 10 | `output_guardrail_node`  | Regex (no LLM)    | PII masking, credential leak detection, SQL sanitization            |

### 2.4 Edge Routing (`app/graph/edges.py`)
Edges are pure Python functions that return a string naming the next node. They contain **zero business logic** — they only read state fields already set by nodes.

| Edge Function                    | From Node            | Possible Next Nodes                         |
|----------------------------------|----------------------|---------------------------------------------|
| `route_after_input_guard`        | input_guardrail      | `domain_scope` or `END`                     |
| `route_after_domain_scope`       | domain_scope         | `intent_classifier` or `END`                |
| `route_after_intent_classifier`  | intent_classifier    | `intent_router` or `END` (clarification)    |
| `route_after_intent_router`      | intent_router        | `nl2sql`, `rag_retrieval`, `workflow_slot`, or `workflow_relevance` |
| `route_after_workflow_relevance` | workflow_relevance   | `workflow_slot` or `intent_router` (topic changed) |
| `route_after_workflow_slot`      | workflow_slot        | `advisor` or `END` (still collecting slots) |
| `route_after_advisor`            | advisor              | `output_guardrail` or `nl2sql` (failsafe reroute) |

### 2.5 Graph Compilation (`app/graph/graph.py`)
The `build_graph()` function registers all 10 nodes, wires all 7 conditional edges + 3 fixed edges, attaches a **SQLite checkpointer** for per-thread state persistence, and compiles the graph into a singleton `finassist_graph` object.

---

## 3. Guardrails Implementation

### 3.1 Input Guardrails (`app/guardrails/input_guard.py`)
Runs **before any LLM call**. Pure regex — zero latency cost.

| Check                    | Method                                                              |
|--------------------------|---------------------------------------------------------------------|
| **Prompt Injection**     | 30+ regex patterns: "ignore previous instructions", "DAN", "god mode", "developer mode" |
| **Suspicious Access**    | Detects attempts to access other users' data: "show John's transactions", "all users data" |
| **Profanity**            | `better_profanity` library (global dictionary of 1000+ words) + custom financial-abuse terms ("scam", "fraud", "hack", "exploit") |
| **Length Limit**         | Hard cap at 2000 characters                                        |
| **Special Char Flood**   | Blocks messages where >50% of characters are non-alphanumeric      |

### 3.2 Output Guardrails (`app/guardrails/output_guard.py`)
Runs **after the LLM generates the response**, before it reaches the user.

| Check                    | Action                                                              |
|--------------------------|---------------------------------------------------------------------|
| **Credential Leakage**  | Regex scans for API keys, JWTs, DB connection strings, private keys → **hard block** (returns generic apology) |
| **Raw SQL Exposure**    | Detects SELECT/INSERT/UPDATE clusters → **sanitize** (replaces with `[System Query Removed for Security]`) |
| **PII Masking**         | `PIIMasker.mask_all()` applied to the cleaned response              |

### 3.3 PII Masking (`app/guardrails/pii_masking.py`)
Regex-based masking specifically tuned for Indian financial PII:

| PII Type         | Format Detected                   | Masked Output                |
|------------------|-----------------------------------|------------------------------|
| Phone            | `9876543210`                      | `******3210`                 |
| PAN Card         | `ABCDE1234F`                      | `***MASKED***`               |
| Aadhaar          | `1234 5678 9012`                  | `***MASKED***`               |
| Credit Card      | `4111-1111-1111-1111`             | `XXXX-XXXX-XXXX-1111`        |
| Email            | `user@example.com`                | `us***@example.com`          |
| IFSC Code        | `HDFC0001234`                     | `***MASKED***`               |
| Bank Account     | `123456789012`                    | `****9012`                   |

---

## 4. NL2SQL Engine

### 4.1 Two-Phase Query Planner (`app/utils/query_planner.py`)

**Phase 1 — Pure Python Date Resolution (zero LLM tokens):**
LLMs hallucinate on calendar math. We resolve all relative date expressions in pure Python using `datetime`, `timedelta`, and the native `calendar` module:

| User Says          | Resolved `date_from`    | Resolved `date_to`      |
|--------------------|-------------------------|-------------------------|
| "today"            | `2026-06-03`            | `2026-06-03`            |
| "yesterday"        | `2026-06-02`            | `2026-06-02`            |
| "last week"        | Monday of prev week     | Sunday of prev week     |
| "this month"       | `2026-06-01`            | `2026-06-03` (today)    |
| "last month"       | `2026-05-01`            | `2026-05-31`            |
| "May" (in June)    | `2026-05-01`            | `2026-05-31`            |
| "between Jan and March" | `2026-01-01`        | `2026-03-31`            |

**Phase 2 — LLM Semantic Extraction:**
The LLM receives the pre-resolved dates as a system hint and extracts the remaining fields into a JSON `QuerySpec`:
```json
{
  "metric": "sum",
  "transaction_type": "expense",
  "merchant": null,
  "category": "Food & Drinks",
  "date_from": "2026-05-01",
  "date_to": "2026-05-31",
  "limit": null,
  "sort": "desc",
  "group_by": "category"
}
```

### 4.2 Query Executor (`app/utils/query_executor.py`)
- Translates the JSON spec into a Supabase PostgREST query (no raw SQL — immune to SQL injection).
- Uses **nested select joins**: `categories(main_category)` to resolve UUID foreign keys into human-readable category names (e.g., "Food & Drinks" instead of `cf798fba-849d-...`).
- Supports aggregation functions: `sum`, `count`, `average`, `max`, `min`.
- Groups by `category` or `merchant` with automatic sorting.
- Hard-caps fetch at 200 rows for safety.

---

## 5. Hybrid RAG (Retrieval-Augmented Generation)

### 5.1 Retrieval Strategy
The RAG Agent uses a **two-tier hybrid retrieval** system:

**Tier 1 — ChromaDB Local Vector Store (~50ms latency):**
- Query is embedded and searched against local collections.
- Collections searched depend on the classified intent:
  - `financial_knowledge` → `banking_data`, `investment_data`, `financial_tips`
  - `financial_goal_planning` → `financial_tips`
- Results are **deduplicated** by exact text match.
- Capped at **5 context blocks** maximum.
- **Confidence threshold**: cosine distance ≤ 0.6 = high confidence (use local results).

**Tier 2 — Live Web Scraper Fallback (triggered when distance > 0.6):**
- If ChromaDB has no relevant or confident results, the system triggers `live_web_search_and_scrape()`.
- Uses the **`ddgs` (DuckDuckGo Search)** library to search the web.
- Top result URL is scraped using **Playwright** (headless Chromium browser).
- Scraped text is injected directly into the `retrieved_context` state field.

### 5.2 Chunking Strategy (`app/utils/scrapers.py`)

Before storing scraped content into ChromaDB, long documents are split into embeddable chunks:

| Parameter        | Value   | Rationale                                                    |
|------------------|---------|--------------------------------------------------------------|
| `chunk_size`     | 800 chars (~160 words) | Large enough to contain a complete thought; small enough to embed accurately |
| `overlap`        | 100 chars (~20 words)  | Prevents context loss at chunk boundaries — subjects and predicates stay connected |
| `min_chunk_len`  | 50 chars | Drops navigation links, footers, and HTML noise              |

**How it works internally:**
1. All whitespace is collapsed into single spaces (`re.sub(r'\s+', ' ', text)`).
2. Text is split into words.
3. A sliding window of `words_per_chunk` moves forward by `words_per_chunk - words_overlap` on each step.
4. Each resulting chunk is validated against the 50-character minimum.
5. Each chunk gets a UUID-based `id`, source metadata (URL, category, timestamp), and is **upserted** (not inserted) into ChromaDB to ensure idempotent re-seeding.

### 5.3 Embedding Strategy (`app/utils/chroma_store.py`)
Two options, configured via environment variable:

| Strategy                  | When                                    | Model                       |
|---------------------------|-----------------------------------------|-----------------------------|
| **Local ONNX (default)**  | `CHROMA_USE_OPENAI_EMBED=false` or unset | ChromaDB `DefaultEmbeddingFunction` (mini-LM, fully offline) |
| **OpenAI Cloud**          | `CHROMA_USE_OPENAI_EMBED=true`           | `text-embedding-3-small` (better quality, requires API key) |

### 5.4 ChromaDB Collections

| Collection         | Content                                                   | Sources                              |
|--------------------|-----------------------------------------------------------|--------------------------------------|
| `banking_data`     | FD rates, RD rates, savings accounts, credit cards, loans | BankBazaar, Groww                    |
| `investment_data`  | Stocks, mutual funds, gold prices, SIP data               | MoneyControl, Screener, GoodReturns  |
| `financial_tips`   | Budgeting tips, tax advice, insurance, retirement (PPF)   | ET Wealth, MoneyControl              |

---

## 6. Web Scraping & Anti-Blocking

### 6.1 Batch Scraping (Offline Seeding)
Used to pre-populate ChromaDB with financial data from 17+ URLs:
- **Library**: Playwright (headless Chromium) + BeautifulSoup
- **User-Agent**: Spoofed as Chrome 120 desktop browser
- **JS Rendering**: 3-second wait after DOM load for React/Angular tables to render
- **HTML Cleaning**: Strips `<script>`, `<style>`, `<nav>`, `<footer>`, `<aside>`, `<iframe>` tags; extracts `<main>` or `<article>` content preferentially
- **Rate Limiting**: 3-second delay between requests to avoid IP bans

### 6.2 Live Search Fallback (Runtime)
Used when ChromaDB has no relevant results:
- **Library**: `ddgs` (DuckDuckGo Search) — hooks into DDG Lite HTML engine
- **Why not BeautifulSoup/Requests?**: Cloudflare/Akamai WAFs block raw HTTP requests on MoneyControl, BankBazaar, etc.
- **Why not Playwright directly?**: Too slow for real-time (15–30 seconds per page)
- **How `ddgs` bypasses blocks**: It queries the DuckDuckGo search index, which has already crawled and cached the target pages. We get the text snippets instantly without ever hitting the target website directly.

---

## 7. Workflow / HITL (Human-in-the-Loop) Slot Filling

When a user asks a complex goal-planning question (e.g., "I want to save for a house"), the system enters a **multi-turn conversation loop**:

1. **`workflow_slot_node`** identifies missing information slots (budget, timeline, risk tolerance, etc.).
2. It generates a **clarification question** and returns it as the `final_answer`.
3. On the next user message, **`workflow_relevance_node`** checks if the user is answering the question or changing the subject.
4. If answering → route back to `workflow_slot_node` (fill the next slot).
5. If changing topic → **pause** the workflow (preserving state) and route to `intent_router` for the new topic.
6. Once all slots are filled → hand off to `advisor_node` for final plan generation.

---

## 8. Prompt Engineering (`app/utils/prompts.py`)

| Prompt                        | Used By                | Structure                                                    |
|-------------------------------|------------------------|--------------------------------------------------------------|
| `DOMAIN_SCOPE_SYSTEM/USER`    | `domain_scope_node`    | JSON output: `{supported, reason, detected_domain}`          |
| `INTENT_CLASSIFIER_SYSTEM/USER` | `intent_classifier_node` | JSON output: `{intent_candidates: [{intent, confidence}]}` |
| `WORKFLOW_RELEVANCE_SYSTEM/USER` | `workflow_relevance_node` | JSON output: `{workflow_related, confidence, reason}`     |
| `NL2SQL_PLANNER_SYSTEM/USER`  | `query_planner.py`     | JSON output: Full `QuerySpec` dict                           |
| `FINASSIST_SYSTEM_PROMPT`     | `advisor_node`         | Injects user profile (income, risk, balances) + retrieved context; enforces markdown formatting |

All LLM calls use `response_format={"type": "json_object"}` for structured extraction (except the final advisor which outputs free-form markdown).

---

## 9. API & Data Flow (Frontend ↔ Backend)

### Request
```
POST /api/chat/message
Content-Type: application/json

{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "How much did I spend on food last month?",
  "thread_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

### Response
```json
{
  "answer": "You spent ₹4,250 on Food & Drinks in May 2026...",
  "intent": "personal_transaction",
  "sources": ["Supabase Transactions"],
  "thread_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "user_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### CORS Configuration
- Explicit origin whitelist: `http://localhost:5173`, `http://127.0.0.1:5173`, `http://localhost:3000`
- `allow_credentials=True` (requires explicit origins, not `*`)

---

## 10. Technology Stack

| Layer              | Technology                                                   |
|--------------------|--------------------------------------------------------------|
| **Frontend**       | React 18, TypeScript, Vite, Tailwind CSS, Lucide Icons       |
| **Backend API**    | FastAPI, Uvicorn (async)                                     |
| **Orchestration**  | LangGraph (StateGraph + SQLite Checkpointer)                 |
| **LLM Provider**   | OpenAI API (GPT models via configurable base URL)            |
| **Vector Store**   | ChromaDB (PersistentClient, HNSW cosine similarity)          |
| **Embeddings**     | Local ONNX mini-LM (default) or OpenAI `text-embedding-3-small` |
| **Database**       | Supabase (PostgreSQL + PostgREST)                            |
| **Web Scraping**   | Playwright (batch), `ddgs` DuckDuckGo Search (live fallback) |
| **Security**       | `better_profanity`, custom regex guardrails, `PIIMasker`     |
| **Date Parsing**   | Python `calendar`, `datetime`, `timedelta` (no external lib) |

---

*Architecture designed and maintained by the FinAssist Core Engineering Team.*
