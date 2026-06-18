import re
from .models import AccountMetadata
from .bank_configs import BANK_CONFIGS

class AccountExtractor:
    """
    Extracts bank account metadata (holder, account number, IFSC, bank name)
    from extracted raw statement text.
    """

    @classmethod
    def extract_account_details(cls, text: str, detected_bank: str) -> AccountMetadata:
        """
        Parses raw text to collect account details.
        Uses regex patterns tuned to standard banking schemas.
        """
        text_lines = [line.strip() for line in text.split("\n") if line.strip()]
        text_full = "\n".join(text_lines)

        # Retrieve configurations if available
        config = BANK_CONFIGS.get(detected_bank, {})

        # 1. Resolve Bank Name
        bank_name = config.get("bank_name", detected_bank.upper())
        if bank_name == "GENERIC":
            bank_name = "BANK STATEMENT"

        # 2. Extract IFSC Code
        ifsc = "UNKNOWN"
        ifsc_match = re.search(r"\b([A-Z]{4})0([A-Z0-9]{6})\b", text_full.upper())
        if ifsc_match:
            ifsc = ifsc_match.group(0)

        # 3. Extract Account Number
        account_number = "UNKNOWN"
        # Try custom configuration patterns first
        for idx, pat in enumerate(config.get("account_number_patterns", [])):
            acc_match = re.search(pat, text_full, re.IGNORECASE)
            if acc_match:
                account_number = acc_match.group(1).strip()
                break
        
        # If not found, use standard check
        if account_number == "UNKNOWN":
            acc_matches = re.findall(
                r"\b(?:account|acc|a/c|acct|number|no\.?)\b\s*[\-:：]?\s*([0-9Xx\*]{9,18})\b",
                text_full,
                re.IGNORECASE
            )
            if acc_matches:
                account_number = acc_matches[0]
            else:
                digits_matches = re.findall(r"\b(\d{11,16})\b", text_full)
                if digits_matches:
                    account_number = digits_matches[0]

        # 4. Extract Account Holder Name
        account_holder = "UNKNOWN"
        
        # Try custom configuration patterns first
        for idx, pat in enumerate(config.get("account_holder_patterns", [])):
            name_match = re.search(pat, text_full, re.IGNORECASE)
            if name_match:
                candidate = name_match.group(1).strip()
                invalid_keywords = ["statement", "number", "date", "address", "branch", "summary"]
                has_invalid = any(k in candidate.lower() for k in invalid_keywords)
                if not has_invalid:
                    account_holder = candidate
                    break
                    
        # Fallback to standard check
        if account_holder == "UNKNOWN":
            name_patterns = [
                r"\b(?:account\s+holder|customer\s+name|name\s+of\s+account\s+holder|name)\b\s*[\-:：]?\s*([A-Za-z\s\.]{3,40})",
                r"\b(?:mr|ms|m/s|dr)\.?\s+([A-Za-z\s\.]{3,40})"
            ]
            
            for idx, pat in enumerate(name_patterns):
                name_match = re.search(pat, text_full, re.IGNORECASE)
                if name_match:
                    candidate = name_match.group(1).strip()
                    invalid_keywords = ["statement", "number", "date", "address", "branch", "summary"]
                    has_invalid = any(k in candidate.lower() for k in invalid_keywords)
                    if not has_invalid:
                        account_holder = candidate
                        break
        
        if account_holder == "UNKNOWN" and text_lines:
            # Fallback to the first line or line after logo
            for line in text_lines[:6]:
                has_invalid = any(kw in line.lower() for kw in ["statement", "summary", "page", "account", "bank", "kotak"])
                matched_alpha = re.match(r"^[A-Za-z\s\.\']{3,35}$", line)
                if has_invalid:
                    continue
                # If the line consists of words, it's a good candidate for holder name
                if matched_alpha:
                    account_holder = line.strip()
                    break
 
        # Clean fields
        account_holder = account_holder.replace("\r", "").strip().title()
        account_number = account_number.replace("\r", "").strip()
        ifsc = ifsc.strip().upper()

        return AccountMetadata(
            bank_name=bank_name,
            account_holder=account_holder if account_holder else "Valued Customer",
            account_number=account_number if account_number else "XXXXXX",
            ifsc=ifsc
        )
