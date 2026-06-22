import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

SECURITY_EVENTS_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "security_events.json")
)

def log_security_event(
    user_id: str,
    event_type: str,
    message: str,
    reason: str,
    thread_id: Optional[str] = None
) -> None:
    """
    Logs security events to a local JSON file and standard logging for real-time monitoring.
    """
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "user_id": user_id,
        "thread_id": thread_id,
        "event_type": event_type,
        "message": message[:500],  # Truncate long messages
        "reason": reason,
    }

    # Log to python logger (console/files)
    logger.warning(
        "[SECURITY_EVENT] type=%s | user=%s | reason=%s | msg=%s",
        event_type,
        user_id,
        reason,
        event["message"],
    )

    # Persist to local JSON file
    try:
        data = []
        if os.path.exists(SECURITY_EVENTS_FILE):
            with open(SECURITY_EVENTS_FILE, "r", encoding="utf-8") as fh:
                try:
                    data = json.load(fh)
                    if not isinstance(data, list):
                        data = []
                except (json.JSONDecodeError, OSError):
                    data = []
        
        data.append(event)
        
        # Keep only the last 1000 events to prevent file growing indefinitely
        if len(data) > 1000:
            data = data[-1000:]

        with open(SECURITY_EVENTS_FILE, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)   
            
    except Exception as exc:
        logger.error("Failed to persist security event: %s", exc)
