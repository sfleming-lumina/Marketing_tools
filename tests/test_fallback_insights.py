import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard_server import DashboardHandler


def test_fallback_uses_live_campaign_recommendations():
    handler = DashboardHandler.__new__(DashboardHandler)
    context = {
        "filters": {"market": "All markets", "source": "All sources"},
        "campaign_planner": {
            "top_recommendations": [
                {
                    "campaign": "Efficient Search",
                    "decision": "Scale",
                    "spend": 10000,
                    "wins": 10,
                    "revenue_per_spend": 8,
                    "cost_per_win": 1000,
                    "lead_to_win_rate": 0.2,
                    "sample_size_bucket": "Sufficient Sample",
                },
                {
                    "campaign": "Weak Events",
                    "decision": "Avoid",
                    "spend": 9000,
                    "wins": 3,
                    "revenue_per_spend": 1.5,
                    "cost_per_win": 3000,
                    "lead_to_win_rate": 0.04,
                    "sample_size_bucket": "Low Sample",
                },
            ]
        },
    }
    insights = handler._fallback_insights("Where should we spend?", context, "fixture")
    rendered = str(insights)
    assert "Weak Events" in rendered
    assert "Efficient Search" in rendered
    assert "actual spend" in insights["executive_summary"]
    assert "capacity-adjusted" not in rendered.lower()
    assert "planned spend" not in rendered.lower()
