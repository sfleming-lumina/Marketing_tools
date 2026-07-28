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


from dashboard_server import DashboardHandler


class FakeQueryResult:
    def __init__(self, rows):
        self._rows = rows

    def result(self):
        return self._rows


class FakeClient:
    def __init__(self, rows):
        self._rows = rows
        self.last_query = None
        self.last_job_config = None

    def query(self, query, job_config=None):
        self.last_query = query
        self.last_job_config = job_config
        return FakeQueryResult(self._rows)


def test_ahj_performance_handler_shapes_rows(monkeypatch):
    fake_rows = [
        {"market": "Fairfax County, VA", "campaign": "Solar Reviews", "leads": 100, "wins": 10, "spend": 10000, "revenue": 50000},
    ]
    monkeypatch.setattr(DashboardHandler, "_client", FakeClient(fake_rows))
    handler = DashboardHandler.__new__(DashboardHandler)
    result = handler._ahj_performance({})
    assert result[0]["market"] == "Fairfax County, VA"
    assert result[0]["cpw"] == 1000


def test_ahj_performance_handler_passes_months_param(monkeypatch):
    fake_client = FakeClient([])
    monkeypatch.setattr(DashboardHandler, "_client", fake_client)
    handler = DashboardHandler.__new__(DashboardHandler)
    handler._ahj_performance({"months": ["3"]})
    param_names = [param.name for param in fake_client.last_job_config.query_parameters]
    assert "months" in param_names


def test_ahj_performance_handler_passes_campaign_and_market_params(monkeypatch):
    fake_client = FakeClient([])
    monkeypatch.setattr(DashboardHandler, "_client", fake_client)
    handler = DashboardHandler.__new__(DashboardHandler)
    handler._ahj_performance({"campaign": ["Solar Reviews"], "market": ["Fairfax County, VA"]})
    param_names = [param.name for param in fake_client.last_job_config.query_parameters]
    assert "campaign" in param_names
    assert "market" in param_names
