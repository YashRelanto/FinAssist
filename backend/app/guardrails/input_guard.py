import re
import unicodedata
from typing import Tuple
import logging
from better_profanity import profanity

logger = logging.getLogger(__name__)

# Add custom financial abuse words to the default global profanity list
custom_badwords = ["scam", "fraud", "cheat", "steal", "hack", "scammer", "swindle", "exploit"]
profanity.add_censor_words(custom_badwords)

# Patterns that indicate prompt injection attempts
INJECTION_PATTERNS = [
    # System prompt override attempts
    r"ignore (previous|all|above|your) (instructions|prompts?)",
    r"disregard (previous|all|above|your)",
    r"forget (everything|all|previous|your)",
    r"new (instructions|rules|system prompt)",
    r"you are now",
    r"act as if",
    r"pretend (you are|to be)",
    r"simulate being",
    
    # Role manipulation
    r"(your|the) (new|real) (role|purpose|instructions) (is|are)",
    r"from now on",
    r"developer mode",
    r"god mode",
    r"admin mode",
    
    # Output format manipulation
    r"output (raw|unfiltered) data",
    r"show (all|complete) (data|database|table)",
    r"dump (database|all data|everything)",
    r"select \* from",  # SQL injection in natural language
    
    # Jailbreak phrases
    r"DAN|Do Anything Now",
    r"broken (free|out)",
    r"without (any |)restrictions",
    r"no (limitations|rules|filters)",
]

# Suspicious phrases requesting sensitive operations
SUSPICIOUS_PHRASES = [
    r"other users?('| )?(transactions|data|accounts?)",
    r"all users?('| )?data",
    r"admin (access|panel|dashboard)",
    r"system (password|credentials|keys?)",
    r"database (schema|structure|credentials)",
    r"API (key|secret|token)",
    r"internal (config|settings)",
    r"user_id\s*(?:!=|<>|\bin\b|\bnot\s+in\b)",  # user_id IN/!= bypass indicators
    r"(show|get|retrieve|view|display)\s+(\w+)'s\s+(transactions|data|spending|expenses|income|records|purchases)", # e.g. "show John's transactions"
    r"compare\s+(my|user)\s+(expenses|data|spending|transactions)\s+(with|to|against)\s+other\s+users", # e.g. "compare my expenses with other users"
]



def detect_prompt_injection(message: str) -> Tuple[bool, str]:
    """
    Returns (is_safe, reason)
    - is_safe: True if message is safe, False if injection detected
    - reason: Explanation if blocked
    """
    message_lower = message.lower()
    
    # Check for prompt injection patterns
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, message_lower, re.IGNORECASE):
            return False, "Potential prompt injection detected: attempting to override system behavior"
    
    # Check for suspicious data access attempts
    for pattern in SUSPICIOUS_PHRASES:
        if re.search(pattern, message_lower, re.IGNORECASE):
            return False, "Suspicious request: attempting to access unauthorized data"
    
    return True, ""

def detect_excessive_length(message: str, max_length: int = 2000) -> Tuple[bool, str]:
    """
    Extremely long messages can be used to confuse the model or cause DoS
    """
    if len(message) > max_length:
        return False, f"Message too long ({len(message)} chars). Max {max_length} allowed."
    
    return True, ""

def detect_special_characters_flood(message: str) -> Tuple[bool, str]:
    """
    Flooding with special characters can break tokenization or confuse the model
    """
    special_chars = sum(1 for c in message if not c.isalnum() and not c.isspace())
    total_chars = len(message)
    
    if total_chars > 0 and (special_chars / total_chars) > 0.5:
        return False, "Message contains excessive special characters"
    
    return True, ""

def contains_profanity(message: str) -> Tuple[bool, str]:
    """
    Check if message contains profanity or abusive language
    """
    if profanity.contains_profanity(message):
        return False, "Message contains inappropriate language"
    return True, ""

# Common unicode homoglyphs → ASCII equivalents
_HOMOGLYPHS = str.maketrans({
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u00a0": " ", "\u200b": "", "\u200c": "", "\u200d": "",
    "\uff01": "!", "\uff1f": "?",
})


def normalize_query(message: str) -> str:
    """Normalize whitespace and unicode homoglyphs for consistent validation."""
    if not message:
        return ""
    text = unicodedata.normalize("NFKC", message).translate(_HOMOGLYPHS)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class InputGuard:
    """
    Validates user input before it reaches the LLM
    """

    @staticmethod
    def validate(message: str, user_id: str) -> Tuple[bool, str]:
        """
        Run all input validation checks
        Returns (is_safe, error_message)
        """
        message = normalize_query(message)

        # 1. Check for prompt injection
        is_safe, reason = detect_prompt_injection(message)
        if not is_safe:
            return False, "Your message was flagged by our security system. Please rephrase your question."
        
        # 2. Check message length
        is_safe, reason = detect_excessive_length(message, max_length=2000)
        if not is_safe:
            return False, reason
        
        # 3. Check for special character flooding
        is_safe, reason = detect_special_characters_flood(message)
        if not is_safe:
            return False, reason
        
        # 4. Check for profanity
        is_safe, reason = contains_profanity(message)
        if not is_safe:
            return False, reason
        
        return True, ""
