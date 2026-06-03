from app.utils.nl2sql import execute_nl2sql

class NL2SQLAgent:
    """
    Agent handling Natural Language to SQL translation for personal transactions.
    """
    
    @staticmethod
    async def process(user_id: str, message: str) -> dict:
        """
        Executes NL2SQL query on personal transactions.
        """
        answer = await execute_nl2sql(user_id, message)
        return {
            "answer": answer,
            "sources": ["Supabase Transactions"]
        }
