from app.services.account_hub_analysis_service import (
    _credit_card_context,
    _fallback_account_spending,
    _fallback_credit_alerts,
)


def test_credit_card_near_limit_alert():
    accounts = [
        {
            "account_name": "HDFC Credit",
            "account_type": "credit_card",
            "current_balance": 45000,
            "credit_limit": 50000,
        }
    ]
    cards = _credit_card_context(accounts)
    alerts = _fallback_credit_alerts(cards)
    assert len(alerts) == 1
    assert alerts[0]["account"] == "HDFC Credit"
    assert alerts[0]["utilization_pct"] == 90.0


def test_account_spending_majority_category():
    transactions = [
        {"account": "HDFC", "amount": 1200, "category": "Food & Drinks"},
        {"account": "HDFC", "amount": 300, "category": "Shopping"},
        {"account": "ICICI", "amount": 800, "category": "Transportation"},
    ]
    insights = _fallback_account_spending(transactions)
    by_account = {item["account"]: item for item in insights}
    assert by_account["HDFC"]["majority_category"] == "Food & Drinks"
    assert "Food & Drinks" in by_account["HDFC"]["analysis"]
