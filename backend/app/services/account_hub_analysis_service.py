"""LLM-powered account hub analysis for the dashboard quick-actions panel."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any

import openai

from app.constants.categories import PREDEFINED_MAIN_CATEGORIES
from app.core.config import settings
from app.services.accounts_service import fetch_user_accounts
from app.utils.supabase_client import supabase

logger = logging.getLogger(__name__)

CREDIT_UTILIZATION_WARNING_THRESHOLD = 0.80
NVIDIA_NIM_BASE_URL = settings.NVIDIA_BASE_URL
ACCOUNT_HUB_LLM_MODEL = settings.account_hub_model


def _month_start(today: date | None = None) -> date:
    ref = today or datetime.now(timezone.utc).date()
    return date(ref.year, ref.month, 1)


def _fetch_accounts(user_id: str) -> list[dict[str, Any]]:
    return fetch_user_accounts(user_id)


def _fetch_month_expense_transactions(user_id: str) -> list[dict[str, Any]]:
    if supabase is None:
        raise RuntimeError("Supabase is not configured")

    month_start = _month_start().isoformat()
    res = (
        supabase.table("transactions")
        .select(
            "amount, transaction_type, transaction_date, account_id, "
            "categories(main_category), accounts(account_name)"
        )
        .eq("user_id", user_id)
        .eq("transaction_type", "expense")
        .gte("transaction_date", month_start)
        .execute()
    )
    return res.data or []


def _normalize_category(raw: str | None) -> str:
    if not raw:
        return "others"
    normalized = raw.strip()
    for cat in PREDEFINED_MAIN_CATEGORIES:
        if cat.lower() == normalized.lower():
            return cat
    return "others"


def _credit_card_context(accounts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for acc in accounts:
        if (acc.get("account_type") or "").lower() != "credit_card":
            continue
        limit_raw = acc.get("credit_limit")
        if limit_raw is None:
            continue
        credit_limit = float(limit_raw)
        if credit_limit <= 0:
            continue
        borrowed = abs(float(acc.get("current_balance") or 0))
        utilization = borrowed / credit_limit if credit_limit else 0.0
        cards.append(
            {
                "account": acc.get("account_name") or "Credit Card",
                "borrowed": round(borrowed, 2),
                "credit_limit": round(credit_limit, 2),
                "utilization_pct": round(utilization * 100, 1),
                "near_limit": utilization >= CREDIT_UTILIZATION_WARNING_THRESHOLD,
            }
        )
    return cards


def _transactions_for_prompt(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prompt_rows: list[dict[str, Any]] = []
    for row in rows:
        accounts = row.get("accounts") or {}
        categories = row.get("categories") or {}
        account_name = accounts.get("account_name") or "Unknown"
        category = _normalize_category(categories.get("main_category"))
        amount = abs(float(row.get("amount") or 0))
        if amount <= 0:
            continue
        prompt_rows.append(
            {
                "account": account_name,
                "amount": round(amount, 2),
                "category": category,
            }
        )
    return prompt_rows


def _fallback_credit_alerts(credit_cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    for card in credit_cards:
        if not card.get("near_limit"):
            continue
        alerts.append(
            {
                "account": card["account"],
                "borrowed": card["borrowed"],
                "credit_limit": card["credit_limit"],
                "utilization_pct": card["utilization_pct"],
                "severity": "warning",
                "message": (
                    f"You have borrowed ₹{card['borrowed']:,.0f} of your "
                    f"₹{card['credit_limit']:,.0f} limit on {card['account']} "
                    f"({card['utilization_pct']:.1f}% utilized). Consider paying down "
                    "the balance to avoid high utilization."
                ),
            }
        )
    return alerts


def _fallback_account_spending(transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for tx in transactions:
        totals[tx["account"]][tx["category"]] += float(tx["amount"])

    insights: list[dict[str, Any]] = []
    for account, categories in totals.items():
        if not categories:
            continue
        majority_category, amount = max(categories.items(), key=lambda item: item[1])
        insights.append(
            {
                "account": account,
                "majority_category": majority_category,
                "analysis": (
                    f"You are spending the most amount from {account} on {majority_category}."
                ),
                "category_total": round(amount, 2),
            }
        )
    return insights


def _call_llm(payload: dict[str, Any]) -> dict[str, Any] | None:
    if not settings.NVIDIA_API_KEY:
        logger.warning("NVIDIA_API_KEY missing — using rule-based account hub analysis")
        return None

    logger.info(
        "Account hub analysis via NVIDIA NIM model=%s base_url=%s",
        ACCOUNT_HUB_LLM_MODEL,
        NVIDIA_NIM_BASE_URL,
    )

    month_label = datetime.now(timezone.utc).strftime("%B %Y")
    system_prompt = (
        "You are FinAssist, a concise personal finance analyst for Indian users.\n"
        "Analyze the user's linked accounts using ONLY the JSON data provided.\n"
        "Predefined categories (use exactly these names): "
        f"{', '.join(PREDEFINED_MAIN_CATEGORIES)}.\n\n"
        "Return ONLY valid JSON with this exact shape:\n"
        "{\n"
        '  "credit_card_alerts": [\n'
        "    {\n"
        '      "account": string,\n'
        '      "borrowed": number,\n'
        '      "credit_limit": number,\n'
        '      "utilization_pct": number,\n'
        '      "severity": "warning" | "info",\n'
        '      "message": string\n'
        "    }\n"
        "  ],\n"
        '  "account_spending": [\n'
        "    {\n"
        '      "account": string,\n'
        '      "majority_category": string,\n'
        '      "analysis": string\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Rules:\n"
        "- Include a credit_card_alerts entry for each credit card where borrowed amount is "
        f">= {int(CREDIT_UTILIZATION_WARNING_THRESHOLD * 100)}% of the credit limit. "
        "Use severity \"warning\" when near/at limit.\n"
        "- For account_spending, use ONLY the current-month expense transactions. "
        "For each account with expenses, pick the category with the highest total amount "
        "as majority_category and write a one-sentence analysis like: "
        "\"You are spending the most amount from HDFC on Food & Drinks.\"\n"
        "- If there are no credit cards or no near-limit cards, return an empty "
        "credit_card_alerts array.\n"
        "- If there are no transactions, return an empty account_spending array.\n"
        "- Do not invent accounts, amounts, or categories."
    )

    user_content = json.dumps(
        {
            "month": month_label,
            "credit_cards": payload["credit_cards"],
            "transactions": payload["transactions"],
        },
        ensure_ascii=False,
    )
    request_body = {
        "model": ACCOUNT_HUB_LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "max_tokens": 700,
        "temperature": 0.2,
        "top_p": 0.7,
    }
    logger.info("Account hub LLM request body: %s", json.dumps(request_body, ensure_ascii=False))

    try:
        client = openai.OpenAI(
            api_key=settings.NVIDIA_API_KEY,
            base_url=NVIDIA_NIM_BASE_URL,
            timeout=5.0,
        )
        completion = client.chat.completions.create(**request_body)
        raw = (completion.choices[0].message.content or "").strip()
        logger.error("Account hub LLM response body: %s", raw)
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception as exc:
        logger.error("Account hub LLM analysis failed: %s", exc)
    return None


def generate_account_hub_analysis(user_id: str) -> dict[str, Any]:
    accounts = _fetch_accounts(user_id)
    month_rows = _fetch_month_expense_transactions(user_id)
    credit_cards = _credit_card_context(accounts)
    transactions = _transactions_for_prompt(month_rows)
    month_label = datetime.now(timezone.utc).strftime("%B %Y")

    if not accounts:
        return {
            "success": True,
            "month": month_label,
            "credit_card_alerts": [],
            "account_spending": [],
            "summary": "Link an account to receive personalized spending insights.",
            "has_accounts": False,
        }

    llm_result = _call_llm(
        {"credit_cards": credit_cards, "transactions": transactions},
    )

    if llm_result:
        credit_alerts = llm_result.get("credit_card_alerts") or []
        account_spending = llm_result.get("account_spending") or []
    else:
        credit_alerts = _fallback_credit_alerts(credit_cards)
        account_spending = _fallback_account_spending(transactions)

    return {
        "success": True,
        "month": month_label,
        "credit_card_alerts": credit_alerts,
        "account_spending": account_spending,
        "has_accounts": True,
        "transaction_count": len(transactions),
    }
