import re
from typing import Dict, List, Optional, Any
from app.utils.supabase_client import supabase

class MerchantNormalizer:
    """
    Strips banking noise (reference numbers, UPI VPAs, payment rails) and normalizes
    merchant names using rule mappings and database-backed fuzzy similarity matching.
    """

    # Static pattern noise cleaners
    _NOISE_PATTERNS = [
        re.compile(r"\bUPI\b[/-]?", re.I),
        re.compile(r"\bIMPS\b[/-]?", re.I),
        re.compile(r"\bNEFT\b[/-]?", re.I),
        re.compile(r"\bRTGS\b[/-]?", re.I),
        re.compile(r"\b\d{10,18}\b"),                       # UPI refs / long IDs
        re.compile(r"\b[A-Z]{4}\d{7}\b", re.I),             # Bank IFSC/branch keys
        re.compile(r"\b\d{6,14}\b"),                        # Timestamps/stray sequences
        re.compile(r"\S+@\S+"),                             # UPI VPA handles (e.g. xyz@okicici)
        re.compile(r"[/\-_|:]+"),                           # Punctuation dividers
    ]

    _STATIC_RULES = {
        r".*AMAZON.*": "AMAZON",
        r".*AMZN.*": "AMAZON",
        r".*SWIGGY.*": "SWIGGY",
        r".*ZOMATO.*": "ZOMATO",
        r".*UBER.*": "UBER",
        r".*OLA\s*CABS.*": "OLA",
        r".*OLA.*": "OLA",
        r".*NETFLIX.*": "NETFLIX",
        r".*SPOTIFY.*": "SPOTIFY",
        r".*AIRTEL.*": "AIRTEL",
        r".*JIO.*": "JIO",
        r".*ZEPTO.*": "ZEPTO",
        r".*BLINKIT.*": "BLINKIT",
        r".*BIGBASKET.*": "BIGBASKET",
        r".*DMART.*": "DMART",
        r".*GROWW.*": "GROWW",
        r".*ZERODHA.*": "ZERODHA",
        r".*PAYTM.*": "PAYTM",
        r".*PHONEPE.*": "PHONEPE",
        r".*GPAY.*": "GPAY",
        r".*CRED.*": "CRED",
    }

    @classmethod
    def clean_description(cls, description: str) -> str:
        """
        Removes reference numbers, payment channel noise, and returns a clean payee label.
        """
        if not description:
            return "UNKNOWN"
            
        cleaned = description.strip()
        
        # 1. Clean explicit UPI structures (UPI/DR/RefNo/Payee/Bank/VPA)
        upi_match = re.search(
            r"UPI[-/](?:DR|CR|P2P|P2M|IN|OUT)?[-/]?\d{6,}[-/]([A-Za-z0-9 .&\']{2,45}?)",
            cleaned,
            re.I
        )
        if upi_match:
            candidate = upi_match.group(1).strip(" -/")
            if len(candidate) > 2 and not candidate.isdigit():
                return candidate.upper()

        # 2. General cleanup using regex patterns
        for pat in cls._NOISE_PATTERNS:
            cleaned = pat.sub(" ", cleaned)
            
        # Clean white space
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        
        # Strip currency symbols and numbers from start/end
        cleaned = re.sub(r"^(?:rs|usd|inr|[\$\u20B9\s,\.-])+", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s+(?:cr|dr|dr\.|cr\.)$", "", cleaned, flags=re.I)
        
        # Keep only letters, numbers, and basic spacing
        cleaned = "".join(c for c in cleaned if c.isalnum() or c.isspace())
        
        return cleaned.strip().upper()

    @classmethod
    def normalize_merchant(cls, raw_desc: str, user_id: Optional[str] = None, db_merchants: Optional[List[Dict[str, Any]]] = None) -> str:
        """
        Main entry point for normalising a transaction merchant.
        """
        if not raw_desc:
            return "UNKNOWN"
            
        # 1. Match inline static pattern rule dictionary on raw description first
        for pattern, normalized in cls._STATIC_RULES.items():
            if re.match(pattern, raw_desc, re.I):
                return normalized

        cleaned = cls.clean_description(raw_desc)
        if not cleaned or cleaned in ["-", "."]:
            return "UNKNOWN"

        # 2. Check supabase merchant master fuzzy records
        try:
            merchants_list = db_merchants
            if merchants_list is None:
                db_res = supabase.table("merchant_master").select("merchant_name, normalized_name").execute()
                merchants_list = db_res.data if db_res else []

            if merchants_list:
                # Attempt to use RapidFuzz if present, otherwise fall back to simple substring contains
                try:
                    from rapidfuzz import fuzz
                    best_match = None
                    best_score = 0.0
                    
                    for row in merchants_list:
                        m_name = row["merchant_name"].upper()
                        score = fuzz.token_sort_ratio(cleaned, m_name)
                        if score > best_score:
                            best_score = score
                            best_match = row["normalized_name"]
                            
                    if best_score > 85.0:
                        return best_match.upper()
                except ImportError:
                    # Self-healing fallback: substring contains matching
                    for row in merchants_list:
                        m_name = row["merchant_name"].upper()
                        if m_name in cleaned or cleaned in m_name:
                            return row["normalized_name"].upper()
        except Exception as e:
            print(f"Supabase merchant_master query failed: {e}")

        # Fallback to presenting the cleaned description as the normalized merchant
        return cleaned
