# pyrefly: ignore [missing-import]
from fastapi import APIRouter, HTTPException
# pyrefly: ignore [missing-import]
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Optional
from app.utils.supabase_client import supabase
import json

router = APIRouter()

# Category Mapping helper to resolve frontend simulated categories into database check-constrained categories
def map_category_to_db(main_cat: str) -> str:
    mapping = {
        'Food & Drinks': 'Food & Drinks',
        'Food & Dining': 'Food & Drinks',
        'Food & Drink': 'Food & Drinks',
        'Shopping': 'Shopping',
        'Housing': 'Housing',
        'Transportation': 'Transportation',
        'Travel': 'Transportation',
        'Vehicle': 'Vehicle',
        'Life & Entertainment': 'Life & Entertainment',
        'Entertainment': 'Life & Entertainment',
        'Communication/PC': 'Life & Entertainment',
        'Financial Expense': 'Financial Expenses',
        'Financial Expenses': 'Financial Expenses',
        'Investments': 'Investments',
        'Income': 'Income'
    }
    return mapping.get(main_cat, 'Shopping')

# Request models for transactions and statements
class UploadTransaction(BaseModel):
    date: str
    merchant: str
    category: str
    subCategory: Optional[str] = None
    amount: float
    account: str
    type: str

class UploadStatementRequest(BaseModel):
    user_id: str
    transactions: List[UploadTransaction]

class CreateTransactionRequest(BaseModel):
    user_id: str
    transaction_date: str
    amount: float
    transaction_type: str
    merchant_name: Optional[str] = None
    description: Optional[str] = None
    category_name: str
    sub_category_name: Optional[str] = None

@router.get("/home", response_class=HTMLResponse)
async def home_get(user_id: str):
    # 1. Fetch Transactions for Balance Chart (Line Chart)
    trans_response = supabase.table("transactions")\
        .select("transaction_date, running_balance")\
        .eq("user_id", user_id)\
        .order("transaction_date")\
        .execute()
    
    transactions = trans_response.data
    
    # Fetch initial balance from accounts to use as the starting point
    acc_response = supabase.table("accounts")\
        .select("current_balance, created_at")\
        .eq("user_id", user_id)\
        .execute()
    
    # We'll sum up balances if there are multiple accounts
    initial_balance = sum(float(a["current_balance"]) for a in acc_response.data) if acc_response.data else 0
    
    # Prepend the starting point
    if transactions:
        first_date = transactions[0]["transaction_date"]
        # For the "Start" point, we use the date of the first transaction but show the balance BEFORE it
        # Actually, since your ETL script starts WITH the initial balance, 
        # we can just prepend a dummy "Start" entry.
        dates = ["Start"] + [t["transaction_date"] for t in transactions]
        balances = [initial_balance] + [float(t["running_balance"]) for t in transactions]
    else:
        dates = ["Start"]
        balances = [initial_balance]

    # 2. Fetch Categorical Spending (Donut Chart)
    # We fetch transactions and categories separately and join them in Python 
    # to avoid the "Relationship not found" error.
    trans_expense_response = supabase.table("transactions")\
        .select("amount, category_id")\
        .eq("user_id", user_id)\
        .eq("transaction_type", "expense")\
        .execute()
    
    # Fetch all categories to map IDs to names
    cat_list_response = supabase.table("categories").select("category_id, main_category").execute()
    cat_map = {c["category_id"]: c["main_category"] for c in cat_list_response.data}
    
    spending_by_cat = {}
    for item in trans_expense_response.data:
        category_id = item["category_id"]
        main_cat = cat_map.get(category_id, "Unknown")
        amount = float(item["amount"])
        spending_by_cat[main_cat] = spending_by_cat.get(main_cat, 0) + amount
    
    cat_labels = list(spending_by_cat.keys())
    cat_values = list(spending_by_cat.values())

    return f"""
    <html>
        <head>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        </head>
        <body>
            <h1>Login successful!</h1>
            <p>Welcome to your FinAssist Dashboard.</p>
            
            <div style="width: 600px;">
                <h3>Bank Balance Over Time</h3>
                <canvas id="balanceChart"></canvas>
            </div>
            
            <div style="width: 400px;">
                <h3>Categorical Spending</h3>
                <canvas id="spendingChart"></canvas>
            </div>
 
            <script>
                // Line Chart
                const balanceCtx = document.getElementById('balanceChart').getContext('2d');
                new Chart(balanceCtx, {{
                    type: 'line',
                    data: {{
                        labels: {json.dumps(dates)},
                        datasets: [{{
                            label: 'Balance',
                            data: {json.dumps(balances)},
                            borderColor: 'rgb(75, 192, 192)',
                            tension: 0.1
                        }}]
                    }}
                }});

                // Donut Chart
                const spendingCtx = document.getElementById('spendingChart').getContext('2d');
                new Chart(spendingCtx, {{
                    type: 'doughnut',
                    data: {{
                        labels: {json.dumps(cat_labels)},
                        datasets: [{{
                            label: 'Spending by Category',
                            data: {json.dumps(cat_values)},
                            backgroundColor: [
                                'rgb(255, 99, 132)',
                                'rgb(54, 162, 235)',
                                'rgb(255, 205, 86)',
                                'rgb(75, 192, 192)',
                                'rgb(153, 102, 255)',
                                'rgb(255, 159, 64)'
                            ]
                        }}]
                    }}
                }});
            </script>
            <br>
            <a href="/login">Logout</a>
        </body>
    </html>
    """

# API endpoints for direct React frontend integration
@router.post("/api/upload-statement")
async def api_upload_statement(request: UploadStatementRequest):
    if not request.transactions:
        raise HTTPException(status_code=400, detail="No transactions provided")

    if not supabase:
        # Graceful simulation fallback
        return {
            "success": True,
            "inserted_count": len(request.transactions),
            "account_id": "simulated-account-id",
            "balance": sum(t.amount for t in request.transactions)
        }

    # 1. Resolve or Create the 'Statement Upload' account for the user
    acc_response = supabase.table("accounts")\
        .select("*")\
        .eq("user_id", request.user_id)\
        .eq("account_name", "Statement Upload")\
        .execute()
    
    if not acc_response.data:
        acc_insert = supabase.table("accounts").insert({
            "user_id": request.user_id,
            "account_name": "Statement Upload",
            "account_type": "checking",
            "current_balance": 0.0
        }).execute()
        if not acc_insert.data:
            raise HTTPException(status_code=500, detail="Failed to create statement account")
        account_id = acc_insert.data[0]["account_id"]
    else:
        account_id = acc_response.data[0]["account_id"]

    # 2. Resolve or Seed database categories
    cat_response = supabase.table("categories").select("*").execute()
    db_categories = cat_response.data

    if not db_categories:
        # Seed standard categories if table is empty
        default_categories = [
            {"main_category": "Food & Drinks", "sub_category": "Groceries"},
            {"main_category": "Food & Drinks", "sub_category": "Dining Out"},
            {"main_category": "Food & Drinks", "sub_category": "Cafes & Coffee"},
            {"main_category": "Shopping", "sub_category": "Electronics"},
            {"main_category": "Shopping", "sub_category": "Clothing & Apparel"},
            {"main_category": "Housing", "sub_category": "Rent"},
            {"main_category": "Housing", "sub_category": "Utilities"},
            {"main_category": "Transportation", "sub_category": "Metro & Bus"},
            {"main_category": "Transportation", "sub_category": "Cab & Auto"},
            {"main_category": "Vehicle", "sub_category": "Vehicle EMI"},
            {"main_category": "Life & Entertainment", "sub_category": "Movies & Events"},
            {"main_category": "Life & Entertainment", "sub_category": "Subscriptions"},
            {"main_category": "Financial Expenses", "sub_category": "Bank Charges"},
            {"main_category": "Investments", "sub_category": "Mutual Fund SIP"},
            {"main_category": "Income", "sub_category": "Salary"}
        ]
        supabase.table("categories").insert(default_categories).execute()
        cat_response = supabase.table("categories").select("*").execute()
        db_categories = cat_response.data

    # Match category function
    def find_category_id(main_cat: str, sub_cat: Optional[str]) -> str:
        target_main = map_category_to_db(main_cat)
        
        # Try to match both main and sub (case insensitive)
        if sub_cat:
            for c in db_categories:
                if c["main_category"] == target_main and c["sub_category"].lower() == sub_cat.lower():
                    return c["category_id"]
        
        # Fallback to matching just main category
        for c in db_categories:
            if c["main_category"] == target_main:
                return c["category_id"]
                
        # Ultimate fallback
        return db_categories[0]["category_id"]

    # 3. Batch insert transaction records
    insert_data = []
    total_balance_change = 0.0
    
    for t in request.transactions:
        cat_id = find_category_id(t.category, t.subCategory)
        db_amount = abs(t.amount)
        db_type = t.type.lower()
        if db_type not in ["income", "expense", "transfer"]:
            db_type = "expense"
            
        if db_type == "expense":
            total_balance_change -= db_amount
        elif db_type == "income":
            total_balance_change += db_amount

        insert_data.append({
            "user_id": request.user_id,
            "account_id": account_id,
            "category_id": cat_id,
            "transaction_date": t.date,
            "amount": db_amount,
            "transaction_type": db_type,
            "merchant_name": t.merchant,
            "description": f"Uploaded statement: {t.merchant}"
        })

    # Insert into Supabase
    response = supabase.table("transactions").insert(insert_data).execute()
    if not response.data:
        raise HTTPException(status_code=500, detail="Failed to insert statement transactions")

    # Update account balance with the balance from uploaded statement
    supabase.table("accounts")\
        .update({"current_balance": total_balance_change})\
        .eq("account_id", account_id)\
        .execute()

    return {
        "success": True,
        "inserted_count": len(response.data),
        "account_id": account_id,
        "balance": total_balance_change
    }

@router.get("/api/transactions")
async def api_get_transactions(user_id: str):
    if not supabase:
        # Return empty list in offline/simulation mode so frontend can display standard simulation values gracefully
        return []
        
    response = supabase.table("transactions")\
        .select("transaction_id, transaction_date, amount, transaction_type, merchant_name, description, categories(main_category, sub_category)")\
        .eq("user_id", user_id)\
        .order("transaction_date", desc=True)\
        .execute()
    
    # Flatten categories for cleaner frontend parsing
    formatted = []
    for item in response.data:
        cat_info = item.get("categories", {})
        formatted.append({
            "id": item["transaction_id"],
            "date": item["transaction_date"],
            "amount": -float(item["amount"]) if item["transaction_type"] == "expense" else float(item["amount"]),
            "type": item["transaction_type"],
            "merchant": item["merchant_name"] or "Unknown",
            "description": item["description"] or "",
            "category": cat_info.get("main_category", "Shopping"),
            "subCategory": cat_info.get("sub_category", "General")
        })
    return formatted

@router.post("/api/transactions")
async def api_create_transaction(data: CreateTransactionRequest):
    if not supabase:
        # Simulation fallback
        return {
            "id": "simulated-tx-" + str(json.dumps(data.amount)),
            "date": data.transaction_date,
            "amount": data.amount,
            "type": data.transaction_type,
            "merchant": data.merchant_name or "Unknown",
            "description": data.description or ""
        }
    # 1. Fetch or create checking account
    acc_response = supabase.table("accounts").select("*").eq("user_id", data.user_id).execute()
    if not acc_response.data:
        acc_insert = supabase.table("accounts").insert({
            "user_id": data.user_id,
            "account_name": "Main Checking",
            "account_type": "checking",
            "current_balance": 0.0
        }).execute()
        account_id = acc_insert.data[0]["account_id"]
    else:
        account_id = acc_response.data[0]["account_id"]

    # 2. Fetch DB categories and map category
    cat_response = supabase.table("categories").select("*").execute()
    db_categories = cat_response.data
    
    target_main = map_category_to_db(data.category_name)
    cat_id = None
    for c in db_categories:
        if c["main_category"] == target_main:
            cat_id = c["category_id"]
            break
    if not cat_id:
        cat_id = db_categories[0]["category_id"]

    # 3. Insert transaction
    response = supabase.table("transactions").insert({
        "user_id": data.user_id,
        "account_id": account_id,
        "category_id": cat_id,
        "transaction_date": data.transaction_date,
        "amount": abs(data.amount),
        "transaction_type": data.transaction_type.lower(),
        "merchant_name": data.merchant_name,
        "description": data.description
    }).execute()
    
    if not response.data:
        raise HTTPException(status_code=500, detail="Failed to create transaction")

    item = response.data[0]
    return {
        "id": item["transaction_id"],
        "date": item["transaction_date"],
        "amount": -float(item["amount"]) if item["transaction_type"] == "expense" else float(item["amount"]),
        "type": item["transaction_type"],
        "merchant": item["merchant_name"] or "Unknown",
        "description": item["description"] or ""
    }
