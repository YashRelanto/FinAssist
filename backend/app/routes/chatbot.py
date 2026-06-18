"""
FastAPI router exposing the FinAssist AI chatbot API.

Prefix  : /api/chat
Tags    : Chatbot
Endpoints:
    POST /api/chat/message  — Submit a user message and receive an AI advisory response
"""

import logging
import time
from typing import Dict, List, Any, Optional
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.auth import get_current_user

from app.utils.supabase_client import supabase

# ─── Logging ────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)

# ─── Router ──────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/chat", tags=["Chatbot"])


# ─── Pydantic Schemas ─────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    """Incoming chat payload from the frontend."""

    user_id: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Deprecated — user identity is now derived from the Authorization JWT.",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=4096,
        description="The user's natural language query or statement.",
        examples=["What are the best FD rates available right now?"],
    )
    thread_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description=(
            "Conversation thread identifier.  Use a stable UUID per chat session "
            "to maintain coherent multi-turn history.  Pass a new UUID to start a fresh thread."
        ),
        examples=["a1b2c3d4-e5f6-7890-abcd-ef1234567890"],
    )


class ChatResponse(BaseModel):
    """Outgoing advisory payload returned to the frontend."""

    answer: str = Field(
        ...,
        description="The AI-generated advisory response in markdown-compatible plain text.",
    )
    intent: str = Field(
        ...,
        description=(
            "Classified intent of the query.  One of: "
            "personal_transaction | financial_knowledge | financial_goal_planning | out_of_scope"
        ),
    )
    sources: list[str] = Field(
        default_factory=list,
        description=(
            "List of knowledge sources used to generate the answer "
            "(e.g. 'BankBazaar', 'MoneyControl', 'Supabase: transactions')."
        ),
    )
    clarification_questions: list[dict] = Field(
        default_factory=list,
        description=(
            "When intent='clarification', the list of questions to ask the user. "
            "Each item: {id: 'q0', question: '...'}. The frontend shows them one-at-a-time."
        ),
    )
    artifacts: list[dict] = Field(
        default_factory=list,
        description=(
            "Visualization specs (charts) for the frontend to render. Each item has "
            "type/chart_type/title/x_field/y_field/data."
        ),
    )
    metadata: dict = Field(
        default_factory=dict,
        description=(
            "Run observability: tools_used, iterations, total_tokens, per_tool_token_usage."
        ),
    )
    thread_id: str = Field(
        ...,
        description="Echo of the thread_id used for this turn.",
    )
    user_id: str = Field(
        ...,
        description="Echo of the user_id for client-side correlation.",
    )


# ─── Default Mock User Profile ────────────────────────────────────────────────

def _get_default_user_profile() -> dict:
    """
    Returns a mock user profile dictionary that simulates variables sourced
    from the Supabase users / profiles table.
    """
    return {
        "income": 55000,                         # Monthly net income in INR
        "annual_income": 660000,                 # Annual (12 × monthly)
        "segment": "High Income Low Spender",    # Customer segment from analytics
        "city": "Tier 1",                        # City tier classification
        "age": 32,                               # Estimated age
        "risk_profile": "Moderate",              # Risk tolerance: Conservative / Moderate / Aggressive
        "primary_bank": "HDFC Bank",             # Primary bank name
        "existing_investments": [                # Known investment vehicles
            "Mutual Funds (SIP ₹10,000/mo)",
            "PPF (₹1.5L/year)",
            "EPF (employer + employee)",
        ],
        "outstanding_loans": [],                 # Active loan facilities
        "credit_score": 780,                     # CIBIL / Experian score
        "preferred_language": "English",
    }


# ─── Local Helpers for User Profile Context ───────────────────────────────

def _fetch_user_data(user_id: str) -> Dict[str, Any]:
    """
    Pull real user data from Supabase to construct profile metrics.
    """
    data: Dict[str, Any] = {"transactions": [], "accounts": []}

    try:
        tx_res = (
            supabase.table("transactions")
            .select("transaction_date, amount, transaction_type, merchant_name, description, category_id")
            .eq("user_id", user_id)
            .order("transaction_date", desc=True)
            .limit(200)
            .execute()
        )
        data["transactions"] = tx_res.data or []
    except Exception as e:
        logger.error("Failed to fetch transactions for profile: %s", e)

    try:
        acc_res = (
            supabase.table("accounts")
            .select("account_name, account_type, current_balance")
            .eq("user_id", user_id)
            .execute()
        )
        data["accounts"] = acc_res.data or []
    except Exception as e:
        logger.error("Failed to fetch accounts for profile: %s", e)

    return data


def _build_summary(transactions: List[Dict], accounts: List[Dict]) -> Dict[str, Any]:
    """
    Compute key financial metrics to populate in the LLM user profile system prompt.
    """
    if not transactions:
        return {}

    total_credit = sum(t["amount"] for t in transactions if t.get("transaction_type") == "income")
    total_debit  = sum(t["amount"] for t in transactions if t.get("transaction_type") == "expense")
    net_flow     = total_credit - total_debit
    tx_count     = len(transactions)

    # Spending by merchant (top 10)
    merchant_spend: Dict[str, float] = defaultdict(float)
    for t in transactions:
        if t.get("transaction_type") == "expense":
            name = t.get("merchant_name") or t.get("description") or "Unknown"
            merchant_spend[name] += t.get("amount", 0)
    top_merchants = sorted(merchant_spend.items(), key=lambda x: x[1], reverse=True)[:10]

    # Monthly breakdown (last 6 months)
    monthly: Dict[str, Dict[str, float]] = defaultdict(lambda: {"income": 0.0, "expense": 0.0})
    for t in transactions:
        try:
            month = t["transaction_date"][:7]  # "YYYY-MM"
            monthly[month][t.get("transaction_type", "expense")] += t.get("amount", 0)
        except Exception:
            continue
    monthly_sorted = sorted(monthly.items(), reverse=True)[:6]

    # Largest single transactions
    largest_debits  = sorted(
        [t for t in transactions if t.get("transaction_type") == "expense"],
        key=lambda x: x.get("amount", 0), reverse=True
    )[:5]
    largest_credits = sorted(
        [t for t in transactions if t.get("transaction_type") == "income"],
        key=lambda x: x.get("amount", 0), reverse=True
    )[:5]

    # Date range
    dates = [t["transaction_date"] for t in transactions if t.get("transaction_date")]
    date_from = min(dates) if dates else "N/A"
    date_to   = max(dates) if dates else "N/A"

    # Account balances
    account_info = [
        f"{a.get('account_name', 'Account')} ({a.get('account_type', '')}): ₹{a.get('current_balance', 0):,.2f}"
        for a in accounts
    ]

    return {
        "date_range": f"{date_from} to {date_to}",
        "total_transactions": tx_count,
        "total_money_SPENT_inr": round(total_debit, 2),
        "total_money_RECEIVED_inr": round(total_credit, 2),
        "net_flow_inr": round(net_flow, 2),
        "top_merchants_by_spend": [
            {"merchant": m, "total_SPENT_inr": round(v, 2)} for m, v in top_merchants
        ],
        "monthly_summary": [
            {
                "month": m,
                "money_SPENT_expenses_only_inr": round(v["expense"], 2),
                "money_RECEIVED_income_only_inr": round(v["income"], 2),
            }
            for m, v in monthly_sorted
        ],
        "largest_EXPENSE_transactions": [
            {
                "date": t["transaction_date"],
                "merchant": t.get("merchant_name") or t.get("description"),
                "amount_SPENT_inr": t["amount"],
                "type": "expense",
            }
            for t in largest_debits
        ],
        "largest_INCOME_transactions": [
            {
                "date": t["transaction_date"],
                "merchant": t.get("merchant_name") or t.get("description"),
                "amount_RECEIVED_inr": t["amount"],
                "type": "income",
            }
            for t in largest_credits
        ],
        "account_balances": account_info,
    }


# ─── POST /message Endpoint ──────────────────────────────────────────────────

@router.post(
    "/message",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit a chat message and receive a financial advisory response",
    description=(
        "Accepts a user's natural language financial query along with a conversation thread ID. "
        "The engine classifies the intent, retrieves relevant knowledge from ChromaDB, "
        "optionally queries the Supabase analytical layer for personal data, and returns "
        "a personalised advisory answer with source attribution."
    ),
    responses={
        200: {"description": "Successful advisory response"},
        422: {"description": "Validation error — check request body schema"},
        500: {"description": "Internal server error — engine failure"},
    },
)
async def post_chat_message(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user),
) -> ChatResponse:
    """
    Main chat endpoint orchestrator.
    """
    # Derive user_id from the validated JWT, not from the request body.
    request = request.model_copy(update={"user_id": current_user["user_id"]})

    # 1. Build user profile
    user_profile = _get_default_user_profile()

    # 1b. Fetch real-time transaction summary for live balances
    try:
        user_data = _fetch_user_data(request.user_id)
        summary = _build_summary(user_data.get("transactions", []), user_data.get("accounts", []))

        balances = summary.get("account_balances", [])
        user_profile["real_time_balances"] = "\n  - " + "\n  - ".join(balances) if balances else "N/A"

        net_flow = summary.get("net_flow_inr", 0)
        user_profile["monthly_net_flow"] = f"₹{net_flow:,.2f}"
    except Exception as e:
        logger.error("Failed to fetch real-time balance for profile: %s", e)
        user_profile["real_time_balances"] = "N/A"
        user_profile["monthly_net_flow"] = "N/A"

    # 2. Call the core engine (LangGraph supervisor)
    artifacts: List[dict] = []
    metadata: Dict[str, Any] = {}
    try:
        from langgraph.types import Command

        from app.graph.graph import finassist_graph
        from app.graph.logging_utils import (
            clear_graph_run_context,
            get_token_usage,
            log_graph_run_end,
            log_graph_run_start,
            reset_token_usage,
            set_graph_run_context,
        )
        from app.graph.state import make_initial_state

        config = {"configurable": {"thread_id": f"{request.user_id}:{request.thread_id}"}}
        set_graph_run_context(user_id=request.user_id, thread_id=request.thread_id)
        reset_token_usage()
        log_graph_run_start(
            user_id=request.user_id,
            thread_id=request.thread_id,
            message=request.message,
        )
        run_started = time.perf_counter()

        # Resume-aware invoke: if the graph is paused on an interrupt (HITL
        # clarification), resume it with the user's reply; otherwise start fresh.
        state_snapshot = await finassist_graph.aget_state(config)
        is_paused = bool(state_snapshot and state_snapshot.next)

        if is_paused:
            logger.info("Resuming paused graph for thread=%s", request.thread_id)
            # Recover the EXACT questions that were asked (stored in the interrupt payload)
            # so the brain maps the user's answers to the right questions, regardless of any
            # non-determinism when the node re-executes on resume.
            original_questions = None
            try:
                for task in (state_snapshot.tasks or []):
                    for intr in (getattr(task, "interrupts", None) or []):
                        val = getattr(intr, "value", None)
                        if isinstance(val, dict) and val.get("type") == "clarification_batch":
                            original_questions = val.get("questions")
                            break
                    if original_questions:
                        break
            except Exception:
                original_questions = None

            resume_value: Any = (
                {"answers": request.message, "questions": original_questions}
                if original_questions else request.message
            )
            final_state = await finassist_graph.ainvoke(
                Command(resume=resume_value), config=config
            )
        else:
            initial_state = make_initial_state(
                user_id=request.user_id,
                session_id=request.thread_id,
                user_query=request.message,
                user_profile=user_profile,
            )
            final_state = await finassist_graph.ainvoke(initial_state, config=config)

        # If the Brain raised a clarification interrupt, surface the questions.
        interrupts = final_state.get("__interrupt__") if isinstance(final_state, dict) else None
        clarification_questions_out: List[dict] = []
        if interrupts:
            payload = interrupts[0].value if hasattr(interrupts[0], "value") else interrupts[0]
            if isinstance(payload, dict) and payload.get("type") == "clarification_batch":
                qs = payload.get("questions") or []
                clarification_questions_out = qs
                answer = "I have a few quick questions to help me create the best plan for you."
            else:
                # Legacy single-question form (backward compat)
                question = (payload or {}).get("question", "Could you clarify your request?")
                clarification_questions_out = [{"id": "q0", "question": question}]
                answer = question
            intent = "clarification"
            sources = []
        else:
            answer = final_state.get("final_answer") or ""
            intent = final_state.get("final_intent") or "FINANCIAL_KNOWLEDGE"
            sources = final_state.get("sources") or []
            artifacts = final_state.get("artifacts") or []

        # Build observability metadata.
        token_usage = get_token_usage()
        evidence = final_state.get("evidence") or [] if isinstance(final_state, dict) else []
        tools_used = list(dict.fromkeys(e.get("tool") for e in evidence if e.get("tool")))
        metadata = {
            "tools_used": tools_used,
            "iterations": final_state.get("iterations", 0) if isinstance(final_state, dict) else 0,
            "total_tokens": token_usage.pop("total", 0),
            "per_tool_token_usage": token_usage,
        }

        log_graph_run_end(
            user_id=request.user_id,
            thread_id=request.thread_id,
            intent=intent,
            elapsed_ms=(time.perf_counter() - run_started) * 1000,
            answer_preview=answer,
        )
        clear_graph_run_context()

    except ValueError as exc:
        clear_graph_run_context()
        logger.warning(
            "Validation error in process_chat_message | user=%s | error=%s",
            request.user_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid input: {exc}",
        ) from exc
    except ConnectionError as exc:
        clear_graph_run_context()
        logger.error(
            "Connectivity error in process_chat_message | user=%s | error=%s",
            request.user_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "A downstream service (OpenAI or ChromaDB) is temporarily unavailable. "
                "Please try again in a few moments."
            ),
        ) from exc
    except Exception as exc:
        clear_graph_run_context()
        logger.exception(
            "Unhandled error in /api/chat/message | user=%s | thread=%s",
            request.user_id,
            request.thread_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    # 3. Build and return the response model
    return ChatResponse(
        answer=answer,
        intent=intent.lower(),
        sources=sources,
        clarification_questions=clarification_questions_out,
        artifacts=artifacts,
        metadata=metadata,
        thread_id=request.thread_id,
        user_id=request.user_id,
    )
