"""
Enterprise-grade bank statement extraction and ingestion service.
Designed by a senior data scientist for maximum transaction capture accuracy.
"""

import re
import os
import shutil
import tempfile
from datetime import datetime
from typing import List, Optional, Tuple

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
import pdfplumber
import pytesseract
from PIL import Image
from pdf2image import convert_from_path

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


# ─── Exception ────────────────────────────────────────────────────

class PasswordProtectedException(Exception):
    def __init__(self, message: str, error_type: str):
        super().__init__(message)
        self.error_type = error_type  # "password_required" or "wrong_password"


# ─── PDF Text Extraction ──────────────────────────────────────────

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


# ─── Date & Amount Helpers ────────────────────────────────────────

_DATE_FORMATS = [
    "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%y",
    "%d %b %Y", "%d %b %y", "%d-%b-%Y", "%d-%b-%y", "%d %B %Y",
    "%m/%d/%Y", "%b %d, %Y", "%B %d, %Y",
]


def _parse_date(date_str: str) -> Optional[str]:
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
    """Parse amount string, handling both standard (1,234.56) and
    comma-decimal Indian format (22,00 → 22.00, 48,55 → 48.55)."""
    if not amount_str:
        return None
    cleaned = amount_str.strip()
    # Strip currency symbols and CR/DR suffixes
    cleaned = re.sub(r"[₹$Rs\s]", "", cleaned)
    cleaned = re.sub(r"(CR|DR|cr|dr)$", "", cleaned).strip()
    if not cleaned or cleaned in ["-", "."]:
        return None
    # Detect comma-as-decimal: ONLY when pattern is digits,2digits (e.g. 22,00 or 1234,56)
    # Distinguished from thousands separator which has 3 digits after comma (e.g. 1,234)
    if re.fullmatch(r'\d{1,9},\d{2}', cleaned):
        cleaned = cleaned.replace(',', '.')  # 22,00 → 22.00
    else:
        cleaned = cleaned.replace(',', '')   # Remove thousands separators: 1,234.56 → 1234.56
    try:
        return abs(float(cleaned))
    except (ValueError, TypeError):
        return None


# ─── Smart Merchant Name Extractor ───────────────────────────────

# Tokens that are noise (bank codes, payment rails, etc.)
_NOISE_TOKENS = {
    "UPI", "NEFT", "IMPS", "RTGS", "ATM", "POS", "INB", "MB", "IB",
    "DR", "CR", "TXN", "REF", "TRANSFER", "TRANSACTION", "PAYMENT",
    "ICICI", "ICIC", "HDFC", "SBIN", "AXIS", "KOTAK", "KVBL", "IOBA",
    "BARB", "PUNB", "UTIB", "YESB", "CNRB", "UBIN", "VIJB", "KKBK",
    "SELF", "B/F", "CASH", "DEP", "DEPOSIT", "OPENING", "CLOSING",
    "BALANCE", "BROUGHT", "FORWARD", "CHARGES", "INTEREST", "REVERSAL",
    "FAILED", "RETURN",
}

# Common UPI / NEFT description patterns to strip
_STRIP_PATTERNS = [
    re.compile(r'\bUPI\b[/-]?', re.I),
    re.compile(r'\bIMPS\b[/-]?', re.I),
    re.compile(r'\bNEFT\b[/-]?', re.I),
    re.compile(r'\bRTGS\b[/-]?', re.I),
    # UPI reference numbers (12+ digits)
    re.compile(r'\b\d{10,}\b'),
    # Account numbers (9-18 digits)
    re.compile(r'\b\d{9,18}\b'),
    # Bank IDs like ICICI0001234
    re.compile(r'\b[A-Z]{4}\d{7}\b'),
    # Timestamps like 020524 / 020524103045
    re.compile(r'\b\d{6,14}\b'),
    # @ handles in UPI IDs  e.g., "xyz@okicici"
    re.compile(r'\S+@\S+'),
    # Trailing/leading punctuation blobs
    re.compile(r'[/\-_|:]+'),
]


def _extract_merchant_name(description: str) -> str:
    """
    Extract a clean human-readable merchant/payee name from a raw
    Indian bank statement description line.

    Handles these common Indian bank formats:
      UPI  : UPI/DR/651855670828/PayeeName/BankName/vpa@bank
      UPI  : UPI-DR-651855670828-PayeeName-BankName-vpa@bank
      NEFT : NEFT/INBOUND/123456/BeneficiaryName/HDFC0001234
      IMPS : IMPS/651855670828/PayeeName/KVBL0001234
      ATM  : ATM WDR LOCATION TERMINAL
      POS  : POS TXN MERCHANT NAME
    """
    if not description:
        return "Unknown"

    raw = description.strip()

    # ── 1. UPI: extract payee between REFNO and BANK/VPA ────────────
    # Format: UPI[-/](DR|CR|P2P|P2M)[-/]REFNO[-/]PAYEE[-/]BANK[-/]VPA
    upi_payee = re.search(
        r'UPI[-/](?:DR|CR|P2P|P2M|IN|OUT)?[-/]?\d{6,}[-/]'
        r'([A-Za-z][A-Za-z0-9 .&\']{1,45}?)'
        r'(?:[-/][A-Za-z]{3,}|[-/]\d|@)',
        raw, re.I
    )
    if upi_payee:
        name = upi_payee.group(1).strip(' -/')
        if len(name) > 1 and not re.fullmatch(r'[\d\s]+', name):
            return _title(name)

    # ── 2. UPI simple: UPI/PayeeName (no ref number) ─────────────────
    upi_simple = re.search(
        r'UPI[-/]([A-Za-z][A-Za-z0-9 .&\']{2,40}?)(?:[-/]|\s+\d|$)',
        raw, re.I
    )
    if upi_simple:
        name = upi_simple.group(1).strip(' -/')
        if len(name) > 2 and name.upper() not in _NOISE_TOKENS:
            return _title(name)

    # ── 3. NEFT/IMPS: extract beneficiary name ───────────────────────
    # Format: NEFT/INBOUND/REFNO/BenefName  or  IMPS/REFNO/BenefName/IFSC
    neft_match = re.search(
        r'(?:NEFT|IMPS|RTGS)[-/](?:INBOUND[-/]|OUTBOUND[-/])?\d*[-/]?'
        r'([A-Za-z][A-Za-z0-9 .&\']{2,45}?)'
        r'(?:[-/][A-Z]{4}\d|[-/]\d{6,}|$)',
        raw, re.I
    )
    if neft_match:
        name = neft_match.group(1).strip(' -/')
        if len(name) > 2 and name.upper() not in _NOISE_TOKENS:
            return _title(name)

    # ── 4. ATM withdrawal: use location as merchant ───────────────────
    atm_match = re.search(r'ATM\s+(?:WDR|CASH)?\s*([A-Za-z][A-Za-z0-9 ]{2,30})', raw, re.I)
    if atm_match:
        return _title(f"ATM - {atm_match.group(1).strip()}")

    # ── 5. "To/From/By <Name>" ────────────────────────────────────────
    to_from = re.search(
        r'\b(?:to|from|by)\s+([A-Za-z][A-Za-z0-9 .&\']{2,40}?)'
        r'(?:\s*[-/]|\s*\d{5,}|$)',
        raw, re.I
    )
    if to_from:
        name = to_from.group(1).strip()
        if len(name) > 2 and not _is_noisy(name):
            return _title(name)

    # ── 6. Generic noise stripping ────────────────────────────────────
    cleaned = raw
    # Remove Dr-DIGITS / Cr-DIGITS reference patterns entirely
    cleaned = re.sub(r'\b(?:Dr|Cr|DR|CR)[-/]\d+', '', cleaned)
    for pat in _STRIP_PATTERNS:
        cleaned = pat.sub(' ', cleaned)

    words = cleaned.split()
    kept = []
    for w in words:
        wu = w.upper().strip('/-_')
        if wu in _NOISE_TOKENS:
            continue
        if len(wu) <= 2:
            continue
        if re.fullmatch(r'[\d,\.]+', wu):
            continue  # Skip stray numbers/amounts
        kept.append(w)

    result = re.sub(r'\s+', ' ', ' '.join(kept)).strip()
    if len(result) > 2:
        return _title(result[:50])

    # Last resort: first 40 chars, stripped of leading noise
    fallback = re.sub(r'^[\W\d]+', '', raw).strip()
    return _title(fallback[:40]) if len(fallback) > 2 else "Unknown"


def _is_noisy(name: str) -> bool:
    return name.upper().strip() in _NOISE_TOKENS


def _title(s: str) -> str:
    return s.strip().title()


# ─── Category Predictor ───────────────────────────────────────────

def _predict_category(desc: str, merchant: str) -> Tuple[str, str]:
    combined = f"{desc} {merchant}".lower()
    if any(k in combined for k in ["zerodha", "groww", "upstox", "sip", "mutual fund", "securities"]):
        return ("Investments", "Mutual Fund SIP")
    if any(k in combined for k in ["salary", "wages", "remuneration", "reimbursement"]):
        return ("Income", "Salary")
    if any(k in combined for k in ["swiggy", "zomato", "restaurant", "food", "cafe", "dining", "dominos", "pizza", "burger"]):
        return ("Food & Drinks", "Dining Out")
    if any(k in combined for k in ["grocery", "groceries", "supermarket", "blinkit", "zepto", "bigbasket", "dmart"]):
        return ("Food & Drinks", "Groceries")
    if any(k in combined for k in ["uber", "ola", "rapido", "metro", "irctc", "makemytrip", "redbus"]):
        return ("Transportation", "Cab & Auto")
    if any(k in combined for k in ["rent", "landlord", "pg stay", "housing"]):
        return ("Housing", "Rent")
    if any(k in combined for k in ["electricity", "airtel", "jio", "vodafone", "bsnl", "water bill", "recharge", "broadband"]):
        return ("Housing", "Utilities")
    if any(k in combined for k in ["netflix", "prime", "spotify", "hotstar", "subscription"]):
        return ("Life & Entertainment", "Subscriptions")
    if any(k in combined for k in ["charge", "fee", "fine", "gst", "sms alert", "annual fee"]):
        return ("Financial Expenses", "Bank Charges")
    if any(k in combined for k in ["amazon", "flipkart", "myntra", "meesho", "nykaa", "snapdeal"]):
        return ("Shopping", "Clothing & Apparel")
    return ("Shopping", "Uncategorized")


# ─── Core PDF Text Parser ─────────────────────────────────────────

_DATE_RE = re.compile(
    r'('
    r'\b\d{1,2}[-/\s]+(?:[A-Za-z]{3,9}|\d{1,2})[-/\s]+\d{2,4}\b'  # 01-Jan-2024, 01/01/24
    r'|\b\d{4}[-/\s]+\d{1,2}[-/\s]+\d{1,2}\b'                       # 2024-01-01
    r'|\b[A-Za-z]{3,9}\s+\d{1,2}\s*,\s*\d{4}\b'                     # Jan 01, 2024
    r')'
)

# Amount regex: matches standard (1,234.56) AND Indian comma-decimal (22,00 / 48,55)
# Comma-decimal rule: digits,2digits with NO following period → treated as X.XX
_AMOUNT_RE = re.compile(
    r'(?<![\d,])'
    r'(?:'
    r'[\d,]+\.\d{2}'           # Standard: 1234.56 or 1,234.56
    r'|'
    r'\d{1,9},\d{2}(?!\.)'    # Comma-decimal: 22,00  48,55  (NOT part of 1,234.56)
    r')'
    r'(?!\d)'
)

# Lines to skip (headers, footers, summaries)
_SKIP_RE = re.compile(
    r'\b(brought\s+forward|b/f|opening\s+balance|closing\s+balance|'
    r'statement\s+of|page\s+\d|printed\s+on|generated\s+on|'
    r'total\s+credit|total\s+debit|net\s+amount|account\s+summary)\b',
    re.I,
)

# Keywords indicating credit
_CREDIT_RE = re.compile(
    r'\b(cr|credit|dep|deposit|received|refund|interest\s+credit|'
    r'salary|dividend|reversal\s+cr|cashback)\b', re.I
)
_DEBIT_RE = re.compile(
    r'\b(dr|debit|wdr|withdrawal|payment|purchase|charge|fee|emi|'
    r'transfer\s+to|paid\s+to)\b', re.I
)


def _parse_pdf_text_robust(raw_text: str) -> List[ParsedTransaction]:
    """
    Stateful, line-by-line PDF text parser.

    Key design decisions (senior DS perspective):
    ─────────────────────────────────────────────
    1. Stateful accumulator  →  handles multi-line descriptions correctly.
    2. Date anchors a new transaction; amounts & type resolved per-line.
    3. Amount regex is strict (.XX only) to avoid mismatching 12-digit UPI refs.
    4. Skip-list filters out header/footer/summary lines.
    5. Debit/Credit detection: column position heuristic + keyword fallback.
    6. Merchant name extracted intelligently (not just first token).
    """
    lines = raw_text.split("\n")
    transactions: List[ParsedTransaction] = []
    current_tx: Optional[ParsedTransaction] = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if _SKIP_RE.search(line):
            continue

        date_match = _DATE_RE.search(line)

        if date_match:
            # Flush previous transaction
            if current_tx:
                transactions.append(current_tx)
                current_tx = None

            parsed_date = _parse_date(date_match.group(1))
            if not parsed_date:
                continue

            # Everything after the date on this line
            after_date = line[date_match.end():].strip()

            # Collect all amounts on the entire line
            raw_amounts = _AMOUNT_RE.findall(line)
            numeric_vals: List[float] = []
            for a in raw_amounts:
                v = _parse_amount(a)
                if v is not None:
                    numeric_vals.append(v)

            # ── Step 1: Detect type from keywords FIRST (most reliable) ──
            # Do this before amount column heuristic so we know which column to pick.
            tx_type = "Debit"  # default
            if _CREDIT_RE.search(line):
                tx_type = "Credit"
            elif _DEBIT_RE.search(line):
                tx_type = "Debit"

            # ── Step 2: Resolve amount from numeric columns ───────────
            # Indian bank layout: Debit col | Credit col | Balance col
            # Empty columns use '-' or '0.00' so regex may find 1, 2 or 3 values.
            amount: float = 0.0

            if numeric_vals:
                if len(numeric_vals) >= 3:
                    # [debit, credit, balance] — balance is last
                    debit_v, credit_v = numeric_vals[0], numeric_vals[1]
                    if tx_type == "Credit" and credit_v > 0:
                        amount = credit_v
                    elif tx_type == "Debit" and debit_v > 0:
                        amount = debit_v
                    elif credit_v > 0 and debit_v == 0:
                        amount, tx_type = credit_v, "Credit"
                    elif debit_v > 0:
                        amount = debit_v
                    else:
                        # Both columns present; take the larger (not balance)
                        amount = max(numeric_vals[:-1], default=0.0)

                elif len(numeric_vals) == 2:
                    # Could be [amount, balance] — pick first as transaction amount
                    # unless keyword says Credit and second makes more sense
                    first, second = numeric_vals[0], numeric_vals[1]
                    # Heuristic: balance is usually larger than the transaction amount
                    if first > 0 and (second == 0 or second > first * 0.1):
                        amount = first
                    else:
                        amount = second

                else:
                    # Single amount on line — that is the transaction amount
                    amount = numeric_vals[0]

            # ── Build description (strip amounts from after_date) ────
            desc = after_date
            for a in raw_amounts:
                desc = desc.replace(a, " ")
            # Strip trailing CR/DR suffixes
            desc = re.sub(r'\s+(CR|DR)\s*$', '', desc, flags=re.I)
            desc = re.sub(r'\s+', ' ', desc).strip()
            if not desc:
                desc = "Transaction"

            merchant = _extract_merchant_name(desc)

            running_balance: Optional[float] = None
            if len(numeric_vals) >= 2:
                running_balance = numeric_vals[-1]

            current_tx = ParsedTransaction(
                transaction_date=parsed_date,
                amount=amount,
                transaction_type=tx_type,
                merchant_name=merchant,
                description=desc,
                running_balance=running_balance,
            )

        else:
            # Continuation line – append to current transaction description
            if current_tx and line:
                skip_continuation = _SKIP_RE.search(line) or re.match(r'^\d+$', line)
                if not skip_continuation:
                    current_tx.description = f"{current_tx.description} {line}".strip()
                    # Re-extract merchant from enriched description
                    current_tx.merchant_name = _extract_merchant_name(current_tx.description)

    # Flush last transaction
    if current_tx:
        transactions.append(current_tx)

    return transactions


# ─── CSV Parser ───────────────────────────────────────────────────

def _parse_csv_text(raw_text: str) -> List[ParsedTransaction]:
    lines = [l.strip() for l in raw_text.strip().split("\n") if l.strip()]
    if not lines:
        return []

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
    if file_path.lower().endswith(".csv"):
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return _parse_csv_text(f.read())
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to read CSV: {e}")

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


# ─── Ingestion Logic ──────────────────────────────────────────────

async def _ingest_transactions(
    user_id: str, account_name: str, transactions: List[ParsedTransaction]
) -> IngestResponse:
    # 1. Ensure account exists
    acc_res = supabase.table("accounts").select("*").eq("user_id", user_id).eq("account_name", account_name).execute()
    if not acc_res.data:
        acc_ins = supabase.table("accounts").insert({
            "user_id": user_id, "account_name": account_name,
            "account_type": "checking", "current_balance": 0.0,
        }).execute()
        account_id = acc_ins.data[0]["account_id"]
    else:
        account_id = acc_res.data[0]["account_id"]

    # 2. Resolve default category
    cat_res = supabase.table("categories").select("category_id").eq("sub_category", "Uncategorized").execute()
    if not cat_res.data:
        _seed_default_categories()
        cat_res = supabase.table("categories").select("category_id").eq("sub_category", "Uncategorized").execute()
    if not cat_res.data:
        cat_res = supabase.table("categories").select("category_id").limit(1).execute()
    if not cat_res.data:
        raise HTTPException(status_code=500, detail="No categories found. Please seed the categories table.")

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
            "transaction_type": db_type,
            "description": t.description,
            "merchant_name": t.merchant_name,
            "running_balance": t.running_balance
        })

    res = supabase.table("transactions").insert(insert_data).execute()
    balance_change = sum(
        t.amount if t.transaction_type.lower() in ["credit", "income"] else -t.amount
        for t in transactions
    )
    return IngestResponse(
        success=True,
        inserted_count=len(res.data) if res.data else 0,
        account_id=account_id,
        balance_change=balance_change,
    )


def _seed_default_categories():
    defaults = [
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
        {"main_category": "Shopping", "sub_category": "Uncategorized"},
    ]
    supabase.table("categories").insert(defaults).execute()


# ─── API Endpoints ────────────────────────────────────────────────

@router.post("/parse", response_model=ParseStatementResponse)
async def parse_statement(request: ParseRequest):
    """Parses raw text into structured transactions (no DB write)."""
    txs = _parse_pdf_text_robust(request.raw_text)
    total_credits = sum(t.amount for t in txs if t.transaction_type.lower() in ["credit", "income"])
    total_debits = sum(t.amount for t in txs if t.transaction_type.lower() in ["debit", "expense"])
    return ParseStatementResponse(
        success=True, transactions=txs, file_name=request.file_name,
        total_credits=total_credits, total_debits=total_debits, net_flow=total_credits - total_debits,
    )


@router.post("/ingest", response_model=IngestResponse)
async def ingest_statement(request: IngestRequest):
    """Ingests pre-parsed transactions into the database."""
    return await _ingest_transactions(request.user_id, request.account_name or "Bank Statement", request.transactions)


@router.post("/parse-file", response_model=ParseStatementResponse)
async def parse_statement_file(file: UploadFile = File(...), password: Optional[str] = Form(None)):
    """Parses a PDF/CSV file into structured transactions (no DB write)."""
    suffix = os.path.splitext(file.filename)[1] or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        txs = parse_pdf_to_transactions(tmp_path, password)
        if not txs:
            raise HTTPException(status_code=400, detail="No transactions could be extracted from the file.")
        total_credits = sum(t.amount for t in txs if t.transaction_type.lower() in ["credit", "income"])
        total_debits = sum(t.amount for t in txs if t.transaction_type.lower() in ["debit", "expense"])
        return ParseStatementResponse(
            success=True, transactions=txs, file_name=file.filename,
            total_credits=total_credits, total_debits=total_debits, net_flow=total_credits - total_debits,
        )
    except PasswordProtectedException as e:
        raise HTTPException(status_code=401, detail={"type": e.error_type, "message": str(e)})
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.post("/upload", response_model=IngestResponse)
async def upload_statement(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    account_name: str = Form("Bank Statement"),
    password: Optional[str] = Form(None),
):
    """Upload a bank statement PDF/CSV and ingest all transactions into the DB."""
    suffix = os.path.splitext(file.filename)[1] or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        txs = parse_pdf_to_transactions(tmp_path, password)
        if not txs:
            raise HTTPException(status_code=400, detail="No transactions could be extracted from the file.")
        return await _ingest_transactions(user_id, account_name, txs)
    except PasswordProtectedException as e:
        raise HTTPException(status_code=401, detail={"type": e.error_type, "message": str(e)})
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)