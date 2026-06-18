import os
import tempfile
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from app.core.auth import get_current_user
from pydantic import BaseModel

from app.utils.supabase_client import supabase
from app.services.statement_processor.pdf_ocr_extractor import PDFOCRExtractor, PasswordProtectedException, TextExtractionException
from app.services.statement_processor.account_extractor import AccountExtractor
from app.services.statement_processor.bank_detector import BankDetector
from app.services.statement_processor.transaction_extractor import TransactionExtractor
from app.services.statement_processor.merchant_normalizer import MerchantNormalizer
from app.services.statement_processor.categorizer import Categorizer
from app.services.statement_processor.background_worker import BackgroundWorker
from app.services.statement_processor.validator import Validator

router = APIRouter(prefix="/api/statement", tags=["Statement Parser"])

# ─── Pydantic Models ──────────────────────────────────────────────

class ParsedTxResponse(BaseModel):
    transaction_date: str
    amount: float
    transaction_type: str
    merchant_name: str
    description: str
    running_balance: Optional[float] = None
    category_name: Optional[str] = None

class ParseStatementResponse(BaseModel):
    success: bool
    transactions: List[ParsedTxResponse]
    file_name: Optional[str] = None
    total_credits: float
    total_debits: float
    net_flow: float
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    account_holder: Optional[str] = None
    ifsc: Optional[str] = None

class IngestRequest(BaseModel):
    user_id: Optional[str] = None  # ignored — identity comes from JWT
    transactions: List[ParsedTxResponse]
    account_name: Optional[str] = "Bank Statement"
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    account_holder: Optional[str] = None
    ifsc: Optional[str] = None

class IngestResponse(BaseModel):
    success: bool
    inserted_count: int
    account_id: str
    balance_change: float

class ParseRequest(BaseModel):
    raw_text: str
    file_name: Optional[str] = None

class JobStatusResponse(BaseModel):
    job_id: str
    statement_id: str
    status: str
    progress: int
    error_message: Optional[str] = None


# ─── API Endpoints ────────────────────────────────────────────────

@router.post("/parse-text", response_model=ParseStatementResponse)
async def parse_statement_text(request: ParseRequest):
    """
    Simulated parsing from raw text context directly.
    """
    detected_bank = BankDetector.detect_bank(request.raw_text)
    txs = TransactionExtractor.parse_transactions(request.raw_text, detected_bank)
    
    res_txs = []
    total_credits = 0.0
    total_debits = 0.0
    
    for t in txs:
        res_txs.append(ParsedTxResponse(
            transaction_date=t.transaction_date,
            amount=t.amount,
            transaction_type=t.transaction_type,
            merchant_name=t.merchant_name,
            description=t.description,
            running_balance=t.running_balance,
            category_name="Others"
        ))
        if t.transaction_type.lower() in ["credit", "income"]:
            total_credits += t.amount
        else:
            total_debits += t.amount

    return ParseStatementResponse(
        success=True,
        transactions=res_txs,
        file_name=request.file_name,
        total_credits=total_credits,
        total_debits=total_debits,
        net_flow=total_credits - total_debits
    )


@router.post("/parse-file", response_model=ParseStatementResponse)
async def parse_statement_file(
    file: UploadFile = File(...),
    password: Optional[str] = Form(None),
    user_id: Optional[str] = Form(None)
):
    """
    Parses a PDF/CSV file synchronously into structured transactions for client preview (no DB write).
    Utilizes our robust block parsing pipeline.
    """
    suffix = os.path.splitext(file.filename)[1] or ".pdf"
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        # Extract text & Detect bank format
        text = PDFOCRExtractor.extract_text(tmp_path, password)
        detected_bank = BankDetector.detect_bank(text)
        account_metadata = AccountExtractor.extract_account_details(text, detected_bank)
        
        # Parse transactions using layout strategies
        txs = TransactionExtractor.parse_transactions(text, detected_bank)
        if not txs:
            raise HTTPException(status_code=400, detail="No transactions could be extracted from the file.")

        res_txs = []
        total_credits = 0.0
        total_debits = 0.0

        # Bulk pre-fetch lookup tables once to prevent N+1 loop queries in route
        db_merchants = []
        db_categories = []
        user_overrides = []
        placeholder_user_id = "00000000-0000-0000-0000-000000000000"
        user_id_val = user_id or placeholder_user_id
        
        try:
            merchants_res = supabase.table("merchant_master").select("merchant_name, normalized_name, category").execute()
            db_merchants = merchants_res.data if merchants_res else []
        except Exception as e:
            print(f"[API Route] Failed to bulk fetch merchant_master: {e}")

        try:
            categories_res = supabase.table("categories").select("category_id, main_category").execute()
            db_categories = categories_res.data if categories_res else []
        except Exception as e:
            print(f"[API Route] Failed to bulk fetch categories: {e}")

        try:
            overrides_res = supabase.table("user_category_overrides")\
                .select("override_category_id, categories(main_category), merchant_name")\
                .eq("user_id", user_id_val)\
                .execute()
            user_overrides = overrides_res.data if overrides_res else []
        except Exception as e:
            print(f"[API Route] Failed to bulk fetch user_category_overrides: {e}")

        for t in txs:
            normalized = MerchantNormalizer.normalize_merchant(t.description, db_merchants=db_merchants)
            _, cat_name = Categorizer.resolve_category(
                normalized_merchant=normalized,
                user_id=user_id_val,
                user_overrides=user_overrides,
                master_merchants=db_merchants,
                db_categories=db_categories
            )
            
            res_txs.append(ParsedTxResponse(
                transaction_date=t.transaction_date,
                amount=t.amount,
                transaction_type=t.transaction_type,
                merchant_name=normalized,
                description=t.description,
                running_balance=t.running_balance,
                category_name=cat_name
            ))
            
            if t.transaction_type.lower() in ["credit", "income"]:
                total_credits += t.amount
            else:
                total_debits += t.amount

        return ParseStatementResponse(
            success=True,
            transactions=res_txs,
            file_name=file.filename,
            total_credits=total_credits,
            total_debits=total_debits,
            net_flow=total_credits - total_debits,
            bank_name=account_metadata.bank_name,
            account_number=account_metadata.account_number,
            account_holder=account_metadata.account_holder,
            ifsc=account_metadata.ifsc
        )
    except PasswordProtectedException as e:
        raise HTTPException(status_code=401, detail={"type": e.error_type, "message": str(e)})
    except TextExtractionException as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.post("/upload", response_model=IngestResponse)
async def upload_statement(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    account_name: str = Form("Bank Statement"),
    password: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["user_id"]
    """
    Main upload entrypoint. Integrates with the new modular asynchronous worker queue.
    Ensures statement file hashing, duplicate prevention, and async threading.
    """
    suffix = os.path.splitext(file.filename)[1] or ".pdf"
    
    # 1. Read file bytes and compute file hash
    file_bytes = await file.read()
    file_hash = Validator.generate_file_hash(file_bytes)
    
    # 2. Check for duplicate statement uploads
    if Validator.check_file_duplicate(file_hash):
        raise HTTPException(
            status_code=409, 
            detail=f"Duplicate statement: The statement '{file.filename}' has already been processed."
        )

    # 3. Create temp file for worker access
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        # 4. Insert uploaded_statement record
        statement_ins = supabase.table("uploaded_statements").insert({
            "user_id": user_id,
            "file_name": file.filename,
            "statement_hash": file_hash,
            "status": "PENDING"
        }).execute()
        
        if not statement_ins.data:
            raise HTTPException(status_code=500, detail="Failed to initialize uploaded statement record")
            
        statement_id = statement_ins.data[0]["id"]

        # 5. Insert processing_job record
        job_ins = supabase.table("processing_jobs").insert({
            "statement_id": statement_id,
            "status": "PENDING",
            "progress": 0
        }).execute()
        
        if not job_ins.data:
            raise HTTPException(status_code=500, detail="Failed to initialize processing job record")
            
        job_id = job_ins.data[0]["id"]

        # 6. Queue the background processing thread
        background_tasks.add_task(
            BackgroundWorker.process_statement_task,
            job_id=job_id,
            statement_id=statement_id,
            file_path=tmp_path,
            user_id=user_id,
            password=password
        )

        # Standard compatible success response (can return job_id to the UI)
        return IngestResponse(
            success=True,
            inserted_count=0,
            account_id=job_id,  # Returning job_id as account_id is temporary wrapper
            balance_change=0.0
        )

    except Exception as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise HTTPException(status_code=500, detail=f"Failed to queue statement: {str(e)}")


@router.post("/ingest", response_model=IngestResponse)
async def ingest_statement(
    request: IngestRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Ingests pre-parsed client transactions synchronously from React JSON payloads.
    Optimized for batch-writes and single-trip database updates.
    """
    uid = current_user["user_id"]
    try:
        # 1. Resolve Account Once
        acc_res = supabase.table("accounts").select("account_id, current_balance").eq("user_id", uid).eq("account_name", request.account_name).execute()
        if acc_res.data:
            account_id = acc_res.data[0]["account_id"]
            current_balance = float(acc_res.data[0]["current_balance"] or 0)
            # Update optional missing meta fields if needed
            supabase.table("accounts").update({
                "bank_name": request.bank_name,
                "account_holder": request.account_holder,
                "account_number": request.account_number,
                "ifsc": request.ifsc
            }).eq("account_id", account_id).execute()
        else:
            acc_ins = supabase.table("accounts").insert({
                "user_id": uid,
                "account_name": request.account_name,
                "account_type": "checking", 
                "current_balance": 0.0,
                "bank_name": request.bank_name,
                "account_holder": request.account_holder,
                "account_number": request.account_number,
                "ifsc": request.ifsc
            }).execute()
            account_id = acc_ins.data[0]["account_id"]
            current_balance = 0.0

        # 2. Load Categories lookup table once
        cat_res = supabase.table("categories").select("category_id, main_category").execute()
        category_map = {}
        if cat_res.data:
            for row in cat_res.data:
                category_map[row["main_category"].lower()] = row["category_id"]

        # Default fallback category
        default_category_id = category_map.get("others", list(category_map.values())[0] if category_map else None)

        # 3. Build Batch Payloads
        insert_data = []
        balance_change = 0.0

        for t in request.transactions:
            # Map type representation
            db_tx_type = t.transaction_type.lower()
            magnitude = abs(t.amount)
            if db_tx_type in ["credit", "income"]:
                db_tx_type = "income"
                balance_change += magnitude
            else:
                db_tx_type = "expense"
                balance_change -= magnitude

            # Resolve Category ID in memory
            cat_name_key = (t.category_name or "others").lower()
            cat_id = category_map.get(cat_name_key, default_category_id)

            insert_data.append({
                "user_id": uid,
                "account_id": account_id,
                "category_id": cat_id,
                "transaction_date": t.transaction_date,
                "amount": magnitude,
                "transaction_type": db_tx_type,
                "description": t.description,
                "merchant_name": t.merchant_name,
                "running_balance": t.running_balance
            })

        # 4. Batch Insert Transactions (Single Query)
        inserted_count = 0
        if insert_data:
            # Batch inserts are split into chunks of 100 to avoid payload limits
            for chunk_idx in range(0, len(insert_data), 100):
                chunk = insert_data[chunk_idx:chunk_idx+100]
                ins_res = supabase.table("transactions").insert(chunk).execute()
                inserted_count += len(ins_res.data) if ins_res.data else 0

        # 5. Update Account Balance Once atomically via RPC (with safe fallback)
        if inserted_count > 0:
            try:
                supabase.rpc("sync_account_balance", {
                    "p_account_id": account_id,
                    "p_net_delta": balance_change
                }).execute()
            except Exception as rpc_err:
                try:
                    acc_res = supabase.table("accounts").select("current_balance").eq("account_id", account_id).execute()
                    if acc_res.data:
                        curr_bal = float(acc_res.data[0].get("current_balance") or 0.0)
                        new_bal = curr_bal + balance_change
                        supabase.table("accounts").update({"current_balance": new_bal}).eq("account_id", account_id).execute()
                except Exception as fallback_err:
                    pass

        return IngestResponse(
            success=True,
            inserted_count=inserted_count,
            account_id=account_id,
            balance_change=balance_change
        )
    except Exception as e:
        print(f"Batch ingestion failed: {e}")
        raise HTTPException(status_code=400, detail=f"Synchronous batch ingestion failed: {e}")


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """
    Retrieves progress of an active background processing statement task.
    """
    try:
        res = supabase.table("processing_jobs").select("*").eq("id", job_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Ingestion job not found")
        row = res.data[0]
        return JobStatusResponse(
            job_id=row["id"],
            statement_id=row["statement_id"],
            status=row["status"],
            progress=row["progress"],
            error_message=row["error_message"]
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/uploaded-statements")
async def list_uploaded_statements(current_user: dict = Depends(get_current_user)):
    """
    Lists all processed statements for the authenticated user.
    """
    user_id = current_user["user_id"]
    try:
        res = supabase.table("uploaded_statements")\
            .select("*")\
            .eq("user_id", user_id)\
            .order("upload_date", desc=True)\
            .execute()
        return {"success": True, "data": res.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))