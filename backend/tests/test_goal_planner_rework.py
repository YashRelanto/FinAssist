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


def test_loan_returns_four_scenarios_abcd():
    agg = _agg(total_current_balance=200000.0)
    scenarios, _meta = _loan_scenarios(
        price=1000000.0, existing=0.0, user_months=18, user_dp_pct=30.0,
        surplus=18000.0, cuts=2000.0, rate=10.0, tenure=60, agg=agg, asset="car",
    )
    assert [s["tag"] for s in scenarios] == ["A", "B", "C", "D"]


def test_loan_scenario_a_baseline_uses_bank_no_breaking():
    # A funds the down payment from bank cash (available in every scenario) but breaks NO funds.
    agg = _agg(total_current_balance=1500000.0, liquid_fund_value=400000.0)
    scenarios, _meta = _loan_scenarios(
        price=1000000.0, existing=0.0, user_months=18, user_dp_pct=30.0,
        surplus=18000.0, cuts=2000.0, rate=10.0, tenure=60, agg=agg, asset="car",
    )
    a = scenarios[0]
    assert a["down_payment_pct"] == 30.0                          # user's exact %
    assert a["deployment"]["deployed_total"] == 0.0              # no FD/liquid broken in A
    assert a["down_payment_from_existing"] > 0                   # but bank cash funds the upfront
    # 3L down payment is covered by the 15L bank, EMI 7L loan ~14.9k > 0.7*18k=12.6k → not feasible.
    assert a["down_payment_fundable"] is True
    assert a["emi_fits_capacity"] is False


def test_loan_scenario_b_judges_emi_against_surplus_plus_cuts():
    # B keeps the same plan but its EMI is judged against 0.70*(surplus+cuts).
    agg = _agg(total_current_balance=1500000.0)
    scenarios, _meta = _loan_scenarios(
        price=600000.0, existing=0.0, user_months=18, user_dp_pct=30.0,
        surplus=18000.0, cuts=4000.0, rate=10.0, tenure=60, agg=agg, asset="car",
    )
    b = scenarios[1]
    assert b["tag"] == "B"
    assert b["deployment"]["deployed_total"] == 0.0              # B breaks nothing (cuts only)
    assert b["assumed_monthly_saving"] == 22000.0               # surplus + cuts
    # EMI on a 4.2L loan ~8.9k must fit 0.70*22000 = 15400.
    assert b["emi_fits_capacity"] is True


def test_loan_scenario_c_breaks_minimal_liquidity_to_fit_emi():
    # No cuts; C breaks minimal FD/liquid funds to raise the down payment so EMI fits 0.70*surplus.
    agg = _agg(total_current_balance=100000.0, liquid_fund_value=600000.0)
    scenarios, _meta = _loan_scenarios(
        price=1000000.0, existing=0.0, user_months=12, user_dp_pct=30.0,
        surplus=18000.0, cuts=2000.0, rate=10.0, tenure=60, agg=agg, asset="car",
    )
    c = scenarios[2]
    assert c["tag"] == "C"
    assert c["deployment"]["from_liquid"] > 0                    # liquidity broken
    assert c["deployment"]["from_bank"] == 0.0                  # but NOT bank (already 'available cash')
    assert c["estimated_emi"] <= 0.70 * 18000 + 1              # EMI brought within 70% of current saving
    assert c["down_payment_amount"] > scenarios[0]["down_payment_amount"]


def test_loan_scenario_c_caps_down_payment_at_fundable():
    # Unaffordable goal (1cr on tiny saving): C must NOT invent a 91L down payment to force a small
    # EMI — it caps the down payment at the user's % / fundable amount and reports the REAL EMI.
    agg = _agg(total_current_balance=157246.0, liquid_fund_value=125007.0, total_spending_cuts=0.0)
    scenarios, meta = _loan_scenarios(
        price=10000000.0, existing=0.0, user_months=36, user_dp_pct=20.0,
        surplus=10642.0, cuts=0.0, rate=8.5, tenure=240, agg=agg, extra_upfront=700000.0, asset="home",
    )
    c = scenarios[2]
    assert c["down_payment_amount"] <= 10000000.0                 # never exceeds the price
    assert c["down_payment_amount"] == 2000000.0                 # capped at the user's 20% (not 91L)
    assert c["estimated_emi"] > 60000                            # the REAL EMI on an 80L loan, not ₹7,449
    assert c["feasible"] is False
    assert meta["any_feasible"] is False                          # whole goal is unaffordable


def test_loan_scenario_d_uses_cuts_and_liquidity_beyond_b():
    # When cuts (B) already make it feasible, D must still deploy liquidity to shrink the loan
    # further — it must NOT collapse onto B.
    agg = _agg(total_current_balance=157246.0, liquid_fund_value=300000.0,
               total_spending_cuts=11972.0)
    scenarios, _meta = _loan_scenarios(
        price=900000.0, existing=0.0, user_months=12, user_dp_pct=30.0,
        surplus=10642.0, cuts=11972.0, rate=10.0, tenure=60, agg=agg, asset="car",
    )
    b, c, d = scenarios[1], scenarios[2], scenarios[3]
    assert b["deployment"]["deployed_total"] == 0.0          # B breaks nothing (cuts only)
    assert d["deployment"]["deployed_total"] > 0             # D actually breaks funds
    assert d["loan_amount"] < b["loan_amount"]              # D's bigger down payment → smaller loan
    assert d["deployment"]["deployed_total"] >= c["deployment"]["deployed_total"]  # D >= C's minimal break
    assert d["feasible"] is True


def test_loan_scenario_d_can_prefund_emi_shortfall():
    # Tiny saving but huge liquidity → D deploys liquidity for the down payment (and EMI reserve).
    agg = _agg(total_current_balance=0.0, liquid_fund_value=5000000.0)
    scenarios, _meta = _loan_scenarios(
        price=1000000.0, existing=0.0, user_months=12, user_dp_pct=20.0,
        surplus=3000.0, cuts=1000.0, rate=10.0, tenure=60, agg=agg, asset="car",
    )
    d = scenarios[3]
    assert d["tag"] == "D"
    assert d["deployment"]["deployed_total"] > 0
    assert d["emi_pre_funded_monthly"] >= 0
    assert d["feasible"] is True


from app.graph.tools.goal_planner_tool import _savings_scenarios


def test_savings_returns_four_scenarios_abcd():
    agg = _agg(total_current_balance=100000.0)
    scenarios, _meta = _savings_scenarios(
        target=200000.0, existing=0.0, user_months=24, surplus=18000.0, cuts=2000.0,
        instrument="Liquid MF", agg=agg, annual_return_pct=0.0,
    )
    assert [s["tag"] for s in scenarios] == ["A", "B", "C", "D"]


def test_savings_scenario_a_feasible_from_bank_plus_saving():
    # 1L bank + 18k/mo * 24 reaches a 2L target with no cuts, no breaking.
    agg = _agg(total_current_balance=100000.0)
    scenarios, _meta = _savings_scenarios(
        target=200000.0, existing=0.0, user_months=24, surplus=18000.0, cuts=2000.0,
        instrument="Liquid MF", agg=agg, annual_return_pct=0.0,
    )
    a = scenarios[0]
    assert a["deployment"]["deployed_total"] == 0.0
    assert a["feasible"] is True


def test_savings_scenario_c_breaks_minimal_liquidity_only():
    # No surplus, no bank, target 200k → C breaks EXACTLY the 200k gap from a 250k liquid fund.
    agg = _agg(total_current_balance=0.0, liquid_fund_value=250000.0)
    scenarios, _meta = _savings_scenarios(
        target=200000.0, existing=0.0, user_months=12, surplus=0.0, cuts=0.0,
        instrument="Liquid MF", agg=agg, annual_return_pct=0.0,
    )
    c = scenarios[2]
    assert c["tag"] == "C"
    assert c["deployment"]["from_liquid"] == 200000.0
    assert c["deployment"]["from_bank"] == 0.0
    assert c["feasible"] is True


from app.graph.tools.goal_planner_tool import _education_scenarios


def test_education_four_scenarios_more_effort_smaller_loan():
    # Cost 20L, modest savings + a liquid fund. A=baseline recommended; B/C/D shrink the loan.
    agg = _agg(total_current_balance=100000.0, liquid_fund_value=500000.0)
    scenarios, _meta = _education_scenarios(
        cost=2000000.0, existing=0.0, user_months=24, self_pct=0.0,
        surplus=18000.0, cuts=2000.0, agg=agg, tenure=180,
    )
    assert [s["tag"] for s in scenarios] == ["A", "B", "C", "D"]
    a, b, c, d = scenarios
    assert a["recommended"] is True                  # baseline is least-disruptive
    assert all(s["feasible"] for s in scenarios)     # education is always financeable
    # More effort ⇒ more self-funding ⇒ a smaller loan: A >= B >= D, and C (liquidity) < A.
    assert b["loan_amount"] <= a["loan_amount"] + 1
    assert d["loan_amount"] <= b["loan_amount"] + 1
    assert c["loan_amount"] < a["loan_amount"]       # liquidity cut the loan
    assert c["deployment"]["from_liquid"] > 0


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


from app.graph.tools.goal_planner_tool import (
    _plan_car,
    _apply_what_if,
)


def test_loan_rate_override_zero_interest():
    agg = _agg(total_current_balance=0.0, liquid_fund_value=0.0,
               fd_funding_view=[], funding_selection={"bank_use_pct": 90.0})
    goal = {"goal_type": "car", "target_amount": 600000, "timeline": "60 months",
            "down_payment_pct": 20, "loan_interest_rate_pct": 0}
    out = _plan_car(goal, agg)
    rec = next(s for s in out["scenarios"] if s["recommended"])
    # Zero-interest: total interest is 0 and EMI == loan / tenure.
    assert rec["total_interest_paid"] == 0.0


def test_monthly_savings_override_sets_capacity():
    agg = _agg(monthly_net_flow=10000.0, total_spending_cuts=0.0)
    agg2 = _apply_what_if(agg, {"monthly_savings_override": 15000})
    assert agg2["monthly_net_flow"] == 15000.0


from app.graph.tools.goal_planner_tool import _resolve_down_payment_pct


def test_down_payment_override_explicit_amount():
    agg = _agg()
    # explicit ₹2,00,000 down payment on an ₹8,00,000 car → 25%
    pct = _resolve_down_payment_pct({"down_payment_amount": 200000}, agg, 800000.0, 12, 30.0)
    assert pct == 25.0


def test_down_payment_source_savings_uses_bank_plus_savings():
    # "increase my down payment to whatever I save in 12 months": bank 1.57L + 10,642*12 = 2.84L
    agg = _agg(monthly_net_flow=10642.0, total_current_balance=157246.0)
    pct = _resolve_down_payment_pct({"down_payment_source": "savings"}, agg, 800000.0, 12, 30.0)
    expected = round((157246.0 + 10642.0 * 12) / 800000.0 * 100, 6)
    assert abs(pct - expected) < 0.01


def test_down_payment_source_everything_adds_liquidity():
    agg = _agg(monthly_net_flow=10642.0, total_current_balance=157246.0, liquid_fund_value=50000.0)
    savings_pct = _resolve_down_payment_pct({"down_payment_source": "savings"}, agg, 800000.0, 12, 30.0)
    everything_pct = _resolve_down_payment_pct({"down_payment_source": "everything"}, agg, 800000.0, 12, 30.0)
    assert everything_pct > savings_pct          # "everything" also breaks the 50k liquid fund


def test_max_affordable_price_is_downpayment_plus_max_loan():
    # No stamp (car): price = funds (bank + saving×months + liquid) + max loan at 70% of capacity.
    from app.graph.tools.goal_planner_tool import _max_affordable_price, _inv_emi, _CAP_UTIL
    agg = _agg(monthly_net_flow=10642.0, total_current_balance=157246.0, liquid_fund_value=100000.0,
               total_spending_cuts=0.0)
    price = _max_affordable_price({"down_payment_source": "everything"}, agg, 10.0, 60, 12)
    max_loan = _inv_emi(_CAP_UTIL * 10642.0, 10.0, 60)
    funds = 157246.0 + 10642.0 * 12 + 100000.0      # bank + savings + liquid (everything)
    assert abs(price - (funds + max_loan)) < 1.0


def test_max_affordable_price_accounts_for_stamp_duty():
    # House: stamp duty is a % of price → price = (funds + max loan) / (1 + stamp%).
    from app.graph.tools.goal_planner_tool import _max_affordable_price, _inv_emi, _CAP_UTIL
    agg = _agg(monthly_net_flow=10642.0, total_current_balance=157246.0, liquid_fund_value=100000.0,
               total_spending_cuts=0.0)
    no_stamp = _max_affordable_price({"down_payment_source": "everything"}, agg, 8.5, 240, 24)
    with_stamp = _max_affordable_price({"down_payment_source": "everything"}, agg, 8.5, 240, 24, stamp_pct=7.0)
    assert with_stamp < no_stamp                       # stamp leaves less room for the property
    assert abs(with_stamp - no_stamp / 1.07) < 1.0


def test_find_max_affordable_emi_at_cap():
    # "what car can I afford if I liquidate everything": price is COMPUTED (down payment + max loan),
    # and the EMI lands at 70% of saving (the largest loan that fits).
    from app.graph.tools.goal_planner_tool import _max_affordable_price
    agg = _agg(monthly_net_flow=10642.0, total_current_balance=157246.0, liquid_fund_value=100000.0,
               total_spending_cuts=0.0)
    goal = {"goal_type": "car", "target_amount": 500000, "timeline": "12 months",
            "down_payment_pct": 30, "find_max_affordable": True,
            "down_payment_source": "everything", "what_if": True}
    expected = _max_affordable_price(goal, agg, 10.0, 60, 12)
    out = _plan_car(goal, agg)
    rec = next(s for s in out["scenarios"] if s["recommended"])
    assert abs(rec["purchase_price"] - expected) < 1.0   # price COMPUTED, not the ₹5L prior target
    assert rec["estimated_emi"] <= 0.70 * 10642 + 1       # EMI at/under the savings cap
    assert rec["loan_amount"] > 0


def test_whatif_car_keeps_target_and_shows_loan():
    # The bug: a what-if that loses target_amount → price 0 → no loan. With price carried, it's a
    # real loan scenario (funding_breakdown has a loan slice for the funding pie).
    agg = _agg(total_current_balance=157246.0)
    out = _plan_car({"goal_type": "car", "target_amount": 800000, "timeline": "12 months",
                     "down_payment_pct": 30, "down_payment_source": "savings", "what_if": True}, agg)
    rec = next(s for s in out["scenarios"] if s["recommended"])
    assert rec["purchase_price"] == 800000.0
    assert rec["loan_amount"] > 0                 # a real loan exists → funding pie will render


from app.graph.nodes.answer_node import _funding_split_pie, _select_goal_artifacts


def test_funding_split_pie_has_loan_and_self_funded_slices():
    g = {"funding_breakdown": {"loan": 700000.0, "bank": 150000.0, "fd": 100000.0, "liquid": 50000.0}}
    arts = _funding_split_pie(g)
    assert len(arts) == 1
    pie = arts[0]
    assert pie["chart_type"] == "pie"
    labels = {d["label"] for d in pie["data"]}
    assert {"Loan-financed", "Bank cash", "Fixed deposits", "Liquid funds"} == labels


def test_funding_split_pie_omits_zero_slices():
    g = {"funding_breakdown": {"loan": 0.0, "bank": 200000.0, "fd": 0.0, "liquid": 0.0}}
    arts = _funding_split_pie(g)
    labels = {d["label"] for d in arts[0]["data"]}
    assert labels == {"Bank cash"}


def test_select_goal_artifacts_handles_single_whatif_scenario():
    # What-ifs now DO get charts; a single-scenario what-if must not crash the artifact builder.
    g = {"what_if": True, "monthly_avg_income": 60000, "monthly_avg_spend": 42000,
         "monthly_savings_needed": 5000, "timeline_months": 12,
         "scenarios": [{"tag": "B", "label": "x", "monthly_savings_needed": 5000, "estimated_emi": 9000}]}
    arts = _select_goal_artifacts("car", g)
    assert isinstance(arts, list)        # builds without error (no KeyError)


from app.utils import prompts as P


def test_goal_whatif_system_prompt_exists():
    assert isinstance(getattr(P, "GOAL_WHATIF_SYSTEM", None), str)
    assert "what_if" in P.GOAL_WHATIF_SYSTEM.lower() or "what-if" in P.GOAL_WHATIF_SYSTEM.lower()


def test_brain_schema_has_whatif_fields():
    assert "loan_interest_rate_pct" in P.BRAIN_SYSTEM
    assert "monthly_savings_override" in P.BRAIN_SYSTEM
    assert '"what_if"' in P.BRAIN_SYSTEM
