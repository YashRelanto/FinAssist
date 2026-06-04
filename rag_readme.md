# FinAssist - Architecture & Implementation Guide

This document details the internal architecture, RAG pipelines, LangGraph orchestration, and security mechanisms powering FinAssist.

---

## 1. LangGraph Orchestration & Navigation

FinAssist operates entirely on **LangGraph**, replacing traditional linear agent frameworks with a robust, persistent state machine.

### State Management
All context is stored in `FinAssistState` (a `TypedDict`), acting as the single source of truth. As a query flows through the graph, nodes append data (like `intent_candidates`, `retrieved_context`, `user_profile`) to this state. Checkpointers (`AsyncSqliteSaver` / `AsyncPostgresSaver`) persist this state automatically for multi-turn conversations.

### Nodes and Navigation (Routing)
The graph uses **Conditional Edges** to dynamically route the user's query:

1. **`input_guardrail_node`**: Checks for abuse. If safe, routes to Domain Scope.
2. **`domain_scope_node`**: Uses conversation history to determine if the query is finance-related.
3. **`intent_classifier_node`**: Classifies the *latest* message into an intent (`financial_knowledge`, `financial_goal_planning`, etc.). It strictly selects the highest confidence intent to avoid getting stuck in clarification loops.
4. **`intent_router`** (Edge logic):
   - → `nl2sql` if checking transactions.
   - → `workflow_slot` if planning a goal.
   - → `rag_retrieval` if seeking financial knowledge/rates.
5. **Action Nodes**:
   - **`nl2sql_node`**: Fetches user transaction data.
   - **`workflow_slot_node`**: HITL (Human-in-the-Loop) node that extracts missing slots (target amount, timeline) for goal planning.
   - **`rag_retrieval_node`**: Fetches ChromaDB context or triggers Hybrid Web Search.
6. **`advisor_node`**: The final LLM synthesis node that reads all collected state data and outputs the 1-3 sentence response.

---

## 2. Scraping & Anti-Blocking Strategies

To gather domain-specific financial knowledge, FinAssist utilizes a massive scheduled scraper pipeline (`scrapers.py`).

### Headless Playwright Scraping
We use `playwright.sync_api` to launch a headless Chromium browser. This is critical for modern financial websites (like BankBazaar or Groww) that render data tables asynchronously via React/Angular.
- **Bypassing Blocks**: The browser is injected with realistic User-Agents and viewport sizes. We utilize `page.wait_for_timeout(3000)` to ensure all Javascript dynamic tables physically render before extracting the DOM.
- **Noise Reduction**: BeautifulSoup strips out `<nav>`, `<footer>`, `<script>`, and `<style>` tags to extract only the pure article/table content.

---

## 3. Chunking Strategy

Before storing scraped data into ChromaDB, it must be chunked to fit within LLM context windows while preserving semantic meaning.

- **Algorithm**: Overlapping Sliding Window.
- **Parameters**: `chunk_size = 800` words, `overlap = 100` words.
- **Why?**: Financial articles often span multiple paragraphs. A 100-word overlap guarantees that if a paragraph breaks mid-sentence during chunking, the context is carried over into the next chunk. 
- **Storage**: Chunks are embedded and stored in three isolated ChromaDB collections: `banking_data`, `investment_data`, and `financial_tips`.

---

## 4. Retrieval & Hybrid Search

FinAssist employs a **Real-Time Hybrid RAG Architecture**.

### Local Vector Search (ChromaDB)
When a query enters the `rag_retrieval_node`:
1. It queries ChromaDB using Cosine Distance.
2. If the `min_distance` is `≤ 0.6` (High Confidence), it returns the top 5 chunks immediately (latency: ~50ms).

### Live Web Search Fallback (Agentic Scraping)
If ChromaDB fails to find relevant context (0 results or `min_distance > 0.6`), the graph intercepts the failure and dynamically scrapes the internet to prevent hallucinations.
1. **Search Engine**: Uses the `ddgs` (DuckDuckGo Search) library to bypass standard search engine API rate limits.
2. **Snippet Extraction**: It instantly pulls the search engine's summary "snippet" containing live data (e.g., today's stock price).
3. **Deep Scraping**: It grabs the top-ranking URL from the search result and boots up Playwright mid-conversation to scrape the full article.
4. **Context Injection**: It merges the Search Snippet + Scraped DOM, forces the `rag_confidence` to `0.1` (spoofing high confidence), and hands it to the `advisor_node`.

---

## 5. NL2SQL Implementation

To answer questions like *"How much did I spend on food?"*, we use a secure **2-Stage NL2SQL Pipeline**.

- **Stage 1 (Query Planner)**: An LLM transforms natural language into a strict `QuerySpec` JSON object containing filters (e.g., `category = 'Food'`), date ranges, and aggregations.
- **Stage 2 (Query Executor)**: Instead of generating raw, dangerous SQL strings, the JSON is mapped directly into safe **Supabase Python Client** chains (e.g., `.select().eq().gte()`).
- **Result**: Complete immunity to SQL Injection attacks, as raw SQL is never executed.

---

## 6. Guardrails System

FinAssist utilizes a 4-Layer Security architecture to protect the LLM and the user's data:

1. **L1: Input Guard**: An LLM-based firewall that detects and blocks jailbreaks, prompt injection, and abusive language before the workflow begins.
2. **L2: Domain Scope**: Ensures the conversation remains strictly about finance. Crucially, this node has access to conversation history, so it won't mistakenly block isolated user inputs (like typing "50000" when asked for a budget).
3. **L3: PII Masking**: A Regex-based interceptor that scans for Indian PII (Aadhaar cards, PAN cards, phone numbers) and replaces them with `[MASKED]` before they reach OpenAI's servers.
4. **L4: Output Guard**: Scans the final LLM response to ensure no internal system prompts, database schemas, or API keys are accidentally leaked to the user.
