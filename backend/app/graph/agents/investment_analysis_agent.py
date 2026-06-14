"""
Investment Analysis Agent — Performs direct portfolio, savings, and expense analysis
without generating SQL AST, and queries the LLM directly for natural language advice.
"""

from __future__ import annotations

import json
import logging
import urllib.request
import urllib.parse
from datetime import datetime
from typing import Dict, Any

from app.core.config import settings
from app.graph.logging_utils import graph_chat_completion
from app.graph.state import AgentState
from app.utils.supabase_client import supabase
from app.utils.prompts import INVESTMENT_ANALYSIS_SYSTEM, INVESTMENT_ANALYSIS_USER

logger = logging.getLogger(__name__)


def investment_analysis_agent(state: AgentState) -> dict:
    """
    Directly analyzes user portfolio, income/expense rates, and fixed expenses
    to generate natural language investment recommendations.
    """
    user_id = state.get("user_id") or ""
    query = state.get("rewritten_query") or state.get("user_query") or ""

    if not user_id:
        logger.error("[Agent:investment_analysis] Missing user_id in state")
        return {
            "raw_answer": "I could not locate your user profile. Please log in and try again.",
            "sources": ["Supabase Database"],
        }

    try:
        # 1. Fetch user profile information (income, rent, EMI)
        prof_res = supabase.table("user_profiles")\
            .select("income, fixed_rent, fixed_emi")\
            .eq("user_id", user_id)\
            .execute()
        profile_data = prof_res.data[0] if prof_res.data else {}
        monthly_income = float(profile_data.get("income") or 0.0)
        fixed_rent = float(profile_data.get("fixed_rent") or 0.0)
        fixed_emi = float(profile_data.get("fixed_emi") or 0.0)

        # 2. Fetch user investments
        inv_res = supabase.table("investments").select("*").eq("user_id", user_id).execute()
        db_investments = inv_res.data or []

        # 3. Get unique scheme codes to batch fetch current NAVs
        unique_schemes = list(set(inv["scheme_code"] for inv in db_investments))
        scheme_data_cache = {}

        for code in unique_schemes:
            try:
                url = f"https://api.mfapi.in/mf/{code}"
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req) as response:
                    parsed = json.loads(response.read().decode())
                    scheme_data_cache[code] = parsed
            except Exception as e:
                logger.error("[Agent:investment_analysis] Error fetching live NAV for scheme %s: %s", code, e)

        holdings_map = {}
        total_invested_val = 0.0
        total_current_val = 0.0

        for inv in db_investments:
            code = inv["scheme_code"]
            qty = float(inv["quantity"] or 0.0)
            purch_nav = float(inv["purchase_nav"] or 0.0)
            name = inv["scheme_name"]

            current_nav = purch_nav  # Fallback to purchase_nav
            if code in scheme_data_cache:
                nav_list = scheme_data_cache[code].get("data", [])
                if nav_list:
                    try:
                        current_nav = float(nav_list[0]["nav"])
                    except Exception:
                        pass

            if code not in holdings_map:
                holdings_map[code] = {
                    "name": name,
                    "quantity": 0.0,
                    "invested_value": 0.0,
                    "current_nav": current_nav,
                }
            holdings_map[code]["quantity"] += qty
            holdings_map[code]["invested_value"] += qty * purch_nav

        for code, h in holdings_map.items():
            qty = h["quantity"]
            invested = h["invested_value"]
            current_nav = h["current_nav"]
            current_value = qty * current_nav
            gain = current_value - invested
            gain_pct = (gain / invested * 100.0) if invested > 0 else 0.0

            total_invested_val += invested
            total_current_val += current_value

            h["current_value"] = current_value
            h["gain"] = gain
            h["gain_pct"] = gain_pct

        # Formulate portfolio summary lines
        portfolio_summary_lines = []
        for code, h in holdings_map.items():
            share = (h["current_value"] / total_current_val * 100.0) if total_current_val > 0 else 0.0
            portfolio_summary_lines.append(
                f"- Scheme: {h['name']} ({code})\n"
                f"  Quantity: {h['quantity']:.4f} units\n"
                f"  Invested: ₹{h['invested_value']:,.2f}\n"
                f"  Current NAV: ₹{h['current_nav']:,.2f}\n"
                f"  Current Value: ₹{h['current_value']:,.2f}\n"
                f"  Total Gain: ₹{h['gain']:,.2f} ({h['gain_pct']:.2f}%)\n"
                f"  Portfolio Share: {share:.2f}%"
            )

        total_gain_val = total_current_val - total_invested_val
        total_gain_pct = (total_gain_val / total_invested_val * 100.0) if total_invested_val > 0 else 0.0
        portfolio_header = (
            f"Portfolio Summary:\n"
            f"- Total Invested: ₹{total_invested_val:,.2f}\n"
            f"- Current Value: ₹{total_current_val:,.2f}\n"
            f"- Total Profit/Loss: ₹{total_gain_val:,.2f} ({total_gain_pct:.2f}%)\n\n"
            f"Detailed Holdings:\n"
        )
        portfolio_summary = portfolio_header + "\n".join(portfolio_summary_lines) if db_investments else "No active investments found."

        # 4. Fetch transactions to calculate aggregates
        tx_res = supabase.table("transactions")\
            .select("amount, transaction_type, transaction_date, categories(main_category)")\
            .eq("user_id", user_id)\
            .execute()
        transactions = tx_res.data or []

        total_income = 0.0
        total_expenses = 0.0
        category_totals = {}
        monthly_stats = {}

        for tx in transactions:
            tx_type = (tx.get("transaction_type") or "").lower()
            amount = abs(float(tx.get("amount") or 0.0))
            date_str = tx.get("transaction_date") or ""
            month_str = date_str[:7] if len(date_str) >= 7 else ""

            if tx_type == "income":
                total_income += amount
                if month_str:
                    if month_str not in monthly_stats:
                        monthly_stats[month_str] = {"income": 0.0, "expense": 0.0}
                    monthly_stats[month_str]["income"] += amount
            elif tx_type == "expense":
                total_expenses += amount
                if month_str:
                    if month_str not in monthly_stats:
                        monthly_stats[month_str] = {"income": 0.0, "expense": 0.0}
                    monthly_stats[month_str]["expense"] += amount

                # Category breakdown
                cat_obj = tx.get("categories") or {}
                main_cat = cat_obj.get("main_category") or "Others"
                category_totals[main_cat] = category_totals.get(main_cat, 0.0) + amount

        net_savings = total_income - total_expenses
        net_savings_rate = (net_savings / total_income * 100.0) if total_income > 0.0 else 0.0

        monthly_savings = []
        for m in sorted(monthly_stats.keys()):
            stats = monthly_stats[m]
            inc = stats["income"]
            exp = stats["expense"]
            net = inc - exp
            rate = (net / inc * 100.0) if inc > 0.0 else 0.0
            monthly_savings.append(f"- {m}: savings rate = {rate:.2f}% (income: ₹{inc:,.2f}, expense: ₹{exp:,.2f})")
        monthly_savings_str = "\n".join(monthly_savings) if monthly_savings else "No monthly transaction history found."

        category_expenses_lines = []
        for cat, amt in sorted(category_totals.items(), key=lambda x: x[1], reverse=True):
            category_expenses_lines.append(f"- {cat}: ₹{amt:,.2f}")
        category_expenses_str = "\n".join(category_expenses_lines) if category_expenses_lines else "No expenses logged."

        # 5. Format prompt and run LLM
        user_msg = INVESTMENT_ANALYSIS_USER.format(
            monthly_income=f"₹{monthly_income:,.2f}",
            fixed_rent=f"₹{fixed_rent:,.2f}",
            fixed_emi=f"₹{fixed_emi:,.2f}",
            portfolio_summary=portfolio_summary,
            net_savings=f"₹{net_savings:,.2f}",
            net_savings_rate=f"{net_savings_rate:.2f}%",
            monthly_savings_trajectory=monthly_savings_str,
            category_expenses=category_expenses_str,
            query=query,
        )

        response = graph_chat_completion(
            node="investment_analysis_agent",
            purpose="portfolio_guidance",
            model=settings.active_chat_model,
            messages=[
                {"role": "system", "content": INVESTMENT_ANALYSIS_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=800,
            temperature=0.2,
        )
        answer = response.choices[0].message.content.strip()
        logger.info("[Agent:investment_analysis] Completed investment analysis for user: %s", user_id)
        sources = ["Supabase Investments", "Supabase Transactions", "Supabase User Profiles"]
    except Exception as exc:
        logger.error("[Agent:investment_analysis] Portfolio analysis failed: %s", exc)
        answer = "I encountered an error while analyzing your portfolio. Please try again in a moment."
        sources = ["System Fallback"]

    return {
        "raw_answer": answer,
        "sources": sources,
    }
