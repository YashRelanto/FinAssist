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
import sys

# ─── Self-Healing Windows Poppler Path Loader ──────────────────────
if sys.platform.startswith("win"):
    import glob
    downloads_dir = os.path.expandvars(r"%USERPROFILE%\Downloads")
    
    # Dynamic search for extracted poppler installations in downloads or program files
    candidates = (
        glob.glob(os.path.join(downloads_dir, "**/Library/bin"), recursive=True) +
        glob.glob(os.path.join(downloads_dir, "**/poppler*/bin"), recursive=True) +
        glob.glob(r"C:\Program Files\**/Library/bin", recursive=True) +
        glob.glob(r"C:\Program Files\**/poppler*/bin", recursive=True)
    )
    
    POPPLER_CANDIDATE_PATHS = [
        r"C:\Program Files\poppler\bin",
        r"C:\Program Files\poppler\Library\bin",
        r"C:\poppler\bin",
        r"C:\ProgramData\chocolatey\bin",
        r"C:\ProgramData\chocolatey\lib\poppler\tools\bin",
        r"C:\msys64\mingw64\bin",
    ] + candidates
    
    for path in POPPLER_CANDIDATE_PATHS:
        if os.path.isdir(path) and path not in os.environ["PATH"]:
            os.environ["PATH"] += os.pathsep + path

router = APIRouter(prefix="/api/statement", tags=["Statement Parser"])

# ─── Pydantic Models ──────────────────────────────────────────────

class ParsedTransaction(BaseModel):
    transaction_date: str                  # YYYY-MM-DD
    amount: float                          # Always positive
    transaction_type: str                  # "Credit" or "Debit"
    merchant_name: Optional[str] = None    
    description: str                       
    running_balance: Optional[float] = None
    category: Optional[str] = None
    sub_category: Optional[str] = None

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
        # ─── FIRST PASS: Explicit Pure-Python Encryption Detection ───
        try:
            import pypdf
            reader = pypdf.PdfReader(file_path)
            if reader.is_encrypted:
                if not password:
                    raise PasswordProtectedException("Password required to open PDF.", "password_required")
        except PasswordProtectedException:
            raise
        except Exception:
            pass

        # ─── 1. Try PyMuPDF (fitz) for Digital Extraction (Super Robust & Fast) ───
        # ─── 1. Try PyMuPDF (fitz) for Digital Extraction (Super Robust & Fast) ───
        try:
            import fitz
            with fitz.open(file_path) as doc:
                if doc.is_encrypted:
                    if password:
                        auth_res = doc.authenticate(password)
                        if not auth_res:
                            raise PasswordProtectedException("Incorrect PDF password.", "wrong_password")
                    else:
                        raise PasswordProtectedException("Password required to open PDF.", "password_required")
                
                text = ""
                for page in doc:
                    text += page.get_text() or ""
                if text.strip():
                    return text
        except PasswordProtectedException:
            raise
        except Exception:
            pass

        # ─── 2. Try pdfplumber for Digital Extraction ───
        try:
            with pdfplumber.open(file_path, password=password) as pdf:
                text = ""
                for page in pdf.pages:
                    text += page.extract_text() or ""
                if text.strip():
                    return text
        except Exception as e_plumber:
            from pdfminer.pdfdocument import PDFPasswordIncorrect, PDFEncryptionError
            err_msg = str(e_plumber).lower()
            is_password_err = isinstance(e_plumber, (PDFPasswordIncorrect, PDFEncryptionError)) or any(
                k in err_msg for k in ["password", "encrypted", "authenticate", "passphrase"]
            )
            if is_password_err:
                err_type = "wrong_password" if password else "password_required"
                raise PasswordProtectedException(f"PDF password error: {e_plumber}", err_type)
            pass

        # ─── 3. Try pypdf for Digital Extraction ───
        try:
            import pypdf
            reader = pypdf.PdfReader(file_path)
            if reader.is_encrypted:
                if password:
                    res = reader.decrypt(password)
                    if res == 0:
                        raise PasswordProtectedException("Incorrect PDF password.", "wrong_password")
                else:
                    raise PasswordProtectedException("Password required to open PDF.", "password_required")
            
            text = ""
            for page in reader.pages:
                text += page.extract_text() or ""
            if text.strip():
                return text
        except PasswordProtectedException:
            raise
        except Exception:
            pass

        # ─── 4. Fallback to OCR using PyMuPDF + pytesseract (NO POPPLER REQUIRED!) ───
        try:
            import fitz
            from PIL import Image
            with fitz.open(file_path) as doc:
                if doc.is_encrypted:
                    if password:
                        doc.authenticate(password)
                    else:
                        raise PasswordProtectedException("PDF is password-protected.", "password_required")
                
                text = ""
                for page in doc:
                    pix = page.get_pixmap()
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    text += pytesseract.image_to_string(img)
                if text.strip():
                    return text
        except PasswordProtectedException:
            raise
        except Exception:
            pass

        # ─── 5. Friendly Warning Fallback ───
        raise HTTPException(
            status_code=400,
            detail="FinAssist currently requires standard digital statement PDFs (with selectable text) or CSV files for secure and accurate ledger ingestion. Scanned/image statement PDFs are not supported."
        )

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
    
    # Try to find specific credit/debit columns
    credit_col = next((i for i, h in enumerate(headers) if any(k in h for k in ["credit", "deposit", "inflow", "received"])), None)
    debit_col = next((i for i, h in enumerate(headers) if any(k in h for k in ["debit", "withdrawal", "outflow", "spent"])), None)
    
    amt_col = next((i for i, h in enumerate(headers) if "amt" in h or "amount" in h), 2)
    type_col = next((i for i, h in enumerate(headers) if "type" in h), None)
    
    for line in lines[header_idx + 1:]:
        import csv
        try:
            parts = next(csv.reader([line]))
        except Exception:
            parts = [p.strip() for p in line.split(",")]
            
        if not parts:
            continue
            
        date = _parse_date(parts[date_col]) if len(parts) > date_col else None
        if not date:
            continue
            
        desc = parts[desc_col] if len(parts) > desc_col else "Transaction"
        
        amt = None
        tx_type = "Debit"
        
        if credit_col is not None and debit_col is not None:
            cr_val = parts[credit_col] if len(parts) > credit_col else ""
            dr_val = parts[debit_col] if len(parts) > debit_col else ""
            cr_amt = _parse_amount(cr_val)
            dr_amt = _parse_amount(dr_val)
            
            if cr_amt is not None and cr_amt > 0:
                amt = cr_amt
                tx_type = "Credit"
            elif dr_amt is not None and dr_amt > 0:
                amt = dr_amt
                tx_type = "Debit"
                
        if amt is None:
            val = parts[amt_col] if len(parts) > amt_col else ""
            amt = _parse_amount(val)
            if amt is not None:
                if val.strip().startswith("-"):
                    tx_type = "Debit"
                elif "+" in val:
                    tx_type = "Credit"
                elif type_col is not None and len(parts) > type_col:
                    t_val = parts[type_col].lower()
                    if any(k in t_val for k in ["cr", "credit", "in"]):
                        tx_type = "Credit"
                    else:
                        tx_type = "Debit"
                else:
                    lower_line = line.lower()
                    if any(kw in lower_line for kw in ["cr", "credit", "dep", "deposit", "received", "refund"]):
                        tx_type = "Credit"
                    else:
                        tx_type = "Debit"
                        
        if date and amt is not None:
            transactions.append(ParsedTransaction(
                transaction_date=date,
                amount=amt,
                transaction_type=tx_type,
                merchant_name=desc[:50] if len(desc) > 50 else desc,
                description=desc,
                running_balance=None
            ))
    return transactions

_MONTHS_MAP = {"jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06", "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12"}
def _parse_date_sequential(date_str: str) -> str:
    date_str = date_str.strip()
    m = re.match(r'^(\d{1,2})-([A-Za-z]{3})-(\d{4})$', date_str, re.IGNORECASE)
    if m:
        day = f"{int(m.group(1)):02d}"
        mon = _MONTHS_MAP.get(m.group(2).lower(), "01")
        yr = m.group(3)
        return f"{yr}-{mon}-{day}"
    return date_str

def _parse_pdf_text_robust(raw_text: str) -> List[ParsedTransaction]:
    lines = [l.strip() for l in raw_text.strip().split("\n") if l.strip()]
    
    # ─── PARSER 1: Sequential Columnar Block Parser (e.g. HDFC, Paytm Bank statements) ───
    sequential_txs = []
    date_regex = re.compile(
        r'^(\b\d{1,2}[-/\s]+(?:[A-Za-z]{3,9}|\d{1,2})[-/\s]+\d{2,4}\b)$',
        re.IGNORECASE
    )
    time_regex = re.compile(r'^\d{2}:\d{2}:\d{2}$')
    
    i = 0
    n = len(lines)
    
    while i < n:
        line = lines[i]
        date_match = date_regex.match(line)
        
        if date_match:
            txn_date_str = date_match.group(1)
            parsed_date = _parse_date_sequential(txn_date_str)
            
            has_time = False
            if i + 1 < n and time_regex.match(lines[i+1]):
                has_time = True
                
            val_date_idx = i + 2 if has_time else i + 1
            if val_date_idx < n and date_regex.match(lines[val_date_idx]):
                idx = val_date_idx + 1
                tokens = []
                while idx < n:
                    l = lines[idx]
                    if date_regex.match(l) and (idx + 1 >= n or time_regex.match(lines[idx+1]) or date_regex.match(lines[idx+1]) or idx + 2 >= n or date_regex.match(lines[idx+2])):
                        break
                    if l.lower() in ["account summary", "current balance", "note:", "this is a computer-generated", "account statement"]:
                        break
                    tokens.append(l)
                    idx += 1
                
                if len(tokens) >= 3:
                    balance_tok = tokens[-1]
                    credit_tok = tokens[-2]
                    debit_tok = tokens[-3]
                    
                    debit = _parse_amount(debit_tok) if debit_tok != "-" else 0.0
                    credit = _parse_amount(credit_tok) if credit_tok != "-" else 0.0
                    balance = _parse_amount(balance_tok)
                    
                    desc_tokens = tokens[:-3]
                    ref_no = ""
                    if len(desc_tokens) > 0:
                        last_tok = desc_tokens[-1]
                        if re.match(r'^\d{12,13}$', last_tok) or last_tok == "-":
                            ref_no = last_tok
                            desc_tokens = desc_tokens[:-1]
                            
                    description = " ".join(desc_tokens).strip()
                    
                    if "B/F" not in description and description.lower() != "balance forward":
                        if credit and credit > 0:
                            amount = credit
                            tx_type = "Credit"
                        else:
                            amount = -debit if debit else 0.0
                            tx_type = "Debit"
                            
                        if (debit and debit > 0) or (credit and credit > 0):
                            sequential_txs.append(ParsedTransaction(
                                transaction_date=parsed_date,
                                amount=abs(amount),
                                transaction_type=tx_type,
                                merchant_name=description[:50] if len(description) > 50 else description,
                                description=description,
                                running_balance=balance
                            ))
                i = idx
                continue
        i += 1
        
    if sequential_txs:
        return sequential_txs

    # ─── PARSER 2: Flat Single-Line Regex Parser (Fallback) ───
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
        
        amount_pattern = re.compile(r'[-+]?\s*[\d,]+\.\d{2}\b')
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
    
    print("\n--- DEBUG EXTRACTED PDF TEXT START ---")
    print(raw_text[:3000])
    print("--- DEBUG EXTRACTED PDF TEXT END ---\n")
    
    txs = _parse_pdf_text_robust(raw_text)
    
    print(f"\n--- DEBUG PARSED TRANSACTIONS COUNT: {len(txs)} ---")
    for idx, tx in enumerate(txs[:10]):
        print(f"[{idx}] Date: {tx.transaction_date} | Amount: {tx.amount} | Type: {tx.transaction_type} | Desc: {tx.description}")
    print("--- DEBUG PARSED TRANSACTIONS END ---\n")
    
    return txs


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

    # Fetch all categories to map them dynamically
    cats_db = supabase.table("categories").select("*").execute()
    cat_lookup = {}
    main_cat_lookup = {}
    if cats_db.data:
        for c in cats_db.data:
            m_cat = c.get("main_category", "").lower().strip() if c.get("main_category") else ""
            s_cat = c.get("sub_category", "").lower().strip() if c.get("sub_category") else ""
            c_id = c.get("category_id")
            if m_cat and s_cat:
                cat_lookup[(m_cat, s_cat)] = c_id
            if m_cat and m_cat not in main_cat_lookup:
                main_cat_lookup[m_cat] = c_id

    # 3. Map Data and Enforce DB Constraints
    insert_data = []
    for t in transactions:
        # Convert "Credit/Debit" to DB constraint "income/expense"
        db_tx_type = "income" if t.transaction_type.lower() in ["credit", "income"] else "expense"
        
        # Resolve category dynamically
        category_id = default_cat_id
        t_cat = (t.category or "").lower().strip() if t.category else ""
        t_sub = (t.sub_category or "").lower().strip() if t.sub_category else ""
        
        if t_cat and t_sub and (t_cat, t_sub) in cat_lookup:
            category_id = cat_lookup[(t_cat, t_sub)]
        elif t_cat and t_cat in main_cat_lookup:
            category_id = main_cat_lookup[t_cat]
        elif t_sub:
            for (m, s), c_id in cat_lookup.items():
                if s == t_sub:
                    category_id = c_id
                    break
                    
        insert_data.append({
            "user_id": user_id, 
            "account_id": account_id, 
            "category_id": category_id,
            "transaction_date": t.transaction_date,
            "amount": t.amount, 
            "transaction_type": db_tx_type, # Constraint fix
            "description": t.description,
            "merchant_name": t.merchant_name,
            "running_balance": t.running_balance
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
        import traceback
        traceback.print_exc()
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
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
