# AHJ View Live Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the AHJ view's synthetic demo model with live BigQuery data from `analytics_rpt.rpt_marketing_campaign_ahj_performance`, matching the handoff doc's Recommended Next Steps and the user-approved "Option 1" scope (drop capacity-dependent ranking metrics, simplify Scale/Test/Hold/Avoid gating to CPW-vs-benchmark, lead-to-win rate, and sample-size guardrails).

**Architecture:** A new backend endpoint (`GET /api/ahj-performance`) runs a trailing-window aggregation query against the live BQ view and returns shaped rows (market, campaign, leads, wins, spend, revenue, cpw, revenuePerSpend, leadToWinRate, sampleSizeBucket). The frontend fetches this full unfiltered dataset exactly once per AHJ-tab session (two-tier fetch architecture), caching it in `state.ahjRows`; all campaign/AHJ-focus filtering and ranking then happens 100% client-side against that cached set, exactly as it does today against the synthetic model. The AHJ data/scoring layer and render layer are rewritten in place to consume the new row shape, and `renderAhjPlanner()` becomes `async` to await the fetch.

**Tech Stack:** Python 3.12 stdlib `http.server` + `google-cloud-bigquery` (backend), vanilla JS embedded in a single HTML file (frontend, no framework), Node.js test harnesses with a hand-rolled fake DOM (`work/dom_fake.js`), `pytest` for backend tests, GitHub Actions CI.

## Global Constraints

- Never commit to git in this plan unless the user explicitly asks. Every task's final step is "Do not commit" — this overrides the writing-plans skill's default per-task Commit step.
- Never fix unrelated or pre-existing bugs outside this plan's scope.
- This plan covers the AHJ view only. Overview, Cohorts, Campaigns, and Scenario-baseline views are out of scope and deferred to future plans.
- Per the user-approved "Option 1": the AHJ readiness, Capacity headroom, Margin quality, and Growth-volume-as-capacity-proxy ranking metrics are permanently dropped from the ranking menu in this plan (not deferred as placeholders) — a future capacity-data pass may reintroduce capacity-aware metrics once capacity fields are wired.
- Windows/PowerShell environment. Python at `C:\Users\sflem\AppData\Local\Programs\Python\Python312\python.exe`. Run all Node and Python commands from the repo root `C:\Users\sflem\OneDrive\Documents\Marketing\Marketing_tools`.
- Live source object: `lumina-lakehouse.analytics_rpt.rpt_marketing_campaign_ahj_performance`. Default trailing window: 6 months. Fetch is capped at 500 rows (`ORDER BY leads DESC, spend DESC LIMIT 500`) and happens once per AHJ-tab session; all further filtering (campaign focus, AHJ focus) is client-side against the cached rows.

---

## File Structure

- `dashboard_server.py` (modify) — add `AHJ_TABLE_REF` constant, `build_ahj_performance_query` / `shape_ahj_row` pure functions, `DashboardHandler._ahj_performance` handler method, and the `/api/ahj-performance` GET route.
- `tests/test_ahj_performance.py` (create) — pytest tests for the query builder, row shaper, and handler.
- `.github/workflows/ci.yml` (modify) — add a "Run AHJ performance query tests" step (Python) and a "Verify AHJ scoring logic" step (Node).
- `outputs/marketing_decision_tool.html` (modify) — AHJ view markup (ranking select, area tabs, panel copy), `state` object fields, the AHJ data/scoring function block, the AHJ render function block, and the `ahj_planner` block inside `dashboardContextForClaude()`.
- `work/verify_ahj_scoring.js` (create) — Node harness asserting the AHJ benchmark/decision/ranking logic and the `ahj_planner` context payload shape.
- `work/verify_marketing_tool.js` (modify) — rewritten to mock `fetch` by URL, await the now-async `renderAhjPlanner()`, and assert against a new 60-row AHJ fixture.

---

### Task 1: Backend query builder and row shaper

**Files:**
- Modify: `dashboard_server.py:21` (insert `AHJ_TABLE_REF` after `TABLE_REF`), `dashboard_server.py:45-48` (insert two new functions between the end of `SOURCE_OBJECTS` and `class DashboardHandler`)
- Test: `tests/test_ahj_performance.py`

**Interfaces:**
- Produces: `build_ahj_performance_query(months=6, campaign=None, market=None) -> str`; `shape_ahj_row(row) -> dict` with keys `market, campaign, leads, wins, spend, revenue, cpw, revenuePerSpend, leadToWinRate, sampleSizeBucket`. `row` is any mapping supporting `row["leads"]` etc. (a plain dict in tests, a `google.cloud.bigquery.table.Row` in production).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ahj_performance.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `C:\Users\sflem\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/test_ahj_performance.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_ahj_performance_query' from 'dashboard_server'`

- [ ] **Step 3: Add `AHJ_TABLE_REF`**

In `dashboard_server.py`, immediately after line 21 (`TABLE_REF = f"{PROJECT_ID}.{DATASET}.{TABLE}"`), insert:

```python
AHJ_TABLE_REF = f"{PROJECT_ID}.analytics_rpt.rpt_marketing_campaign_ahj_performance"
```

- [ ] **Step 4: Add the query builder and row shaper**

In `dashboard_server.py`, immediately after the `SOURCE_OBJECTS = [...]` list ends (the `]` on line 45) and before `class DashboardHandler(SimpleHTTPRequestHandler):` (line 48), insert:

```python
def build_ahj_performance_query(months=6, campaign=None, market=None):
    conditions = ["campaign_name IS NOT NULL", "reporting_market_label IS NOT NULL"]
    if campaign:
        conditions.append("campaign_name = @campaign")
    if market:
        conditions.append("reporting_market_label = @market")
    where_clause = " AND ".join(conditions)
    return f"""
        WITH bounds AS (
            SELECT MAX(period_start_date) AS latest_start
            FROM `{AHJ_TABLE_REF}`
            WHERE period_grain = 'MONTH'
        )
        SELECT
            reporting_market_label AS market,
            campaign_name AS campaign,
            SUM(lead_count) AS leads,
            SUM(win_count) AS wins,
            SUM(allocated_spend_amount) AS spend,
            SUM(win_revenue) AS revenue
        FROM `{AHJ_TABLE_REF}`, bounds
        WHERE period_grain = 'MONTH'
            AND period_start_date > DATE_SUB(bounds.latest_start, INTERVAL @months MONTH)
            AND {where_clause}
        GROUP BY market, campaign
        HAVING SUM(allocated_spend_amount) > 0 OR SUM(lead_count) > 0
        ORDER BY leads DESC, spend DESC
        LIMIT 500
    """


def shape_ahj_row(row):
    leads = row["leads"] or 0
    wins = row["wins"] or 0
    spend = row["spend"] or 0
    revenue = row["revenue"] or 0
    if leads == 0 and wins == 0:
        sample_size_bucket = "No Same-Period Sample"
    elif leads < 20 and wins < 3:
        sample_size_bucket = "Low Sample"
    else:
        sample_size_bucket = "Sufficient Sample"
    return {
        "market": row["market"],
        "campaign": row["campaign"],
        "leads": leads,
        "wins": wins,
        "spend": spend,
        "revenue": revenue,
        "cpw": (spend / wins) if wins else None,
        "revenuePerSpend": (revenue / spend) if spend else None,
        "leadToWinRate": (wins / leads) if leads else None,
        "sampleSizeBucket": sample_size_bucket,
    }
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `C:\Users\sflem\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/test_ahj_performance.py -q`
Expected: `7 passed`

- [ ] **Step 6: Do not commit.** Leave the changes staged/unstaged for the user to review.

---

### Task 2: Backend handler and route

**Files:**
- Modify: `dashboard_server.py:93-96` (insert route in `do_GET`), `dashboard_server.py:174-176` (insert `_ahj_performance` method between `_create_note` and `_source_freshness`)
- Test: `tests/test_ahj_performance.py` (append)

**Interfaces:**
- Consumes: `build_ahj_performance_query(months, campaign, market)`, `shape_ahj_row(row)` from Task 1; `self.client` property (existing, `dashboard_server.py:54-58`) backed by `DashboardHandler._client` class attribute.
- Produces: `DashboardHandler._ahj_performance(self, params) -> list[dict]`; `GET /api/ahj-performance?months=&campaign=&market=` route.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ahj_performance.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `C:\Users\sflem\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/test_ahj_performance.py -q`
Expected: FAIL — `AttributeError: 'DashboardHandler' object has no attribute '_ahj_performance'`

- [ ] **Step 3: Add the handler method**

In `dashboard_server.py`, immediately after `_create_note` ends (`return created` on line 174) and before `_source_freshness` (line 176), insert:

```python
    def _ahj_performance(self, params):
        months = int((params.get("months", ["6"])[0]) or "6")
        campaign = (params.get("campaign", [None])[0] or None)
        market = (params.get("market", [None])[0] or None)
        query = build_ahj_performance_query(months=months, campaign=campaign, market=market)
        query_parameters = [bigquery.ScalarQueryParameter("months", "INT64", months)]
        if campaign:
            query_parameters.append(bigquery.ScalarQueryParameter("campaign", "STRING", campaign))
        if market:
            query_parameters.append(bigquery.ScalarQueryParameter("market", "STRING", market))
        job_config = bigquery.QueryJobConfig(query_parameters=query_parameters)
        rows = self.client.query(query, job_config=job_config).result()
        return [shape_ahj_row(row) for row in rows]
```

- [ ] **Step 4: Add the route**

In `dashboard_server.py`'s `do_GET` method, immediately after the `/api/freshness` block ends (`return` on line 95) and before `return super().do_GET()` (line 96), insert:

```python
        if parsed.path == "/api/ahj-performance":
            params = parse_qs(parsed.query)
            self._send_json(HTTPStatus.OK, self._ahj_performance(params))
            return
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `C:\Users\sflem\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/test_ahj_performance.py -q`
Expected: `10 passed`

- [ ] **Step 6: Run the dashboard server syntax check**

Run: `C:\Users\sflem\AppData\Local\Programs\Python\Python312\python.exe -m py_compile dashboard_server.py`
Expected: no output, exit code 0

- [ ] **Step 7: Do not commit.** Leave the changes staged/unstaged for the user to review.

---

### Task 3: CI — run the new backend tests

**Files:**
- Modify: `.github/workflows/ci.yml:45-51`

**Interfaces:**
- Consumes: `tests/test_ahj_performance.py` from Tasks 1-2.
- Produces: a new `test` job step named "Run AHJ performance query tests".

- [ ] **Step 1: Insert the new CI step**

In `.github/workflows/ci.yml`, immediately after the "Check dashboard server syntax" step ends (`python -m py_compile dashboard_server.py` on line 49) and before "Install notes API dependencies" (line 51), insert:

```yaml
      - name: Run AHJ performance query tests
        run: |
          python -m pip install pytest
          python -m pytest tests/test_ahj_performance.py -q
```

- [ ] **Step 2: Review the diff**

Run: `git diff --stat .github/workflows/ci.yml`
Expected: shows only the new step's lines added, no other changes.

- [ ] **Step 3: Re-run the tests locally to confirm no regression**

Run: `C:\Users\sflem\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/test_ahj_performance.py -q`
Expected: `10 passed`

- [ ] **Step 4: Do not commit.** Leave the changes staged/unstaged for the user to review.

---

### Task 4: Frontend HTML and state scaffolding

**Files:**
- Modify: `outputs/marketing_decision_tool.html:1913-1923` (ranking select), `:2000-2005` (area tabs), `:1966`, `:1977`, `:1998` (panel copy), `:2475-2476` (state object)

**Interfaces:**
- Produces: `state.ahjRows` (array, initially empty), `state.ahjRowsFetchKey` (string or null), `state.ahjFetchToken` (number) — consumed by Tasks 5-6.

- [ ] **Step 1: Simplify the ranking select**

In `outputs/marketing_decision_tool.html`, replace:

```html
                <div class="control">
                  <label for="ahjObjective">Rank AHJs by</label>
                  <select id="ahjObjective">
                    <option>Balanced decision score</option>
                    <option>Revenue per spend</option>
                    <option>Lowest cost per win</option>
                    <option>Lead to win rate</option>
                    <option>AHJ readiness</option>
                    <option>Capacity headroom</option>
                    <option>Margin quality</option>
                    <option>Sample confidence</option>
                    <option>Growth volume</option>
                  </select>
                </div>
```

with:

```html
                <div class="control">
                  <label for="ahjObjective">Rank AHJs by</label>
                  <select id="ahjObjective">
                    <option>Balanced decision score</option>
                    <option>Revenue per spend</option>
                    <option>Lowest cost per win</option>
                    <option>Lead to win rate</option>
                    <option>Sample confidence</option>
                  </select>
                </div>
```

- [ ] **Step 2: Drop the Capacity drilldown tab**

Replace:

```html
            <div class="segmented" id="ahjAreaTabs">
              <button class="active" data-ahj-area="efficiency">Efficiency</button>
              <button data-ahj-area="quality">Quality</button>
              <button data-ahj-area="capacity">Capacity</button>
              <button data-ahj-area="growth">Growth</button>
            </div>
```

with:

```html
            <div class="segmented" id="ahjAreaTabs">
              <button class="active" data-ahj-area="efficiency">Efficiency</button>
              <button data-ahj-area="quality">Quality</button>
              <button data-ahj-area="growth">Growth</button>
            </div>
```

- [ ] **Step 3: Update the heatmap panel copy**

Replace:

```html
              <p>Higher scores indicate stronger expected yield after permit, utility, survey, crew, and campaign-fit guardrails.</p>
```

with:

```html
              <p>Higher scores indicate a stronger balanced decision score across cost per win, lead-to-win rate, and sample confidence.</p>
```

- [ ] **Step 4: Update the allocation table panel copy**

Replace:

```html
                <p>Top AHJs for the selected campaign, including volume, cost, conversion, readiness, and decision gate.</p>
```

with:

```html
                <p>Top AHJs for the selected campaign, including volume, cost, conversion, sample size, and decision gate.</p>
```

- [ ] **Step 5: Update the drilldown panel copy**

Replace:

```html
              <p>Investigate why a campaign/AHJ pair is attractive or risky across efficiency, quality, capacity, and growth.</p>
```

with:

```html
              <p>Investigate why a campaign/AHJ pair is attractive or risky across efficiency, quality, and growth.</p>
```

- [ ] **Step 6: Add the new state fields**

Replace:

```javascript
      selectedAhj: "All AHJs",
      shifts: { "Paid Search": 10, "Referral": 18, "Events": -8, capacityBuffer: 8 }
```

with:

```javascript
      selectedAhj: "All AHJs",
      ahjRows: [],
      ahjRowsFetchKey: null,
      ahjFetchToken: 0,
      shifts: { "Paid Search": 10, "Referral": 18, "Events": -8, capacityBuffer: 8 }
```

- [ ] **Step 7: Confirm no regression**

Run: `node work/verify_marketing_tool.js`
Expected: exits 0 and prints the JSON summary (the existing harness does not inspect option counts or the removed copy strings, so it should still pass unchanged).

- [ ] **Step 8: Do not commit.** Leave the changes staged/unstaged for the user to review.

---

### Task 5: Frontend AHJ data/scoring layer rewrite

**Files:**
- Modify: `outputs/marketing_decision_tool.html:3836-4075` (replace the entire block from `activeAhjProfiles()` through the end of `ahjDecisionRows()`)
- Also delete: `outputs/marketing_decision_tool.html:2177-2190` (`ahjCountyProfiles` array — no longer referenced by any function after this task and Task 6)
- Create: `work/verify_ahj_scoring.js`

**Interfaces:**
- Consumes: `state.ahjRows` (Task 4), `escapeAttr`, `fmtCurrency`, `fmtNum`, `pct` (existing helpers, unchanged).
- Produces: `ahjBenchmarks(rows) -> { cpw, leadToWinRate }`; `ahjSampleConfidenceRank(bucket) -> number` (2/1/0); `ahjDecisionFor(row) -> "Scale"|"Test"|"Hold"|"Avoid"`; `ahjRankingValue(row, metric) -> number`; `ahjMetricDisplay(row, metric) -> string`; `ahjBaseDecisionRows() -> array`; `ahjCampaignOptions() -> array`; `selectedAhjCampaignLabel() -> string` (unchanged); `selectedAhjLabel() -> string`; `setAhjSelection(ahjKey, campaign)` (unchanged); `ahjDecisionRows(options = {}) -> array` of rows with fields `market, campaign, leads, wins, spend, revenue, cpw, revenuePerSpend, leadToWinRate, sampleSizeBucket, ahjKey, key, cpwBenchmark, leadToWinBenchmark, decision, suggestedTestSpend, nextTenKWins, nextTenKRevenue, metricValue, metricDisplay` — consumed by Task 6's render layer and Task 7's context block.

**Note:** `work/verify_marketing_tool.js` will fail if run after this task and before Task 6 (the render layer still references the deleted profile-based functions). Do not run it in this task — only run `work/verify_ahj_scoring.js`, which never calls a render function and is fully insulated from that intermediate state.

- [ ] **Step 1: Delete the now-unused `ahjCountyProfiles` array**

In `outputs/marketing_decision_tool.html`, delete:

```javascript
    const ahjCountyProfiles = [
      { key: "dc-district", county: "District of Columbia", ahj: "DCRA / DOB", region: "DC Metro", state: "DC", permit: 73, utility: 66, crew: 72, survey: 69, cancel: 48, demand: 1.08, mediaCost: 1.12, density: 88, reviewIntent: 76, mailFit: 54, partnerFit: 58, eventFit: 70, batteryFit: 72, capacitySlots: 46 },
      { key: "montgomery-md", county: "Montgomery County", ahj: "Montgomery DPS", region: "Maryland Suburbs", state: "MD", permit: 79, utility: 73, crew: 79, survey: 76, cancel: 41, demand: 1.14, mediaCost: 1.02, density: 77, reviewIntent: 82, mailFit: 74, partnerFit: 70, eventFit: 66, batteryFit: 78, capacitySlots: 62 },
      { key: "prince-georges-md", county: "Prince George's County", ahj: "PG County DPIE", region: "Maryland Suburbs", state: "MD", permit: 70, utility: 67, crew: 76, survey: 72, cancel: 47, demand: 1.02, mediaCost: 0.98, density: 73, reviewIntent: 69, mailFit: 80, partnerFit: 62, eventFit: 72, batteryFit: 64, capacitySlots: 55 },
      { key: "fairfax-va", county: "Fairfax County", ahj: "Fairfax Land Development", region: "Northern Virginia", state: "VA", permit: 84, utility: 77, crew: 81, survey: 79, cancel: 38, demand: 1.2, mediaCost: 1.08, density: 80, reviewIntent: 88, mailFit: 70, partnerFit: 76, eventFit: 67, batteryFit: 81, capacitySlots: 68 },
      { key: "loudoun-va", county: "Loudoun County", ahj: "Loudoun Building & Development", region: "Northern Virginia", state: "VA", permit: 81, utility: 76, crew: 78, survey: 77, cancel: 40, demand: 1.12, mediaCost: 1.01, density: 64, reviewIntent: 80, mailFit: 66, partnerFit: 84, eventFit: 58, batteryFit: 76, capacitySlots: 58 },
      { key: "arlington-va", county: "Arlington County", ahj: "Arlington CPHD", region: "Northern Virginia", state: "VA", permit: 77, utility: 72, crew: 74, survey: 75, cancel: 43, demand: 1.06, mediaCost: 1.15, density: 86, reviewIntent: 79, mailFit: 58, partnerFit: 61, eventFit: 73, batteryFit: 73, capacitySlots: 42 },
      { key: "baltimore-county-md", county: "Baltimore County", ahj: "Baltimore County Permits", region: "Baltimore", state: "MD", permit: 66, utility: 63, crew: 70, survey: 67, cancel: 53, demand: 0.95, mediaCost: 0.92, density: 67, reviewIntent: 63, mailFit: 78, partnerFit: 67, eventFit: 80, batteryFit: 59, capacitySlots: 48 },
      { key: "baltimore-city-md", county: "Baltimore City", ahj: "Baltimore DHCD", region: "Baltimore", state: "MD", permit: 58, utility: 60, crew: 66, survey: 62, cancel: 59, demand: 0.88, mediaCost: 0.88, density: 82, reviewIntent: 57, mailFit: 60, partnerFit: 52, eventFit: 78, batteryFit: 55, capacitySlots: 36 },
      { key: "chester-pa", county: "Chester County", ahj: "County / municipal AHJs", region: "Southeast PA", state: "PA", permit: 76, utility: 71, crew: 73, survey: 74, cancel: 44, demand: 1.07, mediaCost: 0.97, density: 63, reviewIntent: 74, mailFit: 82, partnerFit: 78, eventFit: 61, batteryFit: 75, capacitySlots: 54 },
      { key: "bucks-pa", county: "Bucks County", ahj: "County / municipal AHJs", region: "Southeast PA", state: "PA", permit: 72, utility: 70, crew: 71, survey: 73, cancel: 46, demand: 1.03, mediaCost: 0.96, density: 66, reviewIntent: 71, mailFit: 84, partnerFit: 73, eventFit: 64, batteryFit: 70, capacitySlots: 50 },
      { key: "lancaster-pa", county: "Lancaster County", ahj: "County / municipal AHJs", region: "Central PA", state: "PA", permit: 65, utility: 68, crew: 64, survey: 63, cancel: 51, demand: 0.9, mediaCost: 0.87, density: 48, reviewIntent: 58, mailFit: 86, partnerFit: 69, eventFit: 57, batteryFit: 62, capacitySlots: 39 },
      { key: "dauphin-pa", county: "Dauphin County", ahj: "County / municipal AHJs", region: "Central PA", state: "PA", permit: 61, utility: 66, crew: 62, survey: 61, cancel: 54, demand: 0.84, mediaCost: 0.84, density: 52, reviewIntent: 54, mailFit: 78, partnerFit: 64, eventFit: 59, batteryFit: 58, capacitySlots: 34 }
    ];
```

(Delete the whole array; leave the surrounding `campaignTactics` declaration before it and `campaignSegments` after it untouched.)

- [ ] **Step 2: Write the failing test**

Create `work/verify_ahj_scoring.js`:

```javascript
const { installFakeDom, loadDashboardScript } = require("./dom_fake");

installFakeDom();
global.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) });

const script = loadDashboardScript();
const run = new Function(`${script}
state.ahjRows = [
  { market: "Fairfax County, VA", campaign: "Solar Reviews", leads: 400, wins: 80, spend: 80000, revenue: 800000, cpw: 1000, revenuePerSpend: 10, leadToWinRate: 0.2, sampleSizeBucket: "Sufficient Sample" },
  { market: "Loudoun County, VA", campaign: "Solar Reviews", leads: 0, wins: 0, spend: 5000, revenue: 0, cpw: null, revenuePerSpend: 0, leadToWinRate: 0, sampleSizeBucket: "No Same-Period Sample" },
  { market: "Prince George's County, MD", campaign: "Solar Reviews", leads: 100, wins: 20, spend: 45000, revenue: 90000, cpw: 2250, revenuePerSpend: 2, leadToWinRate: 0.2, sampleSizeBucket: "Sufficient Sample" }
];
state.ahjCampaign = "Solar Reviews";
state.selectedAhj = "All AHJs";
const benchmarks = ahjBenchmarks(state.ahjRows);
const rows = ahjDecisionRows();
return {
  benchmarks,
  rows,
  sampleRanks: {
    sufficient: ahjSampleConfidenceRank("Sufficient Sample"),
    low: ahjSampleConfidenceRank("Low Sample"),
    none: ahjSampleConfidenceRank("No Same-Period Sample")
  }
};`);

const output = run();

if (output.benchmarks.cpw !== 1250) {
  console.error(`Expected blended CPW benchmark of 1250, got ${output.benchmarks.cpw}.`);
  process.exit(1);
}

const fairfax = output.rows.find(row => row.market === "Fairfax County, VA");
if (!fairfax || fairfax.decision !== "Scale") {
  console.error(`Expected Fairfax County, VA to resolve to Scale, got ${fairfax && fairfax.decision}.`);
  process.exit(1);
}

const loudoun = output.rows.find(row => row.market === "Loudoun County, VA");
if (!loudoun || loudoun.decision !== "Avoid") {
  console.error(`Expected Loudoun County, VA to resolve to Avoid, got ${loudoun && loudoun.decision}.`);
  process.exit(1);
}

if (output.sampleRanks.sufficient !== 2 || output.sampleRanks.low !== 1 || output.sampleRanks.none !== 0) {
  console.error("ahjSampleConfidenceRank did not map sample-size buckets to the expected ranks.");
  console.error(JSON.stringify(output.sampleRanks));
  process.exit(1);
}

console.log(JSON.stringify({
  blendedCpw: output.benchmarks.cpw,
  leadToWinBenchmark: output.benchmarks.leadToWinRate,
  rowCount: output.rows.length,
  fairfaxDecision: fairfax.decision,
  loudounDecision: loudoun.decision
}, null, 2));
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `node work/verify_ahj_scoring.js`
Expected: FAIL — `TypeError: ahjBenchmarks is not a function` (the function does not exist yet).

- [ ] **Step 4: Replace the data/scoring layer**

In `outputs/marketing_decision_tool.html`, replace the entire block starting at `function activeAhjProfiles() {` and ending at the closing of `ahjDecisionRows` (the `}` before `function renderAhjFocusSelect(rows) {`) with:

```javascript
    function ahjBenchmarks(rows) {
      const totalWins = rows.reduce((sum, row) => sum + (row.wins || 0), 0);
      const totalSpend = rows.reduce((sum, row) => sum + (row.spend || 0), 0);
      const totalLeads = rows.reduce((sum, row) => sum + (row.leads || 0), 0);
      return {
        cpw: totalWins > 0 ? totalSpend / totalWins : 1100,
        leadToWinRate: totalLeads > 0 ? totalWins / totalLeads : 0.2
      };
    }

    function ahjDecisionFor(row) {
      const cpwBenchmark = row.cpwBenchmark;
      const leadToWinBenchmark = row.leadToWinBenchmark;
      const hasSample = row.sampleSizeBucket !== "No Same-Period Sample";
      if (!hasSample) return "Avoid";
      const cpwRatio = row.cpw ? row.cpw / Math.max(1, cpwBenchmark) : Infinity;
      const leadToWinRate = row.leadToWinRate || 0;
      if (
        row.sampleSizeBucket === "Sufficient Sample" &&
        cpwRatio <= 1 &&
        leadToWinRate >= leadToWinBenchmark
      ) {
        return "Scale";
      }
      if (cpwRatio <= 1.45 && leadToWinRate >= leadToWinBenchmark * 0.7) {
        return "Test";
      }
      if (cpwRatio <= 2.15) {
        return "Hold";
      }
      return "Avoid";
    }

    function ahjRankingValue(row, metric = state.ahjObjective) {
      const cpwRatio = row.cpw ? row.cpw / Math.max(1, row.cpwBenchmark) : 2;
      if (metric === "Revenue per spend") return row.revenuePerSpend || 0;
      if (metric === "Lowest cost per win") return 100 / Math.max(0.2, cpwRatio);
      if (metric === "Lead to win rate") return (row.leadToWinRate || 0) * 1000;
      if (metric === "Sample confidence") return ahjSampleConfidenceRank(row.sampleSizeBucket) * 28 + Math.log1p(row.leads) * 4 + Math.log1p(row.wins) * 10;
      return Math.max(0, 22 - cpwRatio * 12) +
        (row.leadToWinRate || 0) * 180 +
        Math.min(24, (row.revenuePerSpend || 0) * 0.55) +
        ahjSampleConfidenceRank(row.sampleSizeBucket) * 6;
    }

    function ahjMetricDisplay(row, metric = state.ahjObjective) {
      if (metric === "Revenue per spend") return `${(row.revenuePerSpend || 0).toFixed(1)}x rev/spend`;
      if (metric === "Lowest cost per win") return row.cpw ? `${fmtCurrency(row.cpw)} CPW` : "No wins yet";
      if (metric === "Lead to win rate") return `${pct(row.leadToWinRate || 0)} lead-to-win`;
      if (metric === "Sample confidence") return row.sampleSizeBucket;
      return `${Math.round(ahjRankingValue(row, "Balanced decision score"))} score`;
    }

    function ahjSampleConfidenceRank(bucket) {
      if (bucket === "Sufficient Sample") return 2;
      if (bucket === "Low Sample") return 1;
      return 0;
    }

    function ahjBaseDecisionRows() {
      const benchmarks = ahjBenchmarks(state.ahjRows);
      return state.ahjRows.map(row => {
        const enriched = {
          ...row,
          ahjKey: row.market,
          key: `${row.market}:${row.campaign}`,
          cpwBenchmark: benchmarks.cpw,
          leadToWinBenchmark: benchmarks.leadToWinRate
        };
        return { ...enriched, decision: ahjDecisionFor(enriched) };
      });
    }

    function ahjCampaignOptions() {
      const options = [...new Set(state.ahjRows.map(row => row.campaign))].sort();
      return ["All campaigns", ...options];
    }

    function selectedAhjCampaignLabel() {
      if (state.ahjCampaign === "All campaigns") return "All campaigns";
      return state.ahjCampaign;
    }

    function selectedAhjLabel() {
      return state.selectedAhj === "All AHJs" ? "All AHJs" : state.selectedAhj;
    }

    function setAhjSelection(ahjKey, campaign) {
      if (ahjKey) state.selectedAhj = ahjKey;
      if (campaign && campaign !== "All campaigns") state.ahjCampaign = campaign;
      renderAhjPlanner();
    }

    function ahjDecisionRows(options = {}) {
      const rows = ahjBaseDecisionRows();
      const filtered = rows.filter(row =>
        (options.ignoreAhj || state.selectedAhj === "All AHJs" || row.ahjKey === state.selectedAhj) &&
        (options.ignoreCampaign || state.ahjCampaign === "All campaigns" || row.campaign === state.ahjCampaign)
      );
      return filtered.map(row => {
        const suggestedTestSpend = row.decision === "Scale"
          ? Math.min(65000, Math.max(18000, row.spend * 0.28))
          : row.decision === "Test"
            ? Math.min(30000, Math.max(8000, row.spend * 0.16))
            : 0;
        const nextTenKWins = row.cpw ? 10000 / row.cpw : 0;
        const nextTenKRevenue = 10000 * (row.revenuePerSpend || 0);
        const enriched = { ...row, suggestedTestSpend, nextTenKWins, nextTenKRevenue };
        return { ...enriched, metricValue: ahjRankingValue(enriched), metricDisplay: ahjMetricDisplay(enriched) };
      }).sort((a, b) => b.metricValue - a.metricValue);
    }
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `node work/verify_ahj_scoring.js`
Expected: exits 0 and prints a JSON summary showing `blendedCpw: 1250`, `fairfaxDecision: "Scale"`, `loudounDecision: "Avoid"`.

- [ ] **Step 6: Do not commit.** Leave the changes staged/unstaged for the user to review.

---

### Task 6: Frontend AHJ render layer rewrite and async fetch wiring

**Files:**
- Modify: `outputs/marketing_decision_tool.html:4077-4471` (replace the entire block from `renderAhjFocusSelect` through the end of `renderAhjPlanner`)
- Modify: `work/verify_marketing_tool.js` (full rewrite)

**Interfaces:**
- Consumes: `ahjBenchmarks`, `ahjSampleConfidenceRank`, `ahjDecisionFor`, `ahjRankingValue`, `ahjMetricDisplay`, `ahjBaseDecisionRows`, `ahjCampaignOptions`, `selectedAhjCampaignLabel`, `selectedAhjLabel`, `setAhjSelection`, `ahjDecisionRows` (Task 5); `NOTES_API_BASE` (existing, `outputs/marketing_decision_tool.html:2298`); `state.ahjRows` / `state.ahjRowsFetchKey` / `state.ahjFetchToken` (Task 4).
- Produces: `ahjCurrentFetchKey() -> string`; `ensureAhjRowsLoaded() -> Promise<void>` (populates `state.ahjRows`); `renderAhjPlanner() -> Promise<void>` (now async — no caller changes needed since the dispatcher at `render()` and the AHJ control event listeners already call it unawaited/fire-and-forget).

- [ ] **Step 1: Write the failing test — rewrite `work/verify_marketing_tool.js`**

Replace the full contents of `work/verify_marketing_tool.js` with:

```javascript
const { installFakeDom, loadDashboardScript } = require("./dom_fake");

installFakeDom();

function fixtureRow(market, campaign, marketIndex, campaignIndex) {
  const costPerLead = [60, 75, 90, 105, 120][campaignIndex];
  const winRate = [0.05, 0.07, 0.09, 0.05, 0.07][campaignIndex];
  const leads = 40 + marketIndex * 11 + campaignIndex * 7;
  const wins = Math.max(1, Math.round(leads * winRate));
  const spend = leads * costPerLead;
  const revenue = wins * (9000 + marketIndex * 300);
  const cpw = spend / wins;
  const revenuePerSpend = revenue / spend;
  const leadToWinRate = wins / leads;
  const sampleSizeBucket = leads >= 20 && wins >= 3 ? "Sufficient Sample" : "Low Sample";
  return { market, campaign, leads, wins, spend, revenue, cpw, revenuePerSpend, leadToWinRate, sampleSizeBucket };
}

const MARKETS = [
  "District of Columbia",
  "Montgomery County, MD",
  "Prince George's County, MD",
  "Fairfax County, VA",
  "Loudoun County, VA",
  "Arlington County, VA",
  "Baltimore County, MD",
  "Baltimore City, MD",
  "Chester County, PA",
  "Bucks County, PA",
  "Lancaster County, PA",
  "Dauphin County, PA"
];
const CAMPAIGNS = ["Solar Reviews", "Google Brand Defense", "Customer Referral Bonus", "EnergySage", "Home Shows"];

const ahjFixtureRows = [];
MARKETS.forEach((market, marketIndex) => {
  CAMPAIGNS.forEach((campaign, campaignIndex) => {
    ahjFixtureRows.push(fixtureRow(market, campaign, marketIndex, campaignIndex));
  });
});

Object.assign(
  ahjFixtureRows.find(row => row.market === "Fairfax County, VA" && row.campaign === "Solar Reviews"),
  { leads: 500, wins: 100, spend: 80000, revenue: 900000, cpw: 800, revenuePerSpend: 11.25, leadToWinRate: 0.2, sampleSizeBucket: "Sufficient Sample" }
);

Object.assign(
  ahjFixtureRows.find(row => row.market === "Dauphin County, PA" && row.campaign === "Solar Reviews"),
  { leads: 10, wins: 0, spend: 15000, revenue: 0, cpw: null, revenuePerSpend: 0, leadToWinRate: 0, sampleSizeBucket: "Low Sample" }
);

global.fetch = url => {
  if (String(url).includes("ahj-performance")) {
    return Promise.resolve({ ok: true, json: () => Promise.resolve(ahjFixtureRows) });
  }
  return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
};

const script = loadDashboardScript();
const run = new Function(`${script}
return (async () => {
  state.view = "campaigns";
  renderCampaignPlanner();
  state.view = "ahj";
  await renderAhjPlanner();
  state.view = "overview";
  renderTrendExplorer();
  return {
    heatmap: document.getElementById("campaignHeatmap").innerHTML,
    ahjHeatmap: document.getElementById("ahjHeatmap").innerHTML,
    ahjMetrics: document.getElementById("ahjMetrics").innerHTML,
    ahjInsights: document.getElementById("ahjImmediateInsights").innerHTML,
    ahjTable: document.getElementById("ahjAllocationTable").innerHTML,
    ahjDetail: document.getElementById("ahjDetail").innerHTML,
    ahjCanvas: document.getElementById("ahjInvestigationCanvas").innerHTML,
    ahjBreakdown: document.getElementById("ahjPerformanceBreakdown").innerHTML,
    cards: document.getElementById("campaignCards").innerHTML,
    moves: document.getElementById("campaignMoves").innerHTML,
    suite: document.getElementById("decisionMetricSuite").innerHTML,
    table: document.getElementById("campaignTable").innerHTML,
    metrics: document.getElementById("campaignMetrics").innerHTML,
    trend: document.getElementById("campaignTrendChart").innerHTML,
    explorer: document.getElementById("trendExplorerChart").innerHTML,
    summary: document.getElementById("trendSummary").innerHTML
  };
})();`);

run().then(output => {
  const joined = Object.values(output).join("\\n");
  if (/NaN|null|undefined/.test(joined)) {
    console.error("Invalid token found in rendered campaign planner output.");
    const match = joined.match(/.{0,80}(NaN|null|undefined).{0,80}/);
    if (match) console.error(match[0]);
    process.exit(1);
  }

  const retiredRegionPattern = /Texas|Northeast|Mid-Atlantic|Southeast(?! PA)|\\bWest\\b/;
  if (retiredRegionPattern.test(output.heatmap)) {
    console.error("Retired national region labels should not render in the campaign heatmap.");
    process.exit(1);
  }

  const heatmapScores = [...output.heatmap.matchAll(/<strong>(\\d+)<\\/strong>/g)].map(match => Number(match[1]));
  if (heatmapScores.length !== 30) {
    console.error(`Expected 30 campaign heatmap scores for six DMV/PA markets, found ${heatmapScores.length}.`);
    process.exit(1);
  }

  if (new Set(heatmapScores).size < 3) {
    console.error("Campaign heatmap scores are not varied enough.");
    console.error(heatmapScores.join(", "));
    process.exit(1);
  }

  const ahjScores = [...output.ahjHeatmap.matchAll(/<strong>(\\d+)<\\/strong>/g)].map(match => Number(match[1]));
  if (ahjScores.length !== 60) {
    console.error(`Expected 60 AHJ heatmap scores for twelve markets and five campaigns, found ${ahjScores.length}.`);
    process.exit(1);
  }

  if (new Set(ahjScores).size < 5) {
    console.error("AHJ heatmap scores are not varied enough.");
    console.error(ahjScores.join(", "));
    process.exit(1);
  }

  const renderedMarketCount = (output.ahjTable.match(/<strong>[^<]+County|<strong>District of Columbia/g) || []).length;
  if (
    renderedMarketCount < 6 ||
    !output.ahjDetail.includes("Solar Reviews") ||
    !output.ahjTable.includes("CPW") ||
    !output.ahjTable.includes("Selected metric") ||
    !output.ahjCanvas.includes("Solar Reviews") ||
    !output.ahjCanvas.includes("ahj-click-card") ||
    !output.ahjInsights.includes("Scale") ||
    !output.ahjTable.includes("Avoid") ||
    !output.ahjBreakdown.includes("rev/spend")
  ) {
    console.error("AHJ planner did not render expected market recommendations and drilldown.");
    process.exit(1);
  }

  if (!output.explorer.includes("Prior month") || !output.summary.includes("Latest")) {
    console.error("Trend explorer did not render expected MOM comparison content.");
    process.exit(1);
  }

  console.log(JSON.stringify({
    heatmapLength: output.heatmap.length,
    heatmapScoreCount: heatmapScores.length,
    uniqueHeatmapScores: new Set(heatmapScores).size,
    ahjHeatmapLength: output.ahjHeatmap.length,
    ahjHeatmapScoreCount: ahjScores.length,
    uniqueAhjHeatmapScores: new Set(ahjScores).size,
    ahjTableLength: output.ahjTable.length,
    ahjDetailLength: output.ahjDetail.length,
    ahjCanvasLength: output.ahjCanvas.length,
    ahjBreakdownLength: output.ahjBreakdown.length,
    cardsLength: output.cards.length,
    movesLength: output.moves.length,
    suiteLength: output.suite.length,
    tableLength: output.table.length,
    metricsLength: output.metrics.length,
    trendLength: output.trend.length,
    explorerLength: output.explorer.length,
    summaryLength: output.summary.length
  }, null, 2));
}).catch(error => {
  console.error(error);
  process.exit(1);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node work/verify_marketing_tool.js`
Expected: FAIL — a runtime error such as `activeAhjProfiles is not defined` or `renderAhjPlanner(...).then is not a function`, since the render layer still references symbols deleted in Task 5 and `renderAhjPlanner` is not yet async.

- [ ] **Step 3: Replace the render layer and add async fetch wiring**

In `outputs/marketing_decision_tool.html`, replace the entire block starting at `function renderAhjFocusSelect(rows) {` and ending at the closing `}` of `renderAhjPlanner` (immediately before `function scenarioMultiplier(source) {`) with:

```javascript
    function renderAhjFocusSelect(rows) {
      const select = document.getElementById("ahjFocusSelect");
      const markets = [...new Set(state.ahjRows.map(row => row.market))].sort();
      const campaignSelect = document.getElementById("ahjCampaignSelect");
      const campaignOptions = ahjCampaignOptions();
      if (!campaignOptions.includes(state.ahjCampaign)) {
        state.ahjCampaign = "All campaigns";
      }
      if (state.selectedAhj !== "All AHJs" && !markets.includes(state.selectedAhj)) {
        state.selectedAhj = "All AHJs";
      }
      campaignSelect.innerHTML = campaignOptions.map(option => `<option value="${escapeAttr(option)}"${option === state.ahjCampaign ? " selected" : ""}>${escapeAttr(option)}</option>`).join("");
      select.innerHTML = [
        `<option value="All AHJs"${state.selectedAhj === "All AHJs" ? " selected" : ""}>All AHJs</option>`,
        ...markets.map(market => `<option value="${escapeAttr(market)}"${market === state.selectedAhj ? " selected" : ""}>${escapeAttr(market)}</option>`)
      ].join("");
      document.getElementById("ahjObjective").value = state.ahjObjective;
      document.getElementById("ahjLayoutSelect").value = state.ahjLayout;
    }

    function renderAhjMetrics(rows) {
      const top = rows[0] || {};
      const wins = rows.reduce((sum, row) => sum + row.wins, 0);
      const revenue = rows.reduce((sum, row) => sum + row.revenue, 0);
      const spend = rows.reduce((sum, row) => sum + row.spend, 0);
      const blendedCpw = rows.filter(row => row.cpw).reduce((sum, row) => sum + row.cpw * row.wins, 0) / Math.max(1, wins);
      const scaleReady = new Set(rows.filter(row => row.decision === "Scale").map(row => row.ahjKey)).size;
      const testReady = new Set(rows.filter(row => row.decision === "Test").map(row => row.ahjKey)).size;
      const holdAvoid = rows.filter(row => row.decision === "Hold" || row.decision === "Avoid").length;
      const risk = [...rows].filter(row => row.cpw).sort((a, b) => b.cpw - a.cpw)[0] || {};
      const metrics = [
        ["Top AHJ candidate", top.market || "n/a", top.campaign || "No AHJ rows", top.decision === "Scale" ? "good" : top.decision === "Test" ? "warn" : "bad"],
        ["Ranking metric", state.ahjObjective, selectedAhjCampaignLabel(), "good"],
        ["Top metric value", top.metricDisplay || "n/a", top.market || "n/a", top.decision === "Scale" ? "good" : "warn"],
        ["Scale-ready AHJs", fmtNum(scaleReady), `${testReady} test candidates`, scaleReady >= 3 ? "good" : scaleReady >= 1 ? "warn" : "bad"],
        ["Hold/Avoid gates", fmtNum(holdAvoid), `${rows.length} AHJ/campaign rows reviewed`, holdAvoid >= rows.length / 2 ? "good" : "warn"],
        ["Campaign CPW", fmtCurrency(blendedCpw), `${fmtNum(wins)} modeled wins`, blendedCpw <= (top.cpwBenchmark || 1200) ? "good" : "warn"],
        ["Campaign revenue", fmtCurrency(revenue), `${(revenue / Math.max(1, spend)).toFixed(1)}x rev/spend`, "good"],
        ["Highest CPW risk", risk.market || "n/a", risk.cpw ? `${fmtCurrency(risk.cpw)} with ${risk.campaign}` : "n/a", "warn"],
        ["Selected focus", selectedAhjLabel(), selectedAhjCampaignLabel(), "good"]
      ];
      document.getElementById("ahjMetrics").innerHTML = metrics.map(metricCardHtml).join("");
      wireTips(document.getElementById("ahjMetrics"));
      wireNoteChips(document.getElementById("ahjMetrics"));
    }

    function renderAhjInsights(rows) {
      const top = rows[0];
      const weak = [...rows].filter(row => row.cpw).sort((a, b) => b.cpw - a.cpw)[0] || rows[0];
      const sampleLeader = [...rows].sort((a, b) => ahjSampleConfidenceRank(b.sampleSizeBucket) - ahjSampleConfidenceRank(a.sampleSizeBucket) || b.leads - a.leads)[0];
      const cards = [top, weak, sampleLeader].filter(Boolean).map((row, index) => {
        if (index === 0) {
          const action = row.decision === "Scale" ? "Scale" : row.decision === "Test" ? "Test" : "Do not scale";
          return decisionCardHtml({
            key: `ahj:insight:top:${row.key}`,
            title: `${action}: ${row.campaign} in ${row.market}`,
            body: row.decision === "Scale"
              ? `${row.market} clears the strict scale gate on cost per win, lead-to-win rate, and sample size.`
              : `${row.market} is the best candidate in this cut, but it should stay in ${row.decision} until the weaker gate clears.`,
            pills: [`${fmtCurrency(row.spend)} spend`, `${fmtNum(row.wins)} wins`, row.cpw ? `${fmtCurrency(row.cpw)} CPW` : "No wins yet", row.sampleSizeBucket],
            tone: row.decision === "Scale" ? "good" : row.decision === "Test" ? "warn" : "bad"
          });
        }
        if (index === 1) {
          return decisionCardHtml({
            key: `ahj:insight:risk:${row.key}`,
            title: `Guardrail ${row.market}`,
            body: `${row.campaign} carries the highest cost per win in this cut; protect spend unless conversion improves.`,
            pills: [row.cpw ? `${fmtCurrency(row.cpw)} CPW` : "No wins yet", `${pct(row.leadToWinRate || 0)} lead-to-win`, row.sampleSizeBucket, row.decision],
            tone: row.decision === "Avoid" ? "bad" : "warn"
          });
        }
        return decisionCardHtml({
          key: `ahj:insight:sample:${row.key}`,
          title: `Sample-confidence leader: ${row.market}`,
          body: `${row.campaign} has the deepest same-period sample in this cut, making its selected metric the most trustworthy read.`,
          pills: [row.sampleSizeBucket, `${fmtNum(row.leads)} leads`, `${fmtNum(row.wins)} wins`],
          tone: "good"
        });
      }).join("");
      document.getElementById("ahjImmediateInsights").innerHTML = cards;
      wireNoteChips(document.getElementById("ahjImmediateInsights"));
    }

    function renderAhjHeatmap(rows) {
      const allRows = ahjDecisionRows({ ignoreCampaign: true });
      const marketTotals = {};
      state.ahjRows.forEach(row => {
        marketTotals[row.market] = (marketTotals[row.market] || 0) + row.leads;
      });
      const markets = Object.keys(marketTotals).sort((a, b) => marketTotals[b] - marketTotals[a]).slice(0, 12);
      const campaignTotals = {};
      state.ahjRows.forEach(row => {
        campaignTotals[row.campaign] = (campaignTotals[row.campaign] || 0) + row.leads;
      });
      const allCampaigns = Object.keys(campaignTotals).sort((a, b) => campaignTotals[b] - campaignTotals[a]);
      const selectedCampaign = state.ahjCampaign === "All campaigns" ? null : state.ahjCampaign;
      const columns = [
        ...(selectedCampaign ? [selectedCampaign] : []),
        ...allCampaigns.filter(campaign => campaign !== selectedCampaign)
      ].slice(0, 5);
      const heatmap = document.getElementById("ahjHeatmap");
      heatmap.style.gridTemplateColumns = `132px repeat(${columns.length}, minmax(96px, 1fr))`;
      const header = `<div class="heat-cell header">Market</div>${columns.map(campaign => `<div class="heat-cell header">${escapeAttr(campaign)}</div>`).join("")}`;
      const cells = markets.map(market => {
        const head = `<div class="heat-cell header">${escapeAttr(market)}</div>`;
        const rowCells = columns.map(campaign => {
          const row = allRows.find(item => item.ahjKey === market && item.campaign === campaign);
          const score = row ? Math.max(0, Math.round(row.metricValue)) : 0;
          const hue = Math.round(6 + Math.min(100, score) * 1.22);
          const tone = row && row.decision === "Avoid" ? "bad" : row && row.decision === "Scale" ? "good" : "warn";
          return `<div class="heat-cell" role="button" tabindex="0" data-ahj-key="${escapeAttr(market)}" data-campaign="${escapeAttr(campaign)}" style="background:hsl(${hue}, 58%, 84%)" data-tip="${escapeAttr(`${market} ${campaign}: ${row ? row.metricDisplay : "no data"}, ${row && row.cpw ? fmtCurrency(row.cpw) : "no wins"} CPW`)}"><strong>${score}</strong><span class="pill ${tone}">${row ? row.decision : "n/a"}</span></div>`;
        }).join("");
        return head + rowCells;
      }).join("");
      heatmap.innerHTML = header + cells;
      wireTips(heatmap);
      heatmap.querySelectorAll("[data-ahj-key]").forEach(cell => {
        cell.addEventListener("click", () => setAhjSelection(cell.dataset.ahjKey, cell.dataset.campaign));
      });
    }

    function renderAhjAllocationTable(rows) {
      const tableRows = rows.slice(0, 14);
      document.getElementById("ahjAllocationTable").innerHTML = `
        <thead>
          <tr><th>Rank</th><th>Decision</th><th>Market</th><th>Campaign</th><th>Selected metric</th><th>Leads</th><th>Wins</th><th>Spend</th><th>Revenue</th><th>CPW</th><th>Gate</th></tr>
        </thead>
        <tbody>${tableRows.map((row, index) => `
          <tr data-ahj-key="${escapeAttr(row.ahjKey)}" data-campaign="${escapeAttr(row.campaign)}">
            <td>${index + 1}</td>
            <td>${row.decision}</td>
            <td><strong>${escapeAttr(row.market)}</strong></td>
            <td>${escapeAttr(row.campaign)}</td>
            <td>${escapeAttr(row.metricDisplay)}</td>
            <td>${fmtNum(row.leads)}</td>
            <td>${fmtNum(row.wins)}</td>
            <td>${fmtCurrency(row.spend)}</td>
            <td>${fmtCurrency(row.revenue)}</td>
            <td>${row.cpw ? fmtCurrency(row.cpw) : "No wins yet"}</td>
            <td>${escapeAttr(row.sampleSizeBucket)}, ${pct(row.leadToWinRate || 0)} lead-to-win</td>
          </tr>
        `).join("")}</tbody>
      `;
      document.getElementById("ahjAllocationTable").querySelectorAll("[data-ahj-key]").forEach(row => {
        row.addEventListener("click", () => setAhjSelection(row.dataset.ahjKey, row.dataset.campaign));
      });
    }

    function selectedAhjPair(rows) {
      if (state.selectedAhj !== "All AHJs" && state.ahjCampaign !== "All campaigns") {
        return ahjDecisionRows({ ignoreCampaign: true }).find(row => row.ahjKey === state.selectedAhj && row.campaign === state.ahjCampaign) || rows[0];
      }
      return rows[0];
    }

    function selectedPairHtml(row) {
      if (!row) return "";
      const tone = row.decision === "Scale" ? "good" : row.decision === "Test" ? "warn" : "bad";
      return `
        <div class="ahj-selected-pair">
          <h4>${escapeAttr(row.market)} / ${escapeAttr(row.campaign)}</h4>
          <div class="impact">
            <span class="pill ${tone}">${row.decision}</span>
            <span class="pill">${escapeAttr(state.ahjObjective)}: ${escapeAttr(row.metricDisplay)}</span>
            <span class="pill">${row.cpw ? fmtCurrency(row.cpw) : "No wins yet"} CPW</span>
            <span class="pill">${(row.revenuePerSpend || 0).toFixed(1)}x rev/spend</span>
            <span class="pill">${pct(row.leadToWinRate || 0)} lead-to-win</span>
            <span class="pill">${escapeAttr(row.sampleSizeBucket)}</span>
          </div>
        </div>
      `;
    }

    function ahjClickCard(row, label, sublabel, extra = "") {
      const tone = row.decision === "Scale" ? "good" : row.decision === "Test" ? "warn" : "bad";
      return `
        <button type="button" class="ahj-click-card${row.ahjKey === state.selectedAhj && row.campaign === state.ahjCampaign ? " active" : ""}" data-ahj-key="${escapeAttr(row.ahjKey)}" data-campaign="${escapeAttr(row.campaign)}">
          <strong>${escapeAttr(label)}</strong>
          <span>${escapeAttr(sublabel)}</span>
          <div class="impact">
            <span class="pill ${tone}">${row.decision}</span>
            <span class="pill">${escapeAttr(row.metricDisplay)}</span>
            ${extra}
          </div>
        </button>
      `;
    }

    function renderRankedAhjCanvas(rows) {
      return `
        <div class="ahj-click-grid">
          ${rows.slice(0, 12).map(row => ahjClickCard(
            row,
            row.market,
            row.campaign,
            `<span class="pill">${fmtNum(row.leads)} leads</span><span class="pill">${fmtNum(row.wins)} wins</span>`
          )).join("")}
        </div>
      `;
    }

    function renderCampaignsForAhjCanvas(rows) {
      const focusKey = state.selectedAhj === "All AHJs" ? rows[0]?.ahjKey : state.selectedAhj;
      const campaignRows = ahjDecisionRows({ ignoreCampaign: true })
        .filter(row => !focusKey || row.ahjKey === focusKey)
        .sort((a, b) => b.metricValue - a.metricValue);
      return `
        <div class="ahj-click-grid">
          ${campaignRows.slice(0, 12).map(row => ahjClickCard(
            row,
            row.campaign,
            row.market,
            `<span class="pill">${fmtCurrency(row.spend)} spend</span><span class="pill">${(row.revenuePerSpend || 0).toFixed(1)}x ROI</span>`
          )).join("")}
        </div>
      `;
    }

    function renderMetricMatrixCanvas(rows) {
      const allRows = ahjDecisionRows({ ignoreCampaign: true, ignoreAhj: true });
      const marketTotals = {};
      state.ahjRows.forEach(row => {
        marketTotals[row.market] = (marketTotals[row.market] || 0) + row.leads;
      });
      const markets = Object.keys(marketTotals).sort((a, b) => marketTotals[b] - marketTotals[a]).slice(0, 12);
      const campaignBest = {};
      allRows.forEach(row => {
        campaignBest[row.campaign] = Math.max(campaignBest[row.campaign] || 0, row.metricValue);
      });
      const campaigns = Object.keys(campaignBest).sort((a, b) => campaignBest[b] - campaignBest[a]).slice(0, 5);
      return `
        <div class="metric-matrix">
          <div class="matrix-row">
            <div class="matrix-cell header">AHJ / Campaign</div>
            ${campaigns.map(campaign => `<div class="matrix-cell header">${escapeAttr(campaign)}</div>`).join("")}
          </div>
          ${markets.map(market => `
            <div class="matrix-row">
              <div class="matrix-cell header">${escapeAttr(market)}</div>
              ${campaigns.map(campaign => {
                const row = allRows.find(item => item.ahjKey === market && item.campaign === campaign);
                const tone = row && row.decision === "Scale" ? "good" : row && row.decision === "Test" ? "warn" : "bad";
                return row ? `
                  <button type="button" class="matrix-cell" data-ahj-key="${escapeAttr(row.ahjKey)}" data-campaign="${escapeAttr(row.campaign)}">
                    <strong>${escapeAttr(row.metricDisplay)}</strong>
                    <span class="pill ${tone}">${row.decision}</span>
                  </button>
                ` : `<div class="matrix-cell"></div>`;
              }).join("")}
            </div>
          `).join("")}
        </div>
      `;
    }

    function renderAhjInvestigationCanvas(rows) {
      const selected = selectedAhjPair(rows);
      let body = "";
      if (state.ahjLayout === "campaigns-for-ahj") body = renderCampaignsForAhjCanvas(rows);
      else if (state.ahjLayout === "metric-matrix") body = renderMetricMatrixCanvas(rows);
      else body = renderRankedAhjCanvas(rows);
      const canvas = document.getElementById("ahjInvestigationCanvas");
      canvas.innerHTML = selectedPairHtml(selected) + body;
      canvas.querySelectorAll("[data-ahj-key]").forEach(item => {
        item.addEventListener("click", () => setAhjSelection(item.dataset.ahjKey, item.dataset.campaign));
      });
    }

    function renderAhjDetail(rows) {
      const focusKey = state.selectedAhj === "All AHJs" ? rows[0]?.ahjKey : state.selectedAhj;
      const market = focusKey || (state.ahjRows[0] && state.ahjRows[0].market);
      if (!market) {
        document.getElementById("ahjDetail").innerHTML = "";
        return;
      }
      const detailRows = ahjDecisionRows({ ignoreCampaign: true }).filter(row => row.ahjKey === market)
        .sort((a, b) => {
          if (a.campaign === state.ahjCampaign) return -1;
          if (b.campaign === state.ahjCampaign) return 1;
          return b.metricValue - a.metricValue;
        }).slice(0, 7);
      const top = detailRows.find(row => row.campaign === state.ahjCampaign) || detailRows[0];
      const totalLeads = detailRows.reduce((sum, row) => sum + row.leads, 0);
      const totalWins = detailRows.reduce((sum, row) => sum + row.wins, 0);
      const totalSpend = detailRows.reduce((sum, row) => sum + row.spend, 0);
      document.getElementById("ahjDetail").innerHTML = `
        <div>
          ${noteChip(`ahj:detail:${market}`, `${market} detail`, "tile")}
          <h3>${escapeAttr(market)}</h3>
        </div>
        <div class="ahj-detail-grid">
          <span>Leads <strong>${fmtNum(totalLeads)}</strong></span>
          <span>Wins <strong>${fmtNum(totalWins)}</strong></span>
          <span>Spend <strong>${fmtCurrency(totalSpend)}</strong></span>
          <span>Lead-to-win <strong>${pct(totalLeads ? totalWins / totalLeads : 0)}</strong></span>
        </div>
        ${top ? decisionCardHtml({
          key: `ahj:detail:best:${top.key}`,
          title: `${top.decision}: ${top.campaign}`,
          body: top.cpw ? `${fmtCurrency(top.cpw)} cost per win against a ${fmtCurrency(top.cpwBenchmark)} benchmark.` : "No wins recorded in this window yet.",
          pills: [`${fmtCurrency(top.spend)} spend`, `${fmtNum(top.wins)} wins`, top.cpw ? `${fmtCurrency(top.cpw)} CPW` : "No wins yet", top.sampleSizeBucket],
          tone: top.decision === "Scale" ? "good" : top.decision === "Test" ? "warn" : "bad"
        }) : ""}
        <table class="table">
          <thead><tr><th>Campaign</th><th>Decision</th><th>Leads</th><th>Wins</th><th>CPW</th><th>Selected metric</th></tr></thead>
          <tbody>${detailRows.map(row => `<tr><td>${escapeAttr(row.campaign)}</td><td>${row.decision}</td><td>${fmtNum(row.leads)}</td><td>${fmtNum(row.wins)}</td><td>${row.cpw ? fmtCurrency(row.cpw) : "No wins yet"}</td><td>${escapeAttr(row.metricDisplay)}</td></tr>`).join("")}</tbody>
        </table>
      `;
      wireNoteChips(document.getElementById("ahjDetail"));
    }

    function ahjAreaRows(rows) {
      if (state.ahjArea === "quality") {
        return [...rows].sort((a, b) => ((b.leadToWinRate || 0) * 100 + ahjSampleConfidenceRank(b.sampleSizeBucket) * 20) - ((a.leadToWinRate || 0) * 100 + ahjSampleConfidenceRank(a.sampleSizeBucket) * 20)).slice(0, 6);
      }
      if (state.ahjArea === "growth") {
        return [...rows].sort((a, b) => (b.revenue + b.wins * 32000 + b.leads * 900) - (a.revenue + a.wins * 32000 + a.leads * 900)).slice(0, 6);
      }
      return [...rows].sort((a, b) => {
        const aRatio = a.cpw ? a.cpw / Math.max(1, a.cpwBenchmark) : 2;
        const bRatio = b.cpw ? b.cpw / Math.max(1, b.cpwBenchmark) : 2;
        return ((b.revenuePerSpend || 0) - bRatio) - ((a.revenuePerSpend || 0) - aRatio);
      }).slice(0, 6);
    }

    function ahjAreaCopy(row) {
      if (state.ahjArea === "quality") {
        return {
          title: `${row.market}: ${pct(row.leadToWinRate || 0)} lead-to-win`,
          body: `${row.campaign} quality is driven by lead-to-win rate and ${row.sampleSizeBucket.toLowerCase()} confidence.`,
          pills: [`${fmtNum(row.leads)} leads`, `${fmtNum(row.wins)} wins`, row.cpw ? `${fmtCurrency(row.cpw)} CPW` : "No wins yet"]
        };
      }
      if (state.ahjArea === "growth") {
        return {
          title: `${row.market}: ${fmtCurrency(row.revenue)} revenue`,
          body: `${row.campaign} has ${fmtNum(row.leads)} modeled leads and ${fmtNum(row.wins)} wins, useful only if efficiency and gate status still hold.`,
          pills: [`${(row.revenuePerSpend || 0).toFixed(1)}x rev/spend`, `${fmtCurrency(row.spend)} spend`, row.decision]
        };
      }
      return {
        title: `${row.market}: ${(row.revenuePerSpend || 0).toFixed(1)}x rev/spend`,
        body: `${row.campaign} efficiency pairs ${row.cpw ? fmtCurrency(row.cpw) : "no wins yet"} cost per win with ${pct(row.leadToWinRate || 0)} lead-to-win rate.`,
        pills: [`${pct(row.leadToWinRate || 0)} lead-to-win`, row.sampleSizeBucket, row.decision]
      };
    }

    function renderAhjPerformanceBreakdown(rows) {
      const areaRows = ahjAreaRows(rows);
      document.querySelectorAll("#ahjAreaTabs button").forEach(button => {
        button.classList.toggle("active", button.dataset.ahjArea === state.ahjArea);
      });
      document.getElementById("ahjPerformanceBreakdown").innerHTML = areaRows.map(row => {
        const copy = ahjAreaCopy(row);
        const tone = row.decision === "Scale" ? "good" : row.decision === "Test" ? "warn" : "bad";
        return `
          <div class="ahj-breakdown-card">
            ${noteChip(`ahj:breakdown:${state.ahjArea}:${row.key}`, copy.title, "tile")}
            <h4>${escapeAttr(copy.title)}</h4>
            <p>${escapeAttr(copy.body)}</p>
            <div class="impact">${copy.pills.map(pill => `<span class="pill ${tone}">${escapeAttr(pill)}</span>`).join("")}</div>
          </div>
        `;
      }).join("");
      wireNoteChips(document.getElementById("ahjPerformanceBreakdown"));
    }

    function ahjCurrentFetchKey() {
      return "ahj-performance:trailing";
    }

    async function ensureAhjRowsLoaded() {
      const fetchKey = ahjCurrentFetchKey();
      if (state.ahjRowsFetchKey === fetchKey) return;
      const token = ++state.ahjFetchToken;
      try {
        const response = await fetch(`${NOTES_API_BASE}/ahj-performance`);
        if (!response.ok) throw new Error(`AHJ performance fetch failed: ${response.status}`);
        const rows = await response.json();
        if (token !== state.ahjFetchToken) return;
        state.ahjRows = rows;
        state.ahjRowsFetchKey = fetchKey;
      } catch (error) {
        if (token !== state.ahjFetchToken) return;
        state.ahjRows = state.ahjRows || [];
        state.ahjRowsFetchKey = fetchKey;
      }
    }

    async function renderAhjPlanner() {
      await ensureAhjRowsLoaded();
      const rows = ahjDecisionRows();
      renderAhjFocusSelect(rows);
      renderAhjMetrics(rows);
      renderAhjInsights(rows);
      renderAhjInvestigationCanvas(rows);
      renderAhjHeatmap(rows);
      renderAhjAllocationTable(rows);
      renderAhjDetail(rows);
      renderAhjPerformanceBreakdown(rows);
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `node work/verify_marketing_tool.js`
Expected: exits 0 and prints the JSON summary.

- [ ] **Step 5: Do not commit.** Leave the changes staged/unstaged for the user to review.

---

### Task 7: `dashboardContextForClaude()` AHJ context rewrite

**Files:**
- Modify: `outputs/marketing_decision_tool.html:2645-2689` (the `ahj_planner` block)
- Modify: `work/verify_ahj_scoring.js` (extend with a context-payload assertion)

**Interfaces:**
- Consumes: `state.ahjRows`, `ahjDecisionRows()` (Task 5); `ahjRowsForContext = ahjDecisionRows();` (existing, unchanged, `outputs/marketing_decision_tool.html:2582`).
- Produces: `dashboardContextForClaude().ahj_planner` with keys `campaign_focus, rank_metric, layout, drilldown_area, selected_ahj, active_markets, top_recommendations` (each recommendation: `market, campaign, decision, selected_metric, selected_metric_value, spend, wins, revenue, lead_volume, lead_to_win_rate, sample_size_bucket, cost_per_win, revenue_per_spend, suggested_test_spend, next_10k_revenue, next_10k_wins`).

- [ ] **Step 1: Write the failing test**

In `work/verify_ahj_scoring.js`, replace the script string's `return` statement:

```javascript
return {
  benchmarks,
  rows,
  sampleRanks: {
    sufficient: ahjSampleConfidenceRank("Sufficient Sample"),
    low: ahjSampleConfidenceRank("Low Sample"),
    none: ahjSampleConfidenceRank("No Same-Period Sample")
  }
};`);
```

with:

```javascript
const context = dashboardContextForClaude();
return {
  benchmarks,
  rows,
  sampleRanks: {
    sufficient: ahjSampleConfidenceRank("Sufficient Sample"),
    low: ahjSampleConfidenceRank("Low Sample"),
    none: ahjSampleConfidenceRank("No Same-Period Sample")
  },
  ahjPlannerContext: context.ahj_planner
};`);
```

Then add these assertions after the existing `sampleRanks` check and before the final `console.log`:

```javascript
const contextMarkets = output.ahjPlannerContext.active_markets;
if (!Array.isArray(contextMarkets) || !contextMarkets.includes("Fairfax County, VA") || !contextMarkets.includes("Loudoun County, VA")) {
  console.error("ahj_planner.active_markets did not include the expected fixture markets.");
  console.error(JSON.stringify(contextMarkets));
  process.exit(1);
}

const topRecommendation = output.ahjPlannerContext.top_recommendations[0];
if (!topRecommendation || typeof topRecommendation.cost_per_win === "undefined" || typeof topRecommendation.sample_size_bucket === "undefined") {
  console.error("ahj_planner.top_recommendations did not include the expected live-data fields.");
  console.error(JSON.stringify(topRecommendation));
  process.exit(1);
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node work/verify_ahj_scoring.js`
Expected: FAIL — `topRecommendation.county` / `topRecommendation.readiness` style fields are present instead of `market` / `cost_per_win`, or the script errors because `activeAhjProfiles` (referenced by the old `ahj_planner` block) no longer exists.

- [ ] **Step 3: Replace the `ahj_planner` context block**

In `outputs/marketing_decision_tool.html`, inside `dashboardContextForClaude()`, replace:

```javascript
        ahj_planner: {
          campaign_focus: state.ahjCampaign,
          rank_metric: state.ahjObjective,
          layout: state.ahjLayout,
          drilldown_area: state.ahjArea,
          selected_ahj: state.selectedAhj,
          active_counties: activeAhjProfiles().map(profile => ({
            county: profile.county,
            ahj: profile.ahj,
            region: profile.region,
            readiness_score: ahjReadinessScore(profile),
            permit: profile.permit,
            utility: profile.utility,
            crew: profile.crew,
            survey: profile.survey,
            cancel_risk: profile.cancel,
            capacity_slots: profile.capacitySlots
          })),
          top_recommendations: ahjRowsForContext.slice(0, 12).map(row => ({
            county: row.county,
            ahj: row.ahj,
            region: row.region,
            campaign: row.campaign,
            source: row.source,
            decision: row.decision,
            score: row.score,
            selected_metric: row.metricDisplay,
            selected_metric_value: row.metricValue,
            modeled_spend: row.spend,
            modeled_wins: row.wins,
            modeled_revenue: row.revenue,
            lead_volume: row.leads,
            lead_to_win_rate: row.winRate,
            sample_size_bucket: row.sampleSizeBucket,
            capacity_adjusted_cpw: row.capacityAdjustedCpw,
            revenue_per_spend: row.revenue / Math.max(1, row.spend),
            suggested_test_spend: row.suggestedTestSpend,
            stress: row.stress,
            readiness: row.readiness,
            fit: row.fit,
            next_10k_revenue: row.nextTenKRevenue,
            next_10k_wins: row.nextTenKWins,
            guardrail: row.guardrail
          }))
        },
```

with:

```javascript
        ahj_planner: {
          campaign_focus: state.ahjCampaign,
          rank_metric: state.ahjObjective,
          layout: state.ahjLayout,
          drilldown_area: state.ahjArea,
          selected_ahj: state.selectedAhj,
          active_markets: [...new Set(state.ahjRows.map(row => row.market))],
          top_recommendations: ahjRowsForContext.slice(0, 12).map(row => ({
            market: row.market,
            campaign: row.campaign,
            decision: row.decision,
            selected_metric: row.metricDisplay,
            selected_metric_value: row.metricValue,
            spend: row.spend,
            wins: row.wins,
            revenue: row.revenue,
            lead_volume: row.leads,
            lead_to_win_rate: row.leadToWinRate,
            sample_size_bucket: row.sampleSizeBucket,
            cost_per_win: row.cpw,
            revenue_per_spend: row.revenuePerSpend,
            suggested_test_spend: row.suggestedTestSpend,
            next_10k_revenue: row.nextTenKRevenue,
            next_10k_wins: row.nextTenKWins
          }))
        },
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `node work/verify_ahj_scoring.js`
Expected: exits 0 and prints the JSON summary.

- [ ] **Step 5: Do not commit.** Leave the changes staged/unstaged for the user to review.

---

### Task 8: CI wiring for the new JS harness and final validation

**Files:**
- Modify: `.github/workflows/ci.yml:35-39`

**Interfaces:**
- Consumes: `work/verify_ahj_scoring.js` (Tasks 5 and 7).

- [ ] **Step 1: Insert the new CI step**

In `.github/workflows/ci.yml`, immediately after the "Verify dashboard rendering" step ends (`run: node work/verify_marketing_tool.js` on line 36) and before "Verify dashboard notes wiring" (line 38), insert:

```yaml
      - name: Verify AHJ scoring logic
        run: node work/verify_ahj_scoring.js
```

- [ ] **Step 2: Review the diff**

Run: `git diff --stat .github/workflows/ci.yml`
Expected: shows the new step's lines added, no other changes.

- [ ] **Step 3: Run the full local validation suite**

Run each of the following from the repo root and confirm the stated result:

```powershell
node work/verify_marketing_tool.js
```
Expected: exits 0, prints JSON summary.

```powershell
node work/verify_ahj_scoring.js
```
Expected: exits 0, prints JSON summary.

```powershell
node work/verify_dashboard_notes.js
```
Expected: exits 0 (pre-existing, unrelated to this plan's changes — confirms no regression).

```powershell
C:\Users\sflem\AppData\Local\Programs\Python\Python312\python.exe -m py_compile dashboard_server.py
```
Expected: no output, exit code 0.

```powershell
C:\Users\sflem\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/test_ahj_performance.py -q
```
Expected: `10 passed`.

- [ ] **Step 4: Do not commit.** Leave all changes from this plan staged/unstaged for the user to review and commit themselves.

---

## Self-Review

**Spec coverage:**
- Live AHJ endpoint with filters and named campaign rows → Task 1-2 (`build_ahj_performance_query` supports `months`/`campaign`/`market`; returns named `campaign_name` rows, not rollups).
- Field mapping (`lead_count`→leads, etc.) → Task 1 (`shape_ahj_row`).
- Period control → intentionally simplified to a fixed trailing 6-month `MONTH`-grain window per the two-tier fetch architecture agreed earlier in this project (no UI period control was in the approved design scope; not a gap, a deliberate scope boundary already baked into the Architecture section).
- Sample-size guardrails (no Scale for Low Sample without test-spend; No-Same-Period-Sample surfaced, not scaled) → Task 5 (`ahjDecisionFor`: `Sufficient Sample` required for `Scale`; `No Same-Period Sample` forces `Avoid`); Task 6 (`suggestedTestSpend` only nonzero for `Scale`/`Test`).
- Drop capacity-dependent ranking metrics and Capacity drilldown tab (Option 1) → Task 4 (5-option ranking select, 3-tab drilldown).
- Two-tier fetch (fetch once per session, filter client-side) → Task 6 (`ahjCurrentFetchKey`/`ensureAhjRowsLoaded` cache guard).
- Ask Claude context reflects live AHJ rows → Task 7.
- CI coverage for both new test suites → Tasks 3 and 8.

**Placeholder scan:** No TBD/TODO markers; every step has complete code; no "similar to Task N" references — Task 6 reproduces the full render-layer code even though some functions (`selectedAhjPair`, `ahjClickCard`, `renderAhjInvestigationCanvas`, `renderAhjPerformanceBreakdown`) are logically unchanged from the current file, so the implementer never has to cross-reference another task's code block.

**Type/signature consistency:** `ahjDecisionRows()`'s enriched row shape (`market, campaign, ahjKey, key, cpw, cpwBenchmark, revenuePerSpend, leadToWinRate, leadToWinBenchmark, sampleSizeBucket, decision, suggestedTestSpend, nextTenKWins, nextTenKRevenue, metricValue, metricDisplay`) defined in Task 5 is consumed with identical field names throughout Task 6's render functions and Task 7's context block — verified field-by-field against every consumer during planning (no `county`/`ahj`/`readiness`/`fit`/`stress`/`score`/`profile` references remain anywhere in the rewritten blocks).

---

**Plan complete and saved to `docs/superpowers/plans/2026-07-27-ahj-view-live-data.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
