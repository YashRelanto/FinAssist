"""
NL2SQL Engine — Translates natural language questions into structured
data lookups against the user's Supabase transactions, then returns
a direct, concise answer computed from real data.

Architecture (v2 — Query Planner Pipeline):
  1. plan_query()     → structured QuerySpec JSON (query_planner.py)
  2. execute_query()  → targeted Supabase fetch + Python aggregation (query_executor.py)
  3. generate_answer()→ LLM formats the pre-computed result into natural language

Fallback (when planning fails):
  Legacy _fetch_user_data → _build_summary → LLM with full summary JSON
  This ensures the engine always returns a useful answer.
"""

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import openai

from app.utils.supabase_client import supabase
from app.core.config import settings
from app.utils.query_planner import plan_query
from app.utils.query_executor import execute_query
from app.utils.prompts import (
    NL2SQL_ANSWER_SYSTEM,
    NL2SQL_ANSWER_USER,
    NL2SQL_FALLBACK_SYSTEM,
)

logger = logging.getLogger(__name__)


# ─── Answer Generator ─────────────────────────────────────────────────────────

async def _generate_answer(
    user_question: str,
    spec: Dict[str, Any],
    result: Dict[str, Any],
) -> str:
    """
    Send the pre-computed QuerySpec + ExecutionResult to the LLM and ask it
    to format a direct, factual natural-language answer.

    The LLM receives computed facts, NOT raw rows — so it only needs to
    format, never compute.
    """
    # Build a compact result payload for the prompt
    prompt_result: Dict[str, Any] = {
        "empty": result.get("empty", True),
        "total_fetched": result.get("total_fetched", 0),
        "aggregate": result.get("aggregate", {}),
    }

    if result.get("groups"):
        prompt_result["group_breakdown"] = result["groups"]
    elif result.get("rows"):
        prompt_result["transactions"] = result["rows"][:10]  # cap at 10 rows

    user_content = NL2SQL_ANSWER_USER.format(
        question=user_question,
        spec=json.dumps(spec, indent=2, default=str),
        result=json.dumps(prompt_result, indent=2, default=str),
    )

    client = openai.OpenAI(
        api_key=settings.active_api_key,
        base_url=settings.active_base_url,
    )

    completion = client.chat.completions.create(
        model=settings.active_chat_model,
        messages=[
            {"role": "system", "content": NL2SQL_ANSWER_SYSTEM},
            {"role": "user",   "content": user_content},
        ],
        temperature=0.0,
        max_tokens=400,
    )

    return completion.choices[0].message.content.strip()


# ─── Legacy Data Fetcher (Fallback) ───────────────────────────────────────────

def _fetch_user_data(user_id: str) -> Dict[str, Any]:
    """
    Pull real user data from Supabase and return a structured dict:
      - transactions : list of dicts (last 200, newest first)
      - accounts     : list of account dicts
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
        logger.error("Failed to fetch transactions: %s", e)

    try:
        acc_res = (
            supabase.table("accounts")
            .select("account_name, account_type, current_balance")
            .eq("user_id", user_id)
            .execute()
        )
        data["accounts"] = acc_res.data or []
    except Exception as e:
        logger.error("Failed to fetch accounts: %s", e)

    return data


# ─── Legacy Pre-Aggregator (Fallback) ────────────────────────────────────────

def _build_summary(transactions: List[Dict], accounts: List[Dict]) -> Dict[str, Any]:
    """
    Compute key financial metrics in Python so the LLM receives FACTS,
    not raw JSON.  This guarantees precise numerical answers.
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

        # ── IMPORTANT LABELS (for LLM clarity) ──────────────────────
        # 'money_spent'    = EXPENSE transactions only (debits, withdrawals, payments)
        # 'money_received' = INCOME transactions only (credits, salary, refunds)
        "total_money_SPENT_inr": round(total_debit, 2),      # expenses only
        "total_money_RECEIVED_inr": round(total_credit, 2),  # income/credits only
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


# ─── Legacy Fallback Answer Generator ────────────────────────────────────────

def _fallback_answer(user_question: str, summary: Dict, recent_30: List[Dict]) -> str:
    """
    Legacy answer path: send the full pre-aggregated summary to the LLM.
    Used when plan_query() fails or returns a degenerate spec.
    """
    user_prompt = f"""User Question: {user_question}

A) PRE-COMPUTED SUMMARY (use these numbers to answer):
{json.dumps(summary, indent=2, default=str)}

B) RECENT 30 TRANSACTIONS (for row-level lookups):
{json.dumps(recent_30, indent=2, default=str)}

Answer the user's question directly using the data above."""

    client = openai.OpenAI(
        api_key=settings.active_api_key,
        base_url=settings.active_base_url,
    )

    completion = client.chat.completions.create(
        model=settings.active_chat_model,
        messages=[
            {"role": "system", "content": NL2SQL_FALLBACK_SYSTEM},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.0,
        max_tokens=600,
    )

    return completion.choices[0].message.content.strip()


# ─── Public Entry Point ───────────────────────────────────────────────────────

async def execute_nl2sql(user_id: str, user_question: str) -> str:
    """
    Answer the user's natural language question about their financial data.

    Primary path (v2 — Query Planner Pipeline):
      1. plan_query()    → QuerySpec JSON
      2. execute_query() → targeted Supabase fetch + Python aggregation
      3. _generate_answer() → direct factual answer from pre-computed results

    Fallback path (legacy — triggered when primary spec is degenerate):
      _fetch_user_data() → _build_summary() → _fallback_answer()
    """
    try:
        # ── Primary path ─────────────────────────────────────────────────

        # Step 1: Plan
        spec = await plan_query(user_question)
        logger.info("[NL2SQL] Planned spec: %s", json.dumps(spec))

        # Detect degenerate spec — if metric is "list" with NO filters at all,
        # fall through to the legacy summary path which gives a richer answer.
        is_degenerate = (
            spec.get("metric") == "list"
            and not spec.get("transaction_type")
            and not spec.get("merchant")
            and not spec.get("category")
            and not spec.get("date_from")
            and not spec.get("date_to")
            and not spec.get("group_by")
        )

        if not is_degenerate:
            # Step 2: Execute targeted query
            result = await execute_query(user_id, spec)

            if result.get("empty") and not result.get("error"):
                return (
                    "I couldn't find any transactions matching your query. "
                    "Try adjusting the date range, merchant name, or category."
                )

            if result.get("error"):
                # DB error — fall through to legacy path
                logger.warning("[NL2SQL] execute_query error, falling back: %s", result["error"])
            else:
                # Step 3: Generate answer from pre-computed facts
                return await _generate_answer(user_question, spec, result)

    except Exception as e:
        logger.error("[NL2SQL] Primary path failed: %s", e)

    # ── Fallback path (legacy) ────────────────────────────────────────────
    logger.info("[NL2SQL] Using legacy fallback path")
    try:
        raw_data     = _fetch_user_data(user_id)
        transactions = raw_data["transactions"]
        accounts     = raw_data["accounts"]

        if not transactions and not accounts:
            return (
                "I couldn't find any financial data for your account yet. "
                "Please upload a bank statement first so I can answer questions about your spending."
            )

        summary   = _build_summary(transactions, accounts)
        recent_30 = transactions[:30]
        return _fallback_answer(user_question, summary, recent_30)

    except Exception as e:
        logger.error("[NL2SQL] Fallback path also failed: %s", e)
        return f"I encountered an error while looking up your data: {str(e)}"
