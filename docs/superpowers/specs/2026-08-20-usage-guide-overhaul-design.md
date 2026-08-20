# In-App Usage Guide Overhaul — Design

**Date:** 2026-08-20
**Status:** Approved
**Author:** Sean Fleming (with Claude)

## Problem

`#guideDrawer` ("How to use this workspace") holds 12 `.guide-section` blocks, but:

- Only 6 have anchor `id`s and a `.guide-toc` entry (Workflow, Filters, Cohorts, Findings, Analysis, Markets). "Tile and chart feedback," "Decision tracker," "Targets and benchmark periods," "Decision monitoring," "Seasonality and unavailable dimensions," and "Plan a scenario" have no way to jump to them from the TOC.
- Related content is scattered: the three decision-lifecycle tools (Plan a scenario, Decision tracker, Decision monitoring) sit in different, non-adjacent parts of the document, disconnected from each other and from the "Track automatically" bullet in Workflow that introduces the same lifecycle.
- The AI assistant (`#assistantDrawer`, "Ask about this view") has no documentation anywhere in the guide.
- Some paragraphs are dense without an example (notably the decision-market/adaptive-hierarchy paragraph in Findings).
- Section titles are inconsistently named relative to what they cover (e.g., "Targets and benchmark periods" doesn't mention the dropdown driving it; "Seasonality and unavailable dimensions" undersells that it's a general "what this tool doesn't do" section).

This is scoped separately from the funnel comparison-timeframe work ([[2026-08-20-funnel-comparison-timeframe-design]]) — that spec makes one small copy addition to the timeframe section; this spec is the full structural pass the user asked for after seeing that addition.

## Goal

Reorganize the guide into a logical, fully-navigable structure that groups related tools together, documents the previously-undocumented assistant, and tightens the densest existing paragraph — without changing any actual product behavior.

## Non-goals

- No visual/CSS redesign of the drawer itself (layout, styling, TOC chip appearance all stay as-is).
- No new guide content management system — this stays a static block of markup in `outputs/marketing_decision_tool.html`, matching every other drawer in the app.
- No change to the assistant's actual behavior — the new section documents what exists today. When the "Ask AI" enhancement (item #6 of the broader feature set) ships, that work will update this section again as part of its own spec.

## Sequencing

This spec's section 4 text incorporates the one-sentence addition specified in [[2026-08-20-funnel-comparison-timeframe-design]]. Implement that spec first (or in the same pass) so section 4 describes shipped behavior rather than a pending change. If this guide overhaul lands first for any reason, section 4 should temporarily keep its current "Targets and benchmark periods" text unchanged until the timeframe spec ships, rather than describing behavior that doesn't exist yet.

## Design

### Final structure (11 sections, replacing the current 12)

`.guide-toc` gets one entry per section, all 11 anchored:

| # | Anchor id | Title | Source |
|---|---|---|---|
| 1 | `guide-workflow` | Discover → Investigate → Test → Implement | unchanged (existing Workflow section) |
| 2 | `guide-filters` | Filters and operating regions | unchanged |
| 3 | `guide-cohorts` | Cohort methodology: current state vs decision evidence | unchanged |
| 4 | `guide-timeframes` | Comparison timeframe and benchmarks | renamed from "Targets and benchmark periods"; text updated per the funnel-timeframe spec's guide tie-in |
| 5 | `guide-findings` | Findings and adaptive decision grain | unchanged content + one added example (see below) |
| 6 | `guide-analysis` | Analysis: funnel health, fallout, and acquisition cost | unchanged content, title tightened to name what's actually in the section |
| 7 | `guide-markets` | Markets | unchanged |
| 8 | `guide-assistant` | Ask the assistant | **new** |
| 9 | `guide-decisions` | Decision tools: plan, track, and monitor | merged from "Plan a scenario," "Decision tracker," and "Decision monitoring" |
| 10 | `guide-feedback` | Tile and chart feedback | unchanged content, now anchored |
| 11 | `guide-limits` | Known data limits | renamed from "Seasonality and unavailable dimensions" |

Sections 1–3 keep their current position (getting-started material stays first). 4–7 keep their relative order (they're the analytical core: timeframe/benchmarks → findings → analysis → markets). 8–9 are new placements: the assistant sits right after the analytical sections since it answers questions about them, and the three decision-lifecycle tools move together into one section immediately after, since "ask a question about this evidence" naturally precedes "now act on it." 10–11 close out the guide as reference/meta material, as they do today.

### Section 4 — Comparison timeframe and benchmarks (renamed)

Content unchanged from "Targets and benchmark periods" except the addition already specified in the funnel-timeframe spec: one sentence noting the same dropdown now sets the mature-cohort reference window for the Funnel Health "Mature benchmark" comparison, and that a specific timeframe (vs. "Match slice") uses every eligible mature month rather than just the most recent three.

### Section 5 — Findings: added example

Append one concrete example to the existing decision-market/adaptive-hierarchy paragraph, after "...evidence is not duplicated.":

> *For example: if a single county doesn't have enough leads and wins to qualify on its own, but pooling it with the other counties in its decision market reaches the 50-lead/5-win/two-county threshold, the queue surfaces the pooled recommendation for that market instead of staying silent — while still listing any county that later qualifies on its own, individually.*

No other wording in this section changes.

### Section 6 — Analysis: title only

Rename from "Analysis" to "Analysis: funnel health, fallout, and acquisition cost" so the TOC chip and heading describe the section's actual contents (currently the TOC just says "Analysis," which doesn't distinguish it from Findings or Markets at a glance). Body content unchanged.

### Section 8 — Ask the assistant (new)

```html
<div class="guide-section" id="guide-assistant"><h3>Ask the assistant</h3><p>Open <strong>Ask about this view</strong> to get a written answer grounded in the exact slice on screen — active period, campaign, rollup, county / market, region, active decision, and scenario. Ask about trends, what's driving a metric, or what to do next; the assistant reasons only over the same filtered cohort data you're already looking at, so its answer changes when your filters do. If the loaded slice is incomplete, the server rehydrates it from the governed data API before answering. Use it to get a second read on a Finding before testing a decision — it's a sounding board grounded in your current evidence, not a replacement for the evidence panel or the maturity/sample/coverage labels.</p></div>
```

This describes current behavior only (no forward-looking claims about trend-awareness or richer prompting — that's tracked separately as a future enhancement).

### Section 9 — Decision tools: plan, track, and monitor (merged)

Combines the three existing sections in lifecycle order, each keeping its existing text verbatim, joined under one heading and one anchor:

```html
<div class="guide-section" id="guide-decisions">
  <h3>Decision tools: plan, track, and monitor</h3>
  <p><strong>Plan a scenario</strong> — Adjust budget, cost per lead, and conversion assumptions to explore directional outcomes. Scenarios are planning aids, not forecasts; the baseline always comes from the selected live cohort.</p>
  <p><strong>Track a decision</strong> — From Findings, Analysis, or Markets, choose <strong>Track automatically</strong> once you've tested a decision. The tool captures the authenticated owner, decision, scope, baseline, assumptions, evidence, expected impact, and review window without forms or uploads.</p>
  <p><strong>Decision tracker</strong> — Open <strong>Decisions</strong> from the sidebar to see every tracked choice. Current lakehouse cohorts are compared with each frozen baseline automatically. Campaign, rollup, county, governed decision market, operating region, and cohort window are frozen with the decision so pooled recommendations continue monitoring the same scope. Spend changes are labeled as observed implementation signals; conversion improvements remain outcome signals unless an external execution system confirms the action.</p>
  <p><strong>Decision monitoring</strong> — Open <strong>Decision monitoring</strong> from Reporting Views, launch it from the active decision banner, or choose <strong>View weekly performance</strong> on a tracked decision. The decision-date marker separates the pre-decision baseline from post-decision activity. Weekly event trends are useful for pacing and execution; matured fixed cohorts determine the final result.</p>
</div>
```

The Workflow section (1) keeps its own brief "Implement: choose Track automatically..." bullet as-is (it's the right level of detail for a first-read workflow overview) and is not edited to cross-reference this new merged section — the TOC makes section 9 discoverable on its own.

### Section 10 — Tile and chart feedback

Unchanged text, gets `id="guide-feedback"` and a TOC entry (currently missing both).

### Section 11 — Known data limits (renamed)

Unchanged text from "Seasonality and unavailable dimensions," renamed heading and `id="guide-limits"` (was un-anchored) so it reads as the general "what this tool intentionally doesn't do" section it actually is (seasonality, Sales Region, Lead Sales Type).

### `.guide-toc` markup

```html
<nav class="guide-toc" aria-label="Guide contents">
  <a href="#guide-workflow">Workflow</a>
  <a href="#guide-filters">Filters</a>
  <a href="#guide-cohorts">Cohorts</a>
  <a href="#guide-timeframes">Timeframes</a>
  <a href="#guide-findings">Findings</a>
  <a href="#guide-analysis">Analysis</a>
  <a href="#guide-markets">Markets</a>
  <a href="#guide-assistant">Assistant</a>
  <a href="#guide-decisions">Decision tools</a>
  <a href="#guide-feedback">Feedback</a>
  <a href="#guide-limits">Data limits</a>
</nav>
```

## Testing

- Manual: open the guide drawer, click every TOC chip, confirm it scrolls to the matching section and that all 11 sections are present and none are orphaned (no section without a TOC entry, no TOC entry without a section).
- Manual: read the merged Decision tools section top-to-bottom and confirm no duplicated sentences and no dangling references to a section that no longer exists at its old heading text (search the file for any other guide cross-references, e.g. in `#assistantDrawer` or tooltip text, that name a section by its old title).
- Diff review: confirm no wording changed anywhere except the two additions (timeframe sentence, Findings example) and the four title renames — this is a reorganization, not a rewrite.
