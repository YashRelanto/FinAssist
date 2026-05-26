import re
import logging

logger = logging.getLogger(__name__)

class AuthorizationGuard:
    """
    Ensures users can only access their own data and enforces strict SQL query safety.
    """
    
    @staticmethod
    def validate_data_access(
        requesting_user_id: str,
        data_owner_user_id: str,
        data_type: str
    ) -> bool:
        """
        Check if requesting_user_id is allowed to access data owned by data_owner_user_id.
        """
        if requesting_user_id != data_owner_user_id:
            logger.error(
                "[SECURITY] Unauthorized data access attempt | requester=%s | owner=%s | data_type=%s",
                requesting_user_id,
                data_owner_user_id,
                data_type
            )
            return False
        return True
    
    @staticmethod
    def validate_query_context(user_id: str, sql_query: str) -> bool:
        """
        Ensure generated SQL only queries data for the authenticated user.
        Checks for the presence of a strict user_id filter matching the authenticated user.
        """
        sql_upper = sql_query.upper()
        
        # SQL should ALWAYS filter by user_id of the active authenticated user
        user_id_filter_variants = [
            f"user_id = '{user_id}'",
            f"user_id='{user_id}'",
            f'user_id = "{user_id}"',
            f'user_id="{user_id}"'
        ]
        
        has_filter = any(variant in sql_query for variant in user_id_filter_variants)
        if not has_filter:
            logger.error(
                "[SECURITY] SQL missing user_id filter matching active user | user=%s | query=%s",
                user_id,
                sql_query
            )
            return False
        
        # Block multi-user query techniques
        if "USER_ID IN" in sql_upper or "USER_ID <>" in sql_upper or "USER_ID !=" in sql_upper:
            logger.error("[SECURITY] Multi-user SQL operator detected and blocked | user=%s", user_id)
            return False
            
        return True
