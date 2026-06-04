import hashlib
from datetime import date
from typing import List, Tuple
from app.utils.supabase_client import supabase
from .models import ParsedTransaction

class Validator:
    """
    Enforces statement integrity, date/amount constraints, and prevents double uploads
    via file-level SHA256 and transaction-level cryptographic hashes.
    """

    @staticmethod
    def generate_file_hash(file_bytes: bytes) -> str:
        """
        Generates SHA-256 of statement raw file bytes.
        """
        return hashlib.sha256(file_bytes).hexdigest()

    @staticmethod
    def generate_transaction_hash(account_number: str, tx_date: str, amount: float, description: str) -> str:
        """
        Generates transaction-level hash: SHA-256 of account_number + date + amount + description.
        """
        payload = f"{account_number.strip()}|{tx_date.strip()}|{abs(amount):.2f}|{description.strip().lower()}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def check_file_duplicate(cls, file_hash: str) -> bool:
        """
        Checks if the statement file has already been ingested.
        """
        try:
            res = supabase.table("uploaded_statements").select("id").eq("statement_hash", file_hash).execute()
            return len(res.data) > 0
        except Exception as e:
            print(f"File hash check failed: {e}")
            return False

    @classmethod
    def filter_duplicate_transactions(cls, transactions: List[ParsedTransaction], account_number: str) -> Tuple[List[ParsedTransaction], List[str]]:
        """
        Calculates hashes and filters out transaction-level duplicates against the database.
        Returns: Tuple[filtered_transactions_list, list_of_all_calculated_hashes]
        """
        if not transactions:
            return [], []

        hashes = []
        filtered = []
        
        # Calculate hashes for this statement batch
        for tx in transactions:
            tx_hash = cls.generate_transaction_hash(
                account_number=account_number,
                tx_date=tx.transaction_date,
                amount=tx.amount,
                description=tx.description
            )
            tx.normalized_merchant = tx_hash # Temporary store hash placeholder or set field
            hashes.append((tx, tx_hash))

        # Check existing hashes in DB in a single batch query
        try:
            db_hashes = []
            tx_hashes = [h for _, h in hashes]
            
            # Query in batches of 200 hashes to avoid SQL parameter limits
            for i in range(0, len(tx_hashes), 200):
                res = supabase.table("transactions")\
                    .select("transaction_hash")\
                    .in_("transaction_hash", tx_hashes[i:i+200])\
                    .execute()
                if res.data:
                    db_hashes.extend([row["transaction_hash"] for row in res.data])

            db_hash_set = set(db_hashes)
            
            for tx, tx_hash in hashes:
                # Basic validation checks: Date must be valid, amount must be positive magnitude
                try:
                    tx_date = date.fromisoformat(tx.transaction_date)
                    if tx_date > date.today():
                        continue  # Skip future dates
                except ValueError:
                    continue  # Invalid date format

                if tx.amount <= 0:
                    continue  # Skip zero or negative values
                    
                # Skip duplicate
                if tx_hash in db_hash_set:
                    continue
                    
                filtered.append(tx)
        except Exception as e:
            print(f"Transaction duplicate validation query failed: {e}")
            # In case of DB query failure, fallback to allowing insertion (non-blocking)
            filtered = [tx for tx, _ in hashes]
            
        return filtered, [h for _, h in hashes]
