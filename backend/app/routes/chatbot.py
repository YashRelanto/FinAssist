"""
FastAPI router exposing the FinAssist AI chatbot API.

Prefix  : /api/chat
Tags    : Chatbot
Endpoints:
    POST /api/chat/message  — Submit a user message and receive an AI advisory response
"""

import logging
import time
from typing import Optional, Dict, List, Any
from collections import defaultdict

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.utils.supabase_client import supabase

# ─── Logging ────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)

# ─── Router ──────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/chat", tags=["Chatbot"])


# ─── Pydantic Schemas ─────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    """Incoming chat payload from the frontend."""

    user_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Unique identifier for the authenticated user (e.g. Supabase UUID).",
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
    needs_clarification: bool = Field(
        default=False,
        description="True when the assistant needs more information before answering.",
    )
    clarification_options: list[str] = Field(
        default_factory=list,
        description="Suggested options for clarification questions when needs_clarification is true.",
    )
    thread_id: str = Field(
        ...,
        description="Echo of the thread_id used for this turn.",
    )
    user_id: str = Field(
        ...,
        description="Echo of the user_id for client-side correlation.",
    )


# ─── User Profile Builder (real Supabase data) ───────────────────────────────

def _fetch_user_profile_row(user_id: str) -> Dict[str, Any]:
    """Load user_profiles row from Supabase; empty dict if missing."""
    try:
        res = (
            supabase.table("user_profiles")
            .select("*")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        return (res.data or [{}])[0]
    except Exception as e:
        logger.warning("Failed to fetch user_profiles for %s: %s", user_id, e)
        return {}


def _fetch_user_goals(user_id: str) -> List[Dict[str, Any]]:
    try:
        res = (
            supabase.table("goals")
            .select("goal_name, target_amount, current_amount, target_date, status")
            .eq("user_id", user_id)
            .execute()
        )
        return res.data or []
    except Exception:
        return []


def build_chat_user_profile(user_id: str) -> Dict[str, Any]:
    """
    Build user_profile for the LangGraph pipeline from real Supabase data.
    No mock defaults — missing fields remain empty/zero.
    """
    profile_row = _fetch_user_profile_row(user_id)
    monthly_income = float(profile_row.get("income") or 0)
    fixed_emi = float(profile_row.get("fixed_emi") or 0)
    fixed_rent = float(profile_row.get("fixed_rent") or 0)

    user_profile: Dict[str, Any] = {
        "income": monthly_income,
        "annual_income": monthly_income * 12 if monthly_income else 0,
        "city": profile_row.get("city_tier") or "",
        "city_tier": profile_row.get("city_tier") or "",
        "risk_profile": profile_row.get("risk_profile") or "",
        "fixed_emi": fixed_emi,
        "fixed_rent": fixed_rent,
        "monthly_obligations": fixed_emi + fixed_rent,
        "primary_goal": profile_row.get("primary_goal") or "",
        "biggest_category": profile_row.get("biggest_category") or "",
        "onboarded": bool(profile_row.get("onboarded")),
        "goals": _fetch_user_goals(user_id),
        "existing_investments": [],
        "real_time_balances": "N/A",
        "monthly_net_flow": "N/A",
    }

    try:
        user_data = _fetch_user_data(user_id)
        summary = _build_summary(user_data.get("transactions", []), user_data.get("accounts", []))
        if summary:
            user_profile["transaction_summary"] = summary
            balances = summary.get("account_balances", [])
            user_profile["real_time_balances"] = (
                "\n  - " + "\n  - ".join(balances) if balances else "N/A"
            )
            net_flow = summary.get("net_flow_inr", 0)
            user_profile["monthly_net_flow"] = f"₹{net_flow:,.2f}"
            if not monthly_income and summary.get("monthly_summary"):
                recent = summary["monthly_summary"][0]
                inc = recent.get("money_RECEIVED_income_only_inr", 0)
                if inc:
                    user_profile["income"] = inc
                    user_profile["annual_income"] = inc * 12
    except Exception as e:
        logger.error("Failed to build transaction summary for profile: %s", e)

    try:
        from app.services.investment_analysis_service import analyze_portfolio

        portfolio = analyze_portfolio(user_id, user_profile=user_profile)
        user_profile["portfolio_summary"] = portfolio.get("portfolio_health", {})
        user_profile["existing_investments"] = [
            h.get("scheme_name") or h.get("name") or h.get("symbol", "Unknown")
            for h in portfolio.get("holdings", [])
        ]
    except Exception as e:
        logger.warning("Failed to fetch portfolio for profile: %s", e)

    return user_profile


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
async def post_chat_message(request: ChatRequest) -> ChatResponse:
    """
    Main chat endpoint orchestrator.
    """
    # 1. Build user profile from real Supabase data
    user_profile = build_chat_user_profile(request.user_id)

    # 2. Call the core engine (LangGraph)
    try:
        from app.graph.graph import finassist_graph
        from app.graph.logging_utils import (
            clear_graph_run_context,
            log_graph_run_end,
            log_graph_run_start,
            set_graph_run_context,
        )
        from app.graph.state import make_initial_state

        config = {"configurable": {"thread_id": f"{request.user_id}:{request.thread_id}"}}
        set_graph_run_context(user_id=request.user_id, thread_id=request.thread_id)
        log_graph_run_start(
            user_id=request.user_id,
            thread_id=request.thread_id,
            message=request.message,
        )
        run_started = time.perf_counter()

        # Fetch the current state snapshot from checkpointer to preserve workflow state
        state_snapshot = await finassist_graph.aget_state(config)
        wf_state = {}
        wf_active = False
        clarification_history = []

        if state_snapshot and state_snapshot.values:
            wf_state = state_snapshot.values.get("workflow_state") or {}
            wf_active = state_snapshot.values.get("workflow_active", False)
            clarification_history = state_snapshot.values.get("clarification_history") or []

        initial_state = make_initial_state(
            user_id=request.user_id,
            session_id=request.thread_id,
            user_query=request.message,
            user_profile=user_profile,
            workflow_state=wf_state,
            workflow_active=wf_active,
        )
        if clarification_history:
            initial_state["clarification_history"] = clarification_history

        final_state = await finassist_graph.ainvoke(initial_state, config=config)

        answer = final_state.get("final_answer") or final_state.get("raw_answer") or ""
        from app.graph.nodes.intent_node import to_brd_intent

        raw_intent = final_state.get("final_intent") or final_state.get("intent") or "FINANCIAL_KNOWLEDGE"
        intent = raw_intent if "_" in raw_intent and raw_intent == raw_intent.lower() else to_brd_intent(raw_intent)
        sources = final_state.get("sources") or []
        needs_clarification = bool(final_state.get("clarification_needed"))
        clarification_options = final_state.get("clarification_options") or []
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
        needs_clarification=needs_clarification,
        clarification_options=clarification_options,
        thread_id=request.thread_id,
        user_id=request.user_id,
    )
