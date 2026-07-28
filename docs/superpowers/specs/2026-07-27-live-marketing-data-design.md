# Live BigQuery Data for the Marketing Decision Tool — Design

**Date:** 2026-07-27
**Status:** Draft (pending review)
**Author:** Sean Fleming (with Claude)

## Problem

The Marketing Decision Workbench (`outputs/marketing_decision_tool.html`) currently renders AHJ, campaign, and cohort performance using a deterministic demo model instead of the live lakehouse data it's meant to represent (see `docs/marketing_tool_handoff.md`, Known Limitations). The BQ freshness badge is live, but the numbers behind every card, chart, and ranking are synthetic. This makes the tool unusable for the thing it's for: real campaign/AHJ/cohort investigation and spend decisions.

## Goal

Replace the synthetic model with live BigQuery-backed data for the five marketing-specific views: **Overview, Cohorts, Campaigns, AHJ, Scenario-baseline**. This is v1 of live-data wiring — it covers marketing performance objects only.

## Non-goals

- Capacity/forecast objects. Deferred to a later pass; not touched by this design.
- Any new dashboard UX beyond what's in this spec. Filters, ranking metrics, and drill-down interactions stay conceptually the same (dropdowns/tabs/cards driving investigation) — only their data source changes, except where a metric/tab/card has no live counterpart at all (see "Data model: AHJ view — ranking & gating simplification" below, a scoping decision made with the user).
- Making `Ask Claude` run arbitrary BQ queries. That's handoff doc Recommended Next Step #6, a separate follow-on once live AHJ/cohort data exists.
- Real-time/streaming updates. The existing `Refresh BQ` freshness-badge pattern is sufficient.

## Scope: view → lakehouse source

| View | Primary source | Status |
|---|---|---|
| AHJ | `analytics_rpt.rpt_marketing_campaign_ahj_performance` | Ready to wire directly — matches handoff doc Recommended Next Steps #1–#2 exactly. |
| Overview | Rollup over the same performance objects as Campaigns/AHJ | Ready — no distinct lakehouse object; aggregate in the API layer. |
| Campaigns | Same base performance objects, grouped by campaign hierarchy fields (`campaign_name` → `parent_campaign_name` → `grandparent_campaign_name`, rollup/sub-rollup) | Ready. |
| Cohorts | New: `marketing_tool_ops.rpt_marketing_cohort_performance_with_yield` | Designed and validated this pass — see below. This is the primary deliverable of this spec. |
| Scenario-baseline | `analytics_rpt.rpt_marketing_period_projection` | **Grain-verified this pass — ready to wire.** See Grain-check section below. |

## Architecture

New read-only endpoints are added to the existing `dashboard_server.py` Cloud Run service (the same service serving the dashboard today) — not a new service like `notes-api`, since this is read-only reporting data, not writes. Each endpoint runs a parameterized `SELECT` against BigQuery under the app's dedicated read-only service account (see Access Model) and returns JSON shaped for its dashboard view, replacing the synthetic demo generator functions currently in `dashboard_server.py`/the HTML file.

Filters supported per handoff doc Recommended Next Step #1: period grain, date range, campaign name, market, state, county, AHJ, sample bucket. Endpoints return named campaign/cohort rows, not rollups only — rollups (Overview) are computed from those rows in the API layer so there's one source of truth per query. (The AHJ view's actual filter set for this pass is narrower than this full list — see the AHJ-specific "Query-affecting filters" note below.)

**Client fetch pattern.** Each view's render function (e.g. `renderAhjPlanner()`) becomes `async`. It computes a small fetch key from its own query-affecting filter state (e.g. `{campaign, market}` for AHJ), and only issues a new `fetch()` when that key differs from the last one it fetched — otherwise it reuses the cached rows already on `state`. A monotonically increasing per-view fetch token guards against out-of-order responses (a slow request resolving after a newer one has already landed is discarded). This keeps every existing call site unchanged — calling an async render function without `await` from a UI event handler is valid, non-blocking JS — while avoiding a redundant BQ query on every purely cosmetic re-render (e.g. switching ranking metric or layout tab, which don't change the fetch key).

## Data model: AHJ view — ranking & gating simplification (decision recorded)

The handoff doc's Recommended Next Steps #1–#2 read like a straight field swap onto live `rpt_marketing_campaign_ahj_performance` columns, but the AHJ tab's actual synthetic-dependency surface is larger than a single ranking menu — confirmed by reading `outputs/marketing_decision_tool.html` in full. This section records the scoping decision made with the user before implementation ("lets do option 1"), since it narrows the Non-goals line above ("ranking metrics... stay as-is") for the AHJ view specifically.

**What's dropped, and why.** The AHJ tab currently computes `readiness`, `fit`, `stress`, `capacityAdjustedCpw`, `productLift`, `grossMargin`, and `profile.capacitySlots` from a deterministic county-profile model (`ahjCountyProfiles`) that has no live counterpart — there is no lakehouse field for "AHJ readiness" or "campaign fit." Consistent with this spec's Non-goal of deferring capacity/forecast objects, every ranking metric, decision-gate branch, tab, card, and detail-grid field that depends on these synthetic values is dropped in this pass and restored in a future, separate capacity/forecast pass:

- **Ranking menu** (`ahjObjective` / `ahjRankingValue` / `ahjMetricDisplay`): reduced from 9 options to 5 — **Balanced decision score** (default), **Revenue per spend**, **Lowest cost per win**, **Lead to win rate**, **Sample confidence**. Dropped: AHJ readiness, Capacity headroom, Margin quality, Growth volume.
- **Decision gate** (`ahjDecisionFor`): simplified to CPW-vs-benchmark, lead-to-win-rate, and sample-size guardrails only — matching handoff doc Recommended Next Step #4 exactly. Readiness/fit/stress gating is removed.
- **Drilldown tabs** (`ahjAreaTabs` / `ahjAreaRows` / `ahjAreaCopy` / `renderAhjPerformanceBreakdown`): the **Capacity tab is dropped**; Efficiency/Quality/Growth are kept, rewritten to use only live fields.
- **`renderAhjDetail`'s** Readiness/Permit/Utility/Capacity 4-box grid is replaced with a live-field equivalent (leads/wins/spend/revenue for the focused campaign×AHJ pair).
- **`renderAhjInsights`'s** "Capacity-safe spend" card and **`renderAhjMetrics`'s** "Weighted AHJ stress" card are dropped — no live stress signal exists to back them.
- **Field/label rename:** `capacityAdjustedCpw` and its display label **"Cap-adj CPW"** become plain `cpw` / **"CPW"** everywhere (allocation table header, detail table, insight pills, breakdown copy) — there's no capacity-stress adjustment left to apply.

**Sample-size model.** The live `sample_size_bucket` field's own lead-count ranges are non-monotonic across `period_grain`/`campaign_type` and aren't safe to reverse-engineer into UI tiers, so the new endpoint defines its own 3-tier bucket over trailing-window-aggregated leads/wins, reusing the handoff doc's category names: 0 leads → **"No Same-Period Sample"**; low volume → **"Low Sample"**; sufficient volume → **"Sufficient Sample"**. This is a deliberate simplification from the demo's 4-tier High/Medium/Low/No-Sample model — there is no "High Sample" tier in this pass.

**Benchmarks.** Rather than the demo's hardcoded per-channel CPW lookup (`ahjCpwBenchmark`, e.g. "Paid Search": $1,250 — channel strings that don't exist in live data), `cpwBenchmark` and `winRateBenchmark` are computed as win-weighted and lead-weighted blended means over the current live filtered row set, fully derived from live data with no invented constants.

**Query-affecting filters, this pass.** The new AHJ endpoint accepts only `campaign` (from the AHJ tab's own "Campaign focus" control, mapped to `campaign_name`) and `market` (from the AHJ tab's own "AHJ focus" control, mapped to `reporting_market_label`) — both nullable. The dashboard's *global* Market/Source selectors (`regionSelect`/`sourceSelect`) are **not** wired into the live AHJ query in this pass: they hold a fixed 6-item/5-item demo list with no clean mapping onto live `reporting_market_label` (515 distinct values) or `inferred_campaign_channel` (17 distinct values), and remapping them is entangled with the still-synthetic Overview/Campaigns/Cohorts views that share those same global controls. They continue to filter only the synthetic views for now; unifying global filtering once every view is live is explicitly deferred, out of scope here.

**Period grain, this pass.** The period-grain control (WEEK vs MONTH) and trailing-4-vs-12-period control called for in handoff doc Recommended Next Step #3 are deferred — this pass uses a fixed 6-month trailing MONTH-grain window with no UI control for it. Opportunity/cancellation quality fields (Next Step #5) remain deferred per the existing Non-goals.

## Data model: Cohorts view

### The problem

The two candidate lakehouse objects for the Cohorts view overlap heavily:

- `rpt_marketing_lead_cohort_performance` — actuals (leads, sets, runs, wins, revenue, cost, realized rates) per campaign × jurisdiction × period cohort.
- `rpt_marketing_cohort_expected_yield` — benchmark/expected-yield overlay for the same cohort grain, but exposed as a **9-rung benchmark candidate ladder** (multiple candidate rows per cohort at different specificity levels), not one row per cohort.

Naively joining them fans out. Two grain quirks had to be resolved first:

1. **AHJ resolution fallback.** When `final_reporting_jurisdiction_key = 'UNKNOWN'` (AHJ resolution failed), `rpt_marketing_lead_cohort_performance` falls back to zip-code grain — `resolved_zip_code` must be part of the join key or rows silently collapse into each other.
2. **Benchmark candidate ladder.** `rpt_marketing_cohort_expected_yield` must be collapsed to the single most-specific *reliable* candidate per cohort before joining, using `QUALIFY ROW_NUMBER() OVER (PARTITION BY ... ORDER BY benchmark_candidate_priority ASC) = 1` filtered to `is_reliable_for_expected_yield`. Cohorts with no reliable candidate at any level are left unmatched (yield fields come back `NULL`, not a guess).

### Validation

The join below was run read-only against live data before being finalized: joined row count = 199,702, exactly matching the base `rpt_marketing_lead_cohort_performance` row count (confirms zero fanout), with 199,041 rows (99.7%) matched to a reliable benchmark candidate.

### Investigation-friendliness

The view keeps the full hierarchy/geography/period/actuals/rates/cost/benchmark column set rather than a narrow dashboard-shaped subset. This was an explicit requirement: the view needs to work as a general-purpose ad hoc investigation surface (for both the dashboard API and for coworkers querying it directly, per the Access Model below), not just an API backing store shaped only for current chart needs.

### Funnel semantics: confirmed fixed-cohort progression

Requirement: the Cohorts view must show, for the *same* population of leads created around a spend date, how many of those leads got a set, how many of those sets became a run, and how many of those runs closed — a true sequential funnel of one tracked group, not period-coincident counts (e.g. "sets that happened in March" mixed with leads from any month).

Confirmed by reading `rpt_marketing_lead_cohort_performance`'s view definition (`INFORMATION_SCHEMA.VIEWS.view_definition`), not just its field names:

- Cohort origin is `cohort_lead_created_date`, truncated to `DATE_TRUNC(..., WEEK(MONDAY))` — a cohort is a fixed group of leads anchored to when they were created.
- `set_count`, `run_count`, `win_count` are each `SUM()` of a per-lead 0/1 indicator (`business_set_count`, `business_run_count`, `official_win_count`) carried at individual-lead grain from the base fact table, `analytics_fact.fact_lead_funnel_attributed`. Each flag answers "did this specific lead (from this cohort) reach this stage," not "how many set/run/win events happened in this period."
- This is why `cohort_age_days` and `cohort_maturity_bucket` exist: cohorts need time to mature, since leads keep progressing through stages after their origin date.

Net effect: `lead_count` → `set_count` → `run_count` → `win_count`/`lost_count` on a single cohort row is already the exact leads-created → sets-from-those-leads → runs-from-those-sets → closed funnel requested, for the same tracked lead population, sourced from a single fact table with no separate per-stage joins needed. `rpt_marketing_cohort_performance_with_yield` passes all four fields through unchanged, so no SQL redesign is required — the dashboard's Cohorts view can render this funnel directly from the view already designed above.

### Final SQL

```sql
CREATE OR REPLACE VIEW `lumina-lakehouse.marketing_tool_ops.rpt_marketing_cohort_performance_with_yield` AS

WITH yield_selected AS (
  -- Collapse the 9-rung benchmark candidate ladder to the single most-specific
  -- RELIABLE candidate per cohort. Cohorts with no reliable candidate at any
  -- level are left unmatched (yield fields come back NULL, not a guess).
  SELECT *
  FROM `lumina-lakehouse.analytics_rpt.rpt_marketing_cohort_expected_yield`
  WHERE is_reliable_for_expected_yield
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY campaign_sf_id, final_reporting_jurisdiction_key, resolved_zip_code,
                 cohort_period_grain, cohort_period_start_date
    ORDER BY benchmark_candidate_priority ASC
  ) = 1
)

SELECT
  -- Campaign hierarchy
  p.campaign_sf_id, p.campaign_sk, p.campaign_name, p.parent_campaign_name,
  p.grandparent_campaign_name, p.campaign_reporting_rollup_name, p.campaign_sub_rollup_name,
  p.campaign_hierarchy_path, p.campaign_type, p.campaign_status, p.campaign_stage,
  p.inferred_campaign_channel, p.campaign_group,

  -- Geography / resolution chain
  p.final_reporting_jurisdiction_key, p.final_reporting_jurisdiction_type,
  p.final_reporting_jurisdiction_label, p.final_reporting_ahj_sf_id, p.final_reporting_ahj_name,
  p.final_ahj_resolution_method, p.final_ahj_resolution_confidence, p.resolved_county,
  p.resolved_state, p.resolved_zip_code, p.resolved_ops_region, p.reporting_market_label,
  p.reporting_market_county, p.reporting_market_state,

  -- Period / maturity
  p.cohort_period_grain, p.cohort_period_start_date, p.cohort_period_end_date,
  p.cohort_age_days, p.cohort_maturity_bucket, p.sample_size_bucket,

  -- Actuals: raw counts
  p.lead_count, p.distinct_campaign_members, p.distinct_people, p.set_count, p.run_count,
  p.win_count, p.lost_count, p.win_revenue, p.win_kw,

  -- Backlog / aging signals
  p.set_no_run_30_plus_count, p.run_no_win_60_plus_count, p.open_no_set_30_plus_count,
  p.active_pipeline_candidate_count, p.active_pipeline_candidate_revenue,

  -- Realized rates
  p.cohort_row_set_rate, p.cohort_row_run_rate_from_sets, p.cohort_row_win_rate_from_runs,
  p.cohort_row_lead_to_win_rate,

  -- Cost / spend
  p.allocated_spend_amount, p.spend_allocation_method, p.cost_per_lead, p.cost_per_set,
  p.cost_per_run, p.cost_per_win, p.revenue_per_spend, p.revenue_per_win,

  -- Benchmark / expected-yield overlay
  y.benchmark_level              AS applied_benchmark_level,
  y.benchmark_candidate_priority AS applied_benchmark_priority,
  y.benchmark_confidence, y.benchmark_confidence_score, y.benchmark_data_quality_status,
  y.benchmark_lead_to_win_rate, y.benchmark_revenue_per_win,
  y.expected_mature_win_count, y.expected_mature_revenue,
  y.expected_remaining_win_count, y.expected_remaining_revenue,
  y.win_attainment_vs_expected, y.revenue_attainment_vs_expected,
  y.expected_yield_category, y.expected_yield_usability,
  y.campaign_sf_id IS NOT NULL   AS has_reliable_benchmark,

  p.rpt_loaded_at

FROM `lumina-lakehouse.analytics_rpt.rpt_marketing_lead_cohort_performance` p
LEFT JOIN yield_selected y
  ON  y.campaign_sf_id = p.campaign_sf_id
  AND y.final_reporting_jurisdiction_key = p.final_reporting_jurisdiction_key
  AND IFNULL(y.resolved_zip_code, '') = IFNULL(p.resolved_zip_code, '')
  AND y.cohort_period_grain = p.cohort_period_grain
  AND y.cohort_period_start_date = p.cohort_period_start_date
```

## Data model: Scenario-baseline grain-check

`rpt_marketing_period_projection` was flagged in an earlier draft of this spec as not yet grain-verified. Ran the same `COUNT(*)` vs `COUNT(DISTINCT <candidate key>)` spike used for Cohorts above, directly against live data.

**Result: clean, zero-fanout grain.** Candidate key `(campaign_sf_id, metric_name, metric_variant, projection_period_grain, projection_period_start_date)`:

- `total_rows` = 35,122
- `distinct_key_no_asof` = 35,122 (exact match — no fanout on this key)
- `null_campaign_rows` = 0 (every row ties to a named campaign, satisfying the handoff doc's "named campaign rows, not rollups only" requirement)
- `distinct_campaigns` = 166, `distinct_metric_names` = 8, `distinct_metric_variants` = 3

Metric taxonomy (`metric_name` × `metric_category`, each available at all four `projection_period_grain` values — WEEK/MONTH/QUARTER/YEAR):

| metric_name | metric_category |
|---|---|
| KW | Outcome Value |
| Leads | Funnel Count |
| Revenue | Outcome Value |
| Runs | Funnel Count |
| Sets | Funnel Count |
| Spend - Daily Prorated | Spend |
| Spend - Week Assigned | Spend |
| Wins | Funnel Count |

No new view is needed for Scenario-baseline — unlike Cohorts, this object can be queried directly from `analytics_rpt.rpt_marketing_period_projection` with the confirmed grain key as filters/group-by, plus `metric_name`/`metric_category` used to pivot Spend/Funnel Count/Outcome Value metrics into the scenario chart's series. Endpoint filter/response shaping is implementation-plan work, not yet done here — this section only confirms the source is safe to build against.

## Dataset placement: `marketing_tool_ops` vs `analytics_rpt`

The view is created in `marketing_tool_ops`, not `analytics_rpt`. `analytics_rpt` is owned and maintained by the core lakehouse pipeline team; parking a dashboard-specific reduction view there risks silent breakage on their refactors and blurs ownership of a view nobody on that team asked for. `marketing_tool_ops` is already the dashboard app's own dataset (created for `dashboard_notes` in the prior notes design), so this keeps app-owned derived SQL under the app team's own change control, decoupled from the core pipeline's release cadence.

## Access model / IAM

Two tiers, kept deliberately separate: the app's own read path, and human coworkers doing ad hoc investigation via GCP IAM.

**App service account.** A dedicated, minimally-scoped service account (e.g. `marketing-dashboard-reader@lumina-lakehouse.iam.gserviceaccount.com`) runs the dashboard's live-data queries. It's granted `roles/bigquery.dataViewer` on both `marketing_tool_ops` (for the new Cohorts view) and `analytics_rpt` (for the AHJ/Overview/Campaigns endpoints, which read `rpt_marketing_campaign_ahj_performance` directly per the handoff doc's original plan), plus `roles/bigquery.jobUser` at the project level to run query jobs. No broader role (`bigquery.admin`/`editor`) is needed since the app never writes to BigQuery.

*Open question to confirm before implementation:* what service account the existing `marketing-decision-tool` Cloud Run service currently runs as. If it's already a broad/shared identity, migrate the live-data code path to this new dedicated SA rather than granting BigQuery access to whatever it currently uses.

**Coworker ad hoc access.** Coworkers get access through a Google Group (e.g. `marketing-lakehouse-readers@luminasolar.com`), not a shared service account or individual IAM bindings — group membership is managed once, in one place, and is auditable. The group is granted `roles/bigquery.dataViewer` on `marketing_tool_ops` only, plus `roles/bigquery.jobUser` at the project level so members can run their own queries.

Critically, the group is **not** granted access to `analytics_rpt` directly — that dataset also holds non-marketing sensitive reporting (payroll/ADP, finance/forecast) that coworkers have no reason to see. To let the group query `rpt_marketing_cohort_performance_with_yield` (which reads from `analytics_rpt` tables under the hood), that relationship is made a BigQuery **Authorized View**: the view (or a thin passthrough view placed in `marketing_tool_ops` for other marketing-only `analytics_rpt` objects the group should see, like the AHJ performance view) is added to `analytics_rpt`'s authorized-view list. This lets the view read its underlying tables without granting the group's members any direct IAM grant on `analytics_rpt` itself.

Net effect: coworkers can query anything the app team has explicitly chosen to expose via `marketing_tool_ops`, and nothing else in the lakehouse, without needing to touch `analytics_rpt`'s ACL for every new person.

Illustrative sketch (exact `bq`/`gcloud` syntax to confirm at implementation time):

```powershell
# App service account: read access to both datasets it needs
bq add-iam-policy-binding `
  --member="serviceAccount:marketing-dashboard-reader@lumina-lakehouse.iam.gserviceaccount.com" `
  --role="roles/bigquery.dataViewer" `
  lumina-lakehouse:marketing_tool_ops

bq add-iam-policy-binding `
  --member="serviceAccount:marketing-dashboard-reader@lumina-lakehouse.iam.gserviceaccount.com" `
  --role="roles/bigquery.dataViewer" `
  lumina-lakehouse:analytics_rpt

gcloud projects add-iam-policy-binding lumina-lakehouse `
  --member="serviceAccount:marketing-dashboard-reader@lumina-lakehouse.iam.gserviceaccount.com" `
  --role="roles/bigquery.jobUser"

# Coworker group: dataViewer on marketing_tool_ops only
bq add-iam-policy-binding `
  --member="group:marketing-lakehouse-readers@luminasolar.com" `
  --role="roles/bigquery.dataViewer" `
  lumina-lakehouse:marketing_tool_ops

gcloud projects add-iam-policy-binding lumina-lakehouse `
  --member="group:marketing-lakehouse-readers@luminasolar.com" `
  --role="roles/bigquery.jobUser"

# Authorize the marketing_tool_ops view(s) to read analytics_rpt tables
# without granting the group direct analytics_rpt access. Requires patching
# analytics_rpt's dataset ACL to add the view as an authorized view entry
# (via `bq show --format=prettyjson` + `bq update`, or the equivalent
# Console/Terraform flow) — confirm exact steps against current bq CLI docs.
```

## Error handling

- If a live endpoint's BQ query fails or times out, the dashboard shows a clear "data unavailable" state for that view/card. It must never silently fall back to the synthetic demo values — that would look like real data and defeats the point of this project.
- Sample-size guardrails (handoff doc Recommended Next Step #4) become enforceable now that live `sample_size_bucket` values flow through: don't allow a `Scale` recommendation for `Low Sample` without a test-spend recommendation attached, and surface `No Same-Period Sample` as an investigation flag, not a spend recommendation.
- Cohorts rows with `has_reliable_benchmark = false` (the ~0.3% unmatched) should render with actuals but an explicit "no benchmark available" state instead of blank/zeroed expected-yield fields.

## Testing

- Extend the existing `work/verify_marketing_tool.js`-style harness (or add a sibling script) with fixtures for each new endpoint's response shape, covering the AHJ/Overview/Campaigns/Cohorts data paths.
- Manual: load each of the four ready views against live data in a browser; cross-check a handful of known campaigns/AHJs/cohorts against a direct BigQuery query for the same filters to sanity-check the wiring end to end.
- Confirm the read-only app service account genuinely cannot write (role scope check, not a runtime test — `dataViewer` has no write path).
- Scenario-baseline's endpoint isn't being built in this design pass (grain-check only — see Scope and the grain-check section above), so it's excluded from this pass's testing; it's ready to include in the implementation plan without a further discovery spike.

## Deployment notes (for the implementation plan)

- No new Cloud Run service — new endpoints are added to the existing `marketing-decision-tool` service/`dashboard_server.py`.
- Create `marketing-dashboard-reader` service account (or confirm and reuse the Cloud Run service's current runtime SA if it's already appropriately scoped) and apply the IAM bindings above.
- Execute the `CREATE OR REPLACE VIEW` DDL above in `marketing_tool_ops` (not yet run — validated read-only only).
- Set up the `marketing-lakehouse-readers` Google Group and the `analytics_rpt` authorized-view relationship.
- Scenario-baseline's grain-verification spike is done (see Data model: Scenario-baseline grain-check above) and came back clean, with no join-fanout complexity like Cohorts had — its endpoint can be included directly in this implementation plan rather than needing its own follow-up design note.
