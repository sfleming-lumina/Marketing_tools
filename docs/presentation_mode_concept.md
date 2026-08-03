# Marketing Decision Tool — Presentation Mode Concept

## Product idea

Add a focused, 16:9 presentation surface that turns the current governed dashboard slice into a short decision story. It should be useful in a live meeting without becoming a separate reporting system.

The presenter chooses a scope, a story, and whether the numbers are live or frozen:

- **Scope:** operating footprint, MD Ops, PA Ops, or an individual physical state.
- **Story:** portfolio review, regional review, campaign decision, or tracked-decision follow-up.
- **Data mode:** live as of the latest loaded cohort, or a frozen meeting snapshot with a visible timestamp.

## Geographic contract

Physical state and operating region must be separate controls because they answer different questions.

- **MD Ops:** Maryland operational region, including MD/DC/VA activity assigned to MD Ops.
- **PA Ops:** Pennsylvania operational region, including PA/DE activity assigned to PA Ops.
- **Physical state:** the resolved state on the geography row, regardless of operational assignment.

Every presentation page should display both dimensions when relevant—for example, `Virginia · MD Ops`—so an audience never mistakes an operating rollup for a state boundary.

## Recommended five-page story

1. **Executive headline** — selected scope, period, as-of timestamp, leads, wins, spend, CAC, revenue/spend, benchmark delta, and one sentence on the decision implication.
2. **Funnel and momentum** — current funnel, conversion movement, cohort maturity, and spend-coverage caveat.
3. **Where performance differs** — state or operating-region comparison, leading counties/markets, and the largest recover/scale opportunities.
4. **Decisions** — active tracked decisions, observed progress, evidence, owner, review date, and archived items excluded by default.
5. **Recommendation / scenario** — current baseline versus proposed budget and CPL, expected wins/revenue, assumptions, caveats, and the explicit ask.

## Interaction model

- Add a **Present** action beside the existing global controls.
- Open a distraction-free presentation view that inherits the exact current filters and active decision.
- Provide Previous/Next, page picker, full-screen, speaker notes, live/frozen toggle, and `Copy presentation link`.
- Allow presenters to hide a page but keep the default story opinionated and short.
- Make every page responsive enough to work on a conference-room display and printable to PDF.

## State and region comparison page

Use a small-multiple or ranked-card layout rather than a dense map for the first release. Each card should show:

- physical state and assigned Ops region;
- leads, wins, lead-to-win, spend, CPL, CAC, and revenue/spend;
- benchmark delta and sample/spend-coverage confidence;
- leading campaign and highest-priority decision;
- a clear Scale, Recover, Protect, Test, or Investigate label.

At the Ops-region level, aggregate Maryland/DC/Virginia into MD Ops and Pennsylvania/Delaware into PA Ops using the governed `operatingRegion` field. At the state level, group the same geography results by resolved `state`. Do not derive the Ops rollup from state in the browser.

## Architecture fit

Phase 1 can be a read-only client view built from the same loaded funnel, geography, scenario, and decision state already used by the dashboard and assistant. This keeps every number cohort-consistent and avoids a new reporting pipeline.

For reliable meeting links and historical decks, Phase 2 should persist a presentation definition in `marketing_tool_ops`:

- presentation id, title, creator, created/updated timestamps;
- filter and geographic scope;
- included page ids and order;
- selected decision ids;
- live or frozen mode;
- frozen metric/context JSON and data as-of timestamp.

The presentation URL remains behind IAP. A frozen snapshot should never overwrite the live dashboard or the decision ledger.

## Data work needed

- Use geography API rows for physical-state and Ops-region comparisons; they already carry state and normalized operating-region dimensions.
- Add an explicit state selector for presentation scope rather than overloading the current operating-region control.
- Confirm state-level aggregation does not duplicate leads across geography rows before release.
- Consider adding `physical_state` to future decision records so state-scoped decision pages do not have to infer state from an AHJ label.
- Keep archived decisions available only through an explicit presentation option.

## Suggested delivery sequence

1. Build the five-page read-only presenter using current live state and browser print-to-PDF.
2. Add physical-state versus Ops-region scope selection and comparison cards.
3. Add frozen snapshots and IAP-protected share links.
4. Add lightweight story editing, speaker notes, and saved presentation definitions.
