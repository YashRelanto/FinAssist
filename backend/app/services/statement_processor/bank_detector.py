import re
from .bank_configs import BANK_CONFIGS

class BankDetector:
    """
    Case-insensitive detection of the source bank from the statement's text content.
    Matches landmarks, logos, IFSC prefixes, and known keywords.
    """
    
    # IFSC prefix mappings
    IFSC_MAP = {
        "HDFC": "HDFC",
        "ICIC": "ICICI",
        "SBIN": "SBI",
        "UTIB": "AXIS",
        "KKBK": "KOTAK",
        "KVBL": "KVB",
        "BARB": "BOB"
    }

    @classmethod
    def detect_bank(cls, text: str) -> str:
        """
        Scans statement text to classify the originating bank.
        Returns HDFC, ICICI, SBI, AXIS, KOTAK, or GENERIC.
        """
        if not text:
            return "GENERIC"
            
        text_lower = text.lower()
        
        # ─── 1. Check Config Signatures ───
        for bank_id, config in BANK_CONFIGS.items():
            for signature in config.get("signatures", []):
                matched = re.search(signature, text_lower)
                if matched:
                    return bank_id
                    
        # ─── 2. Check IFSC Prefixes ───
        ifsc_matches = re.findall(r"\b([A-Z]{4})0[A-Z0-9]{6}\b", text.upper())
        for prefix in ifsc_matches:
            if prefix in cls.IFSC_MAP:
                return cls.IFSC_MAP[prefix]
                
        # ─── 3. Check Known Header Combinations ───
        if "customer id" in text_lower and "hdfc" in text_lower:
            return "HDFC"
        if "corporate office" in text_lower and "icici" in text_lower:
            return "ICICI"
        if "cif no" in text_lower or "ifs code" in text_lower and "sbi" in text_lower:
            return "SBI"
            
        return "GENERIC"
