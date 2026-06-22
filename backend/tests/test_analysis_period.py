"""Calendar analysis window helpers."""

from datetime import date

from app.utils.analysis_period import resolve_analysis_window


def test_one_month_starts_first_of_current_month():
    w = resolve_analysis_window("1m", reference=date(2026, 6, 5))
    assert w["start_date"] == "2026-06-01"
    assert w["end_date"] == "2026-06-05"
    assert w["comparison_start_date"] == "2026-05-01"
    assert w["comparison_end_date"] == "2026-05-05"
    assert w["comparison_period_label"] == "May 1–5, 2026 (prior month)"


def test_three_month_window():
    w = resolve_analysis_window("3m", reference=date(2026, 6, 5))
    assert w["start_date"] == "2026-04-01"
    assert w["end_date"] == "2026-06-05"
