"""Generate transactions.csv with income > expense per user per month."""

import csv
import random
import uuid
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

SEED = 42
TOTAL_ROWS = 5000
START_DATE = date(2026, 1, 1)
END_DATE = date(2026, 5, 15)
SURPLUS_MARGIN = 1.15

SALARY_CATEGORY = "0d3983fc-2dc6-40e8-898b-3e446f9ffcb2"
REFUND_CATEGORY = "563cfb4f-7726-4895-ade8-5f8358148b40"
DIVIDEND_CATEGORY = "4729190a-fada-4044-9d59-ee1f814b427c"

SALARY_MERCHANTS = [
    ("Company", "Salary transfer"),
    ("Payroll", "Salary deposit"),
    ("Employer", "Monthly salary credit"),
]
REFUND_MERCHANTS = [
    ("Flipkart", "Refund credit"),
    ("Amazon", "Order refund"),
    ("Myntra", "Return refund"),
]
DIVIDEND_MERCHANTS = [
    ("HDFC Bank", "Interest credit"),
    ("ICICI Bank", "Dividend payout"),
    ("Zerodha", "Dividend credit"),
]

BASE_DIR = Path(__file__).parent


def load_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_templates(existing_txns: list[dict]) -> dict[str, list[tuple]]:
    """category_id -> [(merchant, description, min_amt, max_amt), ...]"""
    buckets: dict[str, list[tuple]] = defaultdict(list)
    for row in existing_txns:
        if row["transaction_type"] != "expense":
            continue
        cid = row["category_id"]
        amt = float(row["amount"])
        buckets[cid].append(
            (row["merchant_name"], row["description"], amt)
        )

    templates: dict[str, list[tuple]] = {}
    for cid, entries in buckets.items():
        amounts = [e[2] for e in entries]
        lo, hi = min(amounts), max(amounts)
        if lo == hi:
            lo = max(50, lo * 0.7)
            hi = lo * 1.4
        unique = {}
        for m, d, _ in entries:
            unique[(m, d)] = (m, d, lo, hi)
        templates[cid] = list(unique.values())
    return templates


def default_template(category_id: str, main_cat: str) -> tuple:
    return (main_cat, f"{main_cat} payment", 100.0, 5000.0)


def month_end(year: int, month: int) -> int:
    if month == 5:
        return 15
    if month == 2:
        return 29 if (year % 4 == 0 and year % 100 != 0) or year % 400 == 0 else 28
    if month in (1, 3, 7, 8, 10, 12):
        return 31
    return 30


def random_date_in_month(year: int, month: int, rng: random.Random) -> date:
    last = month_end(year, month)
    day = rng.randint(1, last)
    return date(year, month, day)


def pick_account(
    accounts: list[dict],
    txn_type: str,
    rng: random.Random,
) -> dict:
    savings = [a for a in accounts if a["account_type"] in ("savings", "checking")]
    cards = [a for a in accounts if a["account_type"] == "credit_card"]
    wallets = [a for a in accounts if a["account_type"] == "wallet"]
    investments = [a for a in accounts if a["account_type"] == "investment"]

    if txn_type == "income":
        pool = savings if savings else accounts
        return rng.choice(pool)

    roll = rng.random()
    if roll < 0.55 and savings:
        return rng.choice(savings)
    if roll < 0.75 and cards:
        return rng.choice(cards)
    if roll < 0.88 and wallets:
        return rng.choice(wallets)
    if investments:
        return rng.choice(investments)
    return rng.choice(accounts)


def allocate_counts(user_ids: list[str], total: int) -> dict[tuple, int]:
    """Allocate transaction counts per (user_id, month)."""
    months = [1, 2, 3, 4, 5]
    buckets = [(uid, m) for uid in user_ids for m in months]
    base = total // len(buckets)
    remainder = total % len(buckets)
    counts = {b: base for b in buckets}
    for i in range(remainder):
        counts[buckets[i]] += 1
    return counts


def sample_amount(lo: float, hi: float, rng: random.Random) -> float:
    if hi <= lo:
        val = lo
    else:
        val = rng.uniform(lo, hi)
    return round(val, 2)


def generate_transactions(
    users: list[dict],
    accounts: list[dict],
    categories: list[dict],
    templates: dict[str, list[tuple]],
    rng: random.Random,
) -> list[dict]:
    user_ids = [u["user_id"] for u in users]
    accounts_by_user: dict[str, list[dict]] = defaultdict(list)
    for acc in accounts:
        accounts_by_user[acc["user_id"]].append(acc)

    cat_main = {c["category_id"]: c["main_category"] for c in categories}
    income_cats = [c["category_id"] for c in categories if c["main_category"] == "Income"]
    expense_cats = [c["category_id"] for c in categories if c["main_category"] != "Income"]

    # fallback templates for categories missing from old data
    for cid in expense_cats:
        if cid not in templates:
            templates[cid] = [
                default_template(cid, cat_main.get(cid, "General"))
            ]

    counts = allocate_counts(user_ids, TOTAL_ROWS)
    transactions: list[dict] = []

    for (user_id, month), count in sorted(counts.items()):
        user_accounts = accounts_by_user[user_id]
        if not user_accounts:
            continue

        num_income = 1 + (1 if rng.random() < 0.35 else 0) + (1 if rng.random() < 0.15 else 0)
        num_income = min(num_income, max(1, count // 10))
        num_expense = count - num_income

        # target monthly expense total (varies by user)
        user_idx = user_ids.index(user_id)
        base_expense = rng.uniform(45000, 180000) * (0.85 + user_idx * 0.025)
        expense_amounts: list[float] = []
        for _ in range(num_expense):
            cid = rng.choice(expense_cats)
            tpl = rng.choice(templates[cid])
            _, _, lo, hi = tpl
            expense_amounts.append(sample_amount(lo, hi, rng))

        total_expense = sum(expense_amounts)
        required_income = round(total_expense * SURPLUS_MARGIN, 2)

        # salary + optional secondary income
        salary_account = pick_account(user_accounts, "income", rng)
        secondary_income = 0.0
        extra_incomes: list[dict] = []

        if num_income >= 2:
            secondary_income = round(rng.uniform(500, min(8000, total_expense * 0.08)), 2)
            extra_cat = rng.choice([REFUND_CATEGORY, DIVIDEND_CATEGORY])
            if extra_cat == REFUND_CATEGORY:
                merch, desc = rng.choice(REFUND_MERCHANTS)
            else:
                merch, desc = rng.choice(DIVIDEND_MERCHANTS)
            extra_incomes.append(
                {
                    "category_id": extra_cat,
                    "merchant_name": merch,
                    "description": desc,
                    "amount": secondary_income,
                    "account": pick_account(user_accounts, "income", rng),
                    "day": rng.randint(10, month_end(2026, month)),
                }
            )

        if num_income >= 3:
            extra2 = round(rng.uniform(300, 5000), 2)
            secondary_income += extra2
            merch2, desc2 = rng.choice(DIVIDEND_MERCHANTS)
            extra_incomes.append(
                {
                    "category_id": DIVIDEND_CATEGORY,
                    "merchant_name": merch2,
                    "description": rng.choice(
                        ["Bonus credit", "Freelance payment", "Cashback reward"]
                    ),
                    "amount": extra2,
                    "account": pick_account(user_accounts, "income", rng),
                    "day": rng.randint(15, month_end(2026, month)),
                }
            )

        salary_amount = round(required_income - secondary_income, 2)
        if salary_amount < 25000:
            salary_amount = round(25000 + rng.uniform(0, 15000), 2)

        merch, desc = rng.choice(SALARY_MERCHANTS)
        salary_day = rng.randint(1, 5)

        # build expense rows
        expense_rows: list[dict] = []
        for i, amt in enumerate(expense_amounts):
            cid = rng.choice(expense_cats)
            tpl = rng.choice(templates[cid])
            merchant, description, lo, hi = tpl
            acc = pick_account(user_accounts, "expense", rng)
            d = random_date_in_month(2026, month, rng)
            expense_rows.append(
                {
                    "transaction_id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "account_id": acc["account_id"],
                    "category_id": cid,
                    "transaction_date": d.isoformat(),
                    "amount": amt,
                    "running_balance": 0,
                    "transaction_type": "expense",
                    "merchant_name": merchant,
                    "description": description,
                }
            )

        income_rows: list[dict] = [
            {
                "transaction_id": str(uuid.uuid4()),
                "user_id": user_id,
                "account_id": salary_account["account_id"],
                "category_id": SALARY_CATEGORY,
                "transaction_date": date(2026, month, salary_day).isoformat(),
                "amount": salary_amount,
                "running_balance": 0,
                "transaction_type": "income",
                "merchant_name": merch,
                "description": desc,
            }
        ]

        for extra in extra_incomes:
            income_rows.append(
                {
                    "transaction_id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "account_id": extra["account"]["account_id"],
                    "category_id": extra["category_id"],
                    "transaction_date": date(2026, month, extra["day"]).isoformat(),
                    "amount": extra["amount"],
                    "running_balance": 0,
                    "transaction_type": "income",
                    "merchant_name": extra["merchant_name"],
                    "description": extra["description"],
                }
            )

        # enforce income > expense
        inc_sum = sum(float(r["amount"]) for r in income_rows)
        exp_sum = sum(float(r["amount"]) for r in expense_rows)
        if inc_sum <= exp_sum:
            bump = round((exp_sum * SURPLUS_MARGIN) - inc_sum + 100, 2)
            income_rows[0]["amount"] = round(float(income_rows[0]["amount"]) + bump, 2)

        transactions.extend(expense_rows)
        transactions.extend(income_rows)

    return transactions


def compute_running_balances(
    transactions: list[dict],
    opening_balances: dict[str, float],
) -> None:
    by_account: dict[str, list[dict]] = defaultdict(list)
    for txn in transactions:
        by_account[txn["account_id"]].append(txn)

    for account_id, txns in by_account.items():
        balance = opening_balances.get(account_id, 0.0)
        sorted_txns = sorted(
            txns, key=lambda t: (t["transaction_date"], t["transaction_id"])
        )
        for txn in sorted_txns:
            amt = float(txn["amount"])
            if txn["transaction_type"] == "income":
                balance += amt
            else:
                balance -= amt
            txn["running_balance"] = round(balance, 2)


def validate(
    transactions: list[dict],
    users: list[dict],
    accounts: list[dict],
    categories: list[dict],
) -> bool:
    ok = True
    user_ids = {u["user_id"] for u in users}
    account_ids = {a["account_id"] for a in accounts}
    account_to_user = {a["account_id"]: a["user_id"] for a in accounts}
    category_ids = {c["category_id"] for c in categories}
    income_cats = {c["category_id"] for c in categories if c["main_category"] == "Income"}

    print(f"\n=== Validation ===")
    print(f"Row count: {len(transactions)} (expected {TOTAL_ROWS})")
    if len(transactions) != TOTAL_ROWS:
        ok = False

    dates = [t["transaction_date"] for t in transactions]
    print(f"Date range: {min(dates)} to {max(dates)}")
    if min(dates) < START_DATE.isoformat() or max(dates) > END_DATE.isoformat():
        ok = False

    for t in transactions:
        if t["user_id"] not in user_ids:
            print(f"Invalid user_id: {t['user_id']}")
            ok = False
        if t["account_id"] not in account_ids:
            print(f"Invalid account_id: {t['account_id']}")
            ok = False
        if t["account_id"] in account_to_user:
            if account_to_user[t["account_id"]] != t["user_id"]:
                print(f"Account/user mismatch: {t['transaction_id']}")
                ok = False
        if t["category_id"] not in category_ids:
            print(f"Invalid category_id: {t['category_id']}")
            ok = False
        is_income = t["category_id"] in income_cats
        if is_income and t["transaction_type"] != "income":
            print(f"Income category with expense type: {t['transaction_id']}")
            ok = False
        if not is_income and t["transaction_type"] != "expense":
            print(f"Non-income category with income type: {t['transaction_id']}")
            ok = False

    months = [(2026, m) for m in range(1, 6)]
    failures = 0
    for uid in sorted(user_ids):
        for year, month in months:
            month_prefix = f"{year}-{month:02d}"
            month_txns = [
                t
                for t in transactions
                if t["user_id"] == uid and t["transaction_date"].startswith(month_prefix)
            ]
            inc = sum(
                float(t["amount"])
                for t in month_txns
                if t["transaction_type"] == "income"
            )
            exp = sum(
                float(t["amount"])
                for t in month_txns
                if t["transaction_type"] == "expense"
            )
            surplus = inc - exp
            if surplus <= 0:
                print(
                    f"FAIL {uid[:8]}… {month_prefix}: income={inc:.2f} expense={exp:.2f}"
                )
                failures += 1
                ok = False

    print(f"User-month income>expense failures: {failures}")
    print(f"Overall: {'PASS' if ok else 'FAIL'}")
    return ok


def main() -> None:
    rng = random.Random(SEED)

    users = load_csv(BASE_DIR / "users.csv")
    accounts = load_csv(BASE_DIR / "accounts.csv")
    categories = load_csv(BASE_DIR / "categories.csv")
    existing = load_csv(BASE_DIR / "transactions.csv")

    templates = build_templates(existing)
    opening_balances = {
        a["account_id"]: float(a["current_balance"]) for a in accounts
    }

    transactions = generate_transactions(
        users, accounts, categories, templates, rng
    )

    compute_running_balances(transactions, opening_balances)

    # update account balances
    final_balances = dict(opening_balances)
    for txn in transactions:
        aid = txn["account_id"]
        final_balances[aid] = float(txn["running_balance"])

    for acc in accounts:
        acc["current_balance"] = f"{final_balances[acc['account_id']]:.2f}"

    txn_fields = [
        "transaction_id",
        "user_id",
        "account_id",
        "category_id",
        "transaction_date",
        "amount",
        "running_balance",
        "transaction_type",
        "merchant_name",
        "description",
    ]
    for t in transactions:
        t["amount"] = f"{float(t['amount']):.2f}"
        t["running_balance"] = f"{float(t['running_balance']):.2f}"

    write_csv(BASE_DIR / "transactions.csv", txn_fields, transactions)

    acc_fields = list(accounts[0].keys())
    write_csv(BASE_DIR / "accounts.csv", acc_fields, accounts)

    validate(transactions, users, accounts, categories)
    print("\nWrote transactions.csv and updated accounts.csv")


if __name__ == "__main__":
    main()
