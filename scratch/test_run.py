import asyncio
import uuid
import sys
import os

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.graph.graph import finassist_graph
from app.graph.state import make_initial_state

async def main():
    user_id = "00000000-0000-0000-0000-000000000000"
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": f"{user_id}:{thread_id}"}}
    profile = {
        "income": 50000,
        "annual_income": 600000,
        "segment": "General",
        "city": "Tier 1",
        "risk_profile": "Moderate",
        "credit_score": 750,
        "real_time_balances": "N/A",
        "monthly_net_flow": "N/A",
    }
    query = "Analyse my portfolio and how do i split my investments"
    initial_state = make_initial_state(
        user_id=user_id,
        session_id=thread_id,
        user_query=query,
        user_profile=profile,
    )
    
    print("Invoking graph...")
    final_state = await finassist_graph.ainvoke(initial_state, config=config)
    print("\n--- Final State Results ---")
    print(f"Intent: {final_state.get('intent')}")
    print(f"Clarification Needed: {final_state.get('clarification_needed')}")
    print(f"Clarification Question: {final_state.get('clarification_question')}")
    print(f"Selected Agent: {final_state.get('selected_agent')}")
    print(f"Final Answer: {final_state.get('final_answer')}")
    print(f"Sources: {final_state.get('sources')}")

if __name__ == "__main__":
    asyncio.run(main())
