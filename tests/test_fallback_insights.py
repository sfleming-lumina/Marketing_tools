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


def test_fallback_answers_from_current_slice_contract():
    handler = DashboardHandler.__new__(DashboardHandler)
    context = {
        "filters": {
            "period": "Last 3 months",
            "campaign": "EnergySage",
            "operatingRegion": "Maryland",
        },
        "summary_metrics": {"spend": 12000, "wins": 6, "cpw": 2000},
        "campaign_breakdown": [
            {"campaign": "EnergySage", "spend": 12000, "wins": 6, "cpw": 2000, "leadToWin": 0.12, "roi": 4.5},
        ],
        "active_decision": {"question": "Should we expand?"},
    }

    insights = handler._fallback_insights("Should we increase budget?", context, "fixture")

    assert "Last 3 months" in insights["executive_summary"]
    assert "EnergySage" in insights["executive_summary"]
    assert "Maryland" in insights["executive_summary"]
    assert "Should we increase budget?" in insights["executive_summary"]


def test_missing_assistant_slice_is_rehydrated_from_governed_data_api():
    handler = DashboardHandler.__new__(DashboardHandler)
    requested = []
    handler._marketing_funnel = lambda params: (requested.append(params) or 200, [{
        "campaign": "EnergySage", "leads": 100, "sets": 40, "runs": 30,
        "wins": 10, "revenue": 400000, "effectiveSpend": 20000,
    }])
    handler._marketing_geo = lambda params: (requested.append(params) or 200, [{
        "geography": "Montgomery County", "opportunityScore": 87,
    }])

    context = handler._ground_assistant_context({
        "query_filters": {"months": 3, "campaign": "EnergySage", "decisionMarket": "DC NORTH WEST", "region": "Maryland"},
    }, allow_data_api_fallback=True)

    assert context["summary_metrics"]["wins"] == 10
    assert context["campaign_breakdown"][0]["campaign"] == "EnergySage"
    assert context["top_geographies"][0]["geography"] == "Montgomery County"
    assert context["data_scope"]["fallback_endpoints"] == ["marketing-funnel", "marketing-geo"]
    assert all(item["decisionMarket"] == ["DC NORTH WEST"] for item in requested)
