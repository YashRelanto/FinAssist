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
    data_dir = Path("./data")

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

        upload_csv_to_supabase(
            csv_path=str(csv_file),
            table_name=table_name,
        )

    print("\nAll tables populated successfully.")


if __name__ == "__main__":
    main()