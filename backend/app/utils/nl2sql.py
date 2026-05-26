import json
import logging
import openai
from app.utils.supabase_client import supabase
from app.core.config import settings
from app.guardrails import Guardrails

logger = logging.getLogger(__name__)

async def execute_nl2sql(user_id: str, user_question: str) -> str:
    try:
        # Step 1 & 2 (Corrected): Fetch the user's recent transactions using standard Supabase .select()
        response = supabase.table('transactions').select('*').eq('user_id', user_id).order('transaction_date', desc=True).limit(100).execute()
        
        transactions_data = response.data
        if not transactions_data:
            return "I couldn't find any recent transactions for your account."
            
        # Apply Layer 3: PII and context data masking
        masked_transactions = Guardrails.mask_context_data(transactions_data, user_id)
        
        transactions_json = json.dumps(masked_transactions, default=str)
        
        # Step 3: Summarize using the LLM
        client = openai.OpenAI(
            api_key=settings.active_api_key,
            base_url=settings.active_base_url,
        )
        
        system_prompt = (
            "You are a highly analytical financial advisor AI. You are provided with a user's recent transactions in JSON format.\n\n"
            "Guidelines for a neat and premium response:\n"
            "  - Answer the user's question based ONLY on this transaction data.\n"
            "  - Format your response beautifully using bold text, neat bullet points, or clean Markdown tables if summarizing figures.\n"
            "  - Always display transaction amounts as formatted Indian Rupees (e.g. ₹5,000).\n"
            "  - Add relevant emojis (like 📊, 💳, 💰, 🛒) to categorize spending categories or highlight key insights.\n"
            "  - Keep paragraphs short and use clean headers so it looks extremely neat and professional."
        )
        
        user_prompt = f"User Question: {user_question}\n\nTransaction Data:\n{transactions_json}"
        
        completion = client.chat.completions.create(
            model=settings.active_chat_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=700
        )
        
        return completion.choices[0].message.content.strip()
        
    except Exception as e:
        logger.error(f"Error in execute_nl2sql: {e}")
        return f"An error occurred while trying to process your request: {str(e)}"
