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
        .select("transaction_date, amount, transaction_type")\
        .eq("user_id", user_id)\
        .order("transaction_date")\
        .execute()
    
    transactions = trans_response.data
    dates = []
    balances = []
    current_balance = 0
    
    for t in transactions:
        amount = float(t["amount"])
        if t["transaction_type"] == "expense":
            current_balance -= amount
        elif t["transaction_type"] == "income":
            current_balance += amount
        
        dates.append(t["transaction_date"])
        balances.append(current_balance)

    # 2. Fetch Categorical Spending (Donut Chart)
    cat_response = supabase.table("transactions")\
        .select("amount, categories(main_category)")\
        .eq("user_id", user_id)\
        .eq("transaction_type", "expense")\
        .execute()
    
    cat_data = cat_response.data
    spending_by_cat = {}
    for item in cat_data:
        main_cat = item["categories"]["main_category"]
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
