from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class ParsedTransaction(BaseModel):
    transaction_date: str          # Format: YYYY-MM-DD
    amount: float                  # Always positive magnitude
    transaction_type: str          # "income" or "expense" or "transfer"
    description: str               # Raw narrative description
    merchant_name: str             # Cleaned/extracted merchant name
    normalized_merchant: Optional[str] = None # Standardized merchant name from master database
    running_balance: Optional[float] = None
    category_id: Optional[str] = None # UUID resolved from database
    category_name: Optional[str] = None # Standard presentation category name (e.g. 'Others')

class AccountMetadata(BaseModel):
    bank_name: str
    account_holder: str
    account_number: str
    ifsc: str
    statement_period: Optional[str] = None

class JobProgress(BaseModel):
    job_id: str
    statement_id: str
    status: str                    # PENDING, PROCESSING, COMPLETED, FAILED
    progress: int                  # 0 to 100
    error_message: Optional[str] = None
    updated_at: datetime
