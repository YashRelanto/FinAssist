import json
import logging
import uuid
from typing import Tuple, Dict, Any, List
import openai

from app.core.config import settings
from app.utils.prompts import (
    DOMAIN_SCOPE_SYSTEM,
    DOMAIN_SCOPE_USER,
    INTENT_CLASSIFIER_SYSTEM, 
    INTENT_CLASSIFIER_USER,
    WORKFLOW_RELEVANCE_SYSTEM,
    WORKFLOW_RELEVANCE_USER
)
from app.agents.state_manager import state_manager
from app.agents.guardrail_agent import GuardrailAgent
from app.agents.workflow_agent import WorkflowAgent
from app.agents.advisor_agent import AdvisorAgent
from app.agents.nl2sql_agent import NL2SQLAgent

logger = logging.getLogger(__name__)

VALID_INTENTS = {
    "personal_transaction",
    "financial_knowledge",
    "financial_goal_planning",
}

class OrchestratorAgent:
    """
    Main orchestrator that maps intents and routes to specific agents.
    """

    @staticmethod
    def classify_intent(user_message: str, history: List[Dict]) -> List[Dict]:
        """
        Classifies the user's message into intents.
        Filters out candidates below 0.4 confidence.
        """
        try:
            history_lines = []
            if history:
                for msg in history[-5:]:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    history_lines.append(f"{role.capitalize()}: {content}")
            history_str = "\n".join(history_lines) if history_lines else "None."

            client = openai.OpenAI(
                api_key=settings.active_api_key,
                base_url=settings.active_base_url,
            )
            response = client.chat.completions.create(
                model=settings.active_chat_model,
                messages=[
                    {"role": "system", "content": INTENT_CLASSIFIER_SYSTEM},
                    {
                        "role": "user",
                        "content": INTENT_CLASSIFIER_USER.format(
                            message=user_message,
                            history=history_str
                        )
                    },
                ],
                response_format={"type": "json_object"},
                max_tokens=150,
                temperature=0.0,
            )
            raw = response.choices[0].message.content.strip()
            data = json.loads(raw)
            
            candidates = data.get("intent_candidates", [])

            # Filter candidates below threshold
            valid_candidates = []
            for c in candidates:
                intent = str(c.get("intent", "general_finance")).lower().strip()
                if intent not in VALID_INTENTS:
                    intent = "financial_knowledge"
                c["intent"] = intent
                
                if float(c.get("confidence", 0.0)) >= 0.4:
                    valid_candidates.append(c)

            if not valid_candidates:
                valid_candidates = [{"intent": "financial_knowledge", "confidence": 1.0}]

            logger.info("[IntentClassifier] Candidates=%s", valid_candidates)
            return valid_candidates

        except Exception as exc:
            logger.error("[IntentClassifier] Failed: %s", exc)
            return [{"intent": "financial_knowledge", "confidence": 1.0}]

    @staticmethod
    def analyze_workflow_relevance(user_message: str, workflow_state: Dict[str, Any]) -> Tuple[bool, float, str]:
        """
        Analyzes if a message is part of the currently active workflow.
        Returns (workflow_related, confidence, reason)
        """
        try:
            workflow_state_json = json.dumps(workflow_state, indent=2)
            
            client = openai.OpenAI(
                api_key=settings.active_api_key,
                base_url=settings.active_base_url,
            )
            response = client.chat.completions.create(
                model=settings.active_chat_model,
                messages=[
                    {"role": "system", "content": WORKFLOW_RELEVANCE_SYSTEM},
                    {
                        "role": "user",
                        "content": WORKFLOW_RELEVANCE_USER.format(
                            message=user_message,
                            workflow_state=workflow_state_json
                        )
                    },
                ],
                response_format={"type": "json_object"},
                max_tokens=150,
                temperature=0.0,
            )
            raw = response.choices[0].message.content.strip()
            data = json.loads(raw)
            
            workflow_related = bool(data.get("workflow_related", False))
            confidence = float(data.get("confidence", 0.0))
            reason = str(data.get("reason", ""))
            
            logger.info("[WorkflowRelevanceAnalyzer] Message='%s' -> related=%s, conf=%.2f, reason='%s'", 
                        user_message[:60], workflow_related, confidence, reason)
            
            return workflow_related, confidence, reason
        except Exception as exc:
            logger.error("[WorkflowRelevanceAnalyzer] Failed: %s", exc)
            return False, 0.0, "Analyzer failed"

    @staticmethod
    def analyze_multi_intent(intent_candidates: List[Dict]) -> Dict:
        """
        Decision Engine for resolving multiple intents.
        Applies Strategy A (dominant) or Strategy B (clarification).
        """
        if not intent_candidates:
            return {"decision_type": "route_dominant", "selected_intent": "financial_knowledge", "reason": "no candidates"}

        # Sort by confidence descending
        sorted_candidates = sorted(intent_candidates, key=lambda x: x.get("confidence", 0.0), reverse=True)
        
        if len(sorted_candidates) == 1:
            return {"decision_type": "route_dominant", "selected_intent": sorted_candidates[0]["intent"], "reason": "single intent"}

        top_1 = sorted_candidates[0]
        top_2 = sorted_candidates[1]
        
        c1 = top_1.get("confidence", 0.0)
        c2 = top_2.get("confidence", 0.0)
        
        gap = c1 - c2
        
        if c1 >= 0.7 and (c2 < 0.5 or gap > 0.3):
            return {"decision_type": "route_dominant", "selected_intent": top_1["intent"], "reason": "strategy A: dominant"}
            
        if c1 >= 0.6 and c2 >= 0.6 and gap <= 0.3:
            return {"decision_type": "clarification_required", "selected_intent": None, "reason": "strategy B: multiple strong intents"}

        # Default fallback to top 1
        return {"decision_type": "route_dominant", "selected_intent": top_1["intent"], "reason": "fallback"}

    @staticmethod
    async def process(user_id: str, message: str, thread_id: str, user_profile: dict) -> dict:
        if not thread_id or thread_id.strip() == "":
            thread_id = str(uuid.uuid4())

        # Layer 1: Input Guardrails
        is_safe, error_message = GuardrailAgent.validate_input(user_id, thread_id, message)
        if not is_safe:
            return {
                "answer": error_message,
                "intent": "out_of_scope",
                "sources": ["Security Guardrails"],
                "thread_id": thread_id,
                "user_id": user_id,
            }

        history = state_manager.get_messages(user_id, thread_id)
        workflow_state = state_manager.get_workflow_state(user_id, thread_id)
        
        is_active = workflow_state.get("workflow_status") == "active"
        is_clarifying_active = workflow_state.get("clarification_required", False) and is_active

        # 1. Domain Scope Validation
        supported, reason, detected_domain = GuardrailAgent.validate_domain_scope(message)
        if not supported:
            out_of_scope_response = (
                "This assistant specializes in personal finance and financial planning. "
                "Please ask a finance-related question."
            )
            state_manager.append_turn(user_id, thread_id, message, out_of_scope_response)
            return {
                "answer": out_of_scope_response,
                "intent": "out_of_scope",
                "sources": ["Domain Scope Validator"],
                "thread_id": thread_id,
                "user_id": user_id,
            }

        # 2. Intent Detection
        candidates = OrchestratorAgent.classify_intent(message, history)
        
        # 2. Multi-Intent Analysis
        decision = OrchestratorAgent.analyze_multi_intent(candidates)
        logger.info(json.dumps({
            "event": "multi_intent_analysis",
            "intent_candidates": candidates,
            "decision": decision
        }))

        if decision["decision_type"] == "clarification_required":
            response_text = "I found multiple requests in your message:\n\n"
            for c in candidates[:2]:
                intent_name = c["intent"].replace("_", " ").title()
                response_text += f"- {intent_name}\n"
            response_text += "\nWhich would you like to address first?"
            
            state_manager.append_turn(user_id, thread_id, message, response_text)
            state_manager.update_multi_intent_state(user_id, thread_id, candidates, "")
            
            return {
                "answer": response_text,
                "intent": "clarification_required",
                "sources": ["Multi-Intent Engine"],
                "thread_id": thread_id,
                "user_id": user_id
            }

        selected_intent = decision["selected_intent"]
        state_manager.update_multi_intent_state(user_id, thread_id, [], selected_intent)
        
        # 3. Workflow Relevance Analysis (if active workflow)
        if is_clarifying_active:
            is_related, conf, reason = OrchestratorAgent.analyze_workflow_relevance(message, workflow_state)
            if is_related:
                logger.info("[Orchestrator] WorkflowRelevance=True. Overriding intent to workflow.")
                current_intent = "financial_goal_planning"
                out_of_scope = False
            else:
                logger.info("[Orchestrator] WorkflowRelevance=False. Workflow paused.")
                current_intent = selected_intent
                
                from datetime import datetime, timezone
                workflow_state["workflow_status"] = "paused"
                workflow_state["last_updated"] = datetime.now(timezone.utc).isoformat()
                state_manager.update_workflow_state(user_id, thread_id, workflow_state)
                
                workflow_state = {}
        else:
            current_intent = selected_intent

        sources: List[str] = []
        answer = ""

        # Route to appropriate Agent
        if current_intent == "personal_transaction":
            logger.info("[Orchestrator] Routing to NL2SQLAgent")
            result = await NL2SQLAgent.process(user_id, message)
            answer = result["answer"]
            sources = result["sources"]
            
        elif current_intent == "financial_goal_planning":
            logger.info("[Orchestrator] Routing to WorkflowAgent")
            requires_clarification, next_question, workflow_state = WorkflowAgent.process(message, history, workflow_state)
            state_manager.update_workflow_state(user_id, thread_id, workflow_state)

            if requires_clarification and next_question:
                answer = next_question
                sources = ["Clarification Planner"]
            else:
                logger.info("[Orchestrator] Workflow slots complete, generating final advisor plan.")
                result = AdvisorAgent.process(message, current_intent, history, user_profile, workflow_state)
                answer = result["answer"]
                sources = result["sources"]
                state_manager.clear_workflow_state(user_id, thread_id)
                
        else:
            logger.info("[Orchestrator] Routing to AdvisorAgent")
            result = AdvisorAgent.process(message, current_intent, history, user_profile, workflow_state)
            
            if result.get("route_to_nl2sql"):
                logger.info("[Orchestrator] Failsafe routing to NL2SQLAgent")
                nl2sql_res = await NL2SQLAgent.process(user_id, message)
                answer = nl2sql_res["answer"]
                sources = nl2sql_res["sources"]
                current_intent = "personal_transaction"
            else:
                answer = result["answer"]
                sources = result["sources"]

        # Layer 6: Output Guardrails
        is_output_safe, cleaned_answer = GuardrailAgent.validate_output(user_id, thread_id, message, answer)
        if not is_output_safe:
            return {
                "answer": cleaned_answer,
                "intent": current_intent,
                "sources": ["Security Guardrails"],
                "thread_id": thread_id,
                "user_id": user_id,
            }
        
        answer = cleaned_answer

        # Persist Turn
        state_manager.append_turn(user_id, thread_id, message, answer)

        return {
            "answer": answer,
            "intent": current_intent,
            "sources": sources,
            "thread_id": thread_id,
            "user_id": user_id,
        }
