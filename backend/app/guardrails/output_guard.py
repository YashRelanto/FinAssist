import re
import logging
from .pii_masking import PIIMasker

logger = logging.getLogger(__name__)

INVESTMENT_DISCLAIMER = (
    "\n\n---\n"
    "Disclaimer: This is general financial information, not SEBI-registered investment advice. "
    "Consult a qualified advisor before making investment decisions."
)

INVESTMENT_KEYWORDS = (
    "invest", "portfolio", "mutual fund", "sip", "stock", "equity",
    "rebalance", "asset allocation", "cagr", "nav",
)


class OutputGuard:
    """
    Validates and cleans LLM outputs before they are delivered to users to prevent leakages of system credentials or code.
    """

    SENSITIVE_PATTERNS = {
        "api_key": r'(api[_\s-]?keys?|secret[_\s-]?keys?|token)["\s:=]+[a-zA-Z0-9_-]{16,}',
        "password": r'(password|passwd|pwd)["\s:=]+\S+',
        "connection_string": r'(mongodb|postgres|mysql|sqlite|supabase):\/\/\S+',
        "jwt": r'eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+',
        "private_key": r'-----BEGIN (RSA |)PRIVATE KEY-----',
        "internal_prompt": r'(you are finassist|role boundaries|system prompt|route_to_nl2sql|nl2sql_planner_system|human-in-the-loop|knowledge strategy|safety guardrails)',
    }
    
    @staticmethod
    def detect_sensitive_leakage(response: str) -> bool:
        """
        Scan response text for unauthorized leakage of passwords, connection strings, keys, or tokens.
        """
        for leak_type, pattern in OutputGuard.SENSITIVE_PATTERNS.items():
            if re.search(pattern, response, re.IGNORECASE):
                logger.error("[SECURITY] Sensitive data leak detected in output: %s", leak_type)
                return True
        return False
    
    @staticmethod
    def detect_sql_in_response(response: str) -> bool:
        """
        Returns True if the output looks like raw SQL query instructions (which should not be shown directly).
        """
        sql_keywords = ["SELECT", "INSERT", "UPDATE", "DELETE", "DROP", "CREATE TABLE", "WHERE USER_ID ="]
        response_upper = response.upper()
        
        # Check if the output has a cluster of SQL keywords
        sql_count = sum(1 for kw in sql_keywords if kw in response_upper)
        if sql_count >= 2:
            logger.warning("[SECURITY] Raw SQL formatting detected in LLM output")
            return True
        return False
    
    @staticmethod
    def needs_investment_disclaimer(response: str) -> bool:
        lower = response.lower()
        return any(kw in lower for kw in INVESTMENT_KEYWORDS)

    @staticmethod
    def append_disclaimer_if_needed(response: str) -> str:
        if OutputGuard.needs_investment_disclaimer(response) and INVESTMENT_DISCLAIMER.strip() not in response:
            return response.rstrip() + INVESTMENT_DISCLAIMER
        return response

    @staticmethod
    def validate_and_clean(response: str, user_id: str) -> tuple[bool, str]:
        """
        Validates LLM output, masks any leftover PII, and strips or flags hazardous elements.
        Returns (is_safe, cleaned_response)
        """
        # 1. Block if highly sensitive system secrets/keys are leaked
        if OutputGuard.detect_sensitive_leakage(response):
            logger.error("[SECURITY] Blocked output due to API key or credentials leakage | user=%s", user_id)
            return False, "I apologize, but I cannot provide that information. Please contact support."
        
        # 2. Sanitize any SQL patterns by replacement rather than breaking the chat entirely
        if OutputGuard.detect_sql_in_response(response):
            logger.warning("[SECURITY] SQL code block sanitized in output | user=%s", user_id)
            response = re.sub(
                r'(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE)\s+.*?;',
                '[System Query Removed for Security]',
                response,
                flags=re.IGNORECASE
            )
            response = re.sub(
                r'SELECT\s+.*?\s+FROM\s+\S+',
                '[System Query Removed for Security]',
                response,
                flags=re.IGNORECASE
            )
            
        # 3. Mask any remaining PII in the output
        response = PIIMasker.mask_all(response)

        # 4. Append regulatory disclaimer for investment-related content
        response = OutputGuard.append_disclaimer_if_needed(response)

        return True, response
