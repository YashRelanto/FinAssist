import json
import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

SESSIONS_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "..", "sessions.json")
SESSIONS_FILE = os.path.normpath(SESSIONS_FILE)

class StateManager:
    """
    Manages per-user, per-thread conversation history and active workflow state.
    """

    def __init__(self, sessions_file: str = SESSIONS_FILE):
        self.sessions_file = sessions_file
        self._ensure_file()

    def _ensure_file(self) -> None:
        """Create the sessions file and its parent directory if absent."""
        os.makedirs(os.path.dirname(self.sessions_file), exist_ok=True)
        if not os.path.exists(self.sessions_file):
            with open(self.sessions_file, "w", encoding="utf-8") as fh:
                json.dump({}, fh, indent=2)

    def _load(self) -> dict:
        try:
            with open(self.sessions_file, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            logger.warning("sessions.json unreadable or corrupt — resetting.")
            return {}

    def _save(self, data: dict) -> None:
        try:
            with open(self.sessions_file, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
        except OSError as exc:
            logger.error("Failed to persist sessions.json: %s", exc)

    def _get_thread_data(self, user_id: str, thread_id: str) -> dict:
        data = self._load()
        thread_data = data.get(user_id, {}).get(thread_id, {})
        # Migrate old format if necessary
        if isinstance(thread_data, list):
            return {"messages": thread_data, "workflow_state": {}}
        
        # In case the old format was dict but used clarification_state
        if "clarification_state" in thread_data and "workflow_state" not in thread_data:
            thread_data["workflow_state"] = thread_data.pop("clarification_state")
            
        if "messages" not in thread_data:
            thread_data["messages"] = []
        if "workflow_state" not in thread_data:
            thread_data["workflow_state"] = {}
        if "pending_intents" not in thread_data:
            thread_data["pending_intents"] = []
        if "selected_intent" not in thread_data:
            thread_data["selected_intent"] = ""
            
        return thread_data

    def get_messages(self, user_id: str, thread_id: str) -> List[Dict]:
        return self._get_thread_data(user_id, thread_id).get("messages", [])

    def get_workflow_state(self, user_id: str, thread_id: str) -> Dict[str, Any]:
        return self._get_thread_data(user_id, thread_id).get("workflow_state", {})

    def update_messages(self, user_id: str, thread_id: str, messages: List[Dict]) -> None:
        data = self._load()
        if user_id not in data:
            data[user_id] = {}
            
        thread_data = data[user_id].get(thread_id, {})
        if isinstance(thread_data, list):
            thread_data = {"messages": messages, "workflow_state": {}}
        else:
            thread_data["messages"] = messages
            if "workflow_state" not in thread_data:
                thread_data["workflow_state"] = {}
                
        data[user_id][thread_id] = thread_data
        self._save(data)

    def update_workflow_state(self, user_id: str, thread_id: str, state: Dict[str, Any]) -> None:
        data = self._load()
        if user_id not in data:
            data[user_id] = {}
            
        thread_data = data[user_id].get(thread_id, {})
        if isinstance(thread_data, list):
            thread_data = {"messages": thread_data, "workflow_state": state}
        else:
            thread_data["workflow_state"] = state
            if "messages" not in thread_data:
                thread_data["messages"] = []
                
        data[user_id][thread_id] = thread_data
        self._save(data)

    def append_turn(self, user_id: str, thread_id: str, user_message: str, assistant_message: str) -> List[Dict]:
        """Append a user+assistant turn to the thread history and persist."""
        history = self.get_messages(user_id, thread_id)
        ts = datetime.now(timezone.utc).isoformat()
        history.append({"role": "user", "content": user_message, "ts": ts})
        history.append({"role": "assistant", "content": assistant_message, "ts": ts})
        self.update_messages(user_id, thread_id, history)
        return history

    def clear_workflow_state(self, user_id: str, thread_id: str) -> None:
        self.update_workflow_state(user_id, thread_id, {})

    def update_multi_intent_state(self, user_id: str, thread_id: str, pending_intents: List[Dict], selected_intent: str) -> None:
        data = self._load()
        if user_id not in data:
            data[user_id] = {}
        thread_data = data[user_id].get(thread_id, {})
        if isinstance(thread_data, list):
            thread_data = {"messages": thread_data, "workflow_state": {}}
        
        thread_data["pending_intents"] = pending_intents
        thread_data["selected_intent"] = selected_intent
        
        data[user_id][thread_id] = thread_data
        self._save(data)

state_manager = StateManager()
