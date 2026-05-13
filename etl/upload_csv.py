from pathlib import Path
import os

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client, Client



# Load environment variables and create Supabase client
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError(
        "SUPABASE_URL and SUPABASE_KEY must be set in your .env file."
    )

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# Table-specific conflict columns for UPSERT
CONFLICT_COLUMNS = {
    "users": "user_id",
    "accounts": "account_id",
    "categories": "category_id",
    "transactions": "transaction_id",
}


# Utility functions
def load_csv(csv_path: str) -> list[dict]:
    df = pd.read_csv(csv_path)

    # Convert all columns to object dtype so None is preserved
    df = df.astype(object)

    # Replace NaN, NaT, and pandas missing values with None
    df = df.where(pd.notna(df), None)

    return df.to_dict(orient="records")


def upload_csv_to_supabase(
    csv_path: str,
    table_name: str,
    batch_size: int = 500,
) -> None:
    print(f"\nUploading {csv_path} -> {table_name}")

    records = load_csv(csv_path)

    if not records:
        print(f"No data found in {csv_path}")
        return

    conflict_cols = CONFLICT_COLUMNS.get(table_name)
    total_rows = len(records)

    for start in range(0, total_rows, batch_size):
        end = min(start + batch_size, total_rows)
        batch = records[start:end]

        if conflict_cols:
            response = (
                supabase
                .table(table_name)
                .upsert(batch, on_conflict=conflict_cols)
                .execute()
            )
        else:
            response = (
                supabase
                .table(table_name)
                .insert(batch)
                .execute()
            )

        # Optional: access response.data if needed
        print(f"Uploaded rows {start + 1}-{end} of {total_rows}")

    print(f"Finished uploading {total_rows} rows to '{table_name}'.")


# Main execution
def main() -> None:
    data_dir = Path("./data/processed/")

    # 1. First, load accounts to get initial balances
    accounts_file = data_dir / "accounts.csv"
    account_balances = {}
    if accounts_file.exists():
        accounts_df = pd.read_csv(accounts_file)
        # Map account_id to its current_balance (which we treat as the starting point)
        account_balances = dict(zip(accounts_df['account_id'], accounts_df['current_balance']))

    files_to_upload = [
        ("users.csv", "users"),
        ("accounts.csv", "accounts"),
        ("categories.csv", "categories"),
        ("transactions.csv", "transactions"),
    ]

    for filename, table_name in files_to_upload:
        csv_file = data_dir / filename

        if not csv_file.exists():
            print(f"Skipping {csv_file}: file not found.")
            continue

        if table_name == "transactions":
            print(f"\nCalculating running balances for {filename}...")
            df = pd.read_csv(csv_file)
            
            # Sort by date to ensure chronological balance calculation
            df['transaction_date'] = pd.to_datetime(df['transaction_date'])
            df = df.sort_values(by=['account_id', 'transaction_date'])
            
            # Calculate running balance per account
            def calculate_balance(group):
                account_id = group.name
                # Start with the initial balance from accounts.csv if available, else 0
                current_bal = account_balances.get(account_id, 0)
                
                balances = []
                for idx, row in group.iterrows():
                    amount = float(row['amount'])
                    if row['transaction_type'] == 'expense':
                        current_bal -= amount
                    elif row['transaction_type'] == 'income':
                        current_bal += amount
                    # Transfers can be complex; for now we assume they impact the current account
                    
                    balances.append(current_bal)
                group['running_balance'] = balances
                return group

            df = df.groupby('account_id', group_keys=False).apply(calculate_balance)
            
            # Convert dates to strings for upload
            df['transaction_date'] = pd.to_datetime(df['transaction_date']).dt.strftime('%Y-%m-%d')
            
            # Convert back to dict records for upload
            df = df.astype(object).where(pd.notna(df), None)
            records = df.to_dict(orient="records")
            
            # Use custom upload logic for the processed transactions
            print(f"Uploading processed transactions -> {table_name}")
            conflict_cols = CONFLICT_COLUMNS.get(table_name)
            total_rows = len(records)
            batch_size = 500
            for start in range(0, total_rows, batch_size):
                end = min(start + batch_size, total_rows)
                batch = records[start:end]
                supabase.table(table_name).upsert(batch, on_conflict=conflict_cols).execute()
                print(f"Uploaded rows {start + 1}-{end} of {total_rows}")
        else:
            upload_csv_to_supabase(
                csv_path=str(csv_file),
                table_name=table_name,
            )

    print("\nAll tables populated successfully.")


if __name__ == "__main__":
    main()