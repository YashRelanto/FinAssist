# pyrefly: ignore [missing-import]
from fastapi import APIRouter
# pyrefly: ignore [missing-import]
from fastapi.responses import HTMLResponse
from app.utils.supabase_client import supabase
import json

router = APIRouter()

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
