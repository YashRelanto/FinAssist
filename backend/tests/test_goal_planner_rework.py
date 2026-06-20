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


from app.graph.tools.goal_planner_tool import _loan_scenarios


def test_loan_scenario_a_is_pure_user_plan_no_asset_deployment():
    # User: 30% down, 18 months, no existing savings, big idle bank balance available.
    agg = _agg(total_current_balance=1500000.0)
    scenarios, _meta = _loan_scenarios(
        price=1000000.0, existing=0.0, user_months=18, user_dp_pct=30.0,
        surplus=18000.0, cuts=2000.0, rate=10.0, tenure=60, agg=agg, asset="car",
    )
    a = scenarios[0]
    assert a["tag"] == "A"
    assert a["down_payment_pct"] == 30.0                 # exactly the user's choice, unchanged
    assert a["down_payment_from_existing"] == 0.0        # A deploys NO assets
    assert a["deployment"]["deployed_total"] == 0.0


def test_loan_scenario_b_deploys_minimal_assets_to_fit_emi():
    # Short 6-month timeline: saving alone (cap 20k * 6 = 120k) can't reach the EMI-fitting down
    # payment, so B deploys minimal liquid-fund assets to bridge the gap.
    agg = _agg(liquid_fund_value=400000.0, total_current_balance=0.0)
    scenarios, _meta = _loan_scenarios(
        price=1000000.0, existing=0.0, user_months=6, user_dp_pct=30.0,
        surplus=18000.0, cuts=2000.0, rate=10.0, tenure=60, agg=agg, asset="car",
    )
    b = scenarios[1]
    assert b["tag"] == "B"
    assert b["deployment"]["deployed_total"] > 0          # B deploys assets to bridge the gap
    assert b["deployment"]["from_liquid"] > 0             # ...from the liquid fund, least-disruptive
    assert b["estimated_emi"] <= 0.70 * 20000 + 1         # EMI fits 70% of max sustainable save
    assert b["down_payment_amount"] >= scenarios[0]["down_payment_amount"]  # deployment raised the down payment


def test_loan_emi_cap_uses_surplus_plus_cuts_not_surplus_alone():
    # An EMI of ~13,500 must be allowed (<= 0.70*(18000+2000)=14,000) where the old cap
    # (0.70*18000=12,600) would have rejected it.
    agg = _agg(liquid_fund_value=350000.0)
    scenarios, _meta = _loan_scenarios(
        price=900000.0, existing=0.0, user_months=24, user_dp_pct=40.0,
        surplus=18000.0, cuts=2000.0, rate=10.0, tenure=60, agg=agg, asset="car",
    )
    b = scenarios[1]
    assert b["estimated_emi"] <= 14000 + 1
    assert b["feasible"] is True


from app.graph.tools.goal_planner_tool import _savings_scenarios


def test_savings_balance_growth_makes_goal_feasible_via_saving():
    # Target 200k reachable by saving alone (cap 20k * 24 = 480k) → feasible WITHOUT touching
    # assets (minimal deployment: none needed). This is the balance-growth feasibility rule.
    agg = _agg(total_current_balance=1500000.0)
    scenarios, _meta = _savings_scenarios(
        target=200000.0, existing=0.0, user_months=24, surplus=18000.0, cuts=2000.0,
        instrument="Liquid MF", agg=agg, annual_return_pct=0.0,
    )
    a, b = scenarios[0], scenarios[1]
    assert a["deployment"]["deployed_total"] == 0.0      # A deploys nothing
    assert b["deployment"]["deployed_total"] == 0.0      # saving suffices → no assets disturbed
    assert b["feasible"] is True
    assert 0 < b["monthly_savings_needed"] <= 20000


def test_savings_scenario_b_minimal_deploy_only_the_gap():
    # No surplus, existing 150k, target 200k → falling short by 50k → redeem EXACTLY 50k from a
    # 60k liquid fund (your Q2 example: deploy the shortfall, not everything).
    agg = _agg(liquid_fund_value=60000.0, total_current_balance=0.0)
    scenarios, _meta = _savings_scenarios(
        target=200000.0, existing=150000.0, user_months=12, surplus=0.0, cuts=0.0,
        instrument="Liquid MF", agg=agg, annual_return_pct=0.0,
    )
    b = scenarios[1]
    assert b["deployment"]["from_liquid"] == 50000.0
    assert b["deployment"]["from_fds_broken"] == 0.0
    assert b["monthly_savings_needed"] == 0.0
    assert b["feasible"] is True


from app.graph.tools.goal_planner_tool import _education_scenarios


def test_education_self_funded_feasibility_uses_surplus_plus_cuts():
    agg = _agg(total_current_balance=0.0)
    scenarios, _meta = _education_scenarios(
        cost=2000000.0, existing=0.0, user_months=24, self_pct=0.0,
        surplus=18000.0, cuts=2000.0, agg=agg, tenure=180,
    )
    b = scenarios[1]                                  # "Maximise the loan" — recommended
    assert b["recommended"] is True
    assert b["loan_amount"] > 0
    # Self-funded slice is minimal; its monthly saving must be within surplus+cuts to be feasible.
    assert b["feasible"] == (b["monthly_savings_needed"] <= 20000 + 1)


from app.graph.tools.goal_planner_tool import (
    _liquid_fund_current_value,
    _liquid_fund_value_at,
)


def _inv(name, current_value):
    return {"holdings": [{"name": name, "current_value": current_value}], "total_current": current_value}


def test_liquid_fund_current_value_picks_liquid_holdings():
    data = _inv("ABC Liquid Fund Direct Growth", 104000.0)
    assert _liquid_fund_current_value(data) == 104000.0


def test_liquid_fund_current_value_ignores_equity():
    data = _inv("XYZ Bluechip Equity Fund", 104000.0)
    assert _liquid_fund_current_value(data) == 0.0


def test_liquid_fund_value_at_grows_for_long_horizon():
    data = _inv("ABC Liquid Fund", 100000.0)
    # 24 months at 7% p.a. > current value (grows); short horizon ~= current.
    grown = _liquid_fund_value_at(data, 24, annual_return_pct=7.0)
    flat = _liquid_fund_value_at(data, 6, annual_return_pct=7.0)
    assert grown > 100000.0
    assert flat == 100000.0          # <= 12 months: kept liquid, no growth assumed
