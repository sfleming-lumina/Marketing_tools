# Marketing Decision Tool Handoff

Date: 2026-07-27  
Repo: `sfleming-lumina/Marketing_tools`  
Local path: `C:\Users\sflem\OneDrive\Documents\Marketing\Marketing_tools`  
Cloud Run URL: https://marketing-decision-tool-6stghdub4a-ue.a.run.app  
Latest deployed revision at handoff: `marketing-decision-tool-00021-qlf`

## Purpose

This stream of work turned the marketing demo into an IAP-protected decision workbench for campaign, AHJ, county, and source performance investigation. The focus shifted from static recommendations to an interactive workflow where marketing can compare named campaign performance by AHJ, inspect performance drivers, leave feedback notes, refresh BQ metadata, and ask Claude questions against the current dashboard context.

## Current Application Shape

Main app file:

- `outputs/marketing_decision_tool.html`

Server/API:

- `dashboard_server.py`

Verifier harness:

- `work/verify_marketing_tool.js`
- `work/verify_dashboard_notes.js`
- `work/dom_fake.js`

Notes API:

- `notes-api/`

CI/CD:

- `.github/workflows/ci.yml`
- Pushes to `master` run dashboard rendering checks, notes wiring checks, Python syntax checks, notes API tests, then deploy notes API and dashboard to Cloud Run.

## Major Features Added

### IAP and Cloud Run Deployment

- Deployed the dashboard to Cloud Run.
- Kept the dashboard protected by IAP.
- Confirmed access flow for approved users.
- Latest confirmed service URL: https://marketing-decision-tool-6stghdub4a-ue.a.run.app

### Data Freshness

- Added top badge for BQ freshness.
- Added `Refresh BQ` button that calls the dashboard API and checks source object metadata.
- Updated stale copy so it no longer claims the demo is blocked by expired local `gcloud` auth.

### Notes and Feedback

- Notes are tied to specific dashboard elements, sections, tiles, charts, controls, and tables.
- Notes persist via the notes API.
- Notes include feedback categories:
  - Helpful
  - Needs tweak
  - Not helpful
- The feedback page rolls up notes across the tool.

### Ask Claude

- Added `Ask Claude` button and same-origin `/api/ask-claude`.
- Claude receives current filters, selected view, campaign planner context, AHJ planner context, freshness, object inventory, and recent notes.
- Output is formatted into clean insight sections instead of raw text.
- Added fallback handling for no text, overloaded, and transient Claude failures.
- Current limitation: Claude uses dashboard-supplied context only. It does not run arbitrary BQ queries from the button.

### Campaign Planner

- Added named campaign detail selection.
- Added campaign-specific trend and legend.
- Added campaign dropdown at the top.
- Improved campaign diagnostics and cost-per-win variance handling.
- Added campaign heatmap and campaign decision table.

### AHJ Planner

The AHJ tab went through several iterations and is now an investigation workspace.

Current AHJ workflow:

- Select `Campaign focus`.
- Select `Rank AHJs by`.
- Select `AHJ focus`.
- Select layout:
  - `Ranked AHJs`
  - `Campaigns for AHJ`
  - `Metric matrix`
- Click AHJ cards, campaign cards, matrix cells, table rows, or heatmap cells to re-center the tab on that AHJ/campaign pair.
- Drill into Efficiency, Quality, Capacity, or Growth.

Current AHJ ranking metrics:

- Balanced decision score
- Revenue per spend
- Lowest cost per win
- Lead to win rate
- AHJ readiness
- Capacity headroom
- Margin quality
- Sample confidence
- Growth volume

Important behavior:

- Volume no longer dominates the default recommendation.
- Growth volume is available as an explicit ranking mode, but it is not silently overweighted in balanced ranking.
- `Scale` is intentionally gated by readiness, fit, stress, CPW, and sample signal.
- `Sample confidence` is modeled to align with the lakehouse field `sample_size_bucket`.

## Lakehouse Objects Reviewed

Primary AHJ/campaign object:

- `lumina-lakehouse.analytics_rpt.rpt_marketing_campaign_ahj_performance`

Legacy or related object:

- `lumina-lakehouse.analytics_rpt.rpt_campaign_ahj_performance`

Schema fields confirmed in the AHJ object include:

- Named campaign:
  - `campaign_name`
  - `parent_campaign_name`
  - `grandparent_campaign_name`
  - `campaign_reporting_rollup_name`
  - `campaign_sub_rollup_name`
  - `campaign_hierarchy_path`
- AHJ and geography:
  - `final_reporting_jurisdiction_label`
  - `final_reporting_ahj_name`
  - `resolved_county`
  - `resolved_state`
  - `reporting_market_label`
  - `reporting_market_county`
  - `reporting_market_state`
- Performance:
  - `lead_count`
  - `set_count`
  - `run_count`
  - `win_count`
  - `win_revenue`
  - `allocated_spend_amount`
  - `cost_per_lead`
  - `cost_per_set`
  - `cost_per_run`
  - `cost_per_win`
  - `revenue_per_spend`
  - `lead_to_win_rate`
  - `win_rate_from_runs`
- Quality and confidence:
  - `sample_size_bucket`
  - `lead_geo_resolution_rate`
  - `final_ahj_resolution_method`
  - `final_ahj_resolution_confidence`
- Gross and cancellation fields in the related object:
  - `gross_win_count`
  - `gross_revenue_per_spend`
  - `cost_per_gross_win`
  - `cancelled_project_revenue_pct`
  - `non_cancelled_revenue_per_win`

During the lakehouse check on 2026-07-27, the object reported available `period_grain` values:

- `WEEK`, latest period returned by BQ: `2026-08-03`
- `MONTH`, latest period returned by BQ: `2026-08-01`

The BQ CLI returned data successfully but also emitted a local ADC file write warning:

- `Error saving Application Default Credentials ... WinError 5 Access is denied`

This did not block the schema and sample queries in the current session, but it is worth cleaning up for future local work.

## Recent Commits

- `88ae65d` - Retool AHJ investigation workflow
- `d66b02d` - Rank AHJs by campaign performance metrics
- `b1fa9d4` - Tighten AHJ campaign performance view
- `4f88600` - Add AHJ spend planner view
- `bd432a9` - fix: update freshness status copy
- `e591859` - fix: tighten top filter spacing
- `1832727` - fix: fallback on claude overload errors
- `de6340a` - fix: fallback claude insights when response has no text

## Validation Commands

From repo root:

```powershell
node work\verify_marketing_tool.js
node work\verify_dashboard_notes.js
C:\Users\sflem\AppData\Local\Programs\Python\Python312\python.exe -m py_compile dashboard_server.py
```

From `notes-api/`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Latest local validation before handoff:

- Dashboard rendering check passed.
- Notes wiring check passed.
- Dashboard server syntax check passed.
- Notes API tests: `14 passed`.

Latest CI validation:

- GitHub Actions run for `88ae65d` passed.
- Cloud Run deployment completed successfully.

## Known Limitations

- The dashboard still uses a deterministic demo model for AHJ performance instead of directly querying the live AHJ campaign object in the browser.
- BQ freshness is live metadata, but the performance cards are not yet live BQ result sets.
- Claude cannot run arbitrary BQ queries from the dashboard. It answers using the dashboard context payload.
- The local `bq` CLI can emit an ADC write warning on this machine even when queries complete.
- The AHJ model approximates readiness, capacity, and margin lift using local demo profiles. It should be swapped to real lakehouse fields where possible.

## Recommended Next Steps

1. Add a controlled dashboard API endpoint for live AHJ campaign performance.
   - Source from `analytics_rpt.rpt_marketing_campaign_ahj_performance`.
   - Support filters for period grain, date range, campaign name, market, state, county, AHJ, and sample bucket.
   - Return named campaign rows, not rollups only.

2. Replace synthetic AHJ model rows with live rows.
   - Map:
     - `lead_count` to leads
     - `set_count` to sets
     - `run_count` to runs
     - `win_count` to wins
     - `allocated_spend_amount` to spend
     - `win_revenue` to revenue
     - `cost_per_win` to CPW
     - `revenue_per_spend` to efficiency
     - `lead_to_win_rate` to quality
     - `sample_size_bucket` to confidence

3. Add a period control for AHJ views.
   - `WEEK` vs `MONTH`
   - latest complete period vs trailing 4 or 12 periods

4. Add explicit sample-size guardrails.
   - Do not allow `Scale` for `Low Sample` without a test-spend recommendation.
   - Surface `No Same-Period Sample` as an investigation item, not a spend recommendation.

5. Add opportunity/cancellation quality once live fields are wired.
   - Use gross vs net win metrics.
   - Use cancelled revenue percentage.
   - Use synced quote revenue coverage where available.

6. Improve Ask Claude once live AHJ data is available.
   - Include the selected live AHJ rows in context.
   - Add a clear note that recommendations are based on current selected filters and sample-size limitations.

## Operational Notes

- Main branch: `master`
- Deployment is automatic on push to `master`.
- Cloud Run service: `marketing-decision-tool`
- Project: `lumina-lakehouse`
- Region: `us-east1`
- Last confirmed deployed revision: `marketing-decision-tool-00021-qlf`

