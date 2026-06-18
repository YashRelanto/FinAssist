from typing import List
from fastapi import HTTPException
from app.utils.supabase_client import supabase
from .models import ParsedTransaction, AccountMetadata

class DBPersistence:
    """
    Persists statement metadata, bank accounts, and transactions back to the database.
    Performs transactional balance adjustments.
    """

    @classmethod
    def resolve_or_create_account(cls, user_id: str, metadata: AccountMetadata) -> str:
        """
        Looks up an existing account matching the parsed account_number.
        If none exists, initializes a new account entry in the accounts table.
        Returns the account_id (UUID).
        """
        # Look up by account number
        try:
            res = supabase.table("accounts")\
                .select("account_id")\
                .eq("user_id", user_id)\
                .eq("account_number", metadata.account_number)\
                .execute()
                
            if res.data:
                account_id = res.data[0]["account_id"]
                # Update optional missing meta fields if needed
                update_payload = {
                    "bank_name": metadata.bank_name,
                    "account_holder": metadata.account_holder,
                    "ifsc": metadata.ifsc
                }
                up_res = supabase.table("accounts").update(update_payload).eq("account_id", account_id).execute()
                return account_id
        except Exception as e:
            pass

        # Fallback/Create new account
        short_num = metadata.account_number[-4:] if len(metadata.account_number) >= 4 else metadata.account_number
        name = f"{metadata.bank_name.title()} *{short_num}" if metadata.bank_name else "Bank Statement Account"
        
        insert_payload = {
            "user_id": user_id,
            "account_name": name,
            "account_type": "checking",
            "current_balance": 0.0,
            "bank_name": metadata.bank_name,
            "account_holder": metadata.account_holder,
            "account_number": metadata.account_number,
            "ifsc": metadata.ifsc
        }
        try:
            new_acc = supabase.table("accounts").insert(insert_payload).execute()
            
            if not new_acc.data:
                raise HTTPException(status_code=500, detail="Failed to create account profile")
            new_id = new_acc.data[0]["account_id"]
            return new_id
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to resolve bank account: {e}")

    @classmethod
    def persist_transactions(
        cls,
        user_id: str,
        account_id: str,
        statement_id: str,
        transactions: List[ParsedTransaction],
        transaction_hashes: List[str]
    ) -> int:
        """
        Inserts valid transactions in a batch. Updates the account balance based on net flows.
        Returns the count of successfully persisted records.
        """
        if not transactions:
            return 0

        insert_data = []
        net_delta = 0.0

        for tx, tx_hash in zip(transactions, transaction_hashes):
            magnitude = abs(tx.amount)
            db_tx_type = tx.transaction_type.lower()
            
            # Map type representation
            if db_tx_type in ["credit", "income"]:
                db_tx_type = "income"
                net_delta += magnitude
            else:
                db_tx_type = "expense"
                net_delta -= magnitude

            insert_data.append({
                "user_id": user_id,
                "account_id": account_id,
                "category_id": tx.category_id,
                "transaction_date": tx.transaction_date,
                "amount": magnitude,
                "transaction_type": db_tx_type,
                "description": tx.description,
                "merchant_name": tx.merchant_name,
                "normalized_merchant": tx.normalized_merchant,
                "running_balance": tx.running_balance,
                "statement_id": statement_id,
                "transaction_hash": tx_hash
            })

        # Insert transactions in a single batch
        inserted_count = 0
        try:
            res = supabase.table("transactions").insert(insert_data).execute()
            inserted_count = len(res.data) if res.data else 0
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database transaction writing failed: {e}")

        # Update account current_balance dynamically via atomic RPC (with safe fallback)
        if inserted_count > 0:
            try:
                rpc_res = supabase.rpc("sync_account_balance", {
                    "p_account_id": account_id,
                    "p_net_delta": net_delta
                }).execute()
            except Exception as e:
                try:
                    acc_res = supabase.table("accounts").select("current_balance").eq("account_id", account_id).execute()
                    if acc_res.data:
                        curr_bal = float(acc_res.data[0].get("current_balance") or 0.0)
                        new_bal = curr_bal + net_delta
                        supabase.table("accounts").update({"current_balance": new_bal}).eq("account_id", account_id).execute()
                except Exception as fallback_err:
                    pass

        return inserted_count
