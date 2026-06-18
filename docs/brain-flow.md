# FinAssist Brain Flow

This document explains how the Brain supervisor decides what to do next, how clarification works, and what information is passed between nodes.

## 1. What the Brain is

The Brain is the supervisor node in the LangGraph loop. It does not answer directly; it decides exactly one next action from:

- `clarify`
- `nl2sql`
- `goal_planner`
- `investment`
- `knowledge`
- `out_of_scope`
- `finish`

The implementation lives in [backend/app/graph/brain/brain_node.py](../backend/app/graph/brain/brain_node.py), and the routing rules are defined in [backend/app/utils/prompts.py](../backend/app/utils/prompts.py).

---

## 2. Inputs the Brain sees

The Brain builds its prompt from the current state and conversation context.

| Input | Where it comes from | Why it matters |
|---|---|---|
| `user_query` | current user message | the latest request to route |
| `messages` | conversation history | lets Brain use prior context when the user says “that”, “it”, etc. |
| `user_profile` | user profile payload | income, balances, risk profile, and other personal context |
| `clarifications` | answers collected this turn | resolves missing fields after a clarification batch |
| `evidence` | outputs from previous tool runs | tells Brain what has already been learned |
| `iterations` | loop counter | prevents infinite loops |

The exact prompt fields are formatted by `_build_brain_messages()` in [backend/app/graph/brain/brain_node.py](../backend/app/graph/brain/brain_node.py).

---

## 3. Output contract from the Brain

The Brain returns one JSON object with:

- `next_action`
- `clarification_questions`
- `task`
- `reasoning`

The `task` object contains:

- `sub_question`: the tool-facing natural-language question
- `entities`: merchant/category/date-range/metric/grouping hints
- `analysis_type`: `basic`, `trend`, `comparison`, or `anomaly`
- `goal`: a structured goal payload for planning flows

The goal payload can include fields such as:

- `goal_type`
- `description`
- `target_amount`
- `timeline`
- `funding`
- `existing_savings`
- `item_name`
- `financing_preference`
- `down_payment_pct`
- `travelers`
- `destination`
- `current_age`
- `target_age`
- `monthly_retirement_expenses`
- `target_months_coverage`
- `loan_preference`
- `sub_goals`

The allowed schema is defined in [backend/app/utils/prompts.py](../backend/app/utils/prompts.py).

---

## 4. How the Brain decides to ask clarification

The prompt tells the Brain to ask clarification only when the request is genuinely ambiguous and not enough information exists to proceed.

### Rule of thumb

The Brain should ask for clarification when:

- the user has not specified the exact goal target or deadline,
- a purchase query is missing key details,
- the request is ambiguous in a way that changes the plan.

### Important behavior

The Brain does **not** ask one-by-one questions. It asks for the full batch at once.

The implementation then:

1. calls `interrupt({ type: "clarification_batch", questions })`,
2. receives one resume payload with all answers,
3. parses them with `_parse_bulk_answers()`, and
4. reruns the Brain decision.

After that, the node deterministically backfills goal fields from the user’s answers using `_backfill_goal_from_clarifs()`. This is important because the model may mis-extract values such as timeline or target amount.

---

## 5. Goal-planning sequence

Goal queries are special.

The prompt explicitly says that for buying/saving/planning workflows the valid sequence is:

1. `clarify` (once, if needed)
2. `goal_planner`
3. `finish`

The Brain must **not** route goal queries to `nl2sql` first.

### Why this matters

The goal planner fetches financial context itself, so it can use:

- income
- expenses
- liquidity
- spending categories
- investments
- fixed deposits

This is why goal-flow questions are handled by the planner rather than generic SQL analysis.

---

## 6. What each node contributes back to the Brain

The Brain loops until it has enough evidence to finish. Each tool returns one or more evidence items.

| Tool / node | What it contributes | How Brain uses it |
|---|---|---|
| `nl2sql_agent` | SQL AST, analysis type, query intent | decides whether to continue or finish |
| `sql_executor` + `analytics_node` | rows, aggregates, trend/comparison/anomaly stats | gives the Brain concrete numbers for final answer generation |
| `goal_planner_tool` | affordability scenarios, monthly savings needed, funding sources, timeline feasibility | usually terminal evidence that leads straight to `finish` |
| `investment_tool` | portfolio narrative + holdings data | used for portfolio/investment questions |
| `knowledge_tool` | retrieved financial education context | used for general finance questions |

The shared evidence shape is a list of objects like:

```json
{
  "tool": "goal_planner",
  "task": "...",
  "summary": "...",
  "data": { ... }
}
```

The graph wiring is defined in [backend/app/graph/graph.py](../backend/app/graph/graph.py) and the routing table is in [backend/app/graph/edges.py](../backend/app/graph/edges.py).

---

## 7. How the Brain avoids wasted loops

The implementation includes several guards so the system does not keep asking the supervisor to do the same thing again:

- once `goal_planner` evidence exists, the Brain immediately goes to `finish`;
- once a basic `nl2sql` answer already exists, the Brain also finishes;
- single-shot tools (`goal_planner`, `investment`, `knowledge`) are not rerun unnecessarily;
- the loop has a hard cap (`MAX_ITERATIONS` = 15).

These guards are in [backend/app/graph/brain/brain_node.py](../backend/app/graph/brain/brain_node.py).

---

## 8. Data flow summary

A compact view of the flow is:

1. `input_guardrail` checks safety.
2. `brain` decides the next action.
3. If `clarify`, the graph pauses and waits for answers.
4. If `nl2sql`, the SQL path runs and analytics are produced.
5. If `goal_planner`, the planner computes scenarios and funding feasibility.
6. `answer_node` synthesizes the final response.
7. `output_guardrail` checks the answer.

The state passed through the loop is defined in [backend/app/graph/state.py](../backend/app/graph/state.py).
