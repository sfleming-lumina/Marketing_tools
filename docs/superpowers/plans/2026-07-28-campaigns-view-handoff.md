# Handoff: Campaigns View Live-Data Plan (not yet written)

**Purpose of this doc:** Let a fresh chat session resume this work with zero
re-discovery. Everything verbatim needed to write the implementation plan
has already been gathered — it just hasn't been transcribed into a plan
file yet. Read this doc, then go straight to drafting the plan; do not
re-read the whole dashboard HTML file from scratch.

## 1. Where this fits

Repo: `sfleming-lumina/Marketing_tools`, local clone
`C:\Users\sflem\OneDrive\Documents\Marketing\Marketing_tools`, branch `master`.

Overarching goal (see approved design spec
`docs/superpowers/specs/2026-07-27-live-marketing-data-design.md`): wire live
BigQuery data into the Marketing Decision Tool dashboard across 5 views —
Overview, Cohorts, Campaigns, AHJ, Scenario-baseline.

**AHJ view is fully shipped** (all 8 tasks + final whole-branch review +
fast-follow fixup complete — see `.git/sdd/progress.md`, which is the
authoritative ledger for that finished plan,
`docs/superpowers/plans/2026-07-27-ahj-view-live-data.md`). AHJ is not being
touched again — it exists purely as the **reference architecture to mirror**
for Campaigns.

**Current task: write and then execute a plan for the Campaigns view**,
following the same live-data pattern as AHJ. The plan file
`docs/superpowers/plans/2026-07-28-campaigns-view-live-data.md` **does not
exist yet** — writing it is the very next action.

## 2. Standing authorizations/constraints (still governing, verbatim)

- **"go ahead and work on the master and commit and push please"** — direct
  work on `master` (no feature branch) and pushing to remote is authorized
  for this project, until revoked.
- **"Never fix unrelated/pre-existing bugs outside the current task's scope
  without being asked."** Out-of-scope findings get logged in the ledger,
  not fixed, unless explicitly requested (this is how the AHJ fast-follow
  items were handled — see progress.md Task entries).
- **Git staging discipline:** stage files individually by name
  (`git add <file1> <file2> ...`), never `git add -A` or `git add .`.
- Local Python default is 3.11.15, which fails `py_compile` on
  `dashboard_server.py` due to a pre-existing (out-of-scope, do-not-fix)
  nested f-string in `_ask_claude` that needs PEP 701 (Python ≥3.12). Use
  `py -3.12 -m py_compile dashboard_server.py` locally to match CI
  (`python-version: "3.12"` in `.github/workflows/ci.yml`).

## 3. Ratified Campaigns-view scope ("yes lets do option 1")

Replace **only the actuals/ranking layer** with live BigQuery data:
campaign cards, campaign table, ranked recommendations, trend chart — driven
by real `leads/wins/spend/revenue/cpw/revenuePerSpend` grouped by campaign,
gated by a CPW-vs-benchmark / lead-to-win-rate / sample-size decision model
that exactly mirrors AHJ's.

**Drop entirely** (confirmed out of scope, safe to delete): budget slider,
channel-allocation sliders, "Capacity safe" objective, capacity-adjusted CPW,
stress, region-fit heatmap scoring, product-mix-lift, margin/payback.

## 4. Backend data source (fully verified via BigQuery MCP tool)

Table: `lumina-lakehouse.analytics_rpt.rpt_marketing_campaign_ahj_performance`
— a **VIEW**, same one AHJ already uses. No new table constant needed; reuse
the existing constant:

```python
AHJ_TABLE_REF = f"{PROJECT_ID}.analytics_rpt.rpt_marketing_campaign_ahj_performance"
```
(`dashboard_server.py:22`)

Relevant columns (of ~110 total, confirmed via `get_table_info`):
`period_grain`, `period_start_date`, `period_end_date`, `campaign_name`,
`campaign_reporting_rollup_name`, `lead_count`, `win_count`,
`allocated_spend_amount`, `win_revenue`, `reporting_market_label`,
`sample_size_bucket`, `cost_per_win`, `revenue_per_spend`,
`lead_to_win_rate`.

**Key difference from AHJ's query:** AHJ collapses straight to trailing
totals per market. Campaigns must group by **campaign + month**
(`period_start_date AS month`) as well, because the ratified scope includes
a trend chart. A new `campaignAggregateRows()` JS function will collapse the
per-month rows into one row per campaign for the cards/table/recommendations
(summing leads/wins/spend/revenue, recomputing cpw/revenuePerSpend/
leadToWinRate/sampleSizeBucket from the sums), while the per-month rows feed
the trend chart directly.

**Date serialization idiom** (confirmed via Grep on `dashboard_server.py`,
the established pattern in this codebase — use for the new `month` field):

```python
row["month"].isoformat()
```
matching the existing precedent `row["created_at"].isoformat()` at
`dashboard_server.py:204`.

## 5. Verbatim source material already captured (do not re-derive)

All of the following has been read fresh, in full, from
`outputs/marketing_decision_tool.html` this session. Re-read the specific
line ranges below only if you need to double check something — you should
NOT need to re-read the whole file.

### 5a. Old Campaigns block to delete — confirmed exact span: **lines 3323–3816 inclusive**

Full function list with line numbers (all confirmed safe to delete — none
are used elsewhere):

- `campaignDetailOptions()` (3323-3326) — **name kept, body replaced**
- `renderGlobalCampaignSelect()` (3328-3333) — **name kept, body replaced**
- `renderCampaignDetailSelect()` (3335-3342) — **name kept, body replaced**
- `campaignBaseRows()` (3344-3369)
- `allocationStore()` (3371-3373)
- `defaultAllocation()` (3375-3377)
- `normalizedCampaignShare()` (3379-3386)
- `objectiveFactor()` (3388-3399)
- `campaignPlanRows()` (3401-3480)
- `campaignRowsByMonth()` (3482-3495)
- `renderCampaignAllocationControls()` (3497-3515)
- `renderCampaignMetrics()` (3517-3547) — old version, will be replaced with a new one of the same name
- `renderDecisionMetricSuite()` (3549-3606)
- `renderCampaignRecommendations()` (3608-3629) — old version, replaced with new one of same name
- `renderCampaignCards()` (3631-3653) — old version, replaced with new one of same name
- `renderCampaignTrend()` (3655-3669) — old version, replaced with new one of same name
- `renderCampaignMoves()` (3671-3719)
- `campaignRegionFit()` (3721-3733)
- `renderCampaignHeatmap()` (3735-3769)
- `renderCampaignTable()` (3771-3795) — old version, replaced with new one of same name
- `renderCampaignPlanner()` (3797-3816) — old version, replaced with new async one of same name

Also delete these Campaigns-only helpers found just **before** that block
(lines 2929-2955), fully verbatim-confirmed and NOT used elsewhere:

```javascript
function activeMarketProfiles() {
  return state.region === "All markets"
    ? regions.map(region => regionProfiles[region])
    : [regionProfiles[state.region]];
}
function marketReadinessScore() {
  const profiles = activeMarketProfiles();
  const total = profiles.reduce((sum, profile) => {
    return sum + profile.utility * 0.18 + profile.permit * 0.24 + profile.crew * 0.22 + profile.survey * 0.2 + (100 - profile.cancel) * 0.16;
  }, 0);
  return Math.round(total / Math.max(1, profiles.length));
}
function marketReadinessTone(score) {
  if (score >= 72) return "good";
  if (score >= 64) return "warn";
  return "bad";
}
function campaignProductLift(row) {
  let lift = row.source === "Partner" ? 0.08 : row.source === "Referral" ? 0.06 : row.source === "Paid Search" ? 0.04 : row.source === "Direct Mail" ? 0.03 : 0.01;
  if (row.campaign.includes("Battery")) lift += 0.14;
  if (row.campaign.includes("Builder") || row.campaign.includes("EnergySage")) lift += 0.06;
  if (row.campaign.includes("Home Shows") || row.campaign.includes("Community")) lift -= 0.02;
  return Math.max(0, lift);
}
```

Also delete (Campaigns-only, elsewhere in the file, already confirmed):
`sourceRegionFit`, `campaignTactics`, `campaignSegments`.

Also delete: `selectedCampaignSegment()` — and simplify `filteredRows()` to
`return baseFilteredRows();` (currently it applies synthetic per-campaign
multipliers via `selectedCampaignSegment()`/`campaignSegments`). This is an
intentional, disclosed, in-scope side effect: Overview loses its
per-campaign-detail reweighting. Not out-of-scope bug-fixing — it's a direct
consequence of deleting `campaignSegments`.

### 5b. SHARED symbols — must NOT touch or delete

`regionProfiles`, `palette`, `heatmapRegions`, `regionReadiness`,
`aggregate()`, `fmtCurrency()`, `fmtNum()`, `pct()`, `noteChip()`,
`metricCardHtml()`, `decisionCardHtml()`, `baseFilteredRows()`,
`escapeAttr()`, `helpChip()`/`helpTextFor()`/`helpCopy`, `drawLineChart()`,
`drawFrontier()` (used by Scenario view, html:4401), `API_BASE`,
`wireNoteChips()`, `wireTips()`, `months`, `sources`, `groupedByMonth()`
(html:2957-2969, used by Overview), `trendMetricDefs`/`trendSeries`/
`renderTrendExplorer` (Overview-only, shared block, not touched by
Campaigns).

Note: `helpCopy` (html:2751-2848, full object, all ~45 entries) contains
several Campaigns-specific strings referencing deleted allocator concepts —
e.g. "Campaign budget allocator", "Recommended campaign buys", "Budget
transfer assistant". These need review/update or removal as part of the
frontend markup task (do not leave stale help text referencing deleted UI).

### 5c. AHJ scoring pattern to mirror exactly — verbatim, html:3818-3850

```javascript
function ahjBenchmarks(rows) {
  const rowsWithWins = rows.filter(row => (row.wins || 0) > 0);
  const totalWins = rowsWithWins.reduce((sum, row) => sum + (row.wins || 0), 0);
  const totalSpend = rowsWithWins.reduce((sum, row) => sum + (row.spend || 0), 0);
  const totalLeads = rowsWithWins.reduce((sum, row) => sum + (row.leads || 0), 0);
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
```

**Important ratified deviation from the AHJ plan's original (literal) text,
now the authoritative semantics carried forward to Campaigns too:** the
benchmark sums exclude rows with `wins === 0` (see `ahjBenchmarks` above —
`rowsWithWins` filter). This was a user-adjudicated decision during AHJ Task
5 (see `.git/sdd/progress.md` Task 5 entry) — the literal unfiltered-sum
version the AHJ plan text originally specified produced a benchmark that
contradicted the plan's own worked example, and the user chose to keep the
filtered version. `campaignBenchmarks()` must use this same filtered-sum
shape.

Default fallback constants (`1100` for cpw, `0.2` for leadToWinRate) may be
revisited for Campaigns in the plan write-up — TBD — but the **shape** of
the function (filter to wins>0, sum, divide, fallback constants) is fixed.

`ahjDecisionFor()` is the exact template for `campaignDecisionFor()` — same
four-tier Scale/Test/Hold/Avoid ladder, same ratio thresholds (1, 1.45,
2.15), same `leadToWinBenchmark * 0.7` relaxation for the Test tier.

### 5d. AHJ render/fetch pattern to mirror — verbatim, html:3852-4346

Full function list confirmed read in full (large block): `ahjRankingValue()`,
`ahjMetricDisplay()`, `ahjSampleConfidenceRank()`, `ahjBaseDecisionRows()`,
`ahjCampaignOptions()`, `selectedAhjCampaignLabel()`, `selectedAhjLabel()`,
`setAhjSelection()`, `ahjDecisionRows()`, `renderAhjFocusSelect()`,
`renderAhjMetrics()`, `renderAhjInsights()`, `renderAhjHeatmap()`,
`renderAhjAllocationTable()`, `selectedAhjPair()`, `selectedPairHtml()`,
`ahjClickCard()`, `renderRankedAhjCanvas()`, `renderCampaignsForAhjCanvas()`,
`renderMetricMatrixCanvas()`, `renderAhjInvestigationCanvas()`,
`renderAhjDetail()`, `ahjAreaRows()`, `ahjAreaCopy()`,
`renderAhjPerformanceBreakdown()`, `ahjCurrentFetchKey()`,
`ensureAhjRowsLoaded()`, `renderAhjLoadError()`, `renderAhjPlanner()`.

Given the ratified Campaigns scope (cards/table/recommendations/trend only —
no heatmap/canvas/allocation-table/detail-drilldown), **only these need
Campaigns equivalents**:

- Scoring core: `campaignBenchmarks`, `campaignSampleConfidenceRank`,
  `campaignDecisionFor`, `campaignRankingValue`, `campaignMetricDisplay`,
  `campaignBaseDecisionRows`, `campaignDecisionRows`, plus a new
  `campaignAggregateRows` (no AHJ equivalent — needed because Campaigns
  fetches month-grained rows and must collapse them to one row per
  campaign for cards/table/recommendations) and `campaignTrendRows` (feeds
  the trend chart from the ungrouped month-grained rows).
- Fetch/error/orchestration trio: `campaignCurrentFetchKey`,
  `ensureCampaignRowsLoaded`, `renderCampaignLoadError`,
  `renderCampaignPlanner`.

Exact templates, verbatim:

```javascript
// ahjCurrentFetchKey() returns a static string: "ahj-performance:trailing"

async function ensureAhjRowsLoaded() {
  const fetchKey = ahjCurrentFetchKey();
  if (state.ahjRowsFetchKey === fetchKey) return;
  const token = ++state.ahjFetchToken;
  try {
    const response = await fetch(`${API_BASE}/ahj-performance`);
    if (!response.ok) throw new Error(`AHJ performance fetch failed: ${response.status}`);
    const rows = await response.json();
    if (token !== state.ahjFetchToken) return;
    state.ahjRows = rows;
    state.ahjRowsFetchKey = fetchKey;
    state.ahjLoadError = null;
  } catch (error) {
    if (token !== state.ahjFetchToken) return;
    state.ahjRows = state.ahjRows || [];
    state.ahjLoadError = error.message || "AHJ performance data is unavailable.";
  }
}

function renderAhjLoadError() {
  const banner = document.getElementById("ahjLoadError");
  const text = document.getElementById("ahjLoadErrorText");
  if (!banner || !text) return;
  if (state.ahjLoadError) {
    text.textContent = `AHJ data unavailable: ${state.ahjLoadError}`;
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
  }
}
```

(`renderAhjPlanner()`, html:4334-4346, is the orchestrator: calls
`ensureAhjRowsLoaded()`, then `renderAhjLoadError()`, then computes
`ahjDecisionRows()`, then calls each sub-renderer in sequence. Exact template
for the new `renderCampaignPlanner()` (async), though its sub-renderer call
list will be much shorter per scope: just the cards/table/recommendations/
trend renderers, no heatmap/canvas/allocation-table/detail-drilldown.)

**Critical architectural wrinkle, unique to Campaigns:** `globalCampaignSelect`
is a **shared topbar control**, populated unconditionally by
`renderGlobalCampaignSelect()` on every single `render()` call. This means
the campaign-rows fetch must happen **eagerly at app init** (unlike AHJ,
which fetches lazily the first time the AHJ view is opened), while the
select-population functions (`campaignDetailOptions`,
`renderGlobalCampaignSelect`, `renderCampaignDetailSelect`) stay synchronous,
reading whatever is already cached in `state.campaignRows` at call time.

### 5e. `currentNoteContext()` — verbatim, html:4523-4537

```javascript
function currentNoteContext() {
  return {
    region: state.region,
    source: state.source,
    range: state.range,
    campaignObjective: state.campaignObjective,
    campaignGrain: state.campaignGrain,
    campaignDetail: state.campaignDetail,
    ahjObjective: state.ahjObjective,
    ahjCampaign: state.ahjCampaign,
    ahjLayout: state.ahjLayout,
    ahjArea: state.ahjArea,
    selectedAhj: state.selectedAhj
  };
}
```

The `campaignGrain: state.campaignGrain,` line (4529) must be **deleted** —
Campaigns no longer has a Source/Detail grain toggle. `campaignObjective`
state field is **kept but repurposed** to a 5-option AHJ-style objective
list (mirroring `ahjObjective`'s option set/semantics).

### 5f. `dashboard_server.py` JSON/date conventions — confirmed via Grep

```
1:import json
118:        body = json.dumps(payload).encode("utf-8")
120:        self.send_header("Content-Type", "application/json")
204:                "created_at": row["created_at"].isoformat(),
220:            "created_at": datetime.now(timezone.utc).isoformat(),
231:        row["context"] = json.dumps(row["context"])
263:        checked_at = datetime.now(timezone.utc).isoformat()
275:                "modified_at": table.modified.isoformat() if table.modified else None,
476:        context_json = json.dumps(context, indent=2, default=str)[:20_000]
506:            data=json.dumps(body).encode("utf-8"),
509:                "content-type": "application/json",
```

Other confirmed (from earlier full read, not re-verified this pass but not
contradicted): `AHJ_TABLE_REF` constant (line 22), `build_ahj_performance_query`,
`shape_ahj_row`, the `do_GET` route block (~141-158), the `_ahj_performance`
handler (~238-260, returns `(status, payload)` tuples — 400 for invalid
`months`, 502 for BigQuery failures, per the AHJ fast-follow fix — see
progress.md), `_fallback_insights` (~328-429), and the `_num`/`_first`/
`_label`/`_currency`/`_percent` helpers (~431-454).

**Before writing Task 1 of the plan**, re-read
`build_ahj_performance_query`/`shape_ahj_row`/`_ahj_performance`/`do_GET` in
full from `dashboard_server.py` if there's any doubt about the exact
`ScalarQueryParameter` binding convention — this was the one piece of
backend source not freshly re-verified in the final session before this
handoff was written.

## 6. Full 9-task breakdown (designed, ready to transcribe into the plan)

1. **Backend query builder & row shaper.** `build_campaign_performance_query()`
   and `shape_campaign_row()` in `dashboard_server.py`, mirroring
   `build_ahj_performance_query`/`shape_ahj_row` exactly but grouping by
   `campaign`/`campaignRollup`/`month` instead of collapsing to trailing
   totals, using `row["month"].isoformat()` for date serialization. Plus
   `tests/test_campaign_performance.py`.
2. **Backend handler + route.** `_campaign_performance` handler +
   `/api/campaign-performance` GET route, inserted after the existing
   `/api/ahj-performance` block in `do_GET`.
3. **CI step insertion** for `tests/test_campaign_performance.py` — insert
   between `.github/workflows/ci.yml` lines 60-62 (right after the existing
   "Run AHJ performance query tests" step, before "Install notes API
   dependencies").
4. **Campaigns view frontend HTML markup rewrite** (lines 1774-1904) + CSS
   cleanup (delete `.budget-total`/`.budget-total strong`, lines 558-569) +
   titleMap Campaigns copy update + review/update or removal of `helpCopy`
   entries referencing deleted allocator concepts (see §5b note).
5. **State fields + JS scoring layer rewrite.** State object edits; delete
   `selectedCampaignSegment()`, simplify `filteredRows()` to
   `return baseFilteredRows();`; delete `campaignCostSpendDiagnostics`;
   delete `sourceRegionFit`/`campaignTactics`/`campaignSegments`/
   `activeMarketProfiles`/`marketReadinessScore`/`marketReadinessTone`/
   `campaignProductLift`; replace the old campaign block (confirmed
   deletion span 3323-3816) with new scoring functions:
   `campaignDetailOptions`, `renderGlobalCampaignSelect`,
   `renderCampaignDetailSelect`, `campaignAggregateRows`,
   `campaignBenchmarks` (mirrors `ahjBenchmarks` exactly),
   `campaignSampleConfidenceRank`, `campaignDecisionFor` (mirrors
   `ahjDecisionFor` exactly), `campaignRankingValue`, `campaignMetricDisplay`,
   `campaignBaseDecisionRows`, `campaignDecisionRows`, `campaignTrendRows`.
   Plus new `work/verify_campaign_scoring.js`.
6. **Render layer rewrite.** `campaignCurrentFetchKey`,
   `ensureCampaignRowsLoaded` (mirrors `ensureAhjRowsLoaded` exactly),
   `renderCampaignLoadError` (mirrors `renderAhjLoadError` exactly), new
   `renderCampaignMetrics`/`renderCampaignRecommendations`/
   `renderCampaignCards`/`renderCampaignTrend`/`renderCampaignTable`, async
   `renderCampaignPlanner` (mirrors `renderAhjPlanner`'s orchestration
   pattern, shorter sub-renderer list per scope) + eager-fetch init wiring
   (see §5d wrinkle) + rewired event listeners + rewritten
   `work/verify_marketing_tool.js` + new `work/verify_campaign_error_state.js`
   (mirrors `work/verify_ahj_error_state.js` exactly) + `work/dom_fake.js`
   cleanup.
7. **`dashboardContextForClaude()` rewrite** (`campaign_planner` block,
   mirroring the AHJ context block's shape) + `currentNoteContext()` update
   (drop the `campaignGrain: state.campaignGrain,` line, §5e) + extend
   `work/verify_campaign_scoring.js` with context-shape assertions.
8. **`_fallback_insights()` Python rewrite** — reads
   `campaign_planner.top_recommendations` instead of the deleted
   `cost_spend_diagnostics`; delete dead `_first()` helper if it becomes
   unused. Plus new `tests/test_fallback_insights.py`.
9. **CI wiring** for the two new JS harnesses (`verify_campaign_scoring.js`,
   `verify_campaign_error_state.js`) + extend Task 3's pytest step to also
   run `test_fallback_insights.py` + final local validation command list.

## 7. What's NOT done yet

- The plan file `docs/superpowers/plans/2026-07-28-campaigns-view-live-data.md`
  **does not exist**. Writing it is the immediate next action.
- The exact SQL text for `build_campaign_performance_query()` and the exact
  body of `shape_campaign_row()` were drafted informally in reasoning but
  never finalized against the real `_ahj_performance` binding convention or
  written to any file. Verify the binding convention (re-read
  `dashboard_server.py`'s AHJ query builder/handler if in doubt — see §5f)
  before finalizing Task 1's code blocks.
- No code changes of any kind have been made yet for Campaigns. The AHJ
  view is untouched and remains fully shipped/working.

## 8. Immediate next step for whoever picks this up

1. If any doubt remains about the BigQuery `ScalarQueryParameter` binding
   convention, re-read `build_ahj_performance_query`/`shape_ahj_row`/
   `_ahj_performance`/`do_GET` in `dashboard_server.py` fresh.
2. Finalize `build_campaign_performance_query(months=6, campaign=None)` and
   `shape_campaign_row(row)`.
3. Use the `writing-plans` skill to draft and save the full 9-task plan to
   `docs/superpowers/plans/2026-07-28-campaigns-view-live-data.md`, using
   every verbatim code block in this handoff doc — no placeholders.
4. Run the `writing-plans` skill's self-review pass (spec coverage /
   placeholder scan / type consistency).
5. Offer the Subagent-Driven vs. Inline Execution choice per that skill,
   then proceed with `subagent-driven-development` (per-task ledger goes in
   `.git/sdd/progress.md`, same file the AHJ plan used — check it first, it
   currently only has AHJ entries).
6. On completion, use `finishing-a-development-branch` — but note the
   standing authorization already covers direct work on `master` with
   pushes, so that skill's merge-PR menu likely collapses to "already on
   master, just confirm final push."

## 9. Reference docs (all still accurate, not re-verified this pass beyond what's noted)

- `docs/superpowers/specs/2026-07-27-live-marketing-data-design.md` — the
  overarching 5-view design spec.
- `docs/superpowers/plans/2026-07-27-ahj-view-live-data.md` — the finished
  AHJ plan (the pattern being mirrored).
- `.git/sdd/progress.md` — AHJ's complete ledger, including the
  user-adjudicated benchmark-filter deviation (Task 5) and the fast-follow
  fixup (error banner, retry, `_ahj_performance` tuple returns, `API_BASE`
  rename). Check this file first when resuming — it's per-repo, not synced.
- Memory file `project_marketing_tools.md` (in the auto-memory system) has a
  condensed version of the standing authorizations/constraints and the
  two-tier AHJ fetch architecture rationale.
