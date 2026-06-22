# Goal Planner Rework — Design Spec

**Date:** 2026-06-20
**Branch:** test/langgraph
**Scope:** `backend/app/graph/tools/goal_planner_tool.py`, `backend/app/utils/prompts.py`,
`backend/app/graph/nodes/answer_node.py`. Existing functions are **updated in place** (no parallel
copies) to keep the code readable.

---

## Problem statement

The goal planner produces three scenarios (A/B/C) for ten goal types. Six issues, from real usage:

1. **Scenario A is not the user's actual plan.** All three scenarios silently deploy assets and
   re-shape the down payment, so the user never sees their *exact* stated plan judged honestly.
2. **EMI cap inflates the down payment.** A future EMI is forced to fit `0.70 × current surplus`.
   To satisfy that, scenario B raises the down payment, which raises the monthly down-payment
   saving **above what the user can actually save** (e.g. "save ₹12,000/mo" when they save
   ₹10,000/mo). This is backwards: if a plan asks the user to commit ₹12,500/mo of saving, then
   post-purchase the user can redirect that same ₹12,500/mo, so a **larger** EMI (hence a larger
   loan) is affordable — the down payment should not be inflated.
3. **Liquid funds valued at cost, not market.** `_fetch_investment_holdings` uses
   `quantity × purchase_nav`, so a fund currently worth ₹1.04L is treated as ₹1.00L. The
   *future* (goal-end) value is also ignored — a 2-year goal should use the fund's matured value.
4. **Feasibility ignores balance growth.** Feasibility checks only `monthly_saving ≤ capacity`.
   It never projects that existing bank balance + monthly saving already reach the target
   (e.g. ₹15L in bank, ₹2L down payment → trivially reachable, should be feasible).
5. **No funding-split visual.** Only bar charts; nothing shows self-funded vs loan-financed.
6. **What-ifs are narrow.** Only funding-selection what-ifs are handled. The user wants *any*
   parameter what-if ("interest-free loan", "retirement spend ₹1L", "4 travellers not 2",
   "save ₹15,000/mo"), answered concisely — **not** as a fresh A/B/C report.

The dashboard random-API-call and financial-score-mismatch regressions are **out of scope** —
already fixed on `main`.

---

## Design decisions (confirmed with user)

| # | Decision |
|---|----------|
| D1 | Scenario **A = the user's exact plan** (their `down_payment_pct`, `target_amount`, `timeline`), judged honestly. No auto-reshaping. |
| D2 | Scenario **B = minimal smart deployment** — deploy only the assets needed to close A's shortfall, least-disruptive first. |
| D3 | Scenario **C = right-size** — largest target/purchase that fits the original timeline. |
| D4 | **EMI cap floats with the suggested saving:** `emi_cap = 0.70 × S` where `S` = that scenario's suggested monthly saving. |
| D5 | **Saving-feasibility gate:** a scenario's `S` is feasible only if `S ≤ current_surplus + total_spending_cuts`. Saving above the current rate is allowed **iff** category cuts support it. |
| D6 | Liquid funds valued at **live NAV** (current) and projected to a **goal-end** value, mirroring FD valuation. |
| D7 | Feasibility projects **balance growth**: `existing + deployable + S × months ≥ needed`. |
| D8 | The above apply **comprehensively** across all goals via the shared builders. Retirement/FIRE/multi-goal keep their domain scenario shapes but gain D5–D7 and what-if overrides. |
| D9 | **What-ifs = arbitrary field overrides** on the carried-forward goal, flagged `what_if: true`, answered with a **single computation + basic explanation, no A/B/C, no charts**. |
| D10 | **Pie chart:** Self-funded (Bank / FD / Liquid slices) vs Loan-financed. Keep the scenario-comparison and budget-impact bars (still 3 charts). Skipped on what-ifs. |

---

## Detailed design

### A. EMI affordability — floating cap + feasibility gate (`goal_planner_tool.py`)

Today (`_loan_scenarios.make` / `feasible_band`):

```python
emi_cap = surplus * _CAP_UTIL        # 0.70 × current surplus, FIXED
feasible = (save <= capacity * _CAP_UTIL + 1) and (emi <= emi_cap + 1)
```

New model. Define once per planner run:

```python
base_capacity        = surplus                       # what the user saves today (net flow)
cut_capacity         = total_spending_cuts           # reclaimable from category cuts (existing logic)
max_sustainable_save = base_capacity + cut_capacity  # most the user can be asked to save / month
```

Per scenario, with suggested monthly saving `S`:

```python
emi_cap        = _CAP_UTIL * S                        # EMI sized to the committed saving (D4)
save_feasible  = S <= max_sustainable_save + 1        # is that saving achievable? (D5)
emi_feasible   = emi <= emi_cap + 1                    # EMI fits 70% of the committed saving
feasible       = save_feasible and emi_feasible
```

**Why this kills the inflation.** Down-payment % and EMI are coupled: a higher down payment → a
higher `S` but a lower loan/EMI. The old code raised the down payment until `EMI ≤ 0.70 × current
surplus` (a fixed, low ceiling), over-inflating `S`. The new code raises it only until
`EMI ≤ 0.70 × S` — which `S` itself satisfies far sooner — so B settles at the **smallest** down
payment that balances, capped by `max_sustainable_save`.

#### Worked example

> User: net surplus ₹18,000/mo; reclaimable cuts ₹2,000/mo → `max_sustainable_save = ₹20,000`.
> Car ₹10L, 30% down payment, 18-month timeline, 5-year loan @ 10%.
>
> - **Old:** `emi_cap = 0.70 × 18,000 = ₹12,600`. To fit, down payment forced to ~55% → save
>   ≈ ₹30,000/mo (impossible). Reported "save ₹30,000/mo", timeline stretched. ❌
> - **New (Scenario B):** pick the smallest down payment where `EMI ≤ 0.70 × S` and
>   `S ≤ ₹20,000`. Settles near the user's 30–35% down payment with `S ≈ ₹14,000` (within
>   ₹20,000) and `EMI ≈ ₹9,500 ≤ 0.70 × 14,000 = ₹9,800`. Feasible, no inflation. ✅

`_CAP_UTIL` (0.70) is retained as the cushion constant; only the base it multiplies changes
(from `surplus` to `S`).

### B. Scenario B — minimal smart deployment (`goal_planner_tool.py`)

New helper:

```python
def _minimal_deployment(gap: float, sources: dict) -> dict:
    """Pick the LEAST-disruptive assets that cover `gap`, in order:
       1. FDs already maturing by the goal date  (free — no penalty)
       2. liquid/debt funds                       (redeem the EXACT amount needed; partial OK)
       3. bank cash                               (keep the chosen cushion)
       4. a still-locked FD, broken ONLY if still short — choose the FD whose value is
          CLOSEST to the remaining need (minimise forfeited interest; never break everything)
    Returns {deployed_total, from_bank, from_liquid, from_fds_matured, from_fds_broken,
             fds_broken: [...], penalty_paid}."""
```

Scenario B flow:
1. Compute A (the user's exact plan) and its **shortfall** — the extra down payment needed so the
   EMI/saving become feasible under §A (or, for cash goals, the gap between target and
   `existing + S × months`).
2. `_minimal_deployment(shortfall, sources)` → the deployed lump raises the down payment, shrinks
   the loan, lowers the EMI.
3. Re-evaluate feasibility under §A.

This replaces today's blanket "deploy 90% of bank + break all selected FDs". The default
`_resolve_funding_selection` still governs what's *eligible*; B now draws only what's *needed*.
(Explicit user funding what-ifs — "break only my SBI FD" — still constrain eligibility.)

### C. Liquid-fund valuation — current + future (`goal_planner_tool.py`)

- Replace cost-basis valuation: value liquid/debt holdings at **live NAV** by reusing the mfapi
  fetch already in `investment_tool.py` (extract/share the scheme-history + latest-NAV helper;
  cache per scheme as it already does).
- Add a **goal-end projection**: grow the current value to the goal date at an assumed debt-fund
  return (reuse `_SAVINGS_RETURN_PCT`-style constant), mirroring `_fd_funding_view`'s maturity
  treatment. Expose both `current_value` and `value_at_goal_end` so funding uses the right figure
  for the goal horizon.
- `_liquid_fund_value` returns the goal-horizon value; `_funding_sources` / `funding_breakdown`
  report current vs projected transparently.

### D. Feasibility via balance growth (`goal_planner_tool.py`)

Feasibility of reaching a savings target / down payment becomes:

```
reachable_by_goal_end = existing + deployable_assets + S × months   (with growth where modelled)
feasible_to_fund      = reachable_by_goal_end >= amount_needed
```

So large idle balances make a goal feasible with little or no monthly saving. EMI feasibility
stays **income-bound** (§A) — a balance cannot service a recurring EMI.

### E. Comprehensiveness across goal types (`goal_planner_tool.py`)

- `_loan_scenarios` (car, house, education down-payment), `_savings_scenarios`
  (gadget, travel, emergency_fund, wedding, generic, and the down-payment/self-funded portions),
  and `_education_scenarios` carry §A–§D in their shared bodies, so every goal routing through
  them benefits.
- `_plan_retirement`, `_plan_fire`, `_plan_multi_goal` keep their return-tier / allocation scenario
  shapes (appropriate to those goals) but gain: the §C liquid-fund valuation, the §D balance-growth
  feasibility, the §D5 saving-feasibility gate, and §F what-if overrides.

### F. What-ifs — generalised, concise (`prompts.py` + `goal_planner_tool.py` + `answer_node.py`)

**Brain prompt (`prompts.py`).** New WHAT-IF section in the goal-planning instructions:
- Detect a what-if on a prior goal; **carry the prior goal from conversation history**.
- Override **only** the changed field(s); set **`what_if: true`**; route to `goal_planner`.
- Field map (existing unless noted):
  - "interest-free / different rate" → `loan_interest_rate_pct` (**new** goal field; defaults to
    each planner's current rate when absent).
  - "retirement spend ₹1L" → `monthly_retirement_expenses`.
  - "N travellers" → `travelers`.
  - "save ₹X/mo" → `monthly_savings_override` (**new** goal field).
  - any other stated parameter → its existing goal field.
- Add `loan_interest_rate_pct` and `monthly_savings_override` to the brain output goal schema.

**Planner (`goal_planner_tool.py`).**
- Read `loan_interest_rate_pct` override wherever a rate is currently hard-coded (car 10%,
  house 8.5%, education 10.5%) — default to the existing value.
- Read `monthly_savings_override`: when present it becomes the committed `S` (driving §A's EMI cap
  and §D feasibility), surfaced in the result.
- When `what_if: true`: run a **single computation** (scenario A semantics with the overrides) and
  **skip B/C generation**. Set `what_if: true` and a short `what_if_summary` on the returned data.

**Answer (`answer_node.py` + new `GOAL_WHATIF_SYSTEM` in `prompts.py`).**
- When `goal data.what_if` is true: use `GOAL_WHATIF_SYSTEM` (concise — the headline answer + a
  short plain-English explanation of what changed and the resulting number), and **skip
  `_select_goal_artifacts`** (no charts).

### G. Visualizations — funding pie (`answer_node.py`)

Keep **three** charts for a normal goal plan:
1. Scenario-comparison bar (kept).
2. Budget-impact bar (kept).
3. **New pie** — `_funding_split_pie`: slices = **Loan-financed**, **Bank cash**, **Fixed
   deposits**, **Liquid funds** (the self-funded sources split out). Built from a small
   `funding_breakdown` the planner exposes (loan amount from the recommended scenario; self-funded
   sources from `_funding_sources`). Replaces the flat `_funding_sources_bar`.
- The pie (and all charts) are skipped when `what_if` is true (§F).

---

## Affected files

| File | Change |
|------|--------|
| `backend/app/graph/tools/goal_planner_tool.py` | Floating EMI cap + saving-feasibility gate (§A); `_minimal_deployment` + B rework (§B); live-NAV + goal-end liquid valuation (§C); balance-growth feasibility (§D); apply across builders/planners (§E); `loan_interest_rate_pct` + `monthly_savings_override` + `what_if` single-computation path (§F); expose `funding_breakdown` (§G). |
| `backend/app/utils/prompts.py` | Brain WHAT-IF section + goal-schema fields (§F); new `GOAL_WHATIF_SYSTEM` (§F); minor wording in `GOAL_PLAN_SYSTEM` / `GOAL_PLAN_SUMMARY_SYSTEM` for the floating-EMI/saving narrative. |
| `backend/app/graph/nodes/answer_node.py` | `_funding_split_pie` replacing `_funding_sources_bar` in `_select_goal_artifacts` (§G); what-if concise path that skips charts (§F). |

---

## Testing strategy

- **EMI floating cap (§A):** unit test the inflation example — assert Scenario B's `S` stays
  ≤ `max_sustainable_save` and the down payment is **not** inflated past the user's stated %
  when the EMI already fits `0.70 × S`.
- **Saving-feasibility gate (§D5):** a scenario whose `S` exceeds `surplus + cuts` is flagged
  infeasible; one within it is feasible.
- **Minimal deployment (§B):** gap of ₹50,000 with a ₹60,000 liquid fund + two FDs → liquid fund
  redeemed for exactly ₹50,000, no FD broken; with no liquid fund → the FD *closest* to ₹50,000 is
  the one broken, not all.
- **Liquid valuation (§C):** current value reflects live NAV (≠ cost basis); a >12-month goal uses
  the projected goal-end value.
- **Balance-growth feasibility (§D):** ₹15L balance + ₹2L down payment → feasible with `S ≈ 0`.
- **What-ifs (§F):** `loan_interest_rate_pct: 0` → EMI computed at 0%; `travelers: 4` → trip total
  ×4; `monthly_retirement_expenses: 100000` → retirement corpus recomputed; each returns
  `what_if: true`, a single result, and no scenarios/charts.
- **Pie (§G):** funding split sums to the down payment + loan; what-if path emits no artifacts.

## Out of scope

- Dashboard `/api/forecast` redundant calls and hero financial-score mismatch (fixed on `main`).
- Any change outside the three files above.
