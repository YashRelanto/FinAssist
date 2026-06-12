"""
Answer Node — Generates final natural language answers based on intent and query results.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Dict, Any

from langchain_core.messages import HumanMessage, AIMessage

from app.core.config import settings
from app.graph.logging_utils import graph_chat_completion
from app.graph.state import AgentState
from app.utils.workflow_logic import WorkflowLogic
from app.utils.prompts import (
    ANSWER_SYSTEM,
    ANSWER_USER,
    ANSWER_KNOWLEDGE_SYSTEM,
    FINASSIST_SYSTEM_PROMPT,
    BRAIN_ANSWER_SYSTEM,
    BRAIN_ANSWER_USER,
)

logger = logging.getLogger(__name__)


def answer_node(state: AgentState) -> dict:
    """
    Generates the final natural language answer using LLM.
    Routes to two distinct formatting pipelines:
      1. RAG/Knowledge + Goal Planning -> uses ANSWER_KNOWLEDGE_SYSTEM
      2. Transaction Agents -> uses ANSWER_SYSTEM + SQL + Analytics
    """
    intent = state.get("intent") or "FINANCIAL_KNOWLEDGE"
    selected_agent = state.get("selected_agent") or "knowledge"
    user_query = state.get("user_query") or ""
    standalone_query = state.get("standalone_query") or state.get("rewritten_query") or user_query
    lc_messages = state.get("messages") or []
    final_context = state.get("final_context") or {}
    execution_plan = state.get("execution_plan") or {}

    is_brain_path = bool(execution_plan.get("tools")) and bool(final_context)
    is_knowledge_path = (intent == "GOAL_PLANNING" or selected_agent == "knowledge")

    try:
        if is_brain_path and intent != "GOAL_PLANNING":
            profile = state.get("user_profile") or {}
            income = profile.get("income", "unknown")
            annual_income = profile.get("annual_income", income)
            income_display = (
                f"₹{annual_income:,.0f} per annum"
                if isinstance(annual_income, (int, float))
                else str(annual_income)
            )

            system_prompt = BRAIN_ANSWER_SYSTEM.format(
                final_context=json.dumps(final_context, indent=2, default=str),
                income_display=income_display,
                risk_profile=profile.get("risk_profile", "Moderate"),
                city=profile.get("city", "India"),
                monthly_net_flow=profile.get("monthly_net_flow", "N/A"),
            )

            completion = graph_chat_completion(
                node="answer_node",
                purpose="brain_answer",
                model=settings.active_chat_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": BRAIN_ANSWER_USER.format(query=standalone_query)},
                ],
                max_tokens=500,
                temperature=0.2,
            )
            answer = completion.choices[0].message.content.strip()

            sources = []
            if state.get("rag_results", {}).get("sources"):
                sources.extend(state["rag_results"]["sources"])
            if state.get("agent_results"):
                sources.append("Supabase Transactions")
            if state.get("portfolio_results", {}).get("portfolio_health"):
                sources.append("Portfolio Analysis")
            sources = sources or ["FinAssist Brain"]

        elif is_knowledge_path:
            # ── 1. RAG / Advisor / Goal Planning Path ──
            profile = state.get("user_profile") or {}
            context_blocks = state.get("retrieved_context") or []
            source_refs = state.get("context_sources") or []
            min_distance = state.get("rag_confidence") or 1.0
            workflow_state = state.get("workflow_state") or {}

            # Construct context text
            if context_blocks and min_distance <= 0.6:
                context_text = "\n\n---\n\n".join(context_blocks)
                sources = source_refs if source_refs else ["FinAssist Knowledge Base"]
            else:
                logger.info("[Node:answer] Low RAG confidence (%.3f) — using LLM general knowledge", min_distance)
                context_text = (
                    "No highly relevant documents found in the knowledge base. "
                    "Use your general financial expertise to answer, while maintaining safety guidelines."
                )
                sources = ["FinAssist General Knowledge"]

            # If coming from a completed HITL workflow, inject the collected slots
            if workflow_state and workflow_state.get("collected_information"):
                slots_str = WorkflowLogic.format_filled_slots(workflow_state["collected_information"])
                context_text = (
                    f"User Scenario Details (ALL these details are already provided):\n{slots_str}\n\n{context_text}"
                )

            # Format user profile values
            income = profile.get("income", "unknown")
            annual_income = profile.get("annual_income", income)
            segment = profile.get("segment", "General")
            city = profile.get("city", "India")
            risk_profile = profile.get("risk_profile", "Moderate")
            credit_score = profile.get("credit_score", "N/A")
            current_date = datetime.now().strftime("%d %B %Y")
            income_display = f"₹{annual_income:,.0f} per annum" if isinstance(annual_income, (int, float)) else str(annual_income)
            real_time_balances = profile.get("real_time_balances", "N/A")
            monthly_net_flow = profile.get("monthly_net_flow", "N/A")

            system_prompt_template = FINASSIST_SYSTEM_PROMPT if intent == "GOAL_PLANNING" else ANSWER_KNOWLEDGE_SYSTEM
            system_prompt = system_prompt_template.format(
                current_date=current_date,
                income_display=income_display,
                segment=segment,
                city=city,
                risk_profile=risk_profile,
                credit_score=credit_score,
                real_time_balances=real_time_balances,
                monthly_net_flow=monthly_net_flow,
                context_text=context_text,
            )

            # Build messages list including last 10 turns of history
            recent_history = []
            for m in lc_messages[-11:-1]:
                if isinstance(m, HumanMessage) or m.__class__.__name__ == "HumanMessage":
                    recent_history.append({"role": "user", "content": m.content})
                elif isinstance(m, AIMessage) or m.__class__.__name__ == "AIMessage":
                    recent_history.append({"role": "assistant", "content": m.content})

            messages_for_llm = [{"role": "system", "content": system_prompt}]
            messages_for_llm.extend(recent_history)
            messages_for_llm.append({"role": "user", "content": user_query})

            completion = graph_chat_completion(
                node="answer_node",
                purpose="knowledge_answer",
                model=settings.active_chat_model,
                messages=messages_for_llm,
                max_tokens=700,
                temperature=0.2,
            )
            answer = completion.choices[0].message.content.strip()

        else:
            # ── 2. Transaction / SQL / Analytics Path ──
            sql_query = state.get("sql_query") or "No query executed"
            sql_results = state.get("sql_results") or []
            analytics_results = state.get("analytics_results") or {}

            # Fallback message if query execution failed or no database connection
            sql_error = state.get("sql_error")
            if sql_error:
                answer = f"I encountered an error while retrieving your transaction details: {sql_error}"
                sources = ["Supabase Database Connection"]
            else:
                user_msg = ANSWER_USER.format(
                    question=user_query,
                    sql_summary=sql_query,
                    results=json.dumps(sql_results, indent=2),
                    analytics=json.dumps(analytics_results, indent=2),
                )

                completion = graph_chat_completion(
                    node="answer_node",
                    purpose="sql_analytics_answer",
                    model=settings.active_chat_model,
                    messages=[
                        {"role": "system", "content": ANSWER_SYSTEM},
                        {"role": "user", "content": user_msg},
                    ],
                    max_tokens=300,
                    temperature=0.0,
                )
                answer = completion.choices[0].message.content.strip()
                sources = ["Supabase Transactions"]

    except Exception as exc:
        logger.error("[Node:answer] LLM call failed: %s", exc)
        answer = "I encountered a temporary issue generating your response. Please try again in a moment."
        sources = ["System Fallback"]

    return {
        "raw_answer": answer,
        "sources": sources,
        "final_intent": intent,
    }
