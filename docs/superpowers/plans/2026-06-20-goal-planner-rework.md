# Goal Planner Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the goal planner's scenarios honest and realistic — Scenario A = the user's exact plan, B = minimal smart asset deployment, C = right-size — with an EMI cap that no longer inflates the down payment, market-value liquid funds, balance-growth feasibility, generalised what-ifs, and a self-funded-vs-loan pie.

**Architecture:** All financial modelling lives in pure functions in `goal_planner_tool.py` (scenario builders take explicit params + an `agg` snapshot dict). Tests call those pure functions directly with synthetic dicts — no DB. Prompts live in `prompts.py`; chart builders in `answer_node.py`.

**Tech Stack:** Python 3.12, pytest. Backend package root is `backend/`; imports are `from app...`. LangGraph state flows through `AgentState`.

## Global Constraints

- **Run tests from `backend/`** with: `../venv/Scripts/python.exe -m pytest tests/test_goal_planner_rework.py -v`
- **New test file:** `backend/tests/test_goal_planner_rework.py` (all tests for this plan go here).
- **Cushion constant:** keep `_CAP_UTIL = 0.70`. Only the base it multiplies changes.
- **Max sustainable saving:** `max_sustainable_save = monthly_net_flow + total_spending_cuts` (current surplus + reclaimable category cuts). The saving phase may use the FULL amount; the permanent EMI is capped at `0.70 × max_sustainable_save`.
- **Scenario contract:** every scenario dict keeps its existing keys (`tag`, `label`, `recommended`, `monthly_savings_needed`, `feasible`, `shortfall_per_month`, plus loan keys). Do not rename existing keys — `answer_node.py` and the prompts read them.
- **Update existing functions in place.** No parallel copies. Keep them readable.
- **Indian currency:** monetary numbers get an `_inr` sibling via `_attach_inr` at the tool boundary — do not add `_inr` keys by hand inside scenarios.
- **Out of scope:** dashboard `/api/forecast` calls and financial-score mismatch (already fixed on `main`). Touch only `goal_planner_tool.py`, `prompts.py`, `answer_node.py`.

---

### Task 1: Saving-capacity & minimal-deployment helpers

**Files:**
- Modify: `backend/app/graph/tools/goal_planner_tool.py` (add two helpers near the other scenario helpers, after `_funding_components`/`_funding_sources`, before `_loan_scenarios`)
- Test: `backend/tests/test_goal_planner_rework.py`

**Interfaces:**
- Produces:
  - `_max_sustainable_save(agg: dict) -> float`
  - `_minimal_deployment(gap: float, agg: dict) -> dict` returning keys: `from_fds_matured`, `from_liquid`, `from_bank`, `from_fds_broken`, `fds_broken` (list of names), `penalty_paid`, `deployed_total`, `shortfall_uncovered` (all floats except `fds_broken`).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_goal_planner_rework.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`): `../venv/Scripts/python.exe -m pytest tests/test_goal_planner_rework.py -v`
Expected: FAIL — `ImportError: cannot import name '_max_sustainable_save'`

- [ ] **Step 3: Implement the two helpers**

In `goal_planner_tool.py`, add after `_funding_sources` (just before `_loan_scenarios`):

```python
def _max_sustainable_save(agg: dict) -> float:
    """Most the user can be asked to save per month: current surplus + reclaimable category cuts.
    The saving phase may use this in full; the permanent EMI is capped at 70% of it (see _loan_scenarios)."""
    return round(max(0.0, agg.get("monthly_net_flow", 0.0))
                 + max(0.0, agg.get("total_spending_cuts", 0.0)), 2)


def _minimal_deployment(gap: float, agg: dict) -> dict:
    """Cover `gap` with the LEAST-disruptive assets, in order (Scenario B helper):
       1. FDs maturing by the goal date  (free — already becoming cash),
       2. liquid/debt funds              (partial redemption to the EXACT amount needed),
       3. bank cash                      (keeping the chosen cushion, only what's needed),
       4. a still-locked FD broken ONLY if still short — the one whose usable value is CLOSEST
          to the remaining need (minimise forfeited interest; never break everything).
    """
    gap = max(0.0, round(gap, 2))
    used = {"from_fds_matured": 0.0, "from_liquid": 0.0, "from_bank": 0.0,
            "from_fds_broken": 0.0, "fds_broken": [], "penalty_paid": 0.0}
    remaining = gap
    view = agg.get("fd_funding_view") or []

    for fd in view:                                   # 1. matured-by-goal-end FDs (free)
        if remaining <= 0:
            break
        if fd.get("matures_by_goal_end"):
            take = min(remaining, float(fd.get("usable_value") or 0.0))
            used["from_fds_matured"] += take
            remaining -= take

    if remaining > 0:                                 # 2. liquid/debt funds (exact partial)
        take = min(remaining, float(agg.get("liquid_fund_value") or 0.0))
        used["from_liquid"] += take
        remaining -= take

    if remaining > 0:                                 # 3. bank cash (keep cushion)
        sel = agg.get("funding_selection") or {}
        pct = float(sel.get("bank_use_pct", (1.0 - _BANK_RETAIN_FRAC) * 100.0))
        bank_avail = max(0.0, float(agg.get("total_current_balance") or 0.0) * pct / 100.0)
        take = min(remaining, bank_avail)
        used["from_bank"] += take
        remaining -= take

    if remaining > 0:                                 # 4. break the FD closest to the remaining need
        locked = [fd for fd in view if not fd.get("matures_by_goal_end")]
        locked.sort(key=lambda fd: abs(float(fd.get("usable_value") or 0.0) - remaining))
        for fd in locked:
            if remaining <= 0:
                break
            take = min(remaining, float(fd.get("usable_value") or 0.0))
            if take <= 0:
                continue
            used["from_fds_broken"] += take
            used["penalty_paid"] += float(fd.get("penalty_if_broken") or 0.0)
            used["fds_broken"].append(fd.get("bank_name") or fd.get("label") or "FD")
            remaining -= take

    for k in ("from_fds_matured", "from_liquid", "from_bank", "from_fds_broken", "penalty_paid"):
        used[k] = round(used[k], 2)
    used["deployed_total"] = round(gap - remaining, 2)
    used["shortfall_uncovered"] = round(max(0.0, remaining), 2)
    return used
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `../venv/Scripts/python.exe -m pytest tests/test_goal_planner_rework.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/graph/tools/goal_planner_tool.py backend/tests/test_goal_planner_rework.py
git commit -m "feat(goal-planner): add max-sustainable-save and minimal-deployment helpers"
```

---

### Task 2: Loan scenarios — A pure, B minimal-deployment, floating EMI cap

**Files:**
- Modify: `backend/app/graph/tools/goal_planner_tool.py` — `_loan_scenarios` (currently lines ~871-1004) and its three callers `_plan_car`, `_plan_house`, `_plan_education`-style call sites (pass `agg`).
- Test: `backend/tests/test_goal_planner_rework.py`

**Interfaces:**
- Consumes: `_max_sustainable_save`, `_minimal_deployment` (Task 1).
- Produces: `_loan_scenarios(*, price, existing, user_months, user_dp_pct, surplus, cuts, rate, tenure, agg, extra_upfront=0.0, down_label="down payment", asset="purchase", instrument=...) -> (list[dict], dict)`. **Change:** the `deployable: float` parameter is replaced by `agg: dict`. Each scenario dict additionally carries `deployment` (the `_minimal_deployment` dict for B/C, or an all-zero dict for A) and `emi_fits_capacity: bool`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_goal_planner_rework.py`:

```python
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
    # EMI at 30% down doesn't fit; a liquid fund can raise the down payment minimally.
    agg = _agg(liquid_fund_value=400000.0, total_current_balance=0.0)
    scenarios, _meta = _loan_scenarios(
        price=1000000.0, existing=0.0, user_months=18, user_dp_pct=30.0,
        surplus=18000.0, cuts=2000.0, rate=10.0, tenure=60, agg=agg, asset="car",
    )
    b = scenarios[1]
    assert b["tag"] == "B"
    assert b["deployment"]["deployed_total"] > 0          # B deploys assets
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../venv/Scripts/python.exe -m pytest tests/test_goal_planner_rework.py -v`
Expected: FAIL — `TypeError: _loan_scenarios() got an unexpected keyword argument 'agg'` (signature still takes `deployable`)

- [ ] **Step 3: Rewrite `_loan_scenarios`**

Replace the entire `_loan_scenarios` function body. Key changes vs the current version:
- Signature: drop `deployable: float = 0.0`, add `agg: dict`. Compute `deployable = _deployable(agg)` internally where the full pool is needed (Scenario C), and use `_minimal_deployment` for B.
- `emi_cap = (surplus + cuts) * _CAP_UTIL` (was `surplus * _CAP_UTIL`).
- `cap = surplus + cuts` stays; the saving-phase feasibility uses the FULL `cap` (drop the extra `* _CAP_UTIL` on the saving check).
- Scenario A: `head_start = 0.0` (no asset deployment) and add `deployment = _minimal_deployment(0.0, agg)`.
- Scenario B: compute the down payment `dp_b` as the smallest `dp >= user_dp_pct` whose EMI fits `emi_cap`; the extra upfront beyond `existing + sustainable monthly saving × months` is funded by `_minimal_deployment(shortfall, agg)`.

Replace with:

```python
def _loan_scenarios(*, price: float, existing: float, user_months: float, user_dp_pct: float,
                    surplus: float, cuts: float, rate: float, tenure: int,
                    agg: dict,
                    extra_upfront: float = 0.0, down_label: str = "down payment",
                    asset: str = "purchase",
                    instrument: str = "Recurring Deposit or Liquid MF") -> tuple:
    """
    Three scenarios that RESPECT the user's timeline.
      A 'Your Plan'   — EXACTLY the user's inputs, funded only by their own existing savings +
                        monthly saving. No asset deployment — judged honestly.
      B 'Recommended' — keep the timeline; raise the down payment just enough that the EMI fits
                        70% of the user's max sustainable saving, funding the extra purely by
                        MINIMAL least-disruptive asset deployment (never inflating the saving).
      C 'Right-Size'  — biggest purchase that fits the timeline using the FULL deployable pool.
    EMI affordability cap = 0.70 × (surplus + cuts): the permanent EMI may use up to 70% of the
    most the user can sustainably save (their current surplus PLUS reclaimable category cuts).
    """
    surplus = max(surplus, 0.0)
    cuts = max(cuts, 0.0)
    price = max(price, 0.0)
    user_months = max(1, int(round(user_months)))
    cap = surplus + cuts                       # full sustainable monthly saving capacity
    emi_cap = cap * _CAP_UTIL                   # permanent EMI: 70% of that capacity
    deployable = _deployable(agg)               # full pool (for Scenario C only)
    cuts_note = f" (with ₹{round(cuts):,}/mo spending cuts)" if cuts > 0 else ""
    max_months = _max_stretch_months(user_months)

    def make(tag, label, recommended, dp_pct, months, P, head_start, deployment):
        dp_pct = min(max(dp_pct, 0.0), 100.0)
        dp_amt = round(P * dp_pct / 100.0, 2)
        loan = round(max(0.0, P - dp_amt), 2)
        emi = round(_calc_emi(loan, rate, tenure), 2) if loan > 0 else 0.0
        months = max(1, int(months))
        upfront_need = dp_amt + extra_upfront
        available = existing + head_start
        lump = round(min(upfront_need, available), 2)        # funded now from existing + deployed
        to_save = round(max(0.0, upfront_need - lump), 2)    # the rest, saved monthly
        save = round(to_save / months, 2)
        interest = round(emi * tenure - loan, 2) if loan > 0 else 0.0
        return {
            "tag": tag, "label": label, "recommended": recommended,
            "purchase_price": round(P, 2),
            "down_payment_pct": round(dp_pct, 1),
            "down_payment_amount": dp_amt,
            "down_payment_from_existing": lump,
            "down_payment_from_savings": to_save,
            "loan_amount": loan,
            "loan_tenure_months": tenure if loan > 0 else 0,
            "estimated_emi": emi,
            "monthly_post_purchase": emi,
            "total_interest_paid": interest,
            "total_cost_of_ownership": round(P + interest + extra_upfront, 2),
            "timeline_months": months,
            "monthly_savings_needed": save,
            # Saving phase may use the FULL sustainable capacity; the EMI must fit 70% of it.
            "feasible": (save <= cap + 1) and (emi <= emi_cap + 1),
            "shortfall_per_month": round(max(0.0, save - cap), 2),
            "emi_fits_capacity": emi <= emi_cap + 1,
            "deployment": deployment,
            "recommended_instrument": instrument,
        }

    zero_deploy = _minimal_deployment(0.0, agg)

    # A — the user's exact plan, no asset deployment.
    sc_a = make("A", f"Your Plan — {user_dp_pct:.0f}% {down_label} over {user_months} months",
                False, user_dp_pct, user_months, price, 0.0, zero_deploy)

    # B — raise the down payment to the smallest % whose EMI fits emi_cap, funding the extra by
    #     MINIMAL asset deployment. Stretch the timeline only if even that can't make saving fit.
    max_loan = _inv_emi(emi_cap, rate, tenure)
    dp_lo_pct = max(user_dp_pct, (price - max_loan) / price * 100.0 if price else 0.0)
    dp_lo_pct = min(100.0, dp_lo_pct)
    dp_b_amt = round(price * dp_lo_pct / 100.0, 2)
    # What the user can fund themselves over the timeline (existing + sustainable saving):
    self_fundable = existing + cap * user_months
    shortfall_b = max(0.0, dp_b_amt + extra_upfront - self_fundable)
    deploy_b = _minimal_deployment(shortfall_b, agg)
    months_b = user_months
    sc_b = make("B", "", False, dp_lo_pct, months_b, price,
                deploy_b["deployed_total"], deploy_b)
    # If the down-payment saving still doesn't fit, extend the timeline modestly.
    while not sc_b["feasible"] and months_b < max_months and sc_b["monthly_savings_needed"] > cap:
        months_b = min(months_b + 3, max_months)
        sc_b = make("B", "", False, dp_lo_pct, months_b, price,
                    deploy_b["deployed_total"], deploy_b)
    deploy_note = f", deploy {_inr(deploy_b['deployed_total'])} now" if deploy_b["deployed_total"] > 0 else ""
    ext = "" if months_b == user_months else f" ({months_b - user_months}-month extension)"
    sc_b["label"] = f"Keep this {asset} — {dp_lo_pct:.0f}% {down_label} over {months_b} months{ext}{deploy_note}{cuts_note}"

    # C — biggest purchase that fits: ALL deployable assets toward the down payment PLUS the
    # largest EMI-affordable loan.
    avail_c = existing + deployable
    down_avail = max(0.0, avail_c + cap * user_months - extra_upfront)
    price_c = down_avail + max_loan
    price_c_capped = min(price_c, price)
    out_of_reach = price > 0 and price_c < price * _TARGET_FLOOR_FRAC
    dp_pct_c = min(100.0, down_avail / price_c_capped * 100.0) if price_c_capped > 0 else user_dp_pct
    deploy_c_dict = _minimal_deployment(down_avail, agg)
    deploy_c = f" by deploying {_inr(deploy_c_dict['deployed_total'])} now" if deploy_c_dict["deployed_total"] > 0 else ""
    if price_c >= price * 0.98:
        need = max(0.0, price * min(max(user_dp_pct / 100.0, 0.0), 1.0) + extra_upfront - avail_c)
        months_fast = max(1, math.ceil(need / cap)) if cap > 0 else user_months
        sc_c = make("C", f"Buy Sooner — same {asset} in {months_fast} months{cuts_note}",
                    False, user_dp_pct, months_fast, price, deploy_c_dict["deployed_total"], deploy_c_dict)
    elif out_of_reach:
        sc_c = make("C", f"Most you can finance — a {_inr(price_c_capped)} {asset}{deploy_c} (your {_inr(price)} target is out of reach in {user_months} months){cuts_note}",
                    False, dp_pct_c, user_months, price_c_capped, deploy_c_dict["deployed_total"], deploy_c_dict)
    else:
        sc_c = make("C", f"Right-Size — a {_inr(price_c_capped)} {asset} fits your {user_months}-month timeline{deploy_c}{cuts_note}",
                    False, dp_pct_c, user_months, price_c_capped, deploy_c_dict["deployed_total"], deploy_c_dict)

    (sc_b if sc_b["feasible"] else sc_c)["recommended"] = True
    meta = {"max_financeable_target": round(price_c_capped, 2), "target_out_of_reach": bool(out_of_reach)}
    return [sc_a, sc_b, sc_c], meta
```

- [ ] **Step 4: Update the three call sites to pass `agg` instead of `deployable`**

In `_plan_car` (call to `_loan_scenarios`): change `deployable=_deployable(agg),` to `agg=agg,`.
In `_plan_house`: same change — `deployable=_deployable(agg),` → `agg=agg,`.
In `_plan_education`'s loan path it calls `_education_scenarios` (handled in Task 4), so only `_plan_car` and `_plan_house` change here.

- [ ] **Step 5: Run tests to verify they pass**

Run: `../venv/Scripts/python.exe -m pytest tests/test_goal_planner_rework.py -v`
Expected: PASS (8 tests total)

- [ ] **Step 6: Run the full goal-planner-adjacent suite for regressions**

Run: `../venv/Scripts/python.exe -m pytest tests/ -q -k "goal or pipeline"`
Expected: PASS (no import or signature breakage)

- [ ] **Step 7: Commit**

```bash
git add backend/app/graph/tools/goal_planner_tool.py backend/tests/test_goal_planner_rework.py
git commit -m "feat(goal-planner): loan scenarios A=pure B=minimal-deploy C=right-size with floating EMI cap"
```

---

### Task 3: Savings scenarios — A pure, B minimal-deployment, balance-growth feasibility

**Files:**
- Modify: `backend/app/graph/tools/goal_planner_tool.py` — `_savings_scenarios` (currently lines ~1007-1106) and `_savings_goal` (passes `deployable`).
- Test: `backend/tests/test_goal_planner_rework.py`

**Interfaces:**
- Consumes: `_minimal_deployment`, `_max_sustainable_save`.
- Produces: `_savings_scenarios(*, target, existing, user_months, surplus, cuts, instrument, agg, asset="goal", annual_return_pct=_SAVINGS_RETURN_PCT) -> (list[dict], dict)`. **Change:** `deployable` param replaced by `agg`. Scenario A deploys nothing; B deploys minimal assets to close the gap; each scenario carries `deployment` and `deployed_now`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_goal_planner_rework.py`:

```python
from app.graph.tools.goal_planner_tool import _savings_scenarios


def test_savings_scenario_a_pure_no_deploy_but_feasible_from_balance_in_b():
    # Target 200k, user has 0 saved but 1.5M idle in bank → B reaches it instantly via deploy.
    agg = _agg(total_current_balance=1500000.0)
    scenarios, _meta = _savings_scenarios(
        target=200000.0, existing=0.0, user_months=24, surplus=18000.0, cuts=2000.0,
        instrument="Liquid MF", agg=agg, annual_return_pct=0.0,
    )
    a, b = scenarios[0], scenarios[1]
    assert a["deployment"]["deployed_total"] == 0.0      # A deploys nothing
    assert b["deployment"]["deployed_total"] >= 200000.0 - 1   # B deploys what's needed
    assert b["monthly_savings_needed"] == 0.0            # fully covered by deployed balance
    assert b["feasible"] is True


def test_savings_scenario_b_minimal_deploy_only_the_gap():
    # Target 200k, existing 150k → gap 50k → deploy exactly 50k from a 60k liquid fund.
    agg = _agg(liquid_fund_value=60000.0, total_current_balance=0.0)
    scenarios, _meta = _savings_scenarios(
        target=200000.0, existing=150000.0, user_months=12, surplus=18000.0, cuts=2000.0,
        instrument="Liquid MF", agg=agg, annual_return_pct=0.0,
    )
    b = scenarios[1]
    assert b["deployment"]["from_liquid"] == 50000.0
    assert b["deployment"]["from_fds_broken"] == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../venv/Scripts/python.exe -m pytest tests/test_goal_planner_rework.py -v`
Expected: FAIL — `TypeError: _savings_scenarios() got an unexpected keyword argument 'agg'`

- [ ] **Step 3: Rewrite `_savings_scenarios`**

Replace the function. Key changes: `deployable` → `agg`; A uses `deploy=0`; B deploys `_minimal_deployment(gap_after_self_funding, agg)`; feasibility already projects balance growth via `_reachable`. Use the FULL `cap` (surplus+cuts) for the monthly capacity (drop the `* _CAP_UTIL` on the saving feasibility, keeping it only as the recommend-tie cushion). Replace with:

```python
def _savings_scenarios(*, target: float, existing: float, user_months: float,
                       surplus: float, cuts: float, instrument: str, agg: dict,
                       asset: str = "goal",
                       annual_return_pct: float = _SAVINGS_RETURN_PCT) -> tuple:
    """
    Three scenarios for a cash (no-loan) goal, respecting the user's timeline.
      A 'Your Plan'   — your timeline, funded only by your own existing savings + monthly saving.
      B 'Recommended' — deploy MINIMAL least-disruptive assets to close the gap, keep the timeline
                        if it fits; else stretch MODESTLY.
      C 'Right-Size'  — the largest target reachable within the original timeline using the FULL pool.
    Feasibility projects balance growth: existing + deployed + saving × months (with returns for
    goals > 12 months), so a large idle balance makes a goal feasible with little/no monthly saving.
    """
    surplus = max(surplus, 0.0)
    cuts = max(cuts, 0.0)
    deployable = _deployable(agg)
    user_months = max(1, int(round(user_months)))
    cap = surplus + cuts                    # full sustainable monthly saving capacity
    r = annual_return_pct / 100.0
    grows = annual_return_pct > 0
    cuts_note = f" (with ₹{round(cuts):,}/mo spending cuts)" if cuts > 0 else ""
    max_months = _max_stretch_months(user_months)

    def _monthly_for(target_amt, months, base):
        if months > _RETURN_MIN_MONTHS and grows:
            base_fv = _corpus_growth(base, 0.0, r, months)
            need = max(0.0, target_amt - base_fv)
            return round(_monthly_sip_for_corpus(need, annual_return_pct, months), 2)
        return round(max(0.0, target_amt - base) / months, 2)

    def _reachable(months, base):
        if months > _RETURN_MIN_MONTHS and grows:
            return _corpus_growth(base, cap, r, months)
        return base + cap * months

    def build(tag, label, recommended, target_amt, months, deployment):
        months = max(1, int(months))
        deploy = deployment["deployed_total"]
        base = existing + deploy
        save = _monthly_for(target_amt, months, base)
        return {
            "tag": tag, "label": label, "recommended": recommended,
            "timeline_months": months,
            "monthly_savings_needed": save,
            "target_amount": round(target_amt, 2),
            "gap": round(max(0.0, target_amt - existing), 2),
            "deployed_now": round(deploy, 2),
            "deployment": deployment,
            "assumed_annual_return_pct": annual_return_pct,
            "feasible": save <= cap + 1,
            "shortfall_per_month": round(max(0.0, save - cap), 2),
            "recommended_instrument": instrument,
        }

    zero_deploy = _minimal_deployment(0.0, agg)

    # A — your plan, no asset deployment.
    sc_a = build("A", f"Your Plan — {user_months} months", False, target, user_months, zero_deploy)

    # B — deploy MINIMAL assets to close the gap the user can't self-fund over the timeline.
    self_fundable_b = _reachable(user_months, existing)
    gap_b = max(0.0, target - self_fundable_b)
    deploy_b = _minimal_deployment(gap_b, agg)
    months_b = user_months
    while cap > 0 and _monthly_for(target, months_b, existing + deploy_b["deployed_total"]) > cap and months_b < max_months:
        months_b += 1
    deploy_note = f", deploy {_inr(deploy_b['deployed_total'])} now" if deploy_b["deployed_total"] > 0 else ""
    if months_b == user_months:
        label_b = f"Keep this target — your {user_months}-month timeline{deploy_note}{cuts_note}"
    else:
        label_b = f"Keep this target — {months_b} months (a {months_b - user_months}-month extension){deploy_note}{cuts_note}"
    sc_b = build("B", label_b, False, target, months_b, deploy_b)

    # C — right-size to the original timeline (or reach sooner if it already fits) using the full pool.
    full_deploy = _minimal_deployment(deployable, agg)
    reachable = _reachable(user_months, existing + deployable)
    affordable_target = round(min(reachable, target), 2)
    out_of_reach = target > 0 and affordable_target < target * _TARGET_FLOOR_FRAC
    if reachable >= target * 0.98:
        months_fast = user_months
        while cap > 0 and _monthly_for(target, months_fast, existing + deployable) <= cap and months_fast > 1:
            months_fast -= 1
        months_fast = min(months_fast + 1, user_months)
        sc_c = build("C", f"Reach Sooner — same target in {months_fast} months{cuts_note}",
                     False, target, months_fast, full_deploy)
    elif out_of_reach:
        sc_c = build("C", f"Most you can save — {_inr(affordable_target)} (your {_inr(target)} target is out of reach in {user_months} months){cuts_note}",
                     False, affordable_target, user_months, full_deploy)
    else:
        sc_c = build("C", f"Right-Size — a {_inr(affordable_target)} target fits your {user_months}-month timeline{cuts_note}",
                     False, affordable_target, user_months, full_deploy)

    (sc_b if sc_b["feasible"] else sc_c)["recommended"] = True
    meta = {"max_financeable_target": affordable_target, "target_out_of_reach": bool(out_of_reach)}
    return [sc_a, sc_b, sc_c], meta
```

- [ ] **Step 4: Update `_savings_goal` to pass `agg`**

In `_savings_goal`, change the `_savings_scenarios(...)` call: replace `deployable=_deployable(agg),` with `agg=agg,`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `../venv/Scripts/python.exe -m pytest tests/test_goal_planner_rework.py -v`
Expected: PASS (10 tests total)

- [ ] **Step 6: Commit**

```bash
git add backend/app/graph/tools/goal_planner_tool.py backend/tests/test_goal_planner_rework.py
git commit -m "feat(goal-planner): savings scenarios A=pure B=minimal-deploy with balance-growth feasibility"
```

---

### Task 4: Education scenarios — saving-feasibility gate + `agg`

**Files:**
- Modify: `backend/app/graph/tools/goal_planner_tool.py` — `_education_scenarios` (lines ~1109-1189) and its caller `_plan_education`.
- Test: `backend/tests/test_goal_planner_rework.py`

**Interfaces:**
- Consumes: `_max_sustainable_save`.
- Produces: `_education_scenarios(*, cost, existing, user_months, self_pct, surplus, cuts, agg, rate=10.5, tenure=180) -> (list[dict], dict)`. **Change:** `deployable: float` → `agg: dict`; the self-funded slice feasibility uses `surplus + cuts` (was `surplus * _CAP_UTIL`).

- [ ] **Step 1: Write the failing test**

Append:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `../venv/Scripts/python.exe -m pytest tests/test_goal_planner_rework.py::test_education_self_funded_feasibility_uses_surplus_plus_cuts -v`
Expected: FAIL — `TypeError: _education_scenarios() got an unexpected keyword argument 'agg'`

- [ ] **Step 3: Edit `_education_scenarios`**

Make these surgical edits inside `_education_scenarios`:

1. Signature: change `deployable: float,` to `agg: dict,`.
2. After the signature docstring, replace:
```python
    surplus = max(surplus, 0.0); cuts = max(cuts, 0.0); cost = max(cost, 0.0)
    deployable = max(deployable, 0.0)
    user_months = max(1, int(round(user_months)))
    avail = existing + deployable
    cuts_note = f" (with ₹{round(cuts):,}/mo spending cuts)" if cuts > 0 else ""
    save_cap = surplus * _CAP_UTIL
```
with:
```python
    surplus = max(surplus, 0.0); cuts = max(cuts, 0.0); cost = max(cost, 0.0)
    deployable = max(_deployable(agg), 0.0)
    user_months = max(1, int(round(user_months)))
    avail = existing + deployable
    cuts_note = f" (with ₹{round(cuts):,}/mo spending cuts)" if cuts > 0 else ""
    # The self-funded slice is saved during study; it may use the FULL sustainable capacity
    # (surplus + reclaimable cuts), not a 70%-of-surplus sliver.
    save_cap = surplus + cuts
```
3. In the `make` inner function, the `feasible` line `"feasible": save <= save_cap + 1,` stays as-is (now compares against the new `save_cap`).

- [ ] **Step 4: Update `_plan_education` call site**

In `_plan_education`, change `deployable=_deployable(agg),` to `agg=agg,` in the `_education_scenarios(...)` call.

- [ ] **Step 5: Run tests**

Run: `../venv/Scripts/python.exe -m pytest tests/test_goal_planner_rework.py -v`
Expected: PASS (11 tests total)

- [ ] **Step 6: Commit**

```bash
git add backend/app/graph/tools/goal_planner_tool.py backend/tests/test_goal_planner_rework.py
git commit -m "feat(goal-planner): education self-funded feasibility uses surplus+cuts"
```

---

### Task 5: Liquid funds — live NAV current value + goal-end projection

**Files:**
- Modify: `backend/app/graph/tools/goal_planner_tool.py` — `_fetch_investment_holdings`, `_liquid_fund_value`, and the `goal_planner_tool` body where `agg["liquid_fund_value"]` is set.
- Reference: `backend/app/graph/tools/investment_tool.py` (`_monthly_nav_map`, scheme-history fetch) for the live-NAV pattern.
- Test: `backend/tests/test_goal_planner_rework.py`

**Interfaces:**
- Produces:
  - `_liquid_fund_current_value(inv_data) -> float` (live-NAV current value of liquid/debt holdings).
  - `_liquid_fund_value_at(inv_data, months, annual_return_pct=_SAVINGS_RETURN_PCT) -> float` (current value grown to the goal horizon).
  - `_liquid_fund_value` retained as an alias returning the goal-horizon value (callers unchanged).

- [ ] **Step 1: Write the failing tests**

Append:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../venv/Scripts/python.exe -m pytest tests/test_goal_planner_rework.py -v`
Expected: FAIL — `ImportError: cannot import name '_liquid_fund_current_value'`

- [ ] **Step 3: Implement live-NAV current value + projection**

Replace `_liquid_fund_value` with the following (keep `_LIQUID_INV_KW` as-is above it):

```python
def _liquid_fund_current_value(inv_data: Optional[Dict]) -> float:
    """Current market value of liquid/debt holdings (near-cash). Uses each holding's
    `current_value`, which the caller fills from LIVE NAV (see _fetch_investment_holdings)."""
    holdings = (inv_data or {}).get("holdings") or []
    return round(sum(float(h.get("current_value") or 0) for h in holdings
                     if any(kw in (h.get("name") or "").lower() for kw in _LIQUID_INV_KW)), 2)


def _liquid_fund_value_at(inv_data: Optional[Dict], months: float,
                          annual_return_pct: float = _SAVINGS_RETURN_PCT) -> float:
    """Liquid-fund value at the goal horizon: current value grown at a debt-fund return for goals
    longer than _RETURN_MIN_MONTHS; kept flat (liquid) for short goals."""
    current = _liquid_fund_current_value(inv_data)
    if current <= 0 or months <= _RETURN_MIN_MONTHS or annual_return_pct <= 0:
        return current
    return round(_corpus_growth(current, 0.0, annual_return_pct / 100.0, int(round(months))), 2)


# Back-compat alias: existing callers expect the goal-horizon value via `_liquid_fund_value`.
def _liquid_fund_value(inv_data: Optional[Dict], months: float = 0.0) -> float:
    return _liquid_fund_value_at(inv_data, months) if months else _liquid_fund_current_value(inv_data)
```

- [ ] **Step 4: Fetch live NAV in `_fetch_investment_holdings`**

Edit `_fetch_investment_holdings` to value holdings at live NAV. Replace its body's valuation loop. Currently it computes `val = quantity * purchase_nav`. Change to fetch the latest NAV per scheme from mfapi (reuse the investment tool's helper) and fall back to `purchase_nav` on failure. Replace the function with:

```python
def _fetch_investment_holdings(user_id: str) -> Optional[Dict]:
    """Portfolio snapshot at LIVE NAV (falls back to purchase NAV per holding if the NAV
    lookup fails). Liquid/debt holdings then reflect their true current market value."""
    from app.graph.tools.investment_tool import _fetch_scheme_history, _latest_nav

    try:
        if not supabase_db:
            return None
        resp = (supabase_db.table("investments")
                .select("scheme_name, scheme_code, quantity, purchase_nav")
                .eq("user_id", user_id).execute())
        rows = resp.data or []
        if not rows:
            return None
        holdings, total = [], 0.0
        for r in rows:
            qty = float(r.get("quantity") or 0)
            purch = float(r.get("purchase_nav") or 0)
            nav = purch
            code = r.get("scheme_code")
            if code:
                live = _latest_nav(_fetch_scheme_history(code))
                if live and live > 0:
                    nav = live
            val = qty * nav
            total += val
            holdings.append({"name": r.get("scheme_name"), "current_value": round(val, 2)})
        for h in holdings:
            h["share_pct"] = round(h["current_value"] / total * 100, 2) if total > 0 else 0.0
        return {"total_current": round(total, 2), "holdings": holdings,
                "valuation_basis": "live_nav"}
    except Exception as exc:
        logger.warning("[goal_planner] investment fetch error: %s", exc)
    return None
```

- [ ] **Step 5: Add `_latest_nav` to `investment_tool.py` if absent**

Check `investment_tool.py` for a helper returning the latest NAV from scheme history. If only `_monthly_nav_map`/`_fetch_scheme_history` exist, add this small helper near `_monthly_nav_map`:

```python
def _latest_nav(scheme_data: Optional[Dict]) -> Optional[float]:
    """Most-recent NAV from an mfapi scheme-history payload (data is latest-first)."""
    data = (scheme_data or {}).get("data") or []
    if not data:
        return None
    try:
        return float(data[0]["nav"])
    except (KeyError, ValueError, TypeError):
        return None
```

(If `scheme_code` is not a column on `investments`, keep the `code = r.get("scheme_code")` guard — it simply falls back to purchase NAV, and the projection tests still pass since they call the pure functions directly.)

- [ ] **Step 6: Use the goal-horizon liquid value in `goal_planner_tool`**

In `goal_planner_tool`, where it currently sets `agg["liquid_fund_value"] = _liquid_fund_value(inv_data)`, change to pass the goal horizon:

```python
    agg["liquid_fund_value"]        = _liquid_fund_value(inv_data, _goal_months)   # value at goal end
    agg["liquid_fund_current_value"] = _liquid_fund_current_value(inv_data)        # value today
```

(`_goal_months` is already computed just above for the FD horizon.)

- [ ] **Step 7: Run tests**

Run: `../venv/Scripts/python.exe -m pytest tests/test_goal_planner_rework.py -v`
Expected: PASS (15 tests total)

- [ ] **Step 8: Commit**

```bash
git add backend/app/graph/tools/goal_planner_tool.py backend/app/graph/tools/investment_tool.py backend/tests/test_goal_planner_rework.py
git commit -m "feat(goal-planner): value liquid funds at live NAV + project to goal horizon"
```

---

### Task 6: What-if path — rate & savings overrides + single-computation short-circuit

**Files:**
- Modify: `backend/app/graph/tools/goal_planner_tool.py` — `_plan_car`, `_plan_house`, `_plan_education` (read `loan_interest_rate_pct`), the planners that use capacity (`monthly_savings_override`), and `goal_planner_tool` (the `what_if` short-circuit).
- Test: `backend/tests/test_goal_planner_rework.py`

**Interfaces:**
- Consumes: goal dict may carry `loan_interest_rate_pct` (float), `monthly_savings_override` (float), `what_if` (bool).
- Produces: when `goal["what_if"]` is true, the planner result keeps ONLY scenario A (list length 1) and the tool sets `data["what_if"] = True` and `data["what_if_summary"]` (str). `monthly_savings_override`, when present, replaces `agg["monthly_net_flow"]`-derived capacity.

- [ ] **Step 1: Write the failing tests**

Append:

```python
from app.graph.tools.goal_planner_tool import _plan_car, _apply_what_if


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


def test_what_if_keeps_only_scenario_a():
    scenarios = [{"tag": "A"}, {"tag": "B"}, {"tag": "C"}]
    kept = _apply_what_if_scenarios(scenarios, what_if=True)
    assert [s["tag"] for s in kept] == ["A"]
    kept_all = _apply_what_if_scenarios(scenarios, what_if=False)
    assert len(kept_all) == 3
```

Add the import line at the top of the new imports: `from app.graph.tools.goal_planner_tool import _apply_what_if_scenarios`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `../venv/Scripts/python.exe -m pytest tests/test_goal_planner_rework.py -v`
Expected: FAIL — `ImportError: cannot import name '_apply_what_if'`

- [ ] **Step 3: Add the what-if helpers**

In `goal_planner_tool.py`, add near the top of the planner section (before `_GOAL_PLANNERS`):

```python
def _apply_what_if(agg: dict, goal: dict) -> dict:
    """Apply goal-level what-if overrides that affect the financial snapshot. Currently:
    `monthly_savings_override` replaces the user's modelled monthly surplus (so feasibility,
    the EMI cap and SIP all reflect the hypothetical saving rate)."""
    override = goal.get("monthly_savings_override")
    if override is not None:
        val = _parse_amount(override)
        if val is not None and val >= 0:
            agg = {**agg, "monthly_net_flow": float(val), "total_spending_cuts": 0.0}
    return agg


def _apply_what_if_scenarios(scenarios: list, what_if: bool) -> list:
    """For a what-if, keep ONLY scenario A (the single direct computation) — no B/C report."""
    if what_if and scenarios:
        head = dict(scenarios[0])
        head["recommended"] = True
        return [head]
    return scenarios
```

- [ ] **Step 4: Read `loan_interest_rate_pct` in the loan planners**

In `_plan_car`: the rate is hard-coded `rate=10.0`. Change to read the override:
```python
    rate = _num(goal.get("loan_interest_rate_pct"), 10.0)
```
and pass `rate=rate` into `_loan_scenarios`.

In `_plan_house`: change `rate=8.5` to:
```python
    rate = _num(goal.get("loan_interest_rate_pct"), 8.5)
```
and pass `rate=rate`.

In `_plan_education`: pass an override into `_education_scenarios` — add before the call:
```python
    edu_rate = _num(goal.get("loan_interest_rate_pct"), 10.5)
```
and pass `rate=edu_rate` (extend the `_education_scenarios` call with `rate=edu_rate`).

- [ ] **Step 5: Wire what-if into `goal_planner_tool`**

In `goal_planner_tool`, right after `agg["funding_selection"] = _resolve_funding_selection(goal, task)` and after the spending-cuts and investment/FD blocks populate `agg`, add the override application just before running the planner:

```python
    what_if = bool(goal.get("what_if"))
    agg = _apply_what_if(agg, goal)
```

Then, after `extra = planner(goal, agg)`, short-circuit the scenarios:

```python
    if "scenarios" in extra:
        extra["scenarios"] = _apply_what_if_scenarios(extra["scenarios"], what_if)
    if what_if:
        extra["what_if"] = True
        extra["what_if_summary"] = goal.get("description") or task.get("sub_question") or "What-if analysis"
```

And include `what_if` in the returned `data` dict (add `"what_if": what_if,` near `"goal_type": goal_type,`).

- [ ] **Step 6: Run tests**

Run: `../venv/Scripts/python.exe -m pytest tests/test_goal_planner_rework.py -v`
Expected: PASS (18 tests total)

- [ ] **Step 7: Commit**

```bash
git add backend/app/graph/tools/goal_planner_tool.py backend/tests/test_goal_planner_rework.py
git commit -m "feat(goal-planner): generalised what-if overrides (rate, savings) + single-scenario short-circuit"
```

---

### Task 7: Funding-split pie + skip charts on what-if (answer_node)

**Files:**
- Modify: `backend/app/graph/tools/goal_planner_tool.py` — expose `funding_breakdown` on the returned data.
- Modify: `backend/app/graph/nodes/answer_node.py` — add `_funding_split_pie`, use it in `_select_goal_artifacts`, and skip artifacts when `what_if`.
- Test: `backend/tests/test_goal_planner_rework.py`

**Interfaces:**
- Consumes: recommended scenario (`loan_amount`, `down_payment_amount`) + `funding_sources` (`from_bank_savings`, `from_fixed_deposits`, `from_liquid_funds`).
- Produces: `data["funding_breakdown"] = {"loan": float, "bank": float, "fd": float, "liquid": float}`; `_funding_split_pie(g) -> List[Dict]` (one pie artifact or `[]`).

- [ ] **Step 1: Write the failing tests**

Append:

```python
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


def test_select_goal_artifacts_empty_on_what_if():
    g = {"what_if": True, "scenarios": [{"tag": "A", "monthly_savings_needed": 5000}]}
    assert _select_goal_artifacts("car", g) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../venv/Scripts/python.exe -m pytest tests/test_goal_planner_rework.py -v`
Expected: FAIL — `ImportError: cannot import name '_funding_split_pie'`

- [ ] **Step 3: Expose `funding_breakdown` in `goal_planner_tool`**

In `goal_planner_tool`, after `extra["funding_sources"] = _funding_sources(agg)`, add:

```python
    # Compact self-funded-vs-loan split for the funding pie (answer_node).
    _rec = next((s for s in (extra.get("scenarios") or []) if s.get("recommended")), None) or {}
    _fs = extra["funding_sources"]
    extra["funding_breakdown"] = {
        "loan": round(float(_rec.get("loan_amount") or 0.0), 2),
        "bank": round(float(_fs.get("from_bank_savings") or 0.0), 2),
        "fd": round(float(_fs.get("from_fixed_deposits") or 0.0), 2),
        "liquid": round(float(_fs.get("from_liquid_funds") or 0.0), 2),
    }
```

- [ ] **Step 4: Add `_funding_split_pie` and wire it into `answer_node.py`**

Add the builder near `_funding_sources_bar`:

```python
def _funding_split_pie(g: Dict[str, Any]) -> List[Dict]:
    """Pie: how the goal is funded — Loan-financed vs self-funded sources (Bank / FD / Liquid)."""
    fb = g.get("funding_breakdown") or {}
    pairs = [("Loan-financed", fb.get("loan")), ("Bank cash", fb.get("bank")),
             ("Fixed deposits", fb.get("fd")), ("Liquid funds", fb.get("liquid"))]
    data = [{"label": lbl, "value": round(float(v), 2)} for lbl, v in pairs if v and float(v) > 0]
    return [_chart("pie", "How This Goal Is Funded", "label", "value", data)] if data else []
```

In `_select_goal_artifacts`, add the what-if guard at the very top and swap the funding bar for the pie:

```python
def _select_goal_artifacts(goal_type: str, g: Dict[str, Any]) -> List[Dict]:
    """Build up to 3 charts for a goal planning result — all from goal_planner data."""
    if g.get("what_if"):                      # what-ifs return a concise answer, no charts
        return []
    charts: List[Dict] = []
    scenarios = g.get("scenarios") or []

    charts += _scenarios_comparison_bar(scenarios)      # 1. scenario comparison
    charts += _budget_impact_bar(g)                     # 2. budget impact
    charts += _funding_split_pie(g)                     # 3. self-funded vs loan (pie)
```

Keep the rest of `_select_goal_artifacts` (the `if len(charts) < 3` fillers) unchanged — they still backfill goal-type charts when the pie has no data.

- [ ] **Step 5: Run tests**

Run: `../venv/Scripts/python.exe -m pytest tests/test_goal_planner_rework.py -v`
Expected: PASS (21 tests total)

- [ ] **Step 6: Commit**

```bash
git add backend/app/graph/tools/goal_planner_tool.py backend/app/graph/nodes/answer_node.py backend/tests/test_goal_planner_rework.py
git commit -m "feat(goal-planner): self-funded-vs-loan funding pie + skip charts on what-if"
```

---

### Task 8: Prompts — brain what-if path, schema fields, concise what-if answer

**Files:**
- Modify: `backend/app/utils/prompts.py` — brain goal schema + WHAT-IF section; new `GOAL_WHATIF_SYSTEM`; minor wording in `GOAL_PLAN_SYSTEM` / `GOAL_PLAN_SUMMARY_SYSTEM`.
- Modify: `backend/app/graph/nodes/answer_node.py` — route to `GOAL_WHATIF_SYSTEM` when `g["what_if"]`.
- Test: `backend/tests/test_goal_planner_rework.py`

**Interfaces:**
- Consumes: `data["what_if"]` from Task 6.
- Produces: `GOAL_WHATIF_SYSTEM` (str constant); brain schema gains `loan_interest_rate_pct`, `monthly_savings_override`, `what_if`.

- [ ] **Step 1: Write the failing tests (constant + schema presence)**

Append:

```python
from app.utils import prompts as P


def test_goal_whatif_system_prompt_exists():
    assert isinstance(getattr(P, "GOAL_WHATIF_SYSTEM", None), str)
    assert "what_if" in P.GOAL_WHATIF_SYSTEM.lower() or "what-if" in P.GOAL_WHATIF_SYSTEM.lower()


def test_brain_schema_has_whatif_fields():
    assert "loan_interest_rate_pct" in P.BRAIN_SYSTEM
    assert "monthly_savings_override" in P.BRAIN_SYSTEM
    assert '"what_if"' in P.BRAIN_SYSTEM
```

(If the brain prompt constant is named differently, grep `prompts.py` for the goal-planning schema block and use that constant name in the test — confirm with `grep -n "next_action" backend/app/utils/prompts.py`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `../venv/Scripts/python.exe -m pytest tests/test_goal_planner_rework.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'GOAL_WHATIF_SYSTEM'`

- [ ] **Step 3: Add the brain WHAT-IF section + schema fields**

In `prompts.py`, in the brain goal-planning instructions, after the existing "FUNDING WHAT-IFS" item (item 6), add item 7:

```
7. PARAMETER WHAT-IFS. When the user asks a hypothetical about a PRIOR goal — "what if the loan is
   interest-free", "what if my post-retirement spend is ₹1L", "what if 4 of us travel not 2",
   "what if I save ₹15,000/mo" — carry the prior goal from history, OVERRIDE ONLY the changed
   field(s), set "what_if": true, and route to goal_planner. Field map:
     • interest-free / different loan rate → loan_interest_rate_pct (0 for interest-free)
     • monthly saving hypothetical        → monthly_savings_override
     • retirement spend                    → monthly_retirement_expenses
     • travellers                          → travelers
     • any other stated parameter          → its existing goal field
   A what-if returns a single concise answer (no A/B/C report).
```

Then add the three fields to the `"goal": { ... }` schema block (after `"funding_selection": null`):

```
      "loan_interest_rate_pct": null,
      "monthly_savings_override": null,
      "what_if": false
```

- [ ] **Step 4: Add `GOAL_WHATIF_SYSTEM`**

In `prompts.py`, after `GOAL_PLAN_SUMMARY_SYSTEM`, add:

```python
GOAL_WHATIF_SYSTEM = """\
You are FinAssist's goal advisor answering a WHAT-IF on a goal the user already planned. You are
given the recomputed numbers (a single scenario — no A/B/C) under the hypothetical the user asked.

Today's Date: {current_date}

Recomputed Goal Data (JSON):
{context_text}

RULES:
1. Answer the specific what-if directly in the FIRST line — state the new headline number(s).
2. Copy every monetary value from its `_inr` sibling verbatim. Never rescale to lakh/crore, never
   recompute.
3. Give 1-3 short bullets of plain-English explanation of WHAT CHANGED and why the number moved
   (e.g. "interest-free → you pay only the principal, so the EMI drops to …"). No full report, no
   month-by-month plan, no scenario table.
4. Keep it under ~90 words. End with one short line inviting a full re-plan if they want options.\
"""
```

- [ ] **Step 5: Route what-ifs to the concise prompt in `answer_node.py`**

In `answer_node`, inside the `if goal_ev:` branch, where it picks `system_prompt`, add a what-if branch BEFORE the `detailed` check:

```python
            if g.get("what_if"):
                system_prompt = GOAL_WHATIF_SYSTEM.format(context_text=ctx, **fields)
                max_tokens = 400
            elif detailed:
                system_prompt = GOAL_PLAN_SYSTEM.format(context_text=ctx, **fields)
                max_tokens = 1400
            else:
                system_prompt = GOAL_PLAN_SUMMARY_SYSTEM.format(context_text=ctx, **fields)
                max_tokens = 1100
```

Add `GOAL_WHATIF_SYSTEM` to the existing `from app.utils.prompts import (...)` block at the top of `answer_node.py`. (`artifacts = _select_goal_artifacts(...)` already returns `[]` for what-ifs from Task 7, so no chart change needed here.)

- [ ] **Step 6: Run tests**

Run: `../venv/Scripts/python.exe -m pytest tests/test_goal_planner_rework.py -v`
Expected: PASS (23 tests total)

- [ ] **Step 7: Update the answer prompts' EMI/saving narrative**

In `GOAL_PLAN_SYSTEM` and `GOAL_PLAN_SUMMARY_SYSTEM`, update the affordability wording so it matches the new model (one-line edits):
- Where they say the EMI/commitment must fit "~70% of surplus", change to "~70% of your sustainable monthly saving (surplus plus the spending cuts identified below)".
- Where they describe Scenario B, change "adjusting the down payment / financing mix" to "deploying only the assets needed to close the gap (least-disruptive first — liquid funds or the FD closest to the amount, never breaking everything)".

These are copy-only edits; verify the prompts still `.format()` without KeyError:

Run: `../venv/Scripts/python.exe -c "from app.utils.prompts import GOAL_PLAN_SYSTEM, GOAL_PLAN_SUMMARY_SYSTEM, GOAL_WHATIF_SYSTEM; print('prompts import OK')"`
Expected: `prompts import OK`

- [ ] **Step 8: Full suite + commit**

Run: `../venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS (no regressions)

```bash
git add backend/app/utils/prompts.py backend/app/graph/nodes/answer_node.py backend/tests/test_goal_planner_rework.py
git commit -m "feat(goal-planner): brain what-if path + concise GOAL_WHATIF answer prompt"
```

---

## Self-Review

**Spec coverage:**
- D1 (A = pure user) → Tasks 2, 3.
- D2 (B = minimal deployment) → Tasks 1 (`_minimal_deployment`), 2, 3.
- D3 (C = right-size) → Tasks 2, 3.
- D4 (floating EMI cap) → Task 2 (`emi_cap = (surplus+cuts) × 0.70`).
- D5 (saving-feasibility gate) → Tasks 2, 3, 4.
- D6 (liquid live NAV + goal-end) → Task 5.
- D7 (balance-growth feasibility) → Tasks 2, 3.
- D8 (comprehensive across goals) → Tasks 2 (car/house), 3 (gadget/travel/emergency/wedding/generic), 4 (education); retirement/FIRE/multi-goal gain overrides via Task 6 `_apply_what_if`.
- D9 (generalised what-ifs, concise) → Tasks 6, 8.
- D10 (funding pie, skip on what-if) → Task 7.

**Placeholder scan:** none — every code/test step shows real code and exact commands.

**Type consistency:** `_loan_scenarios` / `_savings_scenarios` / `_education_scenarios` all take `agg: dict` (callers updated in the same task). `_minimal_deployment` returns the documented keys, consumed by scenario `deployment` fields and the funding pie via `funding_breakdown`. `_apply_what_if`(agg, goal), `_apply_what_if_scenarios`(scenarios, what_if), `_funding_split_pie`(g) signatures match their tests.

## Notes for the implementer
- **Retirement / FIRE / multi-goal** keep their own scenario shapes; they are NOT routed through the rewritten loan/savings builders. They still benefit from `_apply_what_if` (savings override) and the live-NAV liquid valuation via `agg`. Do not force A/B/C deployment semantics onto them.
- If `scheme_code` is missing from the `investments` table, Task 5's live-NAV lookup silently falls back to purchase NAV — acceptable; the pure projection/valuation functions are independently tested.
- After Task 2/3, manually spot-check one end-to-end goal (e.g. a car query) in the running app to confirm the answer narrative reads correctly with the new labels.
