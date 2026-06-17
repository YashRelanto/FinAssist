# `goal_planner_tool.py` — Function Reference

Deep, scenario-based affordability analysis for 10 goal types. Every planner produces **three
scenarios (A / B / C)** so the user sees trade-offs, not just one number. The module fetches the
user's real financials (income, spend, balances, spending categories, investments, fixed deposits)
directly from Supabase and never invents data.

> Source: [`backend/app/graph/tools/goal_planner_tool.py`](../backend/app/graph/tools/goal_planner_tool.py)

## Module constants

| Constant | Value | Meaning |
|---|---|---|
| `_CAP_UTIL` | `0.70` | Only ~70% of the realistic monthly surplus may be committed to a goal — a lifestyle cushion is always left untouched. |
| `_TARGET_FLOOR_FRAC` | `0.5` | If a goal can only be financed below 50% of what was asked, it's "out of reach" (not merely right-sizable). |
| `_EDU_MIN_SELF_FRAC` | `0.05` | Education is financed loan-first: self-fund at most ~5% upfront. |
| `_SAVINGS_RETURN_PCT` | `7.0` | Assumed p.a. return for cash goals longer than 12 months. |
| `_RETURN_MIN_MONTHS` | `12` | Growth is only assumed for goals longer than this. |
| `_FD_COMPOUND_N` | dict | Compounding periods/yr (monthly 12, quarterly 4, half-yearly 2, annually 1). |
| `_MONEY_TOKENS` / `_SKIP_TOKENS` | sets | Decide which numeric fields get a `₹`-formatted `_inr` sibling. |
| `_REDUCIBLE_KEYWORDS` / `_NON_REDUCIBLE` | dict/tuple | Discretionary spend categories (with trim %) vs essentials never to cut. |
| `_NON_LIQUID_TYPES` / `_LIQUID_TYPES` | tuples | Account-type classification (locked vs spendable). |
| `_LIQUID_INV_KW` | tuple | Mutual-fund name tokens that mark a near-cash (liquid/debt) holding. |

---

## 1. Parsing & formatting helpers

### `_parse_amount(v) -> Optional[float]`
Parses human-entered money: `'₹2L'`, `'50k'`, `'2,50,000'`, `'12-15 lakh'` (range → midpoint),
`'1.3cr'`. Handles lakh/crore/million/k suffixes. Returns a float or `None`.

### `_months_from_timeline(timeline) -> Optional[float]`
Converts a timeline phrase to months: `'1-1.5 years'` → `15`, `'6 months'` → `6`, weeks/days
normalised. Range → midpoint. Returns months or `None`.

### `_num(v, default) -> float`
Extracts the first number from messy values (`'30%'`, `'6 months'`, `'age 24'`). Falls back to
`default`.

### `_inr(amount) -> str`
Formats a number in Indian digit grouping with a `₹` prefix: `1350000` → `"₹13,50,000"`.

### `_attach_inr(obj) -> obj`
Recursively walks a dict/list and adds a `"<key>_inr"` sibling for every **monetary** number, so
the answer LLM copies correct full-rupee strings and never rescales to "lakhs". Uses
`_MONEY_TOKENS`/`_SKIP_TOKENS` to decide what's money vs a percent/age/month.

### `_parse_date(v) -> Optional[date]`
Parses `'YYYY-MM-DD'` (used by FD valuation). Returns a `date` or `None`.

---

## 2. Core financial maths

### `_calc_emi(principal, annual_rate_pct, tenure_months) -> float`
Standard reducing-balance EMI. `0` if principal/tenure ≤ 0.

### `_inv_emi(emi_budget, annual_rate_pct, tenure_months) -> float`
**Inverse of `_calc_emi`** — the largest loan principal whose EMI fits within `emi_budget`. Used to
size affordable loans.

### `_monthly_sip_for_corpus(target, annual_return_pct, tenure_months) -> float`
Monthly SIP needed to reach `target` at a given return over `tenure_months` (FV-of-annuity inverse).

### `_corpus_growth(current, monthly, annual_return, months) -> float`
Future value of `current` plus a monthly SIP compounded over `months`.

### `_years_to_fi(current, monthly, corpus, annual_return=0.12) -> Optional[float]`
Years until the corpus reaches the FI target. Returns `None` if not reachable within 50 years
(never `inf`, which would break the UI).

---

## 3. Fixed-deposit valuation

### `_fd_value(principal, rate_pct, comp_freq, years, payout_type="cumulative") -> float`
Value of an FD after `years`. Cumulative → compounded at `comp_freq`; `simple` → simple interest;
`payout` → stays at principal (interest is withdrawn).

### `_fd_years(start, end) -> float`
Fractional years between two dates (`/365.25`), clamped ≥ 0.

### `_fd_metrics(fd, as_of=None) -> dict`
Per-FD snapshot from one DB row. **Returns:** `principal_amount`, `current_value` (accrued to date),
`maturity_value`, `break_value` (net cash if broken today, interest recomputed at the penalised
rate), `break_cost`, `matured`, `days_to_maturity`, `full_term_years`.

### `_fetch_fixed_deposits(user_id) -> List[dict]`
Loads active rows from the `fixed_deposits` table and enriches each with `_fd_metrics` plus
`bank_name`/`label`/`interest_rate_pct`/`maturity_date`. **Returns** `[]` if none / on error.

### `_liquid_fund_value(inv_data) -> float`
Sum of holdings whose name matches `_LIQUID_INV_KW` (liquid/debt/arbitrage/etc.) — i.e. near-cash
mutual funds usable for a goal.

---

## 4. Evidence extraction (when other tools already ran)

### `_extract_nl2sql_financials(evidence) -> Optional[dict]`
Pulls `total_current_balance`, `total_income`, `total_expense` from any `nl2sql` evidence.

### `_extract_spending_categories(evidence) -> List[dict]`
Pulls the category breakdown (`[{category, amount}]`) from `nl2sql` analytics evidence.

### `_extract_investment_data(evidence) -> Optional[dict]`
Returns the `investment` tool's data dict if present.

### `_spending_reduction_opportunities(categories) -> List[dict]`
Identifies discretionary categories to trim. For each non-essential category it scores **all**
matching `_REDUCIBLE_KEYWORDS` and picks the **highest** reduction % (never first-match). **Returns**
top 4 by saving: `[{category, current_monthly, suggested_reduction_pct, matched_keyword,
potential_saving, driven_by:[{name,amount}]}]`.

### `_check_investment_liquidity(gap, inv_data) -> dict`
Estimates how much of the goal `gap` liquid investments could cover. **Returns**
`total_portfolio_value`, `estimated_liquid_value`, `gap`, `can_fully_cover`, `valuation_basis`
(`purchase_cost` for the DB fallback), and a plain-English `recommendation` (with a cost-basis
caveat where relevant).

---

## 5. Direct DB fallbacks (used when no prior evidence exists)

### `_compute_monthly_aggregates(user_id) -> dict`
Averages income/spend over the **last 6 months with data** (recent behaviour > stale history).
**Returns:** `months_observed`, `months_analyzed`, `monthly_avg_spend`, `monthly_avg_income`,
`monthly_net_flow`, `savings_rate_pct`, `monthly_savings_capacity` (= net flow × `_CAP_UTIL`),
`income_source` (falls back to profile income if there are no income transactions).

### `_classify_balances(rows) -> dict`
Splits account rows into **liquid** (savings/current/cash/blank), **credit** (liability — never a
funding source), and **illiquid** (EPF/PPF/FD/NPS/locked). Negative balances are clamped to 0.
**Returns:** `liquid_balance`, `credit_accounts`, `illiquid_accounts`.

### `_get_account_balances(user_id) -> dict`
Fetches account rows from Supabase and runs `_classify_balances`.

### `_compute_category_breakdown(user_id, months_observed) -> List[dict]`
Monthly-average expense by main category (top 10), each with its top 3 sub-categories — over the
**same recent 6-month window** as the aggregates, so numbers reconcile. Feeds spending-cut
justification.

### `_fetch_investment_holdings(user_id) -> Optional[dict]`
Lightweight portfolio snapshot at **purchase value** (no live NAV calls). **Returns**
`total_current`, `holdings:[{name,current_value,share_pct}]`, and `valuation_basis="purchase_cost"`.

---

## 6. Scenario builders

### `_sc(tag, label, recommended, monthly_savings_needed, net_flow, **extra) -> dict`
Builds a standard scenario dict for non-loan goals (retirement/FIRE/multi-goal). Feasible when the
monthly need fits ~70% of `net_flow` (`_CAP_UTIL`).

### `_max_stretch_months(user_months) -> int`
How far a timeline may EVER be stretched: at most ~1.5× the user's months (capped at 360).

### `_deployable(agg) -> float`
The **pooled funding** that can seed a goal: idle bank cash (minus a 3-month buffer) + liquid-fund
value + breakable-FD value. Scenarios only ever draw `min(need, available)`.

### `_funding_sources(agg) -> dict`
Transparent breakdown of every asset and whether it's used. **Returns** `from_bank_savings`,
`from_liquid_funds`, `from_fixed_deposits`, `deployable_total`, `equity_or_other_not_counted`,
`requires_breaking_fd`, and an `explanation` list of plain-English lines (naming FDs by bank, and
justifying assets NOT used — e.g. equity kept invested).

### `_loan_scenarios(*, price, existing, user_months, user_dp_pct, surplus, cuts, rate, tenure, deployable=0, extra_upfront=0, down_label, asset, instrument) -> (List[dict], meta)`
Engine for **loan-funded goals** (car / house / education down-payment). Produces:
- **A — Your Plan:** exactly the user's inputs, judged honestly.
- **B — Recommended:** keep the same purchase, made feasible by deploying funds + raising the down
  payment so the EMI fits, with a modest timeline stretch if needed.
- **C — Right-Size / Max financeable:** the biggest purchase that fits, putting **all** deployable
  funds (incl. broken FDs) into the down payment plus the largest EMI-affordable loan.

Two affordability caps: the **saving phase** may use `(surplus + cuts) × 70%`, but the **EMI** must
fit `surplus × 70%` (`emi_cap`) — a long-term EMI is never assumed to rely on permanent spending
cuts. `meta` carries `max_financeable_target` and `target_out_of_reach`.

### `_savings_scenarios(*, target, existing, user_months, surplus, cuts, instrument, asset="goal", annual_return_pct=_SAVINGS_RETURN_PCT, deployable=0) -> (List[dict], meta)`
Engine for **cash (no-loan) goals**. For goals > 12 months it assumes investment growth (SIP), so
the monthly contribution needed is lower than a flat `gap/months`. `deployable` (incl. broken FDs)
is a one-time head-start that reduces the gap. A = your plan, B = keep target (stretch modestly if
needed), C = right-size to what fits. Each scenario reports `deployed_now` and feasibility against
~70% of capacity.

### `_education_scenarios(*, cost, existing, user_months, self_pct, surplus, cuts, deployable, rate=10.5, tenure=180) -> (List[dict], meta)`
Education **never scales the program cost** — only the financing structure changes.
- **A — Your Plan:** the user's stated self-funded / loan mix.
- **B — Recommended (loan-first):** minimal upfront self-funding (≤5% of cost), loan covers the rest.
- **C — Minimise the loan:** self-fund the most you can during study → smaller loan.

Feasibility depends ONLY on whether the **self-funded slice** is achievable from the sustainable
base surplus (`surplus × 70%`); the EMI is repaid after a moratorium from higher post-degree income,
so it is **not** gated on today's surplus. Never "out of reach".

---

## 7. Type-specific planners — `_plan_*(goal: dict, agg: dict) -> dict`

Each maps the goal payload + financial aggregates onto the right engine and returns the chosen
scenario's headline numbers plus the full `scenarios` list and `meta`.

| Planner | Engine | Notes |
|---|---|---|
| `_plan_gadget` | savings | Liquid MF / HYSA instrument. |
| `_plan_car` | loan | `loan_tenure_months` configurable (default 60); 10% p.a. |
| `_plan_travel` | savings | Multiplies per-person cost by `travelers`. |
| `_plan_emergency_fund` | savings (0% return) | Target = months-of-expenses; kept liquid. |
| `_plan_house` | loan | `stamp_duty_pct` configurable (default 7%); 8.5% p.a., 240 mo; stamp duty as `extra_upfront`. |
| `_plan_education` | education | `loan_tenure_years` configurable (default 15); auto-includes FDs in corpus. |
| `_plan_retirement` | `_sc` × 3 returns (7/10/12%) | Guards against `current_age ≥ target_age`; current corpus read from portfolio + FDs automatically. |
| `_plan_fire` | `_sc` × 3 (Lean/Regular/Fat) | Invests `(net + cuts) × 70%`; net worth = portfolio + FDs + liquid balances. |
| `_plan_wedding` | savings | FD-ladder / RD instrument. |
| `_plan_multi_goal` | per-sub-goal | Sequential schedule (back-to-back windows), parallel, and hybrid allocation strategies. |
| `_plan_generic` | savings | Fallback for unknown goal types. |

`_GOAL_PLANNERS` is the dispatch dict mapping `goal_type` → planner.

---

## 8. Output helpers & entry point

### `_goal_summary(goal_type, target_amount, timeline, monthly_needed, net_flow, feasible, n_scenarios) -> str`
One-line evidence summary for logs. Renders `target=N/A` (never `₹None`) when the target is missing.

### `goal_planner_tool(state: AgentState) -> dict`  ← **the node entry point**
Orchestrates everything:
1. Reads `user_id` and `brain_task.goal` from state.
2. Builds the financial baseline: `_compute_monthly_aggregates`, `_get_account_balances`
   (liquid balance), spending categories + `_spending_reduction_opportunities` (so scenarios can
   cost in cuts), and fetches the investment portfolio + fixed deposits **up-front** (so every goal
   can use them — `portfolio_value`, `liquid_fund_value`, `fd_current_value`, `fd_breakable_value`,
   `fd_list` all stored on `agg`).
3. Dispatches to the matching `_plan_*` via `_GOAL_PLANNERS`.
4. Attaches `funding_sources`, `fixed_deposits`, `investment_liquidity_check`, spending data, and
   `_attach_inr` siblings.
5. **Returns** `{"evidence": [{"tool": "goal_planner", "summary", "data"}], "sources": [...]}` — the
   `data` dict feeds `answer_node` to render the plan.
