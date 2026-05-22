"""
Enterprise-grade bank statement extraction and ingestion service.
"""

import re
import os
import tempfile
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
import pdfplumber
import pytesseract
from PIL import Image
from pdf2image import convert_from_path
from dateutil import parser as date_parser

from app.utils.supabase_client import supabase

router = APIRouter(prefix="/api/statement", tags=["Statement Parser"])

# ─── Pydantic Models ──────────────────────────────────────────────

class ParsedTransaction(BaseModel):
    transaction_date: str                  # YYYY-MM-DD
    amount: float                          # Always positive
    transaction_type: str                  # "Credit" or "Debit"
    merchant_name: Optional[str] = None    
    description: str                       
    running_balance: Optional[float] = None

class ParseStatementResponse(BaseModel):
    success: bool
    transactions: List[ParsedTransaction]
    file_name: Optional[str] = None
    total_credits: float
    total_debits: float
    net_flow: float

class IngestResponse(BaseModel):
    success: bool
    inserted_count: int
    account_id: str
    balance_change: float

class ParseRequest(BaseModel):
    raw_text: str
    file_name: Optional[str] = None

class IngestRequest(BaseModel):
    user_id: str
    transactions: List[ParsedTransaction]
    account_name: Optional[str] = "Bank Statement"


# ─── PDF Parsing & OCR Logic ─────────────────────────────────────────────
# (Keeping your parsing logic intact, with robust password/encryption handling)

class PasswordProtectedException(Exception):
    def __init__(self, message: str, error_type: str):
        super().__init__(message)
        self.error_type = error_type # "password_required" or "wrong_password"

class AdvancedBankParser:
    @staticmethod
    def extract_text_from_pdf(file_path: str, password: Optional[str] = None) -> str:
        # First check if PDF is encrypted/password protected
        try:
            with pdfplumber.open(file_path, password=password) as pdf:
                text = ""
                for page in pdf.pages:
                    text += page.extract_text() or ""
                return text
        except Exception as e:
            err_msg = str(e).lower()
            if any(k in err_msg for k in ["password", "encrypted", "authenticate", "passphrase"]):
                err_type = "wrong_password" if password else "password_required"
                raise PasswordProtectedException(f"PDF password error: {e}", err_type)
            # If it's a general exception, let's fall back to OCR below
            pass

        # Fallback to OCR (if it's scanned or empty text)
        try:
            images = convert_from_path(file_path, userpw=password)
            text = ""
            for img in images:
                text += pytesseract.image_to_string(img)
            return text
        except Exception as e:
            err_msg = str(e).lower()
            if any(k in err_msg for k in ["password", "encrypted", "authenticate", "passphrase"]):
                err_type = "wrong_password" if password else "password_required"
                raise PasswordProtectedException(f"PDF OCR password error: {e}", err_type)
            raise e

# Date/Amount Parsers
_DATE_FORMATS = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%y", "%d %b %Y", "%d %b %y", "%d-%b-%Y", "%d-%b-%y", "%d %B %Y", "%m/%d/%Y", "%b %d, %Y", "%B %d, %Y"]

def _parse_date(date_str: str, fallback_year: int = None) -> Optional[str]:
    date_str = date_str.strip().replace(",", " ").replace("  ", " ")
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.year < 2000 and len(date_str) <= 8:
                dt = dt.replace(year=dt.year + 2000)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None

def _parse_amount(amount_str: str) -> Optional[float]:
    if not amount_str: return None
    cleaned = re.sub(r"[₹$Rs,\s]", "", amount_str.strip())
    cleaned = re.sub(r"(CR|DR|cr|dr)$", "", cleaned).strip()
    try: return abs(float(cleaned))
    except (ValueError, TypeError): return None

def _parse_csv_text(raw_text: str) -> List[ParsedTransaction]:
    lines = [l.strip() for l in raw_text.strip().split("\n") if l.strip()]
    if not lines: return []
    header_idx = 0
    for i, line in enumerate(lines):
        if any(kw in line.lower() for kw in ["date", "transaction", "description"]):
            header_idx = i
            break
            
    headers = [h.strip().lower() for h in lines[header_idx].split(",")]
    transactions = []
    
    date_col = next((i for i, h in enumerate(headers) if "date" in h), 0)
    desc_col = next((i for i, h in enumerate(headers) if "desc" in h or "nar" in h), 1)
    amt_col = next((i for i, h in enumerate(headers) if "amt" in h or "amount" in h), 2)
    
    for line in lines[header_idx + 1:]:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) > amt_col:
            date = _parse_date(parts[date_col])
            amt = _parse_amount(parts[amt_col])
            if date and amt:
                transactions.append(ParsedTransaction(
                    transaction_date=date, amount=amt, transaction_type="Debit",
                    description=parts[desc_col]
                ))
    return transactions

def _parse_pdf_text_robust(raw_text: str) -> List[ParsedTransaction]:
    # 1. Try parsing as CSV first
    txs = _parse_csv_text(raw_text)
    if txs:
        return txs
        
    # 2. Fall back to robust regex line-by-line parsing
    lines = [l.strip() for l in raw_text.strip().split("\n") if l.strip()]
    transactions = []
    
    # regex for dates
    date_pattern = re.compile(
        r'(\b\d{1,2}[-/\s]+(?:[A-Za-z]{3,9}|\d{1,2})[-/\s]+\d{2,4}\b|'
        r'\b\d{4}[-/\s]+\d{1,2}[-/\s]+\d{1,2}\b|'
        r'\b[A-Za-z]{3,9}\s+\d{1,2}\s*,\s*\d{4}\b)'
    )
    
    for line in lines:
        date_match = date_pattern.search(line)
        if not date_match:
            continue
            
        date_str = date_match.group(1)
        parsed_date = _parse_date(date_str)
        if not parsed_date:
            continue
            
        rest = line.replace(date_str, " ").strip()
        
        amount_pattern = re.compile(r'[-+]?\s*[\d,]+\.\d{2}\b|[-+]?\s*\b\d{3,}\b')
        amounts = amount_pattern.findall(rest)
        
        if not amounts:
            continue
            
        parsed_amounts = []
        for amt in amounts:
            cleaned = _parse_amount(amt)
            if cleaned is not None and cleaned > 0:
                parsed_amounts.append((amt, cleaned))
                
        if not parsed_amounts:
            continue
            
        tx_amt_str, tx_amount = parsed_amounts[0]
        
        desc = rest
        for amt_str, _ in parsed_amounts:
            desc = desc.replace(amt_str, " ")
            
        tx_type = "Debit"
        lower_line = line.lower()
        if any(kw in lower_line for kw in ["cr", "credit", "dep", "deposit", "received", "refund"]):
            tx_type = "Credit"
        elif any(kw in lower_line for kw in ["dr", "debit", "wdr", "withdrawal", "payment", "spent"]):
            tx_type = "Debit"
            
        desc = re.sub(r'\s+', ' ', desc).strip()
        desc = re.sub(r'^(?:rs|usd|inr|[\$\u20B9\s,\.-])+', '', desc, flags=re.IGNORECASE).strip()
        desc = re.sub(r'(?:cr|dr)$', '', desc, flags=re.IGNORECASE).strip()
        
        if not desc:
            desc = "Transaction"
            
        transactions.append(ParsedTransaction(
            transaction_date=parsed_date,
            amount=tx_amount,
            transaction_type=tx_type,
            merchant_name=desc[:50] if len(desc) > 50 else desc,
            description=desc,
            running_balance=parsed_amounts[1][1] if len(parsed_amounts) > 1 else None
        ))
        
    return transactions

def parse_pdf_to_transactions(file_path: str, password: Optional[str] = None) -> List[ParsedTransaction]:
    # Check if the file is a CSV based on extension
    is_csv = file_path.lower().endswith('.csv')
    
    if is_csv:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                raw_text = f.read()
            return _parse_csv_text(raw_text)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to read CSV file: {e}")
            
    # Otherwise, treat as PDF
    raw_text = AdvancedBankParser.extract_text_from_pdf(file_path, password)
    return _parse_pdf_text_robust(raw_text)


# ─── Ingestion Logic (WITH FIXES) ─────────────────────────────────────────

async def _ingest_transactions(user_id: str, account_name: str, transactions: List[ParsedTransaction]) -> IngestResponse:
    # 1. Ensure Account Exists
    acc_response = supabase.table("accounts").select("*").eq("user_id", user_id).eq("account_name", account_name).execute()
    if not acc_response.data:
        # Note: Added 'checking' as default account_type to satisfy DB constraint
        acc_insert = supabase.table("accounts").insert({
            "user_id": user_id, 
            "account_name": account_name, 
            "account_type": "checking", 
            "current_balance": 0.0
        }).execute()
        account_id = acc_insert.data[0]["account_id"]
    else:
        account_id = acc_response.data[0]["account_id"]

    # 2. Fetch the Default 'Uncategorized' Category ID to prevent NOT NULL crash
    cat_response = supabase.table("categories").select("category_id").eq("sub_category", "Uncategorized").execute()
    if not cat_response.data:
        # Try finding Shopping -> Electronics or any category
        cat_response = supabase.table("categories").select("category_id").eq("main_category", "Shopping").execute()
    if not cat_response.data:
        # Get any category
        cat_response = supabase.table("categories").select("category_id").limit(1).execute()
        
    if not cat_response.data:
        # Seeding default categories if empty to prevent DB crashes and ensure self-healing
        default_categories = [
            {"main_category": "Food & Drinks", "sub_category": "Groceries"},
            {"main_category": "Food & Drinks", "sub_category": "Dining Out"},
            {"main_category": "Food & Drinks", "sub_category": "Cafes & Coffee"},
            {"main_category": "Shopping", "sub_category": "Electronics"},
            {"main_category": "Shopping", "sub_category": "Clothing & Apparel"},
            {"main_category": "Housing", "sub_category": "Rent"},
            {"main_category": "Housing", "sub_category": "Utilities"},
            {"main_category": "Transportation", "sub_category": "Metro & Bus"},
            {"main_category": "Transportation", "sub_category": "Cab & Auto"},
            {"main_category": "Vehicle", "sub_category": "Vehicle EMI"},
            {"main_category": "Life & Entertainment", "sub_category": "Movies & Events"},
            {"main_category": "Life & Entertainment", "sub_category": "Subscriptions"},
            {"main_category": "Financial Expenses", "sub_category": "Bank Charges"},
            {"main_category": "Investments", "sub_category": "Mutual Fund SIP"},
            {"main_category": "Income", "sub_category": "Salary"},
            {"main_category": "Shopping", "sub_category": "Uncategorized"}
        ]
        supabase.table("categories").insert(default_categories).execute()
        cat_response = supabase.table("categories").select("category_id").eq("sub_category", "Uncategorized").execute()
        if not cat_response.data:
            cat_response = supabase.table("categories").select("category_id").limit(1).execute()
            
    if not cat_response.data:
        raise HTTPException(status_code=500, detail="Default category 'Uncategorized' not found in DB.")
    default_cat_id = cat_response.data[0]["category_id"]

    # 3. Map Data and Enforce DB Constraints
    insert_data = []
    for t in transactions:
        # Convert "Credit/Debit" to DB constraint "income/expense"
        db_tx_type = "income" if t.transaction_type.lower() in ["credit", "income"] else "expense"
        
        insert_data.append({
            "user_id": user_id, 
            "account_id": account_id, 
            "category_id": default_cat_id,  # Injection fix
            "transaction_date": t.transaction_date,
            "amount": t.amount, 
            "transaction_type": db_tx_type, # Constraint fix
            "description": t.description,
            "merchant_name": t.merchant_name
        })
    
    # 4. Bulk Insert
    res = supabase.table("transactions").insert(insert_data).execute()
    
    return IngestResponse(
        success=True, 
        inserted_count=len(res.data) if res.data else 0, 
        account_id=account_id, 
        balance_change=sum(t.amount if t.transaction_type.lower() in ["credit", "income"] else -t.amount for t in transactions)
    )

# ─── API Endpoints ────────────────────────────────────────────────

@router.post("/parse", response_model=ParseStatementResponse)
async def parse_statement(request: ParseRequest):
    """Parses raw statement text into structured transactions without saving to DB."""
    txs = _parse_pdf_text_robust(request.raw_text)
    
    total_credits = sum(t.amount for t in txs if t.transaction_type.lower() in ["credit", "income"])
    total_debits = sum(t.amount for t in txs if t.transaction_type.lower() in ["debit", "expense"])
    
    return ParseStatementResponse(
        success=True,
        transactions=txs,
        file_name=request.file_name,
        total_credits=total_credits,
        total_debits=total_debits,
        net_flow=total_credits - total_debits
    )

@router.post("/ingest", response_model=IngestResponse)
async def ingest_statement(request: IngestRequest):
    """Ingests parsed statement transactions into the Supabase database."""
    return await _ingest_transactions(
        user_id=request.user_id,
        account_name=request.account_name or "Bank Statement",
        transactions=request.transactions
    )

@router.post("/parse-file", response_model=ParseStatementResponse)
async def parse_statement_file(
    file: UploadFile = File(...),
    password: Optional[str] = Form(None)
):
    """Parses a file (PDF or CSV) into structured transactions without saving to the database."""
    suffix = os.path.splitext(file.filename)[1] or ".pdf"
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
        temp.write(await file.read())
        temp_path = temp.name
        
    try:
        txs = parse_pdf_to_transactions(temp_path, password)
        if not txs:
            raise HTTPException(status_code=400, detail="Could not extract any transactions from file.")
            
        total_credits = sum(t.amount for t in txs if t.transaction_type.lower() in ["credit", "income"])
        total_debits = sum(t.amount for t in txs if t.transaction_type.lower() in ["debit", "expense"])
        
        return ParseStatementResponse(
            success=True,
            transactions=txs,
            file_name=file.filename,
            total_credits=total_credits,
            total_debits=total_debits,
            net_flow=total_credits - total_debits
        )
    except PasswordProtectedException as e:
        raise HTTPException(
            status_code=401,
            detail={"type": e.error_type, "message": str(e)}
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@router.post("/upload", response_model=IngestResponse)
async def upload_statement(
    file: UploadFile = File(...),
    user_id: str = Form(...),            # Changed to Form to accept multipart data
    account_name: str = Form("Bank Statement"),
    password: Optional[str] = Form(None)
):
    """Accepts multipart/form-data upload from React."""
    suffix = os.path.splitext(file.filename)[1] or ".pdf"
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
        temp.write(await file.read())
        temp_path = temp.name
        
    try:
        txs = parse_pdf_to_transactions(temp_path, password)
        if not txs:
            raise HTTPException(status_code=400, detail="Could not extract any transactions from file.")
            
        return await _ingest_transactions(user_id, account_name, txs)
    except PasswordProtectedException as e:
        raise HTTPException(
            status_code=401,
            detail={"type": e.error_type, "message": str(e)}
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
