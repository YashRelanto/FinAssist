"""
ETL Pipeline: CSV -> Supabase

This script reads a transactions CSV and populates these tables:

1. users
2. accounts
3. categories
4. transactions

Assumed schema
--------------

users:
    user_id (PK)
    full_name
    email
    password
    created_at
    deleted_at

accounts:
    account_id (PK)
    user_id (FK)
    account_name
    account_type
    current_balance
    credit_limit
    created_at

categories:
    category_id (PK)
    category_name
    parent_category

transactions:
    transaction_id (PK)
    user_id (FK)
    account_id (FK)
    category_id (FK)
    transaction_date
    amount
    transaction_type
    merchant_name
    description

Environment variables required
------------------------------
SUPABASE_URL
SUPABASE_KEY
"""

import os
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

# ==========================================================
# 1. LOAD ENVIRONMENT VARIABLES
# ==========================================================
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================================
# 2. LOAD CSV
# ==========================================================
CSV_PATH = "transactions.csv"
df = pd.read_csv(CSV_PATH)

# Fill NaN with None-compatible values
df = df.where(pd.notnull(df), None)

# ==========================================================
# 3. UPSERT USERS
# ==========================================================
unique_users = df["user_id"].dropna().unique()

for user_id in unique_users:
    user_data = {
        "user_id": user_id,
        "full_name": None,
        "email": None,
        "password": None,
        "deleted_at": None
    }

    # Upsert prevents duplicate insertion
    supabase.table("users").upsert(
        user_data,
        on_conflict="user_id"
    ).execute()

print(f"Inserted/updated {len(unique_users)} users.")

# ==========================================================
# 4. UPSERT ACCOUNTS
# ==========================================================
account_rows = []

for account_id, group in df.groupby("account_id"):
    first_row = group.iloc[0]

    # Extract account name from account_id:
    # acc_kotak_e4fb97 -> kotak
    parts = account_id.split("_")
    account_name = parts[1].upper() if len(parts) >= 3 else account_id

    # Guess account type from the account_id string key.
    # If it's a credit card, store borrowed amounts as a negative balance
    # so expense transactions move the value further negative.
    key = str(account_id).lower()
    if "cc" in key or "credit" in key:
        account_type = "credit_card"
    elif "wallet" in key or "gpay" in key or "paytm" in key:
        account_type = "wallet"
    elif "invest" in key:
        account_type = "investment"
    elif "current" in key:
        account_type = "checking"
    else:
        account_type = "savings"

    # Latest balance based on latest date
    latest_row = group.sort_values("date").iloc[-1]
    current_balance = float(latest_row["initial_balance"])
    credit_limit = None
    if account_type == "credit_card":
        current_balance = -abs(current_balance)
        # Derived credit limit for utilization warnings (can be overridden by CSV later)
        credit_limit = round(max(abs(current_balance) * 1.25, 1.0), 2)

    account_rows.append({
        "account_id": account_id,
        "user_id": first_row["user_id"],
        "account_name": account_name,
        "account_type": account_type,
        "current_balance": current_balance,
        **({"credit_limit": credit_limit} if credit_limit is not None else {}),
    })

# Bulk upsert
supabase.table("accounts").upsert(
    account_rows,
    on_conflict="account_id"
).execute()

print(f"Inserted/updated {len(account_rows)} accounts.")

# ==========================================================
# 5. UPSERT CATEGORIES
# ==========================================================
category_map = {}  # "Income::Salary" -> generated category_id
category_rows = []

for tag in df["tags"].dropna().unique():
    if "::" in tag:
        parent, child = tag.split("::", 1)
    else:
        parent, child = None, tag

    category_id = (
        child.lower()
        .replace("&", "and")
        .replace(" ", "_")
        .replace("/", "_")
    )

    category_map[tag] = category_id

    category_rows.append({
        "category_id": category_id,
        "category_name": child,
        "parent_category": parent
    })

# Remove duplicates
category_rows = list({
    row["category_id"]: row
    for row in category_rows
}.values())

if category_rows:
    supabase.table("categories").upsert(
        category_rows,
        on_conflict="category_id"
    ).execute()

print(f"Inserted/updated {len(category_rows)} categories.")

# ==========================================================
# 6. UPSERT TRANSACTIONS
# ==========================================================
transaction_rows = []

for _, row in df.iterrows():
    transaction_rows.append({
        "transaction_id": row["reference_id"],
        "user_id": row["user_id"],
        "account_id": row["account_id"],
        "category_id": category_map.get(row["tags"]),
        "transaction_date": row["date"],
        "amount": float(row["amount"]),
        "transaction_type": row["transaction_type"],
        "merchant_name": row["merchant_name"],
        "description": row["remark"]
    })

# Insert in batches to avoid payload limits
BATCH_SIZE = 500

for i in range(0, len(transaction_rows), BATCH_SIZE):
    batch = transaction_rows[i:i + BATCH_SIZE]

    supabase.table("transactions").upsert(
        batch,
        on_conflict="transaction_id"
    ).execute()

print(f"Inserted/updated {len(transaction_rows)} transactions.")

print("ETL completed successfully.")