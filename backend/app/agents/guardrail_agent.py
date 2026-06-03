import logging
from typing import Tuple
from app.guardrails import Guardrails
from app.utils.security_logger import log_security_event

logger = logging.getLogger(__name__)

class GuardrailAgent:
    @staticmethod
    def validate_input(user_id: str, thread_id: str, message: str) -> Tuple[bool, str]:
        """
        Validates the input message for safety and prompt injection.
        Returns (is_safe, error_or_cleaned_message).
        """
        is_safe, error_message = Guardrails.validate_input(message, user_id)
        if not is_safe:
            log_security_event(
                user_id=user_id,
                thread_id=thread_id,
                event_type="prompt_injection_attempt" if "flagged" in error_message or "security" in error_message else "input_blocked",
                message=message,
                reason=error_message,
            )
        return is_safe, error_message

    @staticmethod
    def validate_output(user_id: str, thread_id: str, message: str, answer: str) -> Tuple[bool, str]:
        """
        Validates the generated answer to prevent secret leakage or PII exposure.
        Returns (is_safe, cleaned_answer).
        """
        is_output_safe, cleaned_answer = Guardrails.validate_output(answer, user_id)
        if not is_output_safe:
            log_security_event(
                user_id=user_id,
                thread_id=thread_id,
                event_type="output_blocked",
                message=message,
                reason="Sensitive credentials leaked in response",
            )
        return is_output_safe, cleaned_answer
