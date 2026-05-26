from typing import Tuple, List, Dict, Any
from .input_guard import InputGuard
from .authorization import AuthorizationGuard
from .pii_masking import PIIMasker
from .output_guard import OutputGuard

class Guardrails:
    """
    Unified entry point for the FinAssist 5-Layer Security Guardrails system.
    """
    
    @staticmethod
    def validate_input(message: str, user_id: str) -> Tuple[bool, str]:
        """
        LAYER 1: INPUT GUARDRAILS
        Validates the incoming user query. Returns (is_safe, error_message_if_blocked).
        """
        return InputGuard.validate(message, user_id)
        
    @staticmethod
    def validate_sql_query(sql_query: str, user_id: str) -> bool:
        """
        LAYER 2: AUTHORIZATION (SQL validation context)
        Ensures the query only targets the specified user's assets.
        """
        return AuthorizationGuard.validate_query_context(user_id, sql_query)
        
    @staticmethod
    def mask_context_data(transactions: List[Dict[str, Any]], user_id: str) -> List[Dict[str, Any]]:
        """
        LAYER 3: DATA RETRIEVAL / CONTEXT MASKING (PII Masking)
        Filters context to user-owned rows only, and scrubs sensitive Indian PII identifiers.
        """
        # Ensure strict database-level filtering is reinforced
        user_rows = [t for t in transactions if str(t.get("user_id")) == str(user_id)]
        return PIIMasker.mask_transaction_data(user_rows)
        
    @staticmethod
    def validate_output(response: str, user_id: str) -> Tuple[bool, str]:
        """
        LAYER 4: OUTPUT GUARDRAILS
        Ensures the AI advisor answer does not leak system configs, connection credentials, 
        or raw database scripts, and scrubs any residual PII.
        Returns (is_safe, cleaned_response).
        """
        return OutputGuard.validate_and_clean(response, user_id)
