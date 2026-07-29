# Campaigns View Live-Data Implementation Plan

**Goal:** Replace the Campaigns view's synthetic budget allocator with live,
month-grained campaign actuals from
`analytics_rpt.rpt_marketing_campaign_ahj_performance`.

**Scope:** Campaign cards, ranked recommendations, summary metrics, monthly
trend, and decision table. Decisions use the same CPW, lead-to-win, and
sample-confidence gates as the shipped AHJ view. Budget allocation,
capacity-adjusted economics, region-fit scoring, product-mix lift, and
payback modeling are retired.

## Task 1: Add the campaign query and row shaper

Files:

- `dashboard_server.py`
- `tests/test_campaign_performance.py`

Add `build_campaign_performance_query(months=6, campaign=None)` against the
existing `AHJ_TABLE_REF`. Group by campaign reporting rollup, named campaign,
and `period_start_date AS month`. Sum leads, wins, allocated spend, and win
revenue.

Add `shape_campaign_row()` to serialize `month` with `isoformat()`, preserve
the rollup, compute CPW/revenue-per-spend/lead-to-win, and assign the same
sample-size buckets used by AHJ.

Verify trailing-window SQL, optional campaign filtering, month serialization,
ratio calculations, and zero-sample behavior.

## Task 2: Expose the campaign-performance endpoint

Files:

- `dashboard_server.py`
- `tests/test_campaign_performance.py`

Add `GET /api/campaign-performance` and `_campaign_performance()`. Bind
`months` and optional `campaign` with BigQuery scalar parameters. Return 400
for invalid months and 502 for query failures.

## Task 3: Replace Campaigns markup

File:

- `outputs/marketing_decision_tool.html`

Replace the allocator UI with:

- retryable live-data error banner;
- ranking metric and named-campaign selectors;
- actuals metric cards;
- ranked Scale/Test/Hold/Avoid recommendations;
- campaign cards;
- selected-campaign monthly trend; and
- detailed decision table.

Delete allocator-only CSS and update page/help copy so retired concepts are
not described.

## Task 4: Replace synthetic state and scoring

File:

- `outputs/marketing_decision_tool.html`

Delete synthetic campaign segments, allocation state, regional-fit helpers,
capacity adjustments, and per-campaign reweighting of Overview data.

Add month-to-campaign aggregation, filtered benchmark calculation that
excludes zero-win rows, AHJ-equivalent decision gates, objective ranking,
metric display, and chronological trend shaping.

Keep the global campaign selector synchronous and source-filtered so it can
read the eagerly cached campaign rows on every render.

## Task 5: Add live rendering and fetch orchestration

Files:

- `outputs/marketing_decision_tool.html`
- `work/dom_fake.js`
- `work/verify_marketing_tool.js`
- `work/verify_campaign_error_state.js`

Add a static Campaigns fetch key, token-protected fetch, non-caching failures,
retry banner, and async planner orchestration. Start the fetch eagerly during
app initialization so the shared topbar campaign selector is populated even
before the Campaigns view opens.

Render only live actuals and decision outputs. Preserve stable campaign note
keys across cards and recommendations.

## Task 6: Update assistant context and fallback insights

Files:

- `outputs/marketing_decision_tool.html`
- `dashboard_server.py`
- `tests/test_fallback_insights.py`
- `work/verify_campaign_scoring.js`

Replace allocator diagnostics in `campaign_planner` with active campaigns,
rank metric, top live recommendations, and selected-campaign monthly rows.
Remove `campaignGrain` from note context.

Rewrite `_fallback_insights()` to use the ranked live rows, actual spend,
observed CPW, conversion, sample confidence, and Scale/Test/Hold/Avoid gates.
Remove the obsolete `_first()` helper.

## Task 7: Wire CI and complete regression validation

Files:

- `.github/workflows/ci.yml`
- `work/verify_campaign_scoring.js`
- `work/verify_campaign_error_state.js`
- `work/verify_dashboard_notes.js`
- `work/verify_marketing_tool.js`

Run:

```text
node work/verify_marketing_tool.js
node work/verify_campaign_scoring.js
node work/verify_campaign_error_state.js
node work/verify_ahj_scoring.js
node work/verify_ahj_error_state.js
node work/verify_dashboard_notes.js
python -m py_compile dashboard_server.py
python -m pytest tests/test_ahj_performance.py tests/test_campaign_performance.py tests/test_fallback_insights.py -q
```

Confirm no allocator-only identifiers remain, no invalid rendered tokens are
introduced, failed fetches remain retryable, successful fetches are cached,
and AHJ/Overview behavior continues to pass its existing checks.
