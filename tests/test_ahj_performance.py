import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard_server import build_ahj_performance_query, shape_ahj_row


def test_query_includes_trailing_window_bounds():
    query = build_ahj_performance_query(months=6)
    assert "INTERVAL @months MONTH" in query
    assert "period_grain = 'MONTH'" in query
    assert "GROUP BY market, campaign" in query
    assert "LIMIT 500" in query


def test_query_omits_campaign_condition_when_not_provided():
    query = build_ahj_performance_query()
    assert "campaign_name = @campaign" not in query


def test_query_includes_campaign_condition_when_provided():
    query = build_ahj_performance_query(campaign="Solar Reviews")
    assert "campaign_name = @campaign" in query


def test_query_includes_market_condition_when_provided():
    query = build_ahj_performance_query(market="Fairfax County, VA")
    assert "reporting_market_label = @market" in query


def test_shape_ahj_row_computes_ratios():
    row = {"market": "Fairfax County, VA", "campaign": "Solar Reviews", "leads": 100, "wins": 10, "spend": 10000, "revenue": 50000}
    shaped = shape_ahj_row(row)
    assert shaped["cpw"] == 1000
    assert shaped["revenuePerSpend"] == 5
    assert shaped["leadToWinRate"] == 0.1
    assert shaped["sampleSizeBucket"] == "Sufficient Sample"


def test_shape_ahj_row_handles_zero_wins():
    row = {"market": "Fairfax County, VA", "campaign": "Solar Reviews", "leads": 5, "wins": 0, "spend": 500, "revenue": 0}
    shaped = shape_ahj_row(row)
    assert shaped["cpw"] is None
    assert shaped["revenuePerSpend"] == 0
    assert shaped["leadToWinRate"] == 0
    assert shaped["sampleSizeBucket"] == "Low Sample"


def test_shape_ahj_row_handles_no_same_period_sample():
    row = {"market": "Fairfax County, VA", "campaign": "Solar Reviews", "leads": 0, "wins": 0, "spend": 0, "revenue": 0}
    shaped = shape_ahj_row(row)
    assert shaped["cpw"] is None
    assert shaped["revenuePerSpend"] is None
    assert shaped["leadToWinRate"] is None
    assert shaped["sampleSizeBucket"] == "No Same-Period Sample"


def test_shape_ahj_row_sufficient_sample_boundary():
    row = {"market": "Fairfax County, VA", "campaign": "Solar Reviews", "leads": 20, "wins": 3, "spend": 3000, "revenue": 9000}
    shaped = shape_ahj_row(row)
    assert shaped["sampleSizeBucket"] == "Sufficient Sample"
