import re

class PIIMasker:
    """
    Masks PII in both inputs to LLMs and outputs from LLMs, focusing heavily on Indian PII formats.
    """
    
    PATTERNS = {
        "phone": r'\b[6-9]\d{9}\b',                                            # Indian mobile numbers
        "pan": r'\b[A-Z]{5}[0-9]{4}[A-Z]\b',                                  # PAN Card
        "aadhaar": r'\b\d{4}[\s-]\d{4}[\s-]\d{4}\b',                              # Aadhaar Card
        "account_number": r'\b\d{9,18}\b',                                    # Bank account numbers
        "ifsc": r'\b[A-Z]{4}0[A-Z0-9]{6}\b',                                  # IFSC Codes
        "credit_card": r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',         # Credit cards
        "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',      # Email addresses
        "upi": r'\b[a-zA-Z0-9.-]+@[a-zA-Z0-9.-]+\b',                          # UPI ID (virtual payment addresses)
    }
    
    @staticmethod
    def mask_string(text: str, pii_type: str) -> str:
        """
        Masks a specific type of PII in the given text.
        """
        pattern = PIIMasker.PATTERNS.get(pii_type)
        if not pattern:
            return text
        
        def mask_match(match):
            value = match.group(0)
            if pii_type == "phone":
                return f"******{value[-4:]}"  # Mask all except last 4
            elif pii_type == "account_number":
                return f"****{value[-4:]}"    # Mask all except last 4
            elif pii_type == "credit_card":
                clean_value = re.sub(r'[\s-]', '', value)
                return f"XXXX-XXXX-XXXX-{clean_value[-4:]}"
            elif pii_type == "email":
                parts = value.split('@')
                name = parts[0]
                domain = parts[1]
                masked_name = f"{name[:2]}***" if len(name) > 2 else "***"
                return f"{masked_name}@{domain}"
            elif pii_type == "upi":
                parts = value.split('@')
                user = parts[0]
                handle = parts[1]
                masked_user = f"{user[:2]}***" if len(user) > 2 else "***"
                return f"{masked_user}@{handle}"
            else:
                return "***MASKED***"
        
        return re.sub(pattern, mask_match, text)
    
    @staticmethod
    def mask_all(text: str) -> str:
        """
        Masks all recognized types of PII in the given text.
        """
        for pii_type in PIIMasker.PATTERNS.keys():
            text = PIIMasker.mask_string(text, pii_type)
        return text
    
