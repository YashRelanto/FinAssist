"""
FastAPI router exposing the FinAssist AI chatbot API.

Prefix  : /api/chat
Tags    : Chatbot
Endpoints:
    POST /api/chat/message  — Submit a user message and receive an AI advisory response
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.utils.chatbot_engine import process_chat_message

# ─── Logging ────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)

# ─── Router ──────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/chat", tags=["Chatbot"])


# ─── Pydantic Schemas ─────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    """Incoming chat payload from the frontend."""

    user_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Unique identifier for the authenticated user (e.g. Supabase UUID).",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=4096,
        description="The user's natural language query or statement.",
        examples=["What are the best FD rates available right now?"],
    )
    thread_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description=(
            "Conversation thread identifier.  Use a stable UUID per chat session "
            "to maintain coherent multi-turn history.  Pass a new UUID to start a fresh thread."
        ),
        examples=["a1b2c3d4-e5f6-7890-abcd-ef1234567890"],
    )


class ChatResponse(BaseModel):
    """Outgoing advisory payload returned to the frontend."""

    answer: str = Field(
        ...,
        description="The AI-generated advisory response in markdown-compatible plain text.",
    )
    intent: str = Field(
        ...,
        description=(
            "Classified intent of the query.  One of: "
            "personal_transaction | financial_knowledge | financial_goal_planning | out_of_scope"
        ),
    )
    sources: list[str] = Field(
        default_factory=list,
        description=(
            "List of knowledge sources used to generate the answer "
            "(e.g. 'BankBazaar', 'MoneyControl', 'Supabase: transactions')."
        ),
    )
    thread_id: str = Field(
        ...,
        description="Echo of the thread_id used for this turn.",
    )
    user_id: str = Field(
        ...,
        description="Echo of the user_id for client-side correlation.",
    )


# ─── Default Mock User Profile ────────────────────────────────────────────────

def _get_default_user_profile() -> dict:
    """
    Returns a mock user profile dictionary that simulates variables sourced
    from the Supabase users / profiles table.

    In a production deployment, replace this with a Supabase lookup using the
    request's user_id before passing the profile to the engine.
    """
    return {
        "income": 55000,                         # Monthly net income in INR
        "annual_income": 660000,                 # Annual (12 × monthly)
        "segment": "High Income Low Spender",    # Customer segment from analytics
        "city": "Tier 1",                        # City tier classification
        "age": 32,                               # Estimated age
        "risk_profile": "Moderate",              # Risk tolerance: Conservative / Moderate / Aggressive
        "primary_bank": "HDFC Bank",             # Primary bank name
        "existing_investments": [                # Known investment vehicles
            "Mutual Funds (SIP ₹10,000/mo)",
            "PPF (₹1.5L/year)",
            "EPF (employer + employee)",
        ],
        "outstanding_loans": [],                 # Active loan facilities
        "credit_score": 780,                     # CIBIL / Experian score
        "preferred_language": "English",
    }


# ─── POST /message Endpoint ──────────────────────────────────────────────────

@router.post(
    "/message",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit a chat message and receive a financial advisory response",
    description=(
        "Accepts a user's natural language financial query along with a conversation thread ID. "
        "The engine classifies the intent, retrieves relevant knowledge from ChromaDB, "
        "optionally queries the Supabase analytical layer for personal data, and returns "
        "a personalised advisory answer with source attribution."
    ),
    responses={
        200: {"description": "Successful advisory response"},
        422: {"description": "Validation error — check request body schema"},
        500: {"description": "Internal server error — engine failure"},
    },
)
async def post_chat_message(request: ChatRequest) -> ChatResponse:
    """
    Main chat endpoint orchestrator.

    Flow:
      1. Load a fallback user profile (production: fetch from Supabase by user_id)
      2. Call the async chatbot engine
      3. Return structured ChatResponse
      4. Any unhandled exception is caught and re-raised as HTTP 500
    """
    # 1. Build user profile (production: replace with DB fetch)
    user_profile = _get_default_user_profile()

    # 2. Call the core engine
    try:
        result = await process_chat_message(
            user_id=request.user_id,
            message=request.message,
            thread_id=request.thread_id,
            user_profile=user_profile,
        )
    except ValueError as exc:
        logger.warning(
            "Validation error in process_chat_message | user=%s | error=%s",
            request.user_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid input: {exc}",
        ) from exc
    except ConnectionError as exc:
        logger.error(
            "Connectivity error in process_chat_message | user=%s | error=%s",
            request.user_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "A downstream service (OpenAI or ChromaDB) is temporarily unavailable. "
                "Please try again in a few moments."
            ),
        ) from exc
    except Exception as exc:
        logger.exception(
            "Unhandled error in /api/chat/message | user=%s | thread=%s",
            request.user_id,
            request.thread_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "An unexpected error occurred while processing your request. "
                "Our team has been notified. Please try again shortly."
            ),
        ) from exc

    # 3. Build and return the response model
    return ChatResponse(
        answer=result.get("answer", ""),
        intent=result.get("intent", "general_finance"),
        sources=result.get("sources", []),
        thread_id=result.get("thread_id", request.thread_id),
        user_id=result.get("user_id", request.user_id),
    )
