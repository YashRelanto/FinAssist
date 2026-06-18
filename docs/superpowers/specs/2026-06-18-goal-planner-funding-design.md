# Goal Planner — Maturity-Aware Funding & What-If Selection

**Date:** 2026-06-18
**Scope:** `backend/app/graph/tools/goal_planner_tool.py`, `backend/app/utils/prompts.py`
(brain prompt + answer prompts). `brain_node.py` requires no code change — `task.goal`
flows through verbatim.

## Problem

The goal planner already pools three funding sources (idle bank cash, liquid/debt MFs,
breakable FDs) and exposes per-FD `maturity_value` / `break_value` / `break_cost`. But:

1. **FDs are always valued at "break today."** `_fd_metrics(as_of=date.today())` never
   considers whether an FD will have *matured* by the goal's timeline end — so it always
   assumes a penalty even when the FD would mature in time and could be used penalty-free.
2. **The bank buffer is "3 months of expenses," not the requested "keep 10% of idle cash."**
3. **What-if funding is all-or-nothing.** Only a `deploy_all` text flag exists; there is no
   way to express "break only my SBI FD, keep the rest" or "use half my bank cash."

## Decisions (confirmed with user)

- **Bank buffer:** *Replace* the 3-month-expense buffer with "keep 10% of idle cash"
  (deployable bank cash = 90% of liquid balance by default).
- **FD valuation at timeline end:** If an FD matures on/before the goal end-date → count its
  **full maturity value** (no penalty). Otherwise → count its **penalized break value**
  (breaking early is required to use it for this goal).
- **What-if:** The tool accepts a structured `funding_selection` override AND exposes rich
  per-FD data. The brain decides the selection; the tool recomputes deployable accurately.
- **Wiring:** End-to-end — update the brain prompt so it populates `funding_selection`.

## Design

### 1. Timeline-aware FD valuation

Goal end-date = `date.today() + timeline_months` (≈ `months * 30.44` days).

New helper `_fd_funding_view(fds, goal_end_date, selection) -> list[dict]`. Per FD it returns:

| field | meaning |
|---|---|
| `fd_id`, `bank_name`, `label` | identity (for naming + what-if matching) |
| `matures_by_goal_end` | bool — matures on/before the goal end-date |
| `usable_value` | maturity value if `matures_by_goal_end` else break value |
| `penalty_if_broken` | `break_cost` (0 if matured-by-end) |
| `selected` | whether this FD is counted under the current `funding_selection` |

The existing `_fd_metrics` is extended (or a sibling added) to compute the value **at the goal
end-date** rather than only "now": for a matured-by-end FD use `_fd_value(... full_term ...)`
(maturity value); otherwise the existing break-now value.

### 2. Bank buffer → keep 10%

- New constant `_BANK_RETAIN_FRAC = 0.10`.
- `_deployable()` / `_funding_sources()`: `bank_surplus = liquid * (1 - retain_frac)` where
  `retain_frac` comes from the resolved selection (`0.0` when the user says "use everything").
- Explanation strings updated: "keeping 10% in your accounts" instead of the 3-month buffer.

### 3. `funding_selection` contract

Optional `task.goal.funding_selection`, resolved inside the tool against fetched assets:

```python
{
  "bank_use_pct": 90,        # default 90 (keep 10%); 100 if "use everything"
  "bank_use_amount": null,   # optional hard ₹ cap (overrides pct when present)
  "use_liquid_funds": true,  # debt/liquid (near-cash) MFs
  "break_fds": "auto"        # "auto" (default): break non-matured FDs as a source;
                             #   matured-by-end FDs always counted at maturity value.
                             # "none": never break; only matured-by-end FDs usable.
                             # "all": break every FD.
                             # "matured_only": only matured-by-end FDs (alias of "none").
                             # list: identifiers to break — bank/label substring, fd_id,
                             #   or 1-based index. Non-listed FDs only count if matured-by-end.
}
```

`_resolve_funding_selection(goal, task)` builds the effective selection by:
1. starting from defaults,
2. merging any explicit `goal["funding_selection"]` from the brain,
3. text-fallback parsing of goal/sub-question (generalizes today's `deploy_all` detection:
   "use everything" → `bank_use_pct=100, break_fds="all"`; "don't break my FDs" →
   `break_fds="none"`; "break only my <bank> FD" → `break_fds=["<bank>"]`).

`_deployable` / `_funding_sources` take the resolved selection. Default (no override) keeps
ask #1 satisfied (non-matured FDs broken as a source) while the 10% rule satisfies #2/#4.

### 4. Output additions

`data` (and `funding_sources`) gain:
- `funding_selection_applied` — the resolved selection, so the answer/brain can echo it.
- `funding_sources.fixed_deposits[]` entries carry `matures_by_goal_end`, `usable_value`,
  `penalty_if_broken`, `selected`.
- `from_fixed_deposits` reflects only **selected** FDs' usable value.

### 5. Brain + answer prompts (`prompts.py`)

- **BRAIN_SYSTEM:** add `funding_selection` to the `goal` JSON schema and a one-line rule:
  funding what-if follow-ups ("break only my SBI FD", "use half my bank cash", "don't touch
  my FDs") → populate `funding_selection`, route to `goal_planner`.
- **GOAL_PLAN_SYSTEM & GOAL_PLAN_SUMMARY_SYSTEM funding sections:** when an FD is matured by
  the goal end-date, present it as used penalty-free; when broken early, state the penalty.
  Mention the 10% retained in bank accounts (replacing the 3-month-buffer wording).

## Out of scope

No changes to `api.py`, `Investments.tsx`, scenario math (`_loan_scenarios` /
`_savings_scenarios` keep their `min(need, available)` draw), chart builders, or the
clarification flow.

## Testing

- Unit: `_fd_funding_view` for (a) FD maturing before goal end → maturity value, 0 penalty;
  (b) FD maturing after → break value + penalty; (c) `break_fds="none"` excludes non-matured;
  (d) list selection matches by bank/index.
- Unit: `_deployable` keeps exactly 10% by default; 0% when `bank_use_pct=100`.
- Unit: `_resolve_funding_selection` text fallbacks ("use everything", "don't break my FDs",
  "break only my SBI FD").
