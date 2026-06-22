"""Unit tests for financial insights service."""

from app.services.financial_insights_service import (
    build_financial_insights_payload,
    build_precomputed_insight_facts,
    _narrate_from_facts,
    _normalize_merchant_insights,
)


def _sample_analytics():
    return {
        "period": "3m",
        "period_label": "Apr 2026 – May 2026",
        "total_spend": 5000,
        "transaction_count": 12,
        "category_trends": [
            {
                "category": "Food & Drinks",
                "total": 2000,
                "consecutive_growth_months": 3,
                "mom_change_pct": 15.0,
                "monthly_evolution": [
                    {"month": "2026-04", "label": "Apr", "amount": 800},
                    {"month": "2026-05", "label": "May", "amount": 1200},
                ],
            }
        ],
        "category_share": [
            {"category": "Food & Drinks", "amount": 2000, "pct": 40},
            {"category": "Shopping", "amount": 1500, "pct": 30},
        ],
        "merchant_analytics": {
            "top_merchants": [{"name": "Swiggy", "total": 1500, "txn_count": 8}],
            "merchant_growth": [
                {
                    "name": "Swiggy",
                    "current_total": 1500,
                    "prior_total": 1000,
                    "growth_pct": 50,
                }
            ],
            "concentration": {"top_n": 5, "pct_of_total": 47},
        },
        "spending_behavior": {
            "weekday_vs_weekend": {
                "weekday_total": 2000,
                "weekend_total": 3000,
                "weekday_avg_per_day": 200.0,
                "weekend_avg_per_day": 500.0,
                "weekend_multiplier": 2.5,
                "weekend_elevated": True,
            },
            "weekend_insight": "Weekend spending averages 2.5× more per day than weekdays.",
            "day_of_week_heatmap": [
                {"day": "Sat", "amount": 500, "intensity": 5},
                {"day": "Mon", "amount": 100, "intensity": 1},
            ],
            "transaction_frequency": {
                "avg_per_day": 4,
                "total_days_with_txns": 10,
                "total_txns": 42,
            },
        },
    }


def test_precomputed_facts_include_all_aggregates():
    facts = build_precomputed_insight_facts(
        _sample_analytics(),
        predicted_next_month=5500,
        predicted_month_label="June 2026",
    )
    assert facts["spending_summary"]["total_spend_inr"] == 5000
    assert facts["category_trends"][0]["trend_label"] == "rising_streak"
    assert facts["merchants"]["fastest_growing"]["name"] == "Swiggy"
    assert facts["behavior"]["peak_spending_day"] == "Sat"
    assert facts["flags"]["weekend_spending_elevated"] is True
    assert facts["recommendation_triggers"]


def test_narrate_from_facts_fields():
    facts = build_precomputed_insight_facts(
        _sample_analytics(),
        predicted_next_month=5500,
        predicted_month_label="June 2026",
    )
    result = _narrate_from_facts(facts)
    assert "executive_summary" in result
    assert result["recommendations"]
    assert result["category_trends"][0]["insight"]
    assert result["merchant_insights"]["fastest_growing"]
    assert result["behavior_insights"]["weekend"]
    assert result["source"] == "rule_based"


def test_normalize_merchant_insights_coerces_objects_to_strings():
    facts = build_precomputed_insight_facts(_sample_analytics())
    normalized = _normalize_merchant_insights(
        {
            "fastest_growing": facts["merchants"]["fastest_growing"],
            "concentration": facts["merchants"]["concentration"],
        },
        facts,
    )
    assert isinstance(normalized["fastest_growing"], str)
    assert isinstance(normalized["concentration"], str)
    assert "Swiggy" in normalized["fastest_growing"]
    assert "47%" in normalized["concentration"]


def test_build_financial_insights_payload_fallback():
    payload = build_financial_insights_payload(
        _sample_analytics(),
        predicted_next_month=5500,
    )
    assert payload["success"] is True
    assert payload["executive_summary"]
    assert payload["category_analysis"]
