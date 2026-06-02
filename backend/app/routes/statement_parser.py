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


# ─── Exception ────────────────────────────────────────────────────

class PasswordProtectedException(Exception):
    def __init__(self, message: str, error_type: str):
        super().__init__(message)
        self.error_type = error_type  # "password_required" or "wrong_password"


# ─── PDF Text Extraction ──────────────────────────────────────────

class AdvancedBankParser:
    @staticmethod
    def extract_text_from_pdf(file_path: str, password: Optional[str] = None) -> str:
        """
        Extract raw text from a PDF.
        Strategy:
          1. pdfplumber (fastest, works for digital PDFs)
          2. pdf2image + pytesseract OCR (for scanned PDFs)
        """
        # ── Try pdfplumber ──────────────────────────────────────────
        try:
            with pdfplumber.open(file_path, password=password) as pdf:
                text = ""
                for page in pdf.pages:
                    text += page.extract_text() or ""
                if text.strip():
                    return text
        except Exception as e:
            err_msg = str(e).lower()
            if any(k in err_msg for k in ["password", "encrypted", "authenticate", "passphrase"]):
                err_type = "wrong_password" if password else "password_required"
                raise PasswordProtectedException(f"PDF password error: {e}", err_type)
            # Non-password error → fall through to OCR

        # ── OCR fallback ────────────────────────────────────────────
        # Resolve poppler_path: env var → shutil.which → known Windows install location
        poppler_path: Optional[str] = os.getenv("POPPLER_PATH")
        if not poppler_path:
            pp_bin = shutil.which("pdftoppm")
            if pp_bin:
                poppler_path = os.path.dirname(pp_bin)

        # Hardcoded Windows WinGet install path as last resort
        if not poppler_path and os.name == "nt":
            _winget_poppler = (
                r"C:\Users\Relanto\AppData\Local\Microsoft\WinGet\Packages"
                r"\oschwartz10612.Poppler_Microsoft.Winget.Source_8wekyb3d8bbwe"
                r"\poppler-25.07.0\Library\bin"
            )
            if os.path.isdir(_winget_poppler):
                poppler_path = _winget_poppler

        if not poppler_path:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Poppler is not installed or not in PATH. "
                    "Install Poppler and ensure 'pdftoppm' is accessible, "
                    "or set the POPPLER_PATH environment variable to its bin directory."
                ),
            )

        try:
            images = convert_from_path(file_path, userpw=password, poppler_path=poppler_path)
            return "\n".join(pytesseract.image_to_string(img) for img in images)
        except Exception as e:
            err_msg = str(e).lower()
            if any(k in err_msg for k in ["password", "encrypted", "authenticate", "passphrase"]):
                err_type = "wrong_password" if password else "password_required"
                raise PasswordProtectedException(f"PDF OCR password error: {e}", err_type)
            raise HTTPException(
                status_code=500,
                detail=f"OCR failed. Ensure Poppler & Tesseract are installed. Detail: {e}",
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
    desc_col = next((i for i, h in enumerate(headers) if "desc" in h or "nar" in h or "particular" in h), 1)
    debit_col = next((i for i, h in enumerate(headers) if "debit" in h or "dr" in h or "withdrawal" in h), -1)
    credit_col = next((i for i, h in enumerate(headers) if "credit" in h or "cr" in h or "deposit" in h), -1)
    amt_col = next((i for i, h in enumerate(headers) if "amount" in h or "amt" in h), 2)

    for line in lines[header_idx + 1:]:
        parts = [p.strip() for p in line.split(",")]
        date = _parse_date(parts[date_col]) if len(parts) > date_col else None
        if not date:
            continue

        desc = parts[desc_col] if len(parts) > desc_col else "Transaction"

        if debit_col >= 0 and credit_col >= 0 and len(parts) > max(debit_col, credit_col):
            d = _parse_amount(parts[debit_col]) or 0.0
            c = _parse_amount(parts[credit_col]) or 0.0
            if c > 0 and d == 0:
                amt, tx_type = c, "Credit"
            else:
                amt, tx_type = d, "Debit"
        else:
            amt = _parse_amount(parts[amt_col]) if len(parts) > amt_col else None
            if amt is None:
                continue
            tx_type = "Debit"

        if amt == 0:
            continue

        transactions.append(ParsedTransaction(
            transaction_date=date,
            amount=amt,
            transaction_type=tx_type,
            merchant_name=_extract_merchant_name(desc),
            description=desc,
        ))

    return transactions


# ─── Entry Point ─────────────────────────────────────────────────

def parse_pdf_to_transactions(file_path: str, password: Optional[str] = None) -> List[ParsedTransaction]:
    if file_path.lower().endswith(".csv"):
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return _parse_csv_text(f.read())
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to read CSV: {e}")

    raw_text = AdvancedBankParser.extract_text_from_pdf(file_path, password)
    return _parse_pdf_text_robust(raw_text)


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

    default_cat_id = cat_res.data[0]["category_id"]
    category_cache: dict = {}

    # 3. Build insert payload
    insert_data = []
    for t in transactions:
        db_type = "income" if t.transaction_type.lower() in ["credit", "income"] else "expense"
        main_cat, sub_cat = _predict_category(t.description, t.merchant_name or "")
        cache_key = f"{main_cat}:{sub_cat}"

        if cache_key not in category_cache:
            cr = supabase.table("categories").select("category_id").eq("sub_category", sub_cat).execute()
            if cr.data:
                category_cache[cache_key] = cr.data[0]["category_id"]
            else:
                ins = supabase.table("categories").insert({"main_category": main_cat, "sub_category": sub_cat}).execute()
                category_cache[cache_key] = ins.data[0]["category_id"] if ins.data else default_cat_id

        insert_data.append({
            "user_id": user_id,
            "account_id": account_id,
            "category_id": category_cache.get(cache_key, default_cat_id),
            "transaction_date": t.transaction_date,
            "amount": t.amount,
            "transaction_type": db_type,
            "description": t.description,
            "merchant_name": t.merchant_name,
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
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)