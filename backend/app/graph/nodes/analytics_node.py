"""
Analytics Node — Python-based mathematical and statistical calculations on SQL results.
"""

from __future__ import annotations

import logging
import math
from typing import Dict, Any

from app.graph.state import AgentState

logger = logging.getLogger(__name__)


def analytics_node(state: AgentState) -> dict:
    """
    Computes post-SQL statistics (period totals, category breakdowns, monthly trends,
    A/B differences, and z-score anomaly detection) in pure Python.
    """
    sql_results = state.get("sql_results") or []
    selected_agent = state.get("selected_agent") or "transaction"
    resolved_entities = state.get("resolved_entities") or {}

    analytics_results = {}

    if not sql_results:
        logger.info("[Node:analytics] No SQL results to analyze")
        return {"analytics_results": {"status": "no_data"}}

    # Support dict type (e.g. split comparison results)
    if isinstance(sql_results, dict):
        target_a_results = sql_results.get("target_a") or []
        target_b_results = sql_results.get("target_b") or []

        sum_a = sum(float(r.get("amount") or 0.0) for r in target_a_results if "amount" in r)
        sum_b = sum(float(r.get("amount") or 0.0) for r in target_b_results if "amount" in r)

        diff = sum_a - sum_b
        pct_change = (diff / sum_b * 100.0) if sum_b != 0 else 0.0

        analytics_results["comparison"] = {
            "target_a_total": sum_a,
            "target_b_total": sum_b,
            "difference": diff,
            "pct_change": pct_change,
        }
        logger.info("[Node:analytics] Computed dict comparison: A=%f B=%f diff=%f pct=%.2f%%", sum_a, sum_b, diff, pct_change)
        return {"analytics_results": analytics_results}

    # Extract amounts if present in results
    amounts = []
    for r in sql_results:
        if isinstance(r, dict) and "amount" in r and r["amount"] is not None:
            try:
                amounts.append(float(r["amount"]))
            except (ValueError, TypeError):
                pass

    if amounts:
        total = sum(amounts)
        count = len(amounts)
        avg = total / count
        analytics_results.update({
            "total_amount": total,
            "average_amount": avg,
            "count": count,
            "max_amount": max(amounts),
            "min_amount": min(amounts),
        })
    else:
        # Check if pre-aggregated columns exist
        numeric_col = None
        if sql_results and isinstance(sql_results[0], dict):
            for k in sql_results[0].keys():
                if k in ("total", "total_spent", "amount_sum", "sum"):
                    numeric_col = k
                    break
            if not numeric_col:
                for k, v in sql_results[0].items():
                    if isinstance(v, (int, float)):
                        numeric_col = k
                        break
        if numeric_col:
            total_sum = sum(float(r[numeric_col]) for r in sql_results if r.get(numeric_col) is not None)
            analytics_results["total_amount"] = total_sum
            analytics_results["count"] = len(sql_results)

    # ── 1. Trend Calculations ──
    if selected_agent == "trend":
        monthly_data = {}
        for r in sql_results:
            if not isinstance(r, dict):
                continue
            date_val = r.get("transaction_date") or r.get("month") or r.get("week")
            amt = float(r.get("amount") or r.get("total") or r.get("total_spent") or 0.0)
            if date_val:
                month_key = str(date_val)[:7]  # YYYY-MM
                monthly_data[month_key] = monthly_data.get(month_key, 0.0) + amt

        sorted_months = sorted(monthly_data.items())

        trend_list = []
        for i, (m, val) in enumerate(sorted_months):
            prev_val = sorted_months[i-1][1] if i > 0 else None
            growth = ((val - prev_val) / prev_val * 100.0) if prev_val else 0.0

            # 3-month moving average
            ma_vals = [sorted_months[j][1] for j in range(max(0, i-2), i+1)]
            moving_avg = sum(ma_vals) / len(ma_vals)

            trend_list.append({
                "period": m,
                "amount": val,
                "growth_rate": growth,
                "moving_average": moving_avg,
            })

        analytics_results["trend"] = trend_list
        logger.info("[Node:analytics] Computed trends for %d periods", len(trend_list))

    # ── 2. Comparison Calculations ──
    elif selected_agent == "comparison":
        comp_info = resolved_entities.get("comparison") or {}
        targets = comp_info.get("targets") or []

        if len(targets) >= 2:
            target_a, target_b = targets[0], targets[1]
            part_a = []
            part_b = []
            for r in sql_results:
                if not isinstance(r, dict):
                    continue
                target_key = r.get("comparison_target") or r.get("target")
                if target_key:
                    if str(target_key).lower() == str(target_a).lower():
                        part_a.append(r)
                    elif str(target_key).lower() == str(target_b).lower():
                        part_b.append(r)
                else:
                    cat = r.get("main_category")
                    if not cat:
                        cat_obj = r.get("categories")
                        if isinstance(cat_obj, dict):
                            cat = cat_obj.get("main_category")
                    cat = str(cat or "").lower()

                    merch = str(r.get("merchant_name") or "").lower()
                    if target_a.lower() in cat or target_a.lower() in merch:
                        part_a.append(r)
                    elif target_b.lower() in cat or target_b.lower() in merch:
                        part_b.append(r)

            sum_a = sum(float(r.get("amount") or 0.0) for r in part_a)
            sum_b = sum(float(r.get("amount") or 0.0) for r in part_b)
            diff = sum_a - sum_b
            pct_change = (diff / sum_b * 100.0) if sum_b != 0 else 0.0

            analytics_results["comparison"] = {
                "target_a_name": target_a,
                "target_b_name": target_b,
                "target_a_total": sum_a,
                "target_b_total": sum_b,
                "difference": diff,
                "pct_change": pct_change,
            }
            logger.info("[Node:analytics] Computed comparison: A=%s (total=%f) B=%s (total=%f)", target_a, sum_a, target_b, sum_b)

    # ── 3. Anomaly Detection ──
    elif selected_agent == "anomaly":
        if amounts and len(amounts) >= 3:
            mean = sum(amounts) / len(amounts)
            variance = sum((x - mean) ** 2 for x in amounts) / len(amounts)
            std_dev = math.sqrt(variance)

            anomalies = []
            if std_dev > 0:
                for r in sql_results:
                    if not isinstance(r, dict):
                        continue
                    amt = float(r.get("amount") or 0.0)
                    z_score = (amt - mean) / std_dev
                    if z_score > 2.0:
                        anomalies.append({
                            "transaction_id": r.get("transaction_id"),
                            "transaction_date": r.get("transaction_date"),
                            "amount": amt,
                            "merchant_name": r.get("merchant_name"),
                            "main_category": r.get("main_category"),
                            "z_score": z_score,
                        })
            analytics_results["anomalies"] = anomalies
            analytics_results["mean"] = mean
            analytics_results["std_dev"] = std_dev
            logger.info("[Node:analytics] Found %d anomalies among %d transactions", len(anomalies), len(amounts))

    # ── 4. General Breakdown ──
    if sql_results and isinstance(sql_results[0], dict):
        category_totals = {}
        merchant_totals = {}

        for r in sql_results:
            if not isinstance(r, dict):
                continue
            amt = float(r.get("amount") or 0.0)
            if amt > 0:
                cat = r.get("main_category")
                if not cat:
                    cat_obj = r.get("categories")
                    if isinstance(cat_obj, dict):
                        cat = cat_obj.get("main_category")
                if not cat:
                    cat = r.get("category_id") or "Uncategorized"

                category_totals[cat] = category_totals.get(cat, 0.0) + amt
                merch = r.get("merchant_name")
                if merch:
                    merchant_totals[merch] = merchant_totals.get(merch, 0.0) + amt

        if category_totals:
            analytics_results["category_breakdown"] = sorted(category_totals.items(), key=lambda x: x[1], reverse=True)
        if merchant_totals:
            analytics_results["merchant_breakdown"] = sorted(merchant_totals.items(), key=lambda x: x[1], reverse=True)

    return {"analytics_results": analytics_results}
