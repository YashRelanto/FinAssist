"""Unit tests for financial health insights service."""

from app.services.financial_health_insights_service import (
    build_financial_health_insights_payload,
    build_health_insight_facts,
    _rule_based_health_insights,
)


def _sample_health():
    return {
        "score": 45,
        "label": "Fair",
        "savings_rate": 8.0,
        "monthly_commitments_pct": 42.0,
        "monthly_commitments_inr": 42000.0,
        "net_savings": -5000.0,
        "emergency_buffer_months": 1.5,
        "avg_credit_utilization_pct": 55.0,
        "total_liquid_balance": 50000.0,
    }


def test_build_health_insight_facts_weak_pillars():
    facts = build_health_insight_facts(
        _sample_health(),
        profile={"income": 100000, "fixed_rent": 25000, "fixed_emi": 17000},
    )
    assert facts["health_score"]["score"] == 45
    assert "Savings Rate" in facts["weak_pillars"]
    assert len(facts["improvement_triggers"]) >= 2
    assert facts["metrics"]["net_savings_inr"] == -5000.0


def test_rule_based_health_insights():
    facts = build_health_insight_facts(_sample_health())
    insights = _rule_based_health_insights(facts)
    assert "45" in insights["analysis"][0]
    assert isinstance(insights["analysis"], list)
    assert len(insights["recommendations"]) >= 1
    assert len(insights["pillar_insights"]) >= 3
    assert insights["source"] == "rule_based"


def test_build_financial_health_insights_payload_instant():
    payload = build_financial_health_insights_payload(_sample_health())
    assert payload["success"] is True
    assert payload["score"] == 45
    assert isinstance(payload["analysis"], list)
    assert payload["analysis"]
    assert payload["recommendations"]
    assert payload["source"] == "rule_based"
    assert payload["llm_status"] == "skipped"


def test_monthly_commitments_terminology_in_facts():
    facts = build_health_insight_facts(_sample_health())
    assert facts["metrics"]["monthly_commitments_pct"] == 42.0
    assert "debt-to-income" in facts["terminology"]["forbidden_terms"]
    assert facts["monthly_commitments"]["label"] == "Monthly Commitments"
