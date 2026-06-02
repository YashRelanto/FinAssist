import json
import logging
from typing import Tuple, Dict, Any, List
import openai

from app.core.config import settings
from app.utils.prompts import (
    SLOT_EXTRACTION_SYSTEM, 
    SLOT_EXTRACTION_USER,
    QUESTION_GENERATOR_SYSTEM,
    QUESTION_GENERATOR_USER
)

logger = logging.getLogger(__name__)

WORKFLOW_DEFINITIONS = {
    "house_workflow": {
        "required_slots": ["target_amount", "timeline", "funding_option"]
    },
    "car_workflow": {
        "required_slots": ["target_amount", "timeline", "funding_option"]
    },
    "budget_workflow": {
        "required_slots": ["primary_goal"]
    },
    "general_goal": {
        "required_slots": ["target_amount", "timeline"]
    }
}

import uuid
from datetime import datetime, timezone

class WorkflowAgent:
    """
    Generic Slot Manager for handling dynamic multi-turn workflows.
    Responsibilities: slot extraction, slot validation, slot persistence, missing slot detection.
    """
    
    @staticmethod
    def process(user_message: str, history: List[Dict], state: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Executes the explicit slot manager logic.
        Returns (requires_clarification, next_question, updated_state)
        """
        if not state or state.get("workflow_status") in ["completed", "cancelled"]:
            state = {
                "workflow_id": str(uuid.uuid4()),
                "workflow_status": "active",
                "intent": "financial_goal_planning",
                "goal_description": "",
                "workflow_type": "general_goal",
                "collected_information": {},
                "missing_information": [],
                "clarification_required": False,
                "next_question": "",
                "advisor_ready": False,
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
        elif state.get("workflow_status") == "paused":
            logger.info("[WorkflowAgent] Resuming paused workflow %s", state.get("workflow_id"))
            state["workflow_status"] = "active"
            
        state["last_updated"] = datetime.now(timezone.utc).isoformat()

        input_state = {
            "goal_description": state.get("goal_description", ""),
            "workflow_type": state.get("workflow_type", "general_goal"),
            "collected_information": state.get("collected_information", {})
        }
        state_json = json.dumps(input_state, indent=2)

        history_lines = []
        for msg in history[-10:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            history_lines.append(f"{role.capitalize()}: {content}")
        history_str = "\n".join(history_lines) if history_lines else "None."

        client = openai.OpenAI(
            api_key=settings.active_api_key,
            base_url=settings.active_base_url,
        )

        # 1. Extraction Phase
        try:
            response = client.chat.completions.create(
                model=settings.active_chat_model,
                messages=[
                    {"role": "system", "content": SLOT_EXTRACTION_SYSTEM},
                    {
                        "role": "user",
                        "content": SLOT_EXTRACTION_USER.format(
                            state_json=state_json,
                            history=history_str,
                            message=user_message
                        )
                    },
                ],
                response_format={"type": "json_object"},
                max_tokens=500,
                temperature=0.0,
            )
            raw = response.choices[0].message.content.strip()
            extraction_output = json.loads(raw)
            logger.info("[WorkflowAgent] Extracted Slots: %s", extraction_output)
        except Exception as exc:
            logger.error("[WorkflowAgent] Slot Extraction failed: %s", exc)
            extraction_output = {}

        workflow_type = extraction_output.get("workflow_type", state.get("workflow_type", "general_goal"))
        if workflow_type not in WORKFLOW_DEFINITIONS:
            workflow_type = "general_goal"
            
        state["workflow_type"] = workflow_type
        
        desc = extraction_output.get("goal_description")
        if desc:
            state["goal_description"] = str(desc)

        # 2. Persistence Phase
        new_slots = extraction_output.get("extracted_slots", {})
        if isinstance(new_slots, dict):
            for k, v in new_slots.items():
                if v is not None:
                    state.setdefault("collected_information", {})[k] = v
                    
        logger.info("[WorkflowAgent] Persisted Slots in state: %s", state["collected_information"])

        # 3. Missing Slot Detection Phase
        required_slots = WORKFLOW_DEFINITIONS[workflow_type]["required_slots"]
        collected_keys = set(state.get("collected_information", {}).keys())
        
        # Calculate strictly missing slots using set difference, preserving order
        missing_slots = [slot for slot in required_slots if slot not in collected_keys]
        state["missing_information"] = missing_slots
        
        if not missing_slots:
            logger.info("[WorkflowAgent] All slots filled. advisor_ready=True")
            state["workflow_status"] = "completed"
            state["advisor_ready"] = True
            state["clarification_required"] = False
            state["next_question"] = ""
            logger.info("[WorkflowAgent] Workflow state after update: %s", state)
            return False, "", state

        next_missing_slot = missing_slots[0]
        logger.info("[WorkflowAgent] Next missing slot: %s", next_missing_slot)
        
        # 5. Question Generation Phase
        try:
            q_response = client.chat.completions.create(
                model=settings.active_chat_model,
                messages=[
                    {"role": "system", "content": QUESTION_GENERATOR_SYSTEM},
                    {
                        "role": "user",
                        "content": QUESTION_GENERATOR_USER.format(
                            goal_description=state.get("goal_description", "Financial Goal"),
                            next_missing_slot=next_missing_slot
                        )
                    },
                ],
                max_tokens=100,
                temperature=0.7,
            )
            next_question = q_response.choices[0].message.content.strip()
        except Exception as exc:
            logger.error("[WorkflowAgent] Question Generation failed: %s", exc)
            next_question = f"Could you provide your {next_missing_slot}?"

        state["advisor_ready"] = False
        state["clarification_required"] = True
        state["next_question"] = next_question
        
        logger.info("[WorkflowAgent] Workflow state after update: %s", state)

        return state["clarification_required"], state["next_question"], state

    @staticmethod
    def format_filled_slots(slots: dict) -> str:
        lines = []
        for k, v in slots.items():
            key_display = str(k).replace('_', ' ').title()
            if isinstance(v, (int, float)) and "amount" in k.lower() or "budget" in k.lower():
                lines.append(f"- {key_display}: Rs. {v:,.0f}")
            else:
                lines.append(f"- {key_display}: {v}")
        return "\n".join(lines)
