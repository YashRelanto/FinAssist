from app.utils.supabase_client import supabase
import json

def inspect():
    # Try to get one row from each table to see structure
    tables = ["users", "accounts", "transactions", "categories"]
    results = {}
    for table in tables:
        try:
            res = supabase.table(table).select("*").limit(1).execute()
            results[table] = res.data[0] if res.data else "No data"
        except Exception as e:
            results[table] = str(e)
    
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    inspect()
