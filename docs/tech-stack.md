# FinAssist — Technology Overview

A high-level map of the technologies used across the stack, and where each one lives.

---

## 1. Architecture at a glance

```
React + Vite frontend  ──HTTP──>  FastAPI backend  ──>  LangGraph "Brain" supervisor graph
                                        │                     │
                                        │                     ├─ NVIDIA NIM LLMs (reasoning, SQL, answers)
                                        │                     ├─ Supabase (Postgres) — user data
                                        │                     ├─ ChromaDB — RAG knowledge base
                                        │                     ├─ api.mfapi.in — live mutual-fund NAVs
                                        │                     └─ Prophet — expense forecasting
                                        └─ Checkpointer (LangGraph persistence)
```

---

## 2. AI orchestration — LangGraph

- **Framework:** `langgraph` `StateGraph`, compiled once into a singleton (`finassist_graph`).
- **Pattern:** a **Supervisor (“Brain”)** node loops over tools, accumulating `evidence`, until it
  decides to finish. See [langgraph-flow.md](langgraph-flow.md).
- **Human-in-the-loop (HITL):** clarification questions use LangGraph `interrupt()` to pause the
  graph and resume on the user's answers (no separate state machine).
- **Checkpointer (conversation persistence)** — chosen by the `APP_ENV` env var
  ([`graph/checkpointer.py`](../backend/app/graph/checkpointer.py)):

  | `APP_ENV` | Checkpointer | Notes |
  |---|---|---|
  | `development` (default) | `MemorySaver` | in-memory, lost on restart, zero setup |
  | `staging` | `AsyncSqliteSaver` | persistent SQLite file (`SQLITE_CHECKPOINT_PATH`) |
  | `production` | `AsyncPostgresSaver` | same Supabase Postgres (`SUPABASE_DB_URL`); multi-process |

  Falls back to `MemorySaver` if the configured backend can't initialise.

---

## 3. Large Language Models — NVIDIA NIM

- **Provider:** NVIDIA NIM, accessed through the **OpenAI-compatible** API
  (`NVIDIA_BASE_URL`, default `https://integrate.api.nvidia.com/v1`, key `NVIDIA_API_KEY`).
- **Models** (from [`core/config.py`](../backend/app/core/config.py)):

  | Role | Model | Used by |
  |---|---|---|
  | `brain_model` | `meta/llama-3.3-70b-instruct` | Supervisor routing / decisions |
  | `tool_model` | `meta/llama-3.3-70b-instruct` | SQL AST generation, answer synthesis |
  | `active_chat_model` | `NVIDIA_CHAT_MODEL` (env) | general chat completions |
  | `knowledge_model` / `fast_model` | `meta/llama-3.1-8b-instruct` | RAG summarisation, cheap chart captions |
  | `financial_health_chat_model` | `qwen/qwen3.5-122b-a10b` (default) | financial-health score narratives |

- All calls go through `graph_chat_completion` ([`graph/logging_utils.py`](../backend/app/graph/logging_utils.py)),
  which centralises the client, logging, and per-node/purpose telemetry. Structured outputs use
  `response_format={"type": "json_object"}`.

---

## 4. Data layer — Supabase (PostgreSQL)

- **Client:** `supabase-py` ([`utils/supabase_client.py`](../backend/app/utils/supabase_client.py)).
  Backend uses the **service-role key** for table access; a separate **anon key** is used for
  end-user auth.
- **Core tables:** `users`, `user_profiles`, `accounts`, `transactions`, `categories`, `budgets`,
  `goals`, `investments` (mutual funds), `fixed_deposits` (FDs).
- **NL2SQL safety:** only `transactions`, `categories`, `accounts` are exposed to the SQL pipeline
  via the `SCHEMA_REGISTRY` ([`graph/schema_registry.py`](../backend/app/graph/schema_registry.py));
  the validator blocks all write/DDL keywords and enforces `user_id` scoping.

---

## 5. Retrieval / knowledge base — ChromaDB

- **Vector store:** ChromaDB (local persistent dir `CHROMA_DB_PATH`,
  [`utils/chroma_store.py`](../backend/app/utils/chroma_store.py)).
- **Collections:** `banking_data`, `investment_data`, `financial_tips`.
- **Fallback:** live web search & scrape (`utils/scrapers.py`) when the KB has no good match.
- Used by the `knowledge_tool` for general (non-personal) financial questions.

---

## 6. External APIs

- **Mutual-fund data:** `https://api.mfapi.in` — scheme search + historical/live NAV, used by the
  investment tracker and the `investment_tool`.

---

## 7. Forecasting — Prophet

- **Library:** Facebook **Prophet** time-series model ([`services/prophet/`](../backend/app/services/prophet/)).
- Trains per-user expense forecasts; models are stored in a Supabase **Storage** bucket
  (`FORECAST_STORAGE_BUCKET`) and can be (re)trained via an internal cron-triggered endpoint
  (`FORECAST_CRON_SECRET`, `TRAINING_WORKER_URL`).

---

## 8. Security & guardrails

- **Input/Output guards:** regex-based `InputGuard` / `OutputGuard`
  ([`guardrails/`](../backend/app/guardrails/)) — Layer-1 (incoming message) and Layer-2 (generated
  answer). No LLM, so they're fast and deterministic.
- **PII masking** (`guardrails/pii_masking.py`) and **security event logging**
  (`utils/security_logger.py`).

---

## 9. Backend framework & tooling

- **API:** **FastAPI** (`APIRouter(prefix="/api")`, [`routes/`](../backend/app/routes/)), entry
  [`app/main.py`](../backend/app/main.py).
- **Language/runtime:** Python 3.12.
- **Config:** `.env` via `python-dotenv`; settings centralised in `core/config.py`.
- **Tab-scoped logging:** per-UI-tab log toggles (`analytics`, `dashboard`, `chat`, `forecasting`).
- **Tests:** stdlib `unittest` ([`backend/tests/`](../backend/tests/)).

---

## 10. Frontend

- **Framework:** **React 19** + **TypeScript**, bundled with **Vite** (dev server on `:3000`).
- **Styling:** TailwindCSS with a custom design-token system (`lumio-*`, `surface-*` etc.).
- **Charts:** **Recharts** (line/bar/pie) — see `components/ChatChart.tsx`, Investments/Analytics views.
- **Markdown:** **react-markdown** + **remark-gfm** (GitHub-flavoured tables) for AI chat answers
  (`components/Markdown.tsx`).
- **Icons / animation:** `lucide-react`, `motion/react`.
- **Data:** talks to the FastAPI backend over `fetch` (e.g. `/api/chat/message`, `/api/investments`,
  `/api/fixed-deposits`).

---

## 11. Environment variables (key ones)

| Var | Purpose |
|---|---|
| `APP_ENV` | selects the checkpointer (development / staging / production) |
| `NVIDIA_API_KEY`, `NVIDIA_CHAT_MODEL`, `NVIDIA_BASE_URL` | LLM access |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY` | DB + auth |
| `SUPABASE_DB_URL` | Postgres checkpointer (production) |
| `CHROMA_DB_PATH` | RAG vector store location |
| `FORECAST_STORAGE_BUCKET`, `FORECAST_CRON_SECRET`, `TRAINING_WORKER_URL` | Prophet forecasting |
| `LOG_TAB_*` | per-tab logging toggles |
