from typing import List, Tuple, Dict, Any, Optional
from .bank_detector import BankDetector
from .pdf_ocr_extractor import PDFOCRExtractor
from .account_extractor import AccountExtractor
from .transaction_extractor import TransactionExtractor
from .merchant_normalizer import MerchantNormalizer
from .categorizer import Categorizer
from .validator import Validator
from .db_persistence import DBPersistence
from .models import ParsedTransaction

class StatementPipeline:
    """
    Orchestration manager that executes the step-by-step processing pipeline:
    Extract text -> Detect bank -> Resolve Account -> Extract Txs -> Normalize -> Categorize -> Persist.
    """

    @classmethod
    def run_pipeline(
        cls,
        statement_id: str,
        file_path: str,
        user_id: str,
        password: Optional[str] = None,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Executes the full parsing and persistence pipeline synchronously.
        Updates progress via progress_callback (e.g. 10%...50%...100%).
        """
        # ── Step 1: Text Extraction (15%) ──
        if progress_callback:
            progress_callback(10)
        text = PDFOCRExtractor.extract_text(file_path, password)
        if not text.strip():
            raise ValueError("Extracted text is empty. PDF statement could not be read.")
            
        # ── Step 2: Bank Detection (25%) ──
        if progress_callback:
            progress_callback(25)
        detected_bank = BankDetector.detect_bank(text)
        
        # ── Step 3: Account Info Extraction & Resolution (40%) ──
        if progress_callback:
            progress_callback(40)
        account_metadata = AccountExtractor.extract_account_details(text, detected_bank)
        account_id = DBPersistence.resolve_or_create_account(user_id, account_metadata)
        
        # ── Step 4: Transaction Extraction (60%) ──
        if progress_callback:
            progress_callback(60)
        raw_txs = TransactionExtractor.parse_transactions(text, detected_bank)
        if not raw_txs:
            return {
                "success": True,
                "inserted_count": 0,
                "account_id": account_id,
                "message": "No transactions found in this statement period."
            }
            
        # ── Step 5 & 6: Merchant Normalization & V1 Categorization (80%) ──
        if progress_callback:
            progress_callback(80)
            
        # Bulk pre-fetch lookup tables once to prevent N+1 loop queries
        from app.utils.supabase_client import supabase
        db_merchants = []
        db_categories = []
        user_overrides = []
        
        try:
            merchants_res = supabase.table("merchant_master").select("merchant_name, normalized_name, category").execute()
            db_merchants = merchants_res.data if merchants_res else []
        except Exception as e:
            pass

        try:
            categories_res = supabase.table("categories").select("category_id, main_category").execute()
            db_categories = categories_res.data if categories_res else []
        except Exception as e:
            pass

        try:
            overrides_res = supabase.table("user_category_overrides")\
                .select("override_category_id, categories(main_category), merchant_name")\
                .eq("user_id", user_id)\
                .execute()
            user_overrides = overrides_res.data if overrides_res else []
        except Exception as e:
            pass
            
        processed_txs = []
        for tx in raw_txs:
            # Clean and normalize merchant names
            normalized = MerchantNormalizer.normalize_merchant(tx.description, db_merchants=db_merchants)
            tx.normalized_merchant = normalized
            
            # Print targeted debug log for merchant name extraction as requested
            print(f"[DEBUG] Raw Description: '{tx.description}' -> Extracted Merchant Name: '{normalized}'")
            
            # Map category deterministically (V1 rules -> overrides -> Others)
            cat_id, cat_name = Categorizer.resolve_category(
                normalized_merchant=normalized,
                user_id=user_id,
                user_overrides=user_overrides,
                master_merchants=db_merchants,
                db_categories=db_categories
            )
            tx.category_id = cat_id
            tx.category_name = cat_name
            
            processed_txs.append(tx)
            
        # ── Step 7: Deduplication & Filtering (90%) ──
        if progress_callback:
            progress_callback(90)
        filtered_txs, tx_hashes = Validator.filter_duplicate_transactions(
            processed_txs,
            account_metadata.account_number
        )
        
        # ── Step 8: DB Persistence & Balance Sync (100%) ──
        inserted_count = DBPersistence.persist_transactions(
            user_id=user_id,
            account_id=account_id,
            statement_id=statement_id,
            transactions=filtered_txs,
            transaction_hashes=tx_hashes
        )
        
        if progress_callback:
            progress_callback(100)
            
        return {
            "success": True,
            "inserted_count": inserted_count,
            "total_extracted": len(raw_txs),
            "duplicates_skipped": len(raw_txs) - inserted_count,
            "account_id": account_id,
            "bank_name": account_metadata.bank_name,
            "account_number": account_metadata.account_number
        }
