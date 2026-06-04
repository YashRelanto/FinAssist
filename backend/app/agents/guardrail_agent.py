import logging
from typing import Tuple
from app.guardrails import Guardrails
from app.utils.security_logger import log_security_event
import openai

logger = logging.getLogger(__name__)

class GuardrailAgent:

    @staticmethod
    def validate_domain_scope(user_message: str) -> Tuple[bool, str, str]:
        """
        Validates if the user's message is within supported financial domains.
        Returns (supported, reason, detected_domain).
        """
        try:
            client = openai.OpenAI(
                api_key=settings.active_api_key,
                base_url=settings.active_base_url,
            )
            response = client.chat.completions.create(
                model=settings.active_chat_model,
                messages=[
                    {"role": "system", "content": DOMAIN_SCOPE_SYSTEM},
                    {
                        "role": "user",
                        "content": DOMAIN_SCOPE_USER.format(message=user_message)
                    },
                ],
                response_format={"type": "json_object"},
                max_tokens=150,
                temperature=0.0,
            )
            raw = response.choices[0].message.content.strip()
            data = json.loads(raw)
            
            supported = bool(data.get("supported", False))
            reason = str(data.get("reason", ""))
            domain = str(data.get("detected_domain", "unknown"))
            
            logger.info(json.dumps({
                "event": "scope_validation",
                "supported": supported,
                "domain": domain,
                "action": "proceed" if supported else "terminated_before_routing"
            }))
            return supported, reason, domain
        except Exception as exc:
            logger.error("[DomainScopeValidator] Failed: %s", exc)
            return True, "Validator failed, proceeding safely", "unknown"

    # Validate the input message for safety and prompt injection.
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
