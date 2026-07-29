# Marketing lakehouse audit

**Audit date:** 2026-07-28  
**Validation source:** `Marketing Report 2026_Official.xlsx`  
**Dashboard:** Marketing Intelligence / Command Center

## Executive conclusion

The dashboard's curated cohort logic is structurally sound for answering, “What happened to leads created by this campaign?” Its fact grains and principal dimension joins do not create measurable fanout, spend records are uniquely keyed, and recorded spend reconciles exactly to the official workbook at the workbook's last recorded-spend date.

The official workbook and lakehouse do not use the same outcome date semantics. The workbook reports sets, runs, wins, and revenue by the date each event occurred; the dashboard fixes leads into their created-month cohort and follows their later outcomes. Both are valid, but historical event totals cannot be reproduced exactly from mutable current Salesforce records without an immutable snapshot. The product now states this distinction in its reconciliation view.

Fifteen genuine test/demo records are now excluded in the curated reporting layer. Raw Salesforce and `analytics_fact` objects remain unchanged for traceability. State labels are normalized into DMV, Pennsylvania, Outside operating footprint, and Unresolved, with the default dashboard scope set to DMV + Pennsylvania.

## Lineage reviewed

```text
Salesforce/raw campaign, campaign-member, opportunity, quote, project,
lead-source, spend, ZIP, county, and AHJ sources
  |
  +-- analytics_dim.dim_campaign
  +-- analytics_dim.dim_campaign_reporting_hierarchy
  +-- analytics_dim.dim_marketing_cohort_benchmark
  +-- analytics_dim ZIP/AHJ best-map dimensions
  +-- analytics_fact.fact_marketing_spend
  +-- analytics_fact.fact_lead_funnel_attributed
        |
        +-- marketing_tool_ops.rpt_marketing_test_record_exclusions
        +-- marketing_tool_ops.fact_lead_funnel_attributed_clean
              |
              +-- marketing_tool_ops.rpt_marketing_lead_cohort_performance_clean
                    |
                    +-- analytics_rpt.rpt_marketing_cohort_expected_yield
                    +-- marketing_tool_ops.rpt_marketing_cohort_performance_with_yield
                          |
                          +-- marketing_tool_ops.rpt_marketing_funnel_analysis
                                |
                                +-- marketing_tool_ops.rpt_marketing_funnel_analysis_runtime
                                      |
                                      +-- Marketing Intelligence APIs and browser UI

analytics_rpt.rpt_marketing_period_projection
  |
  +-- marketing_tool_ops.rpt_marketing_period_projection_runtime
        |
        +-- Marketing Intelligence projection API
```

The production service reads materialized runtime tables in `marketing_tool_ops`. It does not need direct access to restricted `analytics_dim`, `analytics_fact`, or `analytics_rpt` sources.

## Official workbook reconciliation

### Source cutoffs

| Workbook area | Maximum source date |
|---|---:|
| Campaign members | 2026-07-14 |
| Sets | 2026-07-13 |
| Runs | 2026-07-13 |
| Wins | 2026-07-14 |
| Recorded spend | 2026-06-10 |

### Published January–July totals

| Campaign rollup | Leads | Sets | Runs | Wins | Revenue | Spend |
|---|---:|---:|---:|---:|---:|---:|
| 3rd Party Vendors LSR | 8,759 | 1,117 | 848 | 198 | $8,048,213.92 | $937,555.00 |
| Internal Marketing LSR | 2,792 | 1,230 | 1,047 | 305 | $12,282,543.79 | $417,217.48 |
| Pay Per Install LSR | 492 raw members | 525 | 388 | 202 | $7,434,743.13 | $132,500.00 |
| Co-op | 87 | 74 | 73 | 37 | $1,350,381.79 | $80,467.20 |

Recorded BigQuery spend matches the workbook exactly when BigQuery is restricted to the workbook's 2026-06-10 spend cutoff:

- 3rd Party Vendors LSR: **$937,555.00**
- Internal Marketing LSR: **$417,217.48**

Outcome differences are definition differences, not evidence of join duplication:

- The workbook counts outcomes in the month the set, run, or win occurred.
- The dashboard attributes all later outcomes to the campaign member's lead-created cohort.
- Pay Per Install workbook leads are raw member rows; its sets can consequently exceed that raw lead count.
- Current Salesforce tables can change after a workbook was published, so a past workbook cannot be exactly reconstructed without a dated snapshot.

## Grain, key, and join checks

| Object/check | Result | Assessment |
|---|---:|---|
| `fact_lead_funnel_attributed` rows / unique keys | 129,911 / 129,911 | Healthy |
| Cohort member/campaign/geography keys | 129,887 unique | Healthy |
| Campaign dimension IDs | 202 / 202 unique | Healthy |
| Campaign hierarchy IDs | 202 / 202 unique | Healthy |
| ZIP/AHJ best-map ZIPs | 43,107 / 43,107 unique | Healthy |
| Spend fact keys | 1,163 unique | Healthy |
| Negative spend | 0 | Healthy |

Thirty-nine campaign/period combinations contain multiple spend entries totaling $994,470. These entries have distinct Salesforce source IDs and generally distinct amounts. They are separate source transactions and should not be automatically deduplicated.

## Test/demo record treatment

The audit found 16 broad text-marker candidates. One was a legitimate address containing “Sample Bridge Road,” so `sample` was deliberately removed from the exclusion expression.

The remaining 15 records contain explicit test, testing, demo, training, dummy, fake, sandbox, or “do not use” markers:

- 15 excluded rows
- 0 wins
- $0 revenue
- 3 records affect 2026 cohorts: two lead/set records and one lead/set/run record

Implementation:

- `rpt_marketing_test_record_exclusions` records every excluded key, reason, and source load time.
- `fact_lead_funnel_attributed_clean` excludes those keys.
- Downstream marketing cohort and runtime objects use the clean view.
- Raw sources are not deleted or modified.

Post-change row reconciliation:

| Layer | Rows |
|---|---:|
| Raw attributed funnel fact | 129,911 |
| Curated clean fact | 129,896 |
| Auditable exclusions | 15 |

## Operating-region normalization

The dashboard now uses these deduplicated groups:

| UI option | Included data |
|---|---|
| Operating footprint (default) | DMV + Pennsylvania |
| DMV | DC, Maryland, Virginia, and normalized spelling variants |
| Pennsylvania | PA and Pennsylvania spelling variants |
| Outside operating footprint | Delaware and every other resolved state |
| Unresolved | Blank/unresolved state |
| All data | Every group |

January–July clean cohort activity:

| Region | Leads | Sets | Runs | Wins | Revenue | Effective spend |
|---|---:|---:|---:|---:|---:|---:|
| DMV | 7,836 | 2,401 | 2,281 | 437 | $17,222,396.48 | $856,624.00 |
| Pennsylvania | 4,750 | 891 | 874 | 147 | $5,820,133.72 | $630,768.71 |
| Outside operating footprint | 443 | 97 | 94 | 8 | $316,564.95 | $60,278.28 |
| Unresolved | 452 | 0 | 0 | 0 | $0.00 | $110,263.64 |

Delaware accounts for 418 of the outside-footprint leads and all eight outside-footprint wins. It includes direct-AHJ activity and real revenue, so it is retained for review rather than classified as test data. The small number of leads in other states should be reviewed as possible address, routing, or acquisition-boundary exceptions.

The unresolved group deserves priority attention: 452 leads and approximately $110,264 of allocated spend have no resolved operating state and no recorded sets.

## Exceptions requiring interpretation

- 1,471 members have a run without a recorded set.
- 357 members have a win without a recorded run.
- 3,467 records have at least one negative event duration.

These do not create duplicate keys, but they mean the observed funnel is not strictly monotonic. The dashboard should preserve actual stage counts rather than forcing a cosmetically perfect funnel. Upstream stewardship should distinguish legitimate backfills from event-date or stage-capture defects.

The expected-yield source contains 318,505 reliable candidate rows across 306,403 join keys. Of 9,552 tied minimum-priority keys, 9,550 have identical values; two ties contain materially different benchmark values. The curated view now applies a deterministic secondary ordering, but the durable fix belongs in the benchmark object itself.

## Recommended BigQuery enhancements

### Priority 1 — durable controls

1. **Create immutable daily parity snapshots.** Store the official event-date metrics and cohort metrics by `snapshot_date`, campaign rollup, campaign, geography, and period. This is the only reliable way to reproduce a previously published workbook after Salesforce records change.
2. **Promote test-record rules into governed data.** Replace the embedded regex with a small rule table containing rule ID, field scope, expression, effective dates, owner, and active flag. Persist exclusions with the matched rule and review disposition.
3. **Fix benchmark uniqueness at its source.** Materialize exactly one benchmark row per campaign × jurisdiction × ZIP × grain × period. Add a deterministic candidate ID and a uniqueness assertion; separately quarantine the two conflicting ties.
4. **Schedule runtime-table refreshes with assertions.** Refresh runtime tables only after row-count, unique-key, fanout, freshness, and reconciliation checks pass. Retain the previous successful table if a check fails.

### Priority 2 — data-quality and geography

5. **Create a conformed operating-geography dimension.** Manage state aliases, operating-region membership, effective dates, county, AHJ, market, and exception status in one dimension instead of CASE expressions.
6. **Add an unresolved-geography work queue.** Publish record identifiers, campaign, ZIP/address evidence, spend, age, and recommended resolution path for the 452 unresolved leads.
7. **Add event-sequence quality flags.** Expose `run_without_set`, `win_without_run`, and negative-duration flags with source timestamps so operations can separate valid historical backfills from defects.
8. **Add outside-footprint disposition fields.** Classify activity as approved expansion, customer move/address mismatch, vendor leakage, routing error, or unknown. Delaware should be reviewed as an operating-policy question rather than removed.

### Priority 3 — product and modeling

9. **Version spend completeness.** Track expected spend source, received-through date, completeness SLA, and missing reason by campaign-period so the dashboard can distinguish late, missing, modeled, and true-zero spend.
10. **Add cohort maturity snapshots.** Preserve expected-yield and attainment as known on each snapshot date, preventing later benchmark changes from rewriting historical decisions.
11. **Publish metric contracts.** Add descriptions and tests for lead, set, run, win, revenue, effective spend, and workbook-parity definitions in BigQuery metadata.
12. **Create scenario-ready response curves.** Estimate diminishing returns by campaign and geography only where sample size and spend completeness support it; otherwise constrain scenarios to transparent linear assumptions.

## Reusable audit queries

The supporting read-only SQL is checked into `work/`:

- `audit_marketing_lineage.sql`
- `audit_marketing_anomalies.sql`
- `audit_marketing_jobs.sql`
- `audit_marketing_validation.sql`
- `audit_member_definitions.sql`

These queries should be run after upstream schema changes and before material runtime refreshes.
