"""
Answer Node — synthesises the final structured response from collected evidence.

Produces:
  - final_answer : concise natural-language text
  - artifacts    : visualization specs (chart data filled deterministically from
                   evidence so no numbers are hallucinated)
  - sources      : attribution list

Mode is chosen from the evidence:
  goal_planner   → feasibility plan (FINASSIST_SYSTEM_PROMPT) + net-flow/savings bar
  investment     → tool-authored narrative + portfolio-allocation pie
  knowledge      → RAG answer (ANSWER_KNOWLEDGE_SYSTEM)
  nl2sql / data  → ANSWER_VIZ_SYSTEM (concise text + chart-type choice)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage

from app.core.config import settings
from app.graph.logging_utils import graph_chat_completion
from app.graph.state import AgentState
from app.utils.prompts import (
    ANSWER_VIZ_SYSTEM,
    ANSWER_KNOWLEDGE_SYSTEM,
    FINASSIST_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


# ── chart builders (deterministic — data comes only from evidence) ───────────

def _chart(chart_type: str, title: str, x: str, y: str, data: List[Dict]) -> Dict[str, Any]:
    return {"type": "chart", "chart_type": chart_type, "title": title,
            "x_field": x, "y_field": y, "data": data}


def _artifacts_from_analytics(analytics: Dict[str, Any], chart_type: str, title: str) -> List[Dict]:
    """Build a chart artifact from nl2sql analytics, honouring the requested type."""
    if not analytics or chart_type in (None, "none", ""):
        return []

    # Trend → line over time
    if chart_type == "line" and analytics.get("trend"):
        data = [{"period": p["period"], "amount": round(p["amount"], 2)} for p in analytics["trend"]]
        return [_chart("line", title or "Trend", "period", "amount", data)]

    # Comparison → two bars
    comp = analytics.get("comparison")
    if chart_type == "bar" and comp:
        data = [
            {"label": comp.get("target_a_name", "A"), "amount": round(comp.get("target_a_total", 0), 2)},
            {"label": comp.get("target_b_name", "B"), "amount": round(comp.get("target_b_total", 0), 2)},
        ]
        return [_chart("bar", title or "Comparison", "label", "amount", data)]

    # Category / merchant breakdown → bar or pie
    breakdown = analytics.get("category_breakdown") or analytics.get("merchant_breakdown")
    if breakdown and chart_type in ("bar", "pie"):
        data = [{"label": str(k), "amount": round(float(v), 2)} for k, v in breakdown[:10]]
        return [_chart(chart_type, title or "Breakdown", "label", "amount", data)]

    return []


def _portfolio_pie(inv_data: Dict[str, Any]) -> List[Dict]:
    holdings = inv_data.get("holdings") or []
    if not holdings:
        return []
    data = [{"label": h["name"], "value": h["share_pct"]} for h in holdings if h.get("share_pct")]
    return [_chart("pie", "Portfolio Allocation", "label", "value", data)] if data else []


def _goal_bar(goal: Dict[str, Any]) -> List[Dict]:
    needed = goal.get("monthly_savings_needed")
    net_flow = goal.get("monthly_net_flow")
    if needed is None or net_flow is None:
        return []
    return [_chart("bar", "Monthly Capacity vs. Savings Needed", "label", "amount", [
        {"label": "Net flow / month", "amount": round(net_flow, 2)},
        {"label": "Savings needed / month", "amount": round(needed, 2)},
    ])]


# ── profile helpers ──────────────────────────────────────────────────────────

def _profile_fields(profile: Dict[str, Any]) -> Dict[str, str]:
    income = profile.get("income", "unknown")
    income_display = f"₹{income:,.0f} per month" if isinstance(income, (int, float)) else str(income)
    return {
        "current_date": datetime.now().strftime("%d %B %Y"),
        "income_display": income_display,
        "city": str(profile.get("city", "India")),
        "real_time_balances": str(profile.get("real_time_balances", "N/A")),
        "monthly_net_flow": str(profile.get("monthly_net_flow", "N/A")),
    }


def _find(evidence: List[Dict], tool: str) -> Optional[Dict]:
    for e in evidence:
        if e.get("tool") == tool:
            return e
    return None


# ── node ───────────────────────────────────────────────────────────────────

def answer_node(state: AgentState) -> dict:
    evidence = state.get("evidence") or []
    user_query = state.get("user_query") or ""
    profile = state.get("user_profile") or {}
    sources = state.get("sources") or []

    goal_ev = _find(evidence, "goal_planner")
    inv_ev = _find(evidence, "investment")
    nl2sql_evs = [e for e in evidence if e.get("tool") == "nl2sql"]
    retrieved = state.get("retrieved_context") or []

    answer = ""
    artifacts: List[Dict] = []
    intent = "FINANCIAL_KNOWLEDGE"

    try:
        # ── Goal planning ──
        if goal_ev:
            intent = "GOAL_PLANNING"
            g = goal_ev.get("data") or {}
            ctx = json.dumps(g, indent=2, default=str)
            fields = _profile_fields(profile)
            system_prompt = FINASSIST_SYSTEM_PROMPT.format(context_text=ctx, **fields)
            completion = graph_chat_completion(
                node="answer_node", purpose="goal_plan", model=settings.active_chat_model,
                messages=[{"role": "system", "content": system_prompt},
                          {"role": "user", "content": user_query}],
                max_tokens=600, temperature=0.2,
            )
            answer = completion.choices[0].message.content.strip()
            artifacts = _goal_bar(g)

        # ── Investment ──
        elif inv_ev:
            intent = "PORTFOLIO_ANALYSIS"
            data = inv_ev.get("data") or {}
            answer = data.get("narrative") or "Here is your portfolio analysis."
            artifacts = _portfolio_pie(data)

        # ── Data (nl2sql) ──
        elif nl2sql_evs:
            intent = "TRANSACTION_QUERY"
            evidence_blob = json.dumps(
                [{"task": e.get("task"), "summary": e.get("summary"), "data": e.get("data")} for e in nl2sql_evs],
                indent=2, default=str,
            )
            completion = graph_chat_completion(
                node="answer_node", purpose="data_answer", model=settings.active_chat_model,
                messages=[{"role": "system", "content": ANSWER_VIZ_SYSTEM},
                          {"role": "user", "content": f"User question: {user_query}\n\nEvidence:\n{evidence_blob}"}],
                response_format={"type": "json_object"}, max_tokens=600, temperature=0.1,
            )
            parsed = json.loads(completion.choices[0].message.content.strip())
            answer = parsed.get("answer", "")
            chart = parsed.get("chart") or {}
            if parsed.get("needs_visualization") and chart.get("chart_type") not in (None, "none"):
                # Use the last nl2sql analytics (most complete) for chart data.
                analytics = (nl2sql_evs[-1].get("data") or {}).get("analytics") or {}
                artifacts = _artifacts_from_analytics(analytics, chart.get("chart_type"), chart.get("title", ""))
            if not sources:
                sources = ["Supabase Transactions"]

        # ── Knowledge / general fallback ──
        else:
            intent = "FINANCIAL_KNOWLEDGE"
            context_text = "\n\n---\n\n".join(retrieved) if retrieved else (
                "No specific documents retrieved. Use your general financial expertise to answer safely."
            )
            fields = _profile_fields(profile)
            system_prompt = ANSWER_KNOWLEDGE_SYSTEM.format(context_text=context_text, **fields)
            completion = graph_chat_completion(
                node="answer_node", purpose="knowledge_answer", model=settings.active_chat_model,
                messages=[{"role": "system", "content": system_prompt},
                          {"role": "user", "content": user_query}],
                max_tokens=600, temperature=0.2,
            )
            answer = completion.choices[0].message.content.strip()
            if not sources:
                sources = ["FinAssist Knowledge Base"]

    except Exception as exc:
        logger.error("[Node:answer] Synthesis failed: %s", exc)
        answer = "I encountered a temporary issue generating your response. Please try again in a moment."
        sources = sources or ["System Fallback"]

    logger.info("[Node:answer] intent=%s artifacts=%d", intent, len(artifacts))
    return {
        "final_answer": answer,
        "artifacts": artifacts,
        "sources": sources,
        "final_intent": intent,
        "messages": [AIMessage(content=answer)],
    }
