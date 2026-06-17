# Goal Planner Bug & Logic Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 16 correctness/logic bugs in the goal planner so education financing, FIRE, retirement, savings-growth, liquidity, and multi-goal scheduling produce financially sound results.

**Architecture:** All changes are confined to one file — `backend/app/graph/tools/goal_planner_tool.py`. The biggest change is a rewrite of `_education_scenarios` so education is financed loan-first (debt up to ~100%, repaid post-graduation) rather than constrained by today's surplus. Every other fix is a localized edit to a single planner/helper. The public shape of each scenario dict is preserved so the downstream answer/caption models and chart builders keep working.

**Tech Stack:** Python 3.12, standard library only (`math`, `re`, `collections`), `unittest` for tests.

## Global Constraints

- **No new dependencies.** `pytest` is NOT installed; tests use the stdlib `unittest` module to match the existing `backend/tests/` suite.
- **Single file under change:** `backend/app/graph/tools/goal_planner_tool.py` (plus one new test file).
- **Preserve scenario dict keys.** Each scenario must keep its existing keys (`tag`, `label`, `recommended`, `monthly_savings_needed`, `feasible`, `shortfall_per_month`, `loan_amount`, `estimated_emi`, `down_payment_*`, `timeline_months`, etc.) — `app/utils/prompts.py` and the frontend chart builders read them by name. New keys may be ADDED; none may be removed or renamed except where a task explicitly says so.
- **Currency stays in full rupees.** Never rescale to "lakhs"/"Cr" in numeric fields. `_attach_inr` adds the `*_inr` display strings; do not bypass it.
- **Indian finance context:** rupees (₹), Indian digit grouping, education loans with moratorium + post-graduation repayment.
- **Tests run from the `backend/` directory:** `python -m unittest tests.test_goal_planner -v`
- **The module cannot be imported normally** in a bare checkout (its package `__init__` chain pulls in `langgraph`/`openai`/`supabase`, which are not installed). The test harness in Task 1 loads the file in isolation via `importlib` with stubbed parent packages. Every task reuses that harness.

---

## File Structure

- **Modify:** `backend/app/graph/tools/goal_planner_tool.py` — all production fixes.
- **Create:** `backend/tests/test_goal_planner.py` — unittest suite; one `TestCase` (or method group) per task.

The 16 spec items map to tasks as follows (spec items #17 needs no code — verified inside Task 2; #2 is resolved by Task 2):

| Task | Spec items | Area |
|------|-----------|------|
| 1 | (harness) | Shared test loader |
| 2 | #1, #2, #3, #17, #18 | Education scenarios rewrite |
| 3 | #4 | Education loan tenure configurable |
| 4 | #6 | Retirement divide-by-zero guard |
| 5 | #5, #7 | FIRE: spending cuts + finite years-to-FI |
| 6 | #13 | Savings goals respect investment growth |
| 7 | #8, #9 | Account balances: liquid-only + clamp negatives |
| 8 | #10 | Investment liquidity: label cost-basis valuation |
| 9 | #11 | House stamp duty: configurable + honest label |
| 10 | #12 | Car loan tenure configurable |
| 11 | #14 | Spending-cut category matching: score, don't first-match |
| 12 | #15 | Multi-goal sequential = real milestone schedule |
| 13 | #16 | Summary never prints "₹None" |

Tasks 3–13 are independent of each other and of Task 2 (different functions). Recommended order is as listed, but any order after Task 1 works.

---

### Task 1: Shared test harness

**Files:**
- Create: `backend/tests/test_goal_planner.py`

**Interfaces:**
- Produces: a module-level `gp` object — the loaded `goal_planner_tool` module — that every later test imports behaviors from (`gp._education_scenarios`, `gp._plan_fire`, etc.). Also produces `load_goal_planner()` for clarity.

- [ ] **Step 1: Write the harness + a smoke test**

Create `backend/tests/test_goal_planner.py`:

```python
"""
Unit tests for the goal planner financial logic.

The goal_planner_tool module lives under the `app.graph` package, whose __init__
chain imports langgraph/openai/supabase (not installed in CI for pure-logic tests).
We therefore load the single source file in isolation, stubbing only the two
modules it imports at top level, so the pure financial functions can be tested
without the full app environment.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
import unittest


def load_goal_planner():
    def stub(name, **attrs):
        mod = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(mod, key, value)
        sys.modules[name] = mod

    # Pre-register parent packages + the two import targets so the real __init__
    # files (which pull in heavy deps) never execute.
    stub("app")
    stub("app.graph")
    stub("app.utils")
    stub("app.graph.state", AgentState=dict)
    stub("app.utils.supabase_client", supabase_db=None)

    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "..", "app", "graph", "tools", "goal_planner_tool.py")
    spec = importlib.util.spec_from_file_location("goal_planner_tool_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gp = load_goal_planner()


class TestHarness(unittest.TestCase):
    def test_module_loads_and_emi_is_sane(self):
        # 10 lakh @ 10% p.a. over 60 months ≈ ₹21,247/month.
        emi = gp._calc_emi(1_000_000, 10.0, 60)
        self.assertAlmostEqual(emi, 21247.04, places=0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to confirm the harness loads the module**

Run (from `backend/`): `python -m unittest tests.test_goal_planner -v`
Expected: `test_module_loads_and_emi_is_sane ... ok` — 1 test passing.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_goal_planner.py
git commit -m "test: add goal planner test harness with isolated module loader"
```

---

### Task 2: Education scenarios — finance loan-first, not surplus-bound

Spec #1, #2, #3, #17, #18. This is the single most important correction. Education loans fund up to ~100% of program cost, with a moratorium during study and repayment from higher post-graduation income. Affordability of the **self-funded slice** (paid during study) is the only feasibility lever — NOT whether the loan EMI fits today's surplus.

**Files:**
- Modify: `backend/app/graph/tools/goal_planner_tool.py` — replace `_education_scenarios` (currently lines ~668–761) and the constant block (~463–467).
- Test: `backend/tests/test_goal_planner.py`

**Interfaces:**
- Consumes: `gp._education_scenarios(*, cost, existing, user_months, self_pct, surplus, cuts, deployable, rate=10.5, tenure=180)` → `(list[scenario_dict], meta_dict)`.
- Produces: scenario B always `recommended=True`; B `loan_amount ≈ cost - min(avail, cost*0.05)`; every scenario `feasible` depends only on `monthly_savings_needed <= save_cap`, never on EMI.

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_goal_planner.py`:

```python
class TestEducationScenarios(unittest.TestCase):
    def test_b_is_recommended_and_maximises_loan(self):
        scs, meta = gp._education_scenarios(
            cost=2_000_000, existing=0, user_months=12, self_pct=50,
            surplus=50_000, cuts=0, deployable=0,
        )
        b = next(s for s in scs if s["tag"] == "B")
        self.assertTrue(b["recommended"])
        # No upfront cash available -> loan covers the FULL program cost.
        self.assertEqual(b["loan_amount"], 2_000_000)
        self.assertEqual(b["down_payment_amount"], 0)
        self.assertTrue(b["feasible"])  # zero self-funding is trivially affordable

    def test_b_self_funding_is_capped_at_5pct_even_with_spare_cash(self):
        # Plenty of cash, but B should still MINIMISE self-funding to maximise the loan.
        scs, _ = gp._education_scenarios(
            cost=2_000_000, existing=1_000_000, user_months=12, self_pct=50,
            surplus=50_000, cuts=0, deployable=0,
        )
        b = next(s for s in scs if s["tag"] == "B")
        self.assertEqual(b["down_payment_amount"], 100_000)   # 5% of 20L
        self.assertEqual(b["loan_amount"], 1_900_000)

    def test_feasibility_ignores_emi_affordability(self):
        # A 1.5 Cr program with a tiny surplus: the EMI is unaffordable today, but the plan
        # is FEASIBLE because the (zero) self-funded portion is achievable during study.
        scs, meta = gp._education_scenarios(
            cost=15_000_000, existing=0, user_months=24, self_pct=50,
            surplus=20_000, cuts=0, deployable=0,
        )
        b = next(s for s in scs if s["tag"] == "B")
        self.assertEqual(b["loan_amount"], 15_000_000)
        self.assertTrue(b["feasible"])
        self.assertFalse(meta["target_out_of_reach"])  # education is never "out of reach"

    def test_c_minimises_loan_relative_to_b(self):
        scs, _ = gp._education_scenarios(
            cost=2_000_000, existing=500_000, user_months=24, self_pct=50,
            surplus=40_000, cuts=0, deployable=0,
        )
        b = next(s for s in scs if s["tag"] == "B")
        c = next(s for s in scs if s["tag"] == "C")
        self.assertGreater(c["down_payment_amount"], b["down_payment_amount"])
        self.assertLess(c["loan_amount"], b["loan_amount"])
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m unittest tests.test_goal_planner.TestEducationScenarios -v`
Expected: failures — `test_feasibility_ignores_emi_affordability` fails because current `feasible` includes `emi <= emi_cap`; `test_b_self_funding_is_capped_at_5pct...` fails because current B does not cap self-funding at 5%.

- [ ] **Step 3: Replace the constant block**

In `goal_planner_tool.py`, find:

```python
_EDU_EMI_FRAC = 0.60       # an education loan EMI may use at most this share of the surplus, so a
                           # 15-year repayment always leaves a monthly buffer (don't max it out).
```

Replace with:

```python
_EDU_MIN_SELF_FRAC = 0.05  # education is financed loan-first; self-fund at most this small slice
                           # upfront (capped by available cash) so the loan covers ~95-100%.
```

- [ ] **Step 4: Replace `_education_scenarios` entirely**

Replace the whole function (from `def _education_scenarios(` through its `return [sc_a, sc_b, sc_c], meta`) with:

```python
def _education_scenarios(*, cost: float, existing: float, user_months: float, self_pct: float,
                         surplus: float, cuts: float, deployable: float,
                         rate: float = 10.5, tenure: int = 180) -> tuple:
    """
    Education NEVER scales the program cost — a PhD/MS/MBA costs what it costs. Every scenario
    funds the FULL program; the only lever is the FINANCING STRUCTURE.

    Education loans are financed almost entirely by debt (up to 100%), with a moratorium during
    study and repayment from HIGHER post-graduation income. So feasibility depends ONLY on whether
    the self-funded slice (paid during study from surplus + short-term cuts) is achievable — it is
    NOT constrained by whether the loan EMI fits today's surplus.

        A 'Your Plan'              — the user's stated self-funded / loan mix.
        B 'Maximise the loan'  (RECOMMENDED) — minimal upfront self-funding (<=5% of cost, capped
                                   by available cash), loan covers the remaining ~95-100%.
        C 'Minimise the loan'      — self-fund the most you can during study → smaller loan, less
                                   interest.
    The program is never "out of reach": financing changes, not the program cost (spec #17).
    """
    surplus = max(surplus, 0.0); cuts = max(cuts, 0.0); cost = max(cost, 0.0)
    deployable = max(deployable, 0.0)
    user_months = max(1, int(round(user_months)))
    avail = existing + deployable
    cuts_note = f" (with ₹{round(cuts):,}/mo spending cuts)" if cuts > 0 else ""
    # The self-funded portion is paid DURING study (surplus + short-term spending cuts).
    save_cap = (surplus + cuts) * _CAP_UTIL
    yrs = max(1, tenure // 12)

    def make(tag, label, recommended, self_amt, months):
        months = max(1, int(months))
        self_amt = min(max(self_amt, 0.0), cost)
        loan_amt = round(max(0.0, cost - self_amt), 2)
        emi = round(_calc_emi(loan_amt, rate, tenure), 2) if loan_amt > 0 else 0.0
        lump = round(min(self_amt, avail), 2)
        to_save = round(max(0.0, self_amt - lump), 2)
        save = round(to_save / months, 2)
        interest = round(emi * tenure - loan_amt, 2) if loan_amt > 0 else 0.0
        return {
            "tag": tag, "label": label, "recommended": recommended,
            "purchase_price": round(cost, 2),                       # ALWAYS the full program cost
            "down_payment_pct": round(self_amt / cost * 100, 1) if cost else 0.0,
            "down_payment_amount": round(self_amt, 2),
            "down_payment_from_existing": lump,
            "down_payment_from_savings": to_save,
            "loan_amount": loan_amt,
            "loan_tenure_months": tenure if loan_amt > 0 else 0,
            "estimated_emi": emi, "monthly_post_purchase": emi,
            "post_graduation_emi": emi,   # repaid from higher post-degree income, NOT today's surplus
            "total_interest_paid": interest,
            "total_cost_of_ownership": round(cost + interest, 2),
            "timeline_months": months,
            "monthly_savings_needed": save,
            # Feasibility = can the SELF-FUNDED slice be saved during study? Repayment of the loan
            # happens after graduation from higher income, so the EMI is NOT an affordability gate.
            "feasible": save <= save_cap + 1,
            "shortfall_per_month": round(max(0.0, save - save_cap), 2),
            "recommended_instrument": "Education loan + SIP in debt/liquid MF for the self-funded portion",
        }

    # A — user's stated mix
    sc_a = make("A", f"Your Plan — {self_pct:.0f}% self-funded over {user_months} months",
                False, cost * self_pct / 100.0, user_months)

    # B (RECOMMENDED) — MAXIMISE the loan: self-fund only a minimal upfront slice (<=5% of cost,
    #   capped by available cash); the education loan covers the rest over a {yrs}-year tenure.
    self_b = min(avail, cost * _EDU_MIN_SELF_FRAC)
    loan_pct_b = (cost - self_b) / cost * 100 if cost else 0
    sc_b = make("B", f"Maximise the education loan — {loan_pct_b:.0f}% financed over a {yrs}-year loan{cuts_note}",
                True, self_b, user_months)

    # C — minimise the debt: self-fund the most you can during study → smaller loan, less interest.
    self_c = min(cost, avail + save_cap * user_months)
    sc_c = make("C", f"Minimise the loan — self-fund {self_c / cost * 100:.0f}%, pay less interest{cuts_note}" if cost else "Minimise the loan",
                False, self_c, user_months)

    # B is ALWAYS the recommended route — that's how education is normally financed. Its own
    # `feasible` flag reflects whether the minimal self-funded slice is achievable during study.
    meta = {"max_financeable_target": round(cost, 2), "target_out_of_reach": False}
    return [sc_a, sc_b, sc_c], meta
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m unittest tests.test_goal_planner.TestEducationScenarios -v`
Expected: all 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/graph/tools/goal_planner_tool.py backend/tests/test_goal_planner.py
git commit -m "fix(goal-planner): finance education loan-first, decouple feasibility from EMI"
```

---

### Task 3: Education loan tenure configurable

Spec #4. Allow `loan_tenure_years` in the goal payload; fall back to 15 years (180 months).

**Files:**
- Modify: `backend/app/graph/tools/goal_planner_tool.py` — `_plan_education` (~923–961).
- Test: `backend/tests/test_goal_planner.py`

**Interfaces:**
- Consumes: `gp._plan_education(goal: dict, agg: dict)`.
- Produces: passes a resolved `tenure` (months) into `_education_scenarios`; the human note reflects the chosen tenure.

- [ ] **Step 1: Write failing test**

Add to `backend/tests/test_goal_planner.py`:

```python
class TestEducationTenure(unittest.TestCase):
    AGG = {
        "monthly_net_flow": 30_000, "monthly_avg_spend": 20_000,
        "total_current_balance": 0.0, "total_spending_cuts": 0.0,
    }

    def test_loan_tenure_years_is_honoured(self):
        goal = {"goal_type": "education", "target_amount": 2_000_000,
                "timeline": "24 months", "loan_preference": "full loan",
                "loan_tenure_years": 10}
        out = gp._plan_education(goal, dict(self.AGG))
        b = next(s for s in out["scenarios"] if s["tag"] == "B")
        self.assertEqual(b["loan_tenure_months"], 120)
        self.assertIn("10-year", out["note"])

    def test_loan_tenure_defaults_to_15_years(self):
        goal = {"goal_type": "education", "target_amount": 2_000_000,
                "timeline": "24 months", "loan_preference": "full loan"}
        out = gp._plan_education(goal, dict(self.AGG))
        b = next(s for s in out["scenarios"] if s["tag"] == "B")
        self.assertEqual(b["loan_tenure_months"], 180)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m unittest tests.test_goal_planner.TestEducationTenure -v`
Expected: `test_loan_tenure_years_is_honoured` fails — tenure is hardcoded to 180.

- [ ] **Step 3: Edit `_plan_education`**

Find the body of `_plan_education` after the `user_self_pct = ...` line and the `_education_scenarios(` call. Replace:

```python
    # Education program cost is FIXED — the lever is the financing mix, not a cheaper "price".
    scenarios, meta = _education_scenarios(
        cost=cost, existing=existing, user_months=months, self_pct=user_self_pct,
        surplus=net, cuts=cuts, deployable=_deployable(agg),
    )
```

with:

```python
    # Loan tenure is configurable (10/15/20-year are common); default to 15 years.
    tenure_years = max(1, int(_num(goal.get("loan_tenure_years"), 15)))
    tenure_months = tenure_years * 12

    # Education program cost is FIXED — the lever is the financing mix, not a cheaper "price".
    scenarios, meta = _education_scenarios(
        cost=cost, existing=existing, user_months=months, self_pct=user_self_pct,
        surplus=net, cuts=cuts, deployable=_deployable(agg), tenure=tenure_months,
    )
```

Then replace the `"note": (...)` block in the returned dict:

```python
        "note": "Education loan EMI at 10.5% p.a. over a 15-year tenure (repayment starts after a "
                "moratorium during study; education loans can finance up to 100% of the program). "
                "Explore scholarships, fellowships and funded/stipend programs — many PhDs are fully funded.",
```

with:

```python
        "note": f"Education loan EMI at 10.5% p.a. over a {tenure_years}-year tenure (repayment "
                "starts after a moratorium during study; education loans can finance up to 100% of "
                "the program). Explore scholarships, fellowships and funded/stipend programs — many "
                "PhDs are fully funded.",
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_goal_planner.TestEducationTenure -v`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/graph/tools/goal_planner_tool.py backend/tests/test_goal_planner.py
git commit -m "fix(goal-planner): make education loan tenure configurable (loan_tenure_years)"
```

---

### Task 4: Retirement divide-by-zero / already-retired guard

Spec #6. When `current_age >= target_age`, `mo == 0` and the planner falls into nonsense (`sip = remaining`). Return an honest "already at/over retirement age" result.

**Files:**
- Modify: `backend/app/graph/tools/goal_planner_tool.py` — `_plan_retirement` (~964–1012).
- Test: `backend/tests/test_goal_planner.py`

**Interfaces:**
- Consumes: `gp._plan_retirement(goal, agg)`.
- Produces: when `cur_age >= ret_age`, a dict with `already_retired=True`, `monthly_sip_needed=0.0`, `feasible=True`, `scenarios=[]`.

- [ ] **Step 1: Write failing test**

Add to `backend/tests/test_goal_planner.py`:

```python
class TestRetirementGuard(unittest.TestCase):
    AGG = {"monthly_net_flow": 30_000, "monthly_avg_spend": 25_000}

    def test_already_retired_returns_safe_result(self):
        goal = {"goal_type": "retirement", "current_age": 60, "target_age": 55,
                "monthly_retirement_expenses": 30_000, "existing_savings": 5_000_000}
        out = gp._plan_retirement(goal, dict(self.AGG))
        self.assertTrue(out["already_retired"])
        self.assertEqual(out["monthly_sip_needed"], 0.0)
        self.assertTrue(out["feasible"])
        self.assertEqual(out["scenarios"], [])

    def test_normal_retirement_still_works(self):
        goal = {"goal_type": "retirement", "current_age": 30, "target_age": 60,
                "monthly_retirement_expenses": 50_000}
        out = gp._plan_retirement(goal, dict(self.AGG))
        self.assertNotIn("already_retired", out)
        self.assertEqual(len(out["scenarios"]), 3)
        self.assertGreater(out["monthly_sip_needed"], 0)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m unittest tests.test_goal_planner.TestRetirementGuard -v`
Expected: `test_already_retired_returns_safe_result` fails with `KeyError: 'already_retired'`.

- [ ] **Step 3: Insert the guard**

In `_plan_retirement`, find:

```python
    annual_ret_exp = ret_exp * 12
    base_corpus    = annual_ret_exp * 25  # 4% withdrawal rule
```

Insert immediately AFTER those two lines:

```python
    # Guard: if the user is already at/over their target retirement age there is no accumulation
    # window — return an honest result rather than dividing by a zero-month horizon (spec #6).
    if mo <= 0:
        return {
            "current_age": cur_age, "target_retirement_age": ret_age,
            "years_to_retirement": 0,
            "monthly_expenses_in_retirement": ret_exp,
            "corpus_target_today_value": round(base_corpus, 2),
            "current_investments": cur_inv,
            "monthly_sip_needed": 0.0,
            "feasible": True,
            "shortfall_per_month": 0.0,
            "already_retired": True,
            "note": "Your current age is at or beyond the target retirement age — you are already "
                    "at/over retirement. Shift focus from accumulation to a withdrawal plan (SWP) "
                    "from your existing corpus.",
            "recommended_instrument": "Systematic Withdrawal Plan (SWP) from existing corpus",
            "scenarios": [],
        }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_goal_planner.TestRetirementGuard -v`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/graph/tools/goal_planner_tool.py backend/tests/test_goal_planner.py
git commit -m "fix(goal-planner): guard retirement planner against age>=retirement-age"
```

---

### Task 5: FIRE — count spending cuts, never return infinite years

Spec #5 (FIRE ignores `total_spending_cuts`) and #7 (`_years_to_fi` returns `float('inf')`, which breaks downstream UIs/JSON).

**Files:**
- Modify: `backend/app/graph/tools/goal_planner_tool.py` — `_years_to_fi` (~181–189) and `_plan_fire` (~1015–1056).
- Test: `backend/tests/test_goal_planner.py`

**Interfaces:**
- Consumes: `gp._years_to_fi(current, monthly, corpus, annual_return=0.12)`, `gp._plan_fire(goal, agg)`.
- Produces: `_years_to_fi` returns `None` (not `inf`) when FI is unreachable within 50 years; `_plan_fire` invests `(net + cuts) * 0.7` and reports `feasible=False` when `years_to_fi is None`.

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_goal_planner.py`:

```python
class TestFire(unittest.TestCase):
    def test_years_to_fi_returns_none_when_unreachable(self):
        # Zero monthly investment, zero current worth, huge target -> never reaches FI.
        self.assertIsNone(gp._years_to_fi(0, 0, 10**9))

    def test_fire_counts_spending_cuts_in_investment(self):
        agg = {"monthly_net_flow": 40_000, "monthly_avg_spend": 50_000,
               "total_spending_cuts": 20_000}
        goal = {"goal_type": "fire", "target_amount": 50_000, "existing_savings": 1_000_000}
        out = gp._plan_fire(goal, dict(agg))
        # (40k + 20k) * 0.7 = 42k invested, NOT 40k*0.7=28k.
        self.assertEqual(out["monthly_investment_assumed"], 42_000)

    def test_fire_infeasible_is_not_infinity(self):
        agg = {"monthly_net_flow": 0, "monthly_avg_spend": 50_000,
               "total_spending_cuts": 0}
        goal = {"goal_type": "fire", "target_amount": 200_000, "existing_savings": 0}
        out = gp._plan_fire(goal, dict(agg))
        self.assertIsNone(out["years_to_fi"])
        self.assertFalse(out["feasible"])
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m unittest tests.test_goal_planner.TestFire -v`
Expected: `test_years_to_fi_returns_none...` fails (`inf` returned); `test_fire_counts_spending_cuts...` fails (28000 ≠ 42000).

- [ ] **Step 3: Make `_years_to_fi` return `None`**

In `_years_to_fi`, replace the final line:

```python
    return float("inf")
```

with:

```python
    return None  # FI not reachable within 50 years on these assumptions
```

- [ ] **Step 4: Update `_plan_fire`**

In `_plan_fire`, replace:

```python
    net     = agg["monthly_net_flow"]
    invest  = max(0.0, net * 0.7)  # assume 70% of surplus invested
    RETURN  = 0.12
```

with:

```python
    net     = agg["monthly_net_flow"]
    cuts    = agg.get("total_spending_cuts", 0.0)
    invest  = max(0.0, (net + cuts) * 0.7)  # 70% of (surplus + reclaimed spending cuts) invested
    RETURN  = 0.12
```

Then replace the `feasible` line in the returned dict:

```python
        "feasible": rec["years_to_fi"] < 40,
```

with:

```python
        "feasible": rec["years_to_fi"] is not None and rec["years_to_fi"] < 40,
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m unittest tests.test_goal_planner.TestFire -v`
Expected: all 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/graph/tools/goal_planner_tool.py backend/tests/test_goal_planner.py
git commit -m "fix(goal-planner): FIRE counts spending cuts; years-to-FI is None not inf"
```

---

### Task 6: Savings goals respect investment growth

Spec #13. For cash goals longer than 12 months, money grows — the monthly contribution needed is the SIP amount, not flat `gap / months`. Apply this inside `_savings_scenarios` (the shared engine for gadget, travel, wedding, generic, emergency-fund). Emergency funds stay liquid (0% growth) since they must remain instantly accessible.

> **Scope note:** This task applies growth to `_savings_scenarios` (cash goals) only. The loan-based planners (`_plan_house`, `_plan_car`) keep linear down-payment saving because their feasible-band solver is built on linear capacity math; reworking that solver is out of scope here. Retirement already uses SIP growth.

**Files:**
- Modify: `backend/app/graph/tools/goal_planner_tool.py` — add two constants near `_CAP_UTIL`, rewrite `_savings_scenarios` (~601–665), and pass `annual_return_pct=0.0` from `_plan_emergency_fund` (~857–883).
- Test: `backend/tests/test_goal_planner.py`

**Interfaces:**
- Consumes: `gp._savings_scenarios(*, target, existing, user_months, surplus, cuts, instrument, asset="goal", annual_return_pct=_SAVINGS_RETURN_PCT)`.
- Produces: for `months > 12` and `annual_return_pct > 0`, `monthly_savings_needed` uses the SIP formula and is strictly LESS than `gap / months`; each scenario carries `assumed_annual_return_pct`. For `months <= 12` (or 0% return) behavior is the old linear one.

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_goal_planner.py`:

```python
class TestSavingsGrowth(unittest.TestCase):
    def test_long_goal_needs_less_than_flat_split(self):
        # 5-year ₹10L wedding: with growth, monthly < flat gap/months.
        scs, _ = gp._savings_scenarios(
            target=1_000_000, existing=0, user_months=60,
            surplus=50_000, cuts=0, instrument="FD", asset="wedding",
        )
        a = next(s for s in scs if s["tag"] == "A")
        flat = 1_000_000 / 60  # 16,667
        self.assertLess(a["monthly_savings_needed"], flat)
        self.assertEqual(a["assumed_annual_return_pct"], gp._SAVINGS_RETURN_PCT)

    def test_short_goal_stays_linear(self):
        scs, _ = gp._savings_scenarios(
            target=120_000, existing=0, user_months=6,
            surplus=50_000, cuts=0, instrument="Liquid MF",
        )
        a = next(s for s in scs if s["tag"] == "A")
        self.assertAlmostEqual(a["monthly_savings_needed"], 20_000, places=0)

    def test_zero_return_disables_growth(self):
        scs, _ = gp._savings_scenarios(
            target=1_000_000, existing=0, user_months=60,
            surplus=50_000, cuts=0, instrument="Savings", annual_return_pct=0.0,
        )
        a = next(s for s in scs if s["tag"] == "A")
        self.assertAlmostEqual(a["monthly_savings_needed"], 1_000_000 / 60, places=0)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m unittest tests.test_goal_planner.TestSavingsGrowth -v`
Expected: failures — current code always uses `f / months` and has no `assumed_annual_return_pct` key.

- [ ] **Step 3: Add constants**

Near `_CAP_UTIL = 0.95` add:

```python
_SAVINGS_RETURN_PCT = 7.0   # expected p.a. return for cash goals >12 months (debt/hybrid MF)
_RETURN_MIN_MONTHS = 12     # only assume growth for goals longer than this
```

- [ ] **Step 4: Rewrite `_savings_scenarios`**

Replace the entire function with:

```python
def _savings_scenarios(*, target: float, existing: float, user_months: float,
                       surplus: float, cuts: float, instrument: str, asset: str = "goal",
                       annual_return_pct: float = _SAVINGS_RETURN_PCT) -> tuple:
    """
    Three DYNAMIC scenarios for a cash (no-loan) goal, respecting the user's timeline.
    Money invested for >12 months GROWS, so the monthly contribution needed for long goals is
    the SIP amount (lower than a flat gap/months). Short goals (<=12 months) and 0%-return goals
    (e.g. an emergency fund kept liquid) stay linear.
      A 'Your Plan'   — your timeline.
      B 'Recommended' — keep the timeline if the monthly fits surplus + cuts; else stretch
                        MODESTLY (bounded) to the soonest feasible point.
      C 'Right-Size'  — the largest target reachable within the original timeline (or, if it
                        already fits, the soonest the user could reach it).
    """
    surplus = max(surplus, 0.0)
    cuts = max(cuts, 0.0)
    user_months = max(1, int(round(user_months)))
    cap = surplus + cuts
    c = cap * _CAP_UTIL
    r = annual_return_pct / 100.0
    grows = annual_return_pct > 0
    cuts_note = f" (with ₹{round(cuts):,}/mo spending cuts)" if cuts > 0 else ""
    max_months = _max_stretch_months(user_months)

    def _monthly_for(target_amt, months):
        """Monthly contribution needed to reach target_amt from `existing` over `months`."""
        if months > _RETURN_MIN_MONTHS and grows:
            existing_fv = _corpus_growth(existing, 0.0, r, months)
            need = max(0.0, target_amt - existing_fv)
            return round(_monthly_sip_for_corpus(need, annual_return_pct, months), 2)
        return round(max(0.0, target_amt - existing) / months, 2)

    def _reachable(months):
        """Largest target reachable from `existing` over `months` at full capacity c."""
        if months > _RETURN_MIN_MONTHS and grows:
            return _corpus_growth(existing, c, r, months)
        return existing + c * months

    def build(tag, label, recommended, target_amt, months, capacity):
        months = max(1, int(months))
        save = _monthly_for(target_amt, months)
        return {
            "tag": tag, "label": label, "recommended": recommended,
            "timeline_months": months,
            "monthly_savings_needed": save,
            "target_amount": round(target_amt, 2),
            "gap": round(max(0.0, target_amt - existing), 2),
            "assumed_annual_return_pct": annual_return_pct,
            "feasible": save <= capacity + 1,
            "shortfall_per_month": round(max(0.0, save - capacity), 2),
            "recommended_instrument": instrument,
        }

    # A — your plan
    sc_a = build("A", f"Your Plan — {user_months} months", False, target, user_months, surplus)

    # B — keep the timeline if it fits; else stretch MODESTLY (capped ~1.5x) to the soonest point
    months_b = user_months
    while c > 0 and _monthly_for(target, months_b) > c and months_b < max_months:
        months_b += 1
    if months_b == user_months:
        label_b = f"Keep this target — your {user_months}-month timeline{cuts_note}"
    else:
        label_b = f"Keep this target — {months_b} months (a {months_b-user_months}-month extension){cuts_note}"
    sc_b = build("B", label_b, False, target, months_b, cap)

    # C — right-size the target to the original timeline (or reach sooner if it already fits)
    reachable = _reachable(user_months)
    affordable_target = round(min(reachable, target), 2)
    out_of_reach = target > 0 and affordable_target < target * _TARGET_FLOOR_FRAC
    if reachable >= target * 0.98:
        months_fast = user_months
        while c > 0 and _monthly_for(target, months_fast) <= c and months_fast > 1:
            months_fast -= 1
        months_fast = min(months_fast + 1, user_months)  # smallest months that still fits
        sc_c = build("C", f"Reach Sooner — same target in {months_fast} months{cuts_note}",
                     False, target, months_fast, cap)
    elif out_of_reach:
        sc_c = build("C", f"Most you can save — {_inr(affordable_target)} (your {_inr(target)} target is out of reach in {user_months} months){cuts_note}",
                     False, affordable_target, user_months, cap)
    else:
        sc_c = build("C", f"Right-Size — a {_inr(affordable_target)} target fits your {user_months}-month timeline{cuts_note}",
                     False, affordable_target, user_months, cap)

    # Recommend whichever actually works within the user's (modestly stretched) timeline.
    (sc_b if sc_b["feasible"] else sc_c)["recommended"] = True
    meta = {"max_financeable_target": affordable_target, "target_out_of_reach": bool(out_of_reach)}
    return [sc_a, sc_b, sc_c], meta
```

- [ ] **Step 5: Make the emergency fund stay liquid (no growth)**

In `_plan_emergency_fund`, replace:

```python
    scenarios, meta = _savings_scenarios(target=target, existing=current, user_months=user_months,
                                   surplus=net, cuts=cuts,
                                   instrument="High-yield savings account + Liquid MF (instant access)")
```

with:

```python
    # An emergency fund must stay instantly accessible — assume no growth (kept liquid).
    scenarios, meta = _savings_scenarios(target=target, existing=current, user_months=user_months,
                                   surplus=net, cuts=cuts, annual_return_pct=0.0,
                                   instrument="High-yield savings account + Liquid MF (instant access)")
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m unittest tests.test_goal_planner.TestSavingsGrowth -v`
Expected: all 3 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/graph/tools/goal_planner_tool.py backend/tests/test_goal_planner.py
git commit -m "fix(goal-planner): long-horizon cash goals assume investment growth (SIP)"
```

---

### Task 7: Account balances — liquid-only, clamp negatives

Spec #8 (EPF/PPF/FD/locked balances are NOT deployable cash) and #9 (a negative balance must not reduce the liquid total).

**Files:**
- Modify: `backend/app/graph/tools/goal_planner_tool.py` — `_get_account_balances` (~353–374).
- Test: `backend/tests/test_goal_planner.py`

**Interfaces:**
- Consumes: an injectable list of account rows. To keep this testable without a live DB, refactor the per-row classification into a pure helper `_classify_balances(rows)`.
- Produces: `_classify_balances(rows: list[dict]) -> {"liquid_balance", "credit_accounts", "illiquid_accounts"}`; `_get_account_balances` calls it.

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_goal_planner.py`:

```python
class TestAccountClassification(unittest.TestCase):
    def test_locked_instruments_excluded_from_liquid(self):
        rows = [
            {"account_name": "HDFC Savings", "account_type": "savings", "current_balance": 100_000},
            {"account_name": "EPF",          "account_type": "epf",     "current_balance": 500_000},
            {"account_name": "SBI FD",       "account_type": "fixed deposit", "current_balance": 300_000},
            {"account_name": "Visa CC",      "account_type": "credit card", "current_balance": 20_000},
        ]
        out = gp._classify_balances(rows)
        self.assertEqual(out["liquid_balance"], 100_000)            # only the savings account
        self.assertEqual(len(out["illiquid_accounts"]), 2)          # EPF + FD
        self.assertEqual(len(out["credit_accounts"]), 1)

    def test_negative_balance_does_not_reduce_liquid(self):
        rows = [
            {"account_name": "A", "account_type": "savings", "current_balance": 50_000},
            {"account_name": "B", "account_type": "current", "current_balance": -10_000},
        ]
        out = gp._classify_balances(rows)
        self.assertEqual(out["liquid_balance"], 50_000)             # negative clamped to 0

    def test_blank_type_treated_as_liquid(self):
        rows = [{"account_name": "X", "account_type": "", "current_balance": 25_000}]
        out = gp._classify_balances(rows)
        self.assertEqual(out["liquid_balance"], 25_000)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m unittest tests.test_goal_planner.TestAccountClassification -v`
Expected: `AttributeError: module ... has no attribute '_classify_balances'`.

- [ ] **Step 3: Add `_classify_balances` and refactor `_get_account_balances`**

Replace the whole `_get_account_balances` function with:

```python
# Account-type substrings that are NOT deployable cash (locked / long-term instruments).
_NON_LIQUID_TYPES = ("epf", "ppf", "fixed", "fd", "deposit", "nps", "locked",
                     "retirement", "gratuity", "sukanya", "bond", "ulip")
# Account-type substrings that ARE liquid spendable cash.
_LIQUID_TYPES = ("saving", "current", "cash", "checking", "wallet", "bank")


def _classify_balances(rows: List[Dict]) -> Dict[str, Any]:
    """
    Split account rows into liquid (spendable), credit (liability), and illiquid (locked) buckets.
    - Credit-card balances are LIABILITIES, never a funding source.
    - EPF/PPF/FD/NPS etc. are locked and NOT deployable cash.
    - Negative balances never reduce the liquid total (clamped to 0).
    """
    liquid = 0.0
    credit_accounts: List[Dict] = []
    illiquid_accounts: List[Dict] = []
    for r in (rows or []):
        atype = (r.get("account_type") or "").lower()
        bal = float(r.get("current_balance") or 0)
        if "credit" in atype:
            credit_accounts.append({"name": r.get("account_name"), "outstanding": round(bal, 2)})
        elif any(t in atype for t in _NON_LIQUID_TYPES):
            illiquid_accounts.append({"name": r.get("account_name"), "type": atype,
                                      "balance": round(max(0.0, bal), 2)})
        elif atype == "" or any(t in atype for t in _LIQUID_TYPES):
            liquid += max(0.0, bal)   # a negative balance must not reduce deployable cash
        else:
            # Unknown type: be conservative and treat as illiquid rather than spendable.
            illiquid_accounts.append({"name": r.get("account_name"), "type": atype,
                                      "balance": round(max(0.0, bal), 2)})
    return {
        "liquid_balance": round(liquid, 2),
        "credit_accounts": credit_accounts,
        "illiquid_accounts": illiquid_accounts,
    }


def _get_account_balances(user_id: str) -> Dict[str, Any]:
    """Fetch account rows from Supabase and classify them (liquid / credit / illiquid)."""
    rows: List[Dict] = []
    try:
        if supabase_db:
            resp = (supabase_db.table("accounts")
                    .select("account_name, account_type, current_balance")
                    .eq("user_id", user_id).execute())
            rows = resp.data or []
    except Exception as exc:
        logger.warning("[goal_planner] balance fetch error: %s", exc)
    return _classify_balances(rows)
```

- [ ] **Step 4: Surface illiquid accounts in the main payload (optional honesty field)**

In `goal_planner_tool`, find:

```python
    target_amount = _parse_amount(goal.get("target_amount"))
    credit_accounts = balance_info.get("credit_accounts") or []
```

and after the `credit_accounts = ...` line add:

```python
    illiquid_accounts = balance_info.get("illiquid_accounts") or []
```

Then in the `data = { ... }` dict, after the `"credit_accounts": credit_accounts,` line add:

```python
        "illiquid_accounts": illiquid_accounts,
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m unittest tests.test_goal_planner.TestAccountClassification -v`
Expected: all 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/graph/tools/goal_planner_tool.py backend/tests/test_goal_planner.py
git commit -m "fix(goal-planner): count only liquid accounts, clamp negative balances"
```

---

### Task 8: Investment liquidity — label cost-basis valuation

Spec #10. `_fetch_investment_holdings` values holdings at `quantity * purchase_nav` (cost basis), but the field is named `current_value`. Keep the consuming key intact, but flag the valuation basis so the liquidity recommendation is honest about it.

**Files:**
- Modify: `backend/app/graph/tools/goal_planner_tool.py` — `_fetch_investment_holdings` (~413–433) and `_check_investment_liquidity` (~276–303).
- Test: `backend/tests/test_goal_planner.py`

**Interfaces:**
- Consumes: `gp._check_investment_liquidity(gap, inv_data)`.
- Produces: `_fetch_investment_holdings` adds `"valuation_basis": "purchase_cost"` to its returned dict; `_check_investment_liquidity` echoes `valuation_basis` (defaulting to `"current_nav"`) and appends a caveat to `recommendation` when the basis is purchase cost.

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_goal_planner.py`:

```python
class TestInvestmentValuation(unittest.TestCase):
    def test_cost_basis_caveat_present(self):
        inv = {"total_current": 200_000, "valuation_basis": "purchase_cost",
               "holdings": [{"name": "Liquid Fund", "current_value": 200_000}]}
        out = gp._check_investment_liquidity(50_000, inv)
        self.assertEqual(out["valuation_basis"], "purchase_cost")
        self.assertIn("purchase cost", out["recommendation"].lower())

    def test_nav_based_has_no_caveat(self):
        inv = {"total_current": 200_000,
               "holdings": [{"name": "Liquid Fund", "current_value": 200_000}]}
        out = gp._check_investment_liquidity(50_000, inv)
        self.assertEqual(out["valuation_basis"], "current_nav")
        self.assertNotIn("purchase cost", out["recommendation"].lower())
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m unittest tests.test_goal_planner.TestInvestmentValuation -v`
Expected: `KeyError: 'valuation_basis'`.

- [ ] **Step 3: Tag the DB-sourced snapshot**

In `_fetch_investment_holdings`, replace:

```python
            return {"total_current": round(total, 2), "holdings": holdings}
```

with:

```python
            # Values are cost basis (quantity * purchase_nav), NOT live NAV — flag it honestly.
            return {"total_current": round(total, 2), "holdings": holdings,
                    "valuation_basis": "purchase_cost"}
```

- [ ] **Step 4: Echo the basis in the liquidity check**

In `_check_investment_liquidity`, find the `return { ... }` block at the end and replace it with:

```python
    basis = inv_data.get("valuation_basis") or "current_nav"
    if basis == "purchase_cost":
        note += (" Note: portfolio values are estimated from purchase cost (not live NAV), so the "
                 "actual liquidatable value may differ.")
    return {
        "total_portfolio_value": round(total_current, 2),
        "estimated_liquid_value": liquid_val,
        "gap": round(gap, 2),
        "can_fully_cover": liquid_val >= gap > 0,
        "valuation_basis": basis,
        "recommendation": note,
    }
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m unittest tests.test_goal_planner.TestInvestmentValuation -v`
Expected: both tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/graph/tools/goal_planner_tool.py backend/tests/test_goal_planner.py
git commit -m "fix(goal-planner): flag investment liquidity values as cost-basis estimates"
```

---

### Task 9: House stamp duty — configurable + honest label

Spec #11. Stamp duty varies 4–10%+ by state/gender/property type. Allow a `stamp_duty_pct` override and make the note explicit that 7% is a rough default.

**Files:**
- Modify: `backend/app/graph/tools/goal_planner_tool.py` — `_plan_house` (~886–920).
- Test: `backend/tests/test_goal_planner.py`

**Interfaces:**
- Consumes: `gp._plan_house(goal, agg)`.
- Produces: `stamp_duty_pct_assumed` in the output; `stamp_duty_registration_estimate` computed from the resolved pct; the note labels it a rough, state-varying estimate.

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_goal_planner.py`:

```python
class TestHouseStampDuty(unittest.TestCase):
    AGG = {"monthly_net_flow": 80_000, "monthly_avg_spend": 40_000,
           "total_current_balance": 500_000, "total_spending_cuts": 0.0}

    def test_default_stamp_duty_is_7pct_and_labelled_rough(self):
        goal = {"goal_type": "house", "target_amount": 10_000_000,
                "timeline": "36 months", "down_payment_pct": 20}
        out = gp._plan_house(goal, dict(self.AGG))
        self.assertEqual(out["stamp_duty_pct_assumed"], 7.0)
        self.assertEqual(out["stamp_duty_registration_estimate"], 700_000)
        self.assertIn("rough", out["note"].lower())

    def test_stamp_duty_pct_override(self):
        goal = {"goal_type": "house", "target_amount": 10_000_000,
                "timeline": "36 months", "down_payment_pct": 20, "stamp_duty_pct": 5}
        out = gp._plan_house(goal, dict(self.AGG))
        self.assertEqual(out["stamp_duty_pct_assumed"], 5.0)
        self.assertEqual(out["stamp_duty_registration_estimate"], 500_000)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m unittest tests.test_goal_planner.TestHouseStampDuty -v`
Expected: `KeyError: 'stamp_duty_pct_assumed'`.

- [ ] **Step 3: Edit `_plan_house`**

Replace:

```python
    stamp    = round(prop * 0.07, 2)  # ~7% India stamp duty + registration
```

with:

```python
    stamp_pct = _num(goal.get("stamp_duty_pct"), 7.0)        # rough default; varies by state
    stamp     = round(prop * stamp_pct / 100.0, 2)
```

Replace the `"note": ...` line in the returned dict:

```python
        "note": "Home loan EMI at 8.5% p.a., 20-year tenure. Verify with your bank.",
```

with:

```python
        "note": f"Home loan EMI at 8.5% p.a., 20-year tenure. Stamp duty + registration estimated "
                f"at {stamp_pct:.0f}% — a ROUGH figure that varies 4–10% by state, gender and "
                f"property type; verify your state's rate. Verify loan rates with your bank.",
        "stamp_duty_pct_assumed": stamp_pct,
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_goal_planner.TestHouseStampDuty -v`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/graph/tools/goal_planner_tool.py backend/tests/test_goal_planner.py
git commit -m "fix(goal-planner): configurable stamp duty pct with honest rough-estimate label"
```

---

### Task 10: Car loan tenure configurable

Spec #12. Car loan tenure is hardcoded to 60 months; allow `loan_tenure_months` (common: 36/60/84) with a 60-month fallback.

**Files:**
- Modify: `backend/app/graph/tools/goal_planner_tool.py` — `_plan_car` (~788–827).
- Test: `backend/tests/test_goal_planner.py`

**Interfaces:**
- Consumes: `gp._plan_car(goal, agg)`.
- Produces: the recommended scenario's `loan_tenure_months` reflects the payload value; the note states the resolved tenure.

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_goal_planner.py`:

```python
class TestCarTenure(unittest.TestCase):
    AGG = {"monthly_net_flow": 60_000, "monthly_avg_spend": 30_000,
           "total_current_balance": 300_000, "total_spending_cuts": 0.0}

    def test_loan_tenure_months_honoured(self):
        goal = {"goal_type": "car", "target_amount": 1_000_000, "timeline": "12 months",
                "financing_preference": "loan", "down_payment_pct": 20,
                "loan_tenure_months": 84}
        out = gp._plan_car(goal, dict(self.AGG))
        self.assertIn("7-year", out["note"])
        # at least one scenario with a loan should carry the 84-month tenure
        tenures = {s["loan_tenure_months"] for s in out["scenarios"] if s["loan_amount"] > 0}
        self.assertIn(84, tenures)

    def test_loan_tenure_defaults_to_60(self):
        goal = {"goal_type": "car", "target_amount": 1_000_000, "timeline": "12 months",
                "financing_preference": "loan", "down_payment_pct": 20}
        out = gp._plan_car(goal, dict(self.AGG))
        tenures = {s["loan_tenure_months"] for s in out["scenarios"] if s["loan_amount"] > 0}
        self.assertIn(60, tenures)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m unittest tests.test_goal_planner.TestCarTenure -v`
Expected: `test_loan_tenure_months_honoured` fails — tenure hardcoded to 60.

- [ ] **Step 3: Edit `_plan_car`**

After the `cuts = agg.get("total_spending_cuts", 0.0)` line, add:

```python
    tenure_months = max(1, int(_num(goal.get("loan_tenure_months"), 60)))
```

Replace the `_loan_scenarios(` call's `tenure=60` argument:

```python
        rate=10.0, tenure=60, down_label="down payment", asset="car",
```

with:

```python
        rate=10.0, tenure=tenure_months, down_label="down payment", asset="car",
```

Replace the `"note": ...` line:

```python
        "note": "EMI at 10% p.a., 5-year tenure. Verify current rates with your bank.",
```

with:

```python
        "note": f"EMI at 10% p.a., {tenure_months // 12}-year ({tenure_months}-month) tenure. "
                "Verify current rates with your bank.",
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_goal_planner.TestCarTenure -v`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/graph/tools/goal_planner_tool.py backend/tests/test_goal_planner.py
git commit -m "fix(goal-planner): make car loan tenure configurable (loan_tenure_months)"
```

---

### Task 11: Spending-cut matching — score, don't first-match

Spec #14. The current matcher breaks on the FIRST matching keyword, so dict iteration order silently determines the suggested reduction %. Score all matches and pick the highest reduction explicitly.

**Files:**
- Modify: `backend/app/graph/tools/goal_planner_tool.py` — `_spending_reduction_opportunities` (~250–273).
- Test: `backend/tests/test_goal_planner.py`

**Interfaces:**
- Consumes: `gp._spending_reduction_opportunities(categories: list[dict])`.
- Produces: each result uses the HIGHEST `suggested_reduction_pct` among all matched keywords and adds `matched_keyword`.

- [ ] **Step 1: Write failing test**

Add to `backend/tests/test_goal_planner.py`:

```python
class TestSpendingReduction(unittest.TestCase):
    def test_picks_highest_reduction_match(self):
        # "Food & Dining" with a "cafe" sub-category: 'food' (20%) and 'cafe' (40%) both match;
        # the highest (cafe, 40%) must win regardless of dict order.
        cats = [{
            "category": "Food & Dining", "amount": 10_000,
            "subcategories": [{"name": "Cafe Coffee Day", "amount": 4_000}],
        }]
        out = gp._spending_reduction_opportunities(cats)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["suggested_reduction_pct"], 40)
        self.assertEqual(out[0]["potential_saving"], 4_000)

    def test_non_reducible_skipped(self):
        cats = [{"category": "Rent", "amount": 30_000, "subcategories": []}]
        self.assertEqual(gp._spending_reduction_opportunities(cats), [])
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m unittest tests.test_goal_planner.TestSpendingReduction -v`
Expected: `test_picks_highest_reduction_match` may fail — current code breaks on first match (`food`=20%), so it can return 20 instead of 40.

- [ ] **Step 3: Rewrite the matching loop**

In `_spending_reduction_opportunities`, replace the inner `for kw, pct in _REDUCIBLE_KEYWORDS.items(): ... break` block. The full function body becomes:

```python
def _spending_reduction_opportunities(categories: List[Dict]) -> List[Dict]:
    """Identify reducible categories with sub-category justification + potential monthly saving."""
    result = []
    for cat in categories:
        name = (cat.get("category") or "").lower()
        amount = float(cat.get("amount") or 0)
        if amount <= 500:
            continue
        if any(nr in name for nr in _NON_REDUCIBLE):
            continue
        # Match on the main category OR any of its sub-categories.
        subs = cat.get("subcategories") or []
        haystack = name + " " + " ".join((s.get("name") or "").lower() for s in subs)
        # Score ALL keyword matches and pick the HIGHEST reduction — never first-match-wins
        # (dict order must not silently determine the recommendation).
        matches = [(kw, pct) for kw, pct in _REDUCIBLE_KEYWORDS.items() if kw in haystack]
        if not matches:
            continue
        best_kw, best_pct = max(matches, key=lambda kp: kp[1])
        result.append({
            "category": cat["category"],
            "current_monthly": round(amount, 2),
            "suggested_reduction_pct": best_pct,
            "matched_keyword": best_kw,
            "potential_saving": round(amount * best_pct / 100, 2),
            "driven_by": [{"name": s.get("name"), "amount": s.get("amount")} for s in subs[:3]],
        })
    result.sort(key=lambda x: x["potential_saving"], reverse=True)
    return result[:4]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_goal_planner.TestSpendingReduction -v`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/graph/tools/goal_planner_tool.py backend/tests/test_goal_planner.py
git commit -m "fix(goal-planner): pick highest-reduction category match, not first match"
```

---

### Task 12: Multi-goal sequential = real milestone schedule

Spec #15. The "sequential" strategy currently funds only the first goal (`alloc = needed if i==0 else 0`) and never models what happens after Goal 1 finishes. Build a real back-to-back milestone schedule.

**Files:**
- Modify: `backend/app/graph/tools/goal_planner_tool.py` — `_plan_multi_goal` (~1083–1137).
- Test: `backend/tests/test_goal_planner.py`

**Interfaces:**
- Consumes: `gp._plan_multi_goal(goal, agg)`.
- Produces: in the "sequential" scenario, each goal has `start_month`, `end_month`, `funding_window` and a non-zero `allocated_monthly` during its window; goals are funded one after another (windows do not overlap).

- [ ] **Step 1: Write failing test**

Add to `backend/tests/test_goal_planner.py`:

```python
class TestMultiGoalSequential(unittest.TestCase):
    def test_sequential_builds_back_to_back_windows(self):
        agg = {"monthly_net_flow": 50_000}
        goal = {"goal_type": "multi_goal", "sub_goals": [
            {"description": "Laptop", "target_amount": 100_000, "timeline": "5 months"},
            {"description": "Trip",   "target_amount": 200_000, "timeline": "10 months"},
        ]}
        out = gp._plan_multi_goal(goal, dict(agg))
        seq = next(s for s in out["scenarios"] if s["strategy"] == "sequential")
        goals = seq["goals"]
        self.assertEqual(len(goals), 2)
        # First goal starts at month 1; the second starts right after the first ends.
        self.assertEqual(goals[0]["start_month"], 1)
        self.assertEqual(goals[1]["start_month"], goals[0]["end_month"] + 1)
        # During its window each goal receives a non-zero allocation (real funding, not 0).
        self.assertGreater(goals[1]["allocated_monthly"], 0)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m unittest tests.test_goal_planner.TestMultiGoalSequential -v`
Expected: failures — current sequential goals lack `start_month`/`end_month` and the 2nd goal's `allocated_monthly` is 0.

- [ ] **Step 3: Store the per-goal gap, then rewrite the sequential allocator**

In `_plan_multi_goal`, in the loop that builds `planned`, replace:

```python
        if target and mo and mo > 0:
            ms = max(0.0, round((target - ex) / mo, 2))
            total_needed += ms
            planned.append({
                "description": sg.get("description"),
                "goal_type": sg.get("goal_type", "generic"),
                "target_amount": target, "timeline_months": mo,
                "monthly_savings_needed": ms,
            })
```

with:

```python
        if target and mo and mo > 0:
            gap = max(0.0, target - ex)
            ms = round(gap / mo, 2)
            total_needed += ms
            planned.append({
                "description": sg.get("description"),
                "goal_type": sg.get("goal_type", "generic"),
                "target_amount": target, "timeline_months": mo,
                "gap": round(gap, 2),
                "monthly_savings_needed": ms,
            })
```

Then in `_allocate`, replace the `if strategy == "sequential":` branch. The relevant part of the function becomes:

```python
    def _allocate(strategy: str) -> list:
        if strategy == "sequential":
            # Fund goals one after another at FULL capacity: compute each goal's funding window
            # (gap / investable, rounded up) and schedule them back-to-back.
            result = []
            start = 0
            for p in planned:
                if investable > 0:
                    duration = max(1, math.ceil(p["gap"] / investable))
                    alloc = round(min(investable, p["gap"]), 2)
                else:
                    duration = int(p.get("timeline_months") or 1)
                    alloc = 0.0
                result.append({
                    **p,
                    "allocated_monthly": alloc,
                    "start_month": start + 1,
                    "end_month": start + duration,
                    "funding_window": f"Month {start + 1}–{start + duration}",
                })
                start += duration
            return result
        result = []
        for i, p in enumerate(planned):
            if strategy == "parallel":
                prop  = p["monthly_savings_needed"] / max(total_needed, 1)
                alloc = round(investable * prop, 2)
            else:  # hybrid: 60% to most urgent, 40% split
                if i == 0:
                    alloc = round(investable * 0.60, 2)
                else:
                    rest_prop = p["monthly_savings_needed"] / max(total_needed - planned[0]["monthly_savings_needed"], 1)
                    alloc = round(investable * 0.40 * rest_prop, 2)
            result.append({**p, "allocated_monthly": alloc})
        return result
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_goal_planner.TestMultiGoalSequential -v`
Expected: the test PASSES.

- [ ] **Step 5: Commit**

```bash
git add backend/app/graph/tools/goal_planner_tool.py backend/tests/test_goal_planner.py
git commit -m "fix(goal-planner): multi-goal sequential builds real back-to-back schedule"
```

---

### Task 13: Summary never prints "₹None"

Spec #16. When `target_amount` is `None` the log/summary string renders `target=₹None`. Use `_inr` with an `N/A` fallback and format the other monetary fields consistently.

**Files:**
- Modify: `backend/app/graph/tools/goal_planner_tool.py` — `goal_planner_tool`, the `summary = (...)` block (~1245–1251).
- Test: `backend/tests/test_goal_planner.py`

**Interfaces:**
- Consumes: a small pure helper to format the summary; extract it so it is testable without a DB. Add `_goal_summary(goal_type, target_amount, timeline, monthly_needed, net_flow, feasible, n_scenarios) -> str`.
- Produces: `_goal_summary(...)` never contains the substring `₹None`; a `None` target renders `target=N/A`.

- [ ] **Step 1: Write failing test**

Add to `backend/tests/test_goal_planner.py`:

```python
class TestGoalSummary(unittest.TestCase):
    def test_none_target_renders_na_not_rupee_none(self):
        s = gp._goal_summary("retirement", None, "30 years", 12_000, 40_000, True, 3)
        self.assertNotIn("₹None", s)
        self.assertIn("target=N/A", s)

    def test_numeric_target_is_inr_formatted(self):
        s = gp._goal_summary("car", 1_000_000, "12 months", 50_000, 60_000, True, 3)
        self.assertIn("target=₹10,00,000", s)
        self.assertIn("monthly_needed=₹50,000", s)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m unittest tests.test_goal_planner.TestGoalSummary -v`
Expected: `AttributeError: ... '_goal_summary'`.

- [ ] **Step 3: Add `_goal_summary` and use it**

Add this helper just above `def goal_planner_tool(state: AgentState) -> dict:`:

```python
def _goal_summary(goal_type: str, target_amount: Any, timeline: Any,
                  monthly_needed: Any, net_flow: Any, feasible: Any, n_scenarios: int) -> str:
    """One-line evidence summary that never renders '₹None' for a missing target."""
    target_display = _inr(target_amount) if target_amount else "N/A"
    return (
        f"Goal '{goal_type}' — target={target_display}, "
        f"timeline={timeline}, monthly_needed={_inr(monthly_needed or 0)}, "
        f"net_flow={_inr(net_flow)}, feasible={feasible}, "
        f"scenarios={n_scenarios}"
    )
```

In `goal_planner_tool`, replace:

```python
    ms      = extra.get("monthly_savings_needed") or extra.get("total_monthly_needed") or 0
    summary = (
        f"Goal '{goal_type}' — target=₹{data.get('target_amount')}, "
        f"timeline={goal.get('timeline')}, monthly_needed=₹{ms}, "
        f"net_flow=₹{agg['monthly_net_flow']}, feasible={extra.get('feasible')}, "
        f"scenarios={len(extra.get('scenarios') or [])}"
    )
```

with:

```python
    ms      = extra.get("monthly_savings_needed") or extra.get("total_monthly_needed") or 0
    summary = _goal_summary(
        goal_type, data.get("target_amount"), goal.get("timeline"),
        ms, agg["monthly_net_flow"], extra.get("feasible"),
        len(extra.get("scenarios") or []),
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_goal_planner.TestGoalSummary -v`
Expected: both tests PASS.

- [ ] **Step 5: Run the FULL suite**

Run: `python -m unittest tests.test_goal_planner -v`
Expected: every test from Tasks 1–13 PASSES.

- [ ] **Step 6: Commit**

```bash
git add backend/app/graph/tools/goal_planner_tool.py backend/tests/test_goal_planner.py
git commit -m "fix(goal-planner): summary renders N/A instead of ₹None for missing target"
```

---

## Self-Review

**Spec coverage:**
- #1 surplus-bound education loan → Task 2 (loan-first `self_b = min(avail, cost*5%)`). ✓
- #2 misleading B label → Task 2 (label now matches loan-maximising logic). ✓
- #3 wrong feasibility flag → Task 2 (`feasible = save <= save_cap`, EMI dropped). ✓
- #4 hardcoded 15y tenure → Task 3. ✓
- #5 FIRE ignores cuts → Task 5. ✓
- #6 retirement divide-by-zero → Task 4. ✓
- #7 FIRE infinite years → Task 5 (`None`). ✓
- #8 non-liquid balances counted → Task 7. ✓
- #9 negative balances → Task 7 (`max(0, bal)`). ✓
- #10 cost-basis liquidity → Task 8. ✓
- #11 stamp duty → Task 9. ✓
- #12 car tenure → Task 10. ✓
- #13 savings ignore returns → Task 6 (scoped to `_savings_scenarios`; loan down-payments documented as out of scope). ✓
- #14 category double/first-match → Task 11. ✓
- #15 fake sequential → Task 12. ✓
- #16 ₹None → Task 13. ✓
- #17 education never out of reach → Task 2 keeps `target_out_of_reach=False` (verified by `test_feasibility_ignores_emi_affordability`). ✓
- #18 recommended education design → Task 2 (A=user mix, B=max-loan recommended, C=min-loan). ✓

**Placeholder scan:** No TBDs; every code step shows full code.

**Type/name consistency:** `_education_scenarios`, `_savings_scenarios`, `_classify_balances`, `_goal_summary` signatures match their call sites and tests. Scenario dict keys are preserved (new keys added only: `post_graduation_emi`, `assumed_annual_return_pct`, `valuation_basis`, `stamp_duty_pct_assumed`, `matched_keyword`, `start_month`/`end_month`/`funding_window`, `illiquid_accounts`). `_EDU_EMI_FRAC` is removed and replaced by `_EDU_MIN_SELF_FRAC` — confirmed used only inside `_education_scenarios`.

**Risk note (out of scope, by design):** `_plan_house`/`_plan_car` down-payment saving stays linear (no growth); the brain/clarification layer is not modified to *collect* the new optional payload fields (`loan_tenure_years`, `loan_tenure_months`, `stamp_duty_pct`) — the planner simply honors them when present and falls back otherwise. Surfacing them as clarification questions is a separate follow-up.

## Execution Handoff

(See options below.)
