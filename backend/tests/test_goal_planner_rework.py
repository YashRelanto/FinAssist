"""Unit tests for the 2026-06-20 goal planner rework (pure functions, no DB)."""

from app.graph.tools.goal_planner_tool import (
    _max_sustainable_save,
    _minimal_deployment,
)


def _agg(**over):
    """A synthetic financial snapshot with the fields the scenario builders read."""
    base = {
        "monthly_net_flow": 18000.0,
        "total_spending_cuts": 2000.0,
        "monthly_avg_income": 60000.0,
        "monthly_avg_spend": 42000.0,
        "total_current_balance": 0.0,
        "liquid_fund_value": 0.0,
        "fd_funding_view": [],
        "funding_selection": {"bank_use_pct": 90.0, "use_liquid_funds": True, "break_fds": "auto"},
        "portfolio_value": 0.0,
    }
    base.update(over)
    return base


def test_max_sustainable_save_adds_cuts_to_surplus():
    assert _max_sustainable_save(_agg()) == 20000.0


def test_max_sustainable_save_clamps_negative_surplus():
    assert _max_sustainable_save(_agg(monthly_net_flow=-5000.0, total_spending_cuts=0.0)) == 0.0


def test_minimal_deployment_redeems_exact_liquid_first_no_fd_break():
    agg = _agg(
        liquid_fund_value=60000.0,
        fd_funding_view=[
            {"bank_name": "SBI", "matures_by_goal_end": False, "usable_value": 100000.0, "penalty_if_broken": 1200.0},
        ],
    )
    out = _minimal_deployment(50000.0, agg)
    assert out["from_liquid"] == 50000.0
    assert out["from_fds_broken"] == 0.0
    assert out["fds_broken"] == []
    assert out["deployed_total"] == 50000.0
    assert out["shortfall_uncovered"] == 0.0


def test_minimal_deployment_breaks_fd_closest_to_remaining_need():
    # No liquid, no bank: must break an FD — choose the one CLOSEST to 50k, not the biggest.
    agg = _agg(
        liquid_fund_value=0.0,
        total_current_balance=0.0,
        fd_funding_view=[
            {"bank_name": "HDFC", "matures_by_goal_end": False, "usable_value": 200000.0, "penalty_if_broken": 5000.0},
            {"bank_name": "SBI", "matures_by_goal_end": False, "usable_value": 55000.0, "penalty_if_broken": 1200.0},
        ],
    )
    out = _minimal_deployment(50000.0, agg)
    assert out["fds_broken"] == ["SBI"]
    assert out["penalty_paid"] == 1200.0
    assert out["deployed_total"] == 50000.0


def test_minimal_deployment_uses_matured_fd_free_before_breaking():
    agg = _agg(
        liquid_fund_value=0.0,
        fd_funding_view=[
            {"bank_name": "ICICI", "matures_by_goal_end": True, "usable_value": 80000.0, "penalty_if_broken": 0.0},
            {"bank_name": "SBI", "matures_by_goal_end": False, "usable_value": 100000.0, "penalty_if_broken": 3000.0},
        ],
    )
    out = _minimal_deployment(50000.0, agg)
    assert out["from_fds_matured"] == 50000.0
    assert out["from_fds_broken"] == 0.0
    assert out["penalty_paid"] == 0.0
