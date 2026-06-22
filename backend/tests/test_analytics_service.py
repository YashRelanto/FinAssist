"""Unit tests for spending analytics service."""

from datetime import datetime

from app.services.analytics_service import (
    build_category_share,
    build_category_trends,
    build_merchant_analytics,
    build_spending_analytics_payload,
    build_spending_behavior,
)


def _txn(date: str, amount: float, category: str, merchant: str = "Store"):
    return {
        "transaction_date": date,
        "amount": amount,
        "transaction_type": "expense",
        "merchant_name": merchant,
        "categories": {"main_category": category},
    }


def test_category_share_percentages():
    rows = [
        _txn("2026-05-01", 300, "Food & Drinks"),
        _txn("2026-05-02", 200, "Shopping"),
        _txn("2026-05-03", 100, "Food & Drinks"),
    ]
    share = build_category_share(rows, start_date="2026-05-01", end_date="2026-05-31")
    assert share[0]["category"] == "Food & Drinks"
    assert share[0]["amount"] == 400
    assert share[0]["pct"] == 66.7


def test_category_trends_mom_change():
    rows = [
        _txn("2026-04-10", 100, "Food & Drinks"),
        _txn("2026-05-10", 200, "Food & Drinks"),
    ]
    trends = build_category_trends(
        rows, start_date="2026-04-01", end_date="2026-05-31"
    )
    assert trends[0]["category"] == "Food & Drinks"
    assert trends[0]["mom_change_pct"] == 100.0


def test_merchant_growth_sorted():
    rows = [
        _txn("2026-04-01", 1000, "Food", "Swiggy"),
        _txn("2026-05-01", 2000, "Food", "Swiggy"),
        _txn("2026-04-01", 500, "Food", "Amazon"),
        _txn("2026-05-01", 600, "Food", "Amazon"),
    ]
    ma = build_merchant_analytics(
        rows,
        start_date="2026-05-01",
        end_date="2026-05-31",
        comparison_start="2026-04-01",
        comparison_end="2026-04-30",
    )
    assert ma["top_merchants"][0]["name"] == "Swiggy"
    assert ma["merchant_growth"][0]["name"] == "Swiggy"
    assert ma["merchant_growth"][0]["growth_pct"] == 100.0
    assert ma["merchant_growth"][0]["growth_display"] == "+100.0%"
    assert "₹1,000" in ma["merchant_growth"][0]["growth_insight"]


def test_merchant_growth_excludes_low_baseline():
    rows = [
        _txn("2026-04-01", 30, "Food", "Barbeque Nation"),
        _txn("2026-05-01", 9386, "Food", "Barbeque Nation"),
        _txn("2026-04-01", 1000, "Food", "Swiggy"),
        _txn("2026-05-01", 1500, "Food", "Swiggy"),
    ]
    ma = build_merchant_analytics(
        rows,
        start_date="2026-05-01",
        end_date="2026-05-31",
        comparison_start="2026-04-01",
        comparison_end="2026-04-30",
    )
    names = [m["name"] for m in ma["merchant_growth"]]
    assert "Barbeque Nation" not in names
    assert names[0] == "Swiggy"


def test_spending_behavior_weekend_multiplier():
    rows = [
        _txn("2026-05-04", 100, "Food"),  # Monday
        _txn("2026-05-09", 300, "Food"),  # Saturday
    ]
    behavior = build_spending_behavior(
        rows, start_date="2026-05-01", end_date="2026-05-31"
    )
    wknd = behavior["weekday_vs_weekend"]
    assert wknd["weekend_total"] == 300
    assert wknd["weekday_total"] == 100
    # May 2026: 21 weekdays, 10 weekend days → avg 100/21 vs 300/10
    assert wknd["weekday_avg_per_day"] == round(100 / 21, 2)
    assert wknd["weekend_avg_per_day"] == round(300 / 10, 2)
    assert wknd["weekend_multiplier"] == round(wknd["weekend_avg_per_day"] / wknd["weekday_avg_per_day"], 2)
    assert wknd["weekend_avg_per_day"] > wknd["weekday_avg_per_day"]
    assert "weekend_insight" in behavior
    assert len(behavior["day_of_week_heatmap"]) == 7


def test_spending_behavior_weekday_heavier_per_day():
    """When weekday avg exceeds weekend avg, multiplier and chart agree."""
    rows = []
    for day in range(1, 29):
        d = f"2026-05-{day:02d}"
        # Weekdays (Mon–Fri in first 4 weeks): high spend; weekends: low spend
        dt = datetime.fromisoformat(d).date()
        if dt.weekday() >= 5:
            rows.append(_txn(d, 50, "Food"))
        else:
            rows.append(_txn(d, 500, "Food"))

    behavior = build_spending_behavior(
        rows, start_date="2026-05-01", end_date="2026-05-28"
    )
    wknd = behavior["weekday_vs_weekend"]
    assert wknd["weekday_avg_per_day"] > wknd["weekend_avg_per_day"]
    assert wknd["weekend_multiplier"] < 1.0
    assert "weekday" in behavior["weekend_insight"].lower()


def test_spending_behavior_heatmap_totals():
    rows = [
        _txn("2026-05-04", 100, "Food"),  # Mon
        _txn("2026-05-05", 200, "Food"),  # Tue
        _txn("2026-05-09", 300, "Food"),  # Sat
    ]
    behavior = build_spending_behavior(
        rows, start_date="2026-05-01", end_date="2026-05-31"
    )
    heatmap = {d["day"]: d["amount"] for d in behavior["day_of_week_heatmap"]}
    assert heatmap["Mon"] == 100
    assert heatmap["Tue"] == 200
    assert heatmap["Sat"] == 300
    assert heatmap["Wed"] == 0
    assert behavior["peak_spending_day"] == "Sat"


def test_build_spending_analytics_payload():
    rows = [
        _txn("2026-05-01", 100, "Food & Drinks", "Swiggy"),
        _txn("2026-05-15", 200, "Shopping", "Amazon"),
    ]
    payload = build_spending_analytics_payload(
        rows,
        period="1m",
        reference=datetime(2026, 5, 20),
    )
    assert payload["success"] is True
    assert payload["total_spend"] == 300
    assert len(payload["category_share"]) >= 1
    assert "merchant_analytics" in payload
    assert "spending_behavior" in payload
