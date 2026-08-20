# Funnel Comparison Timeframe — Design

**Date:** 2026-08-20
**Status:** Approved
**Author:** Sean Fleming (with Claude)

## Problem

The Funnel Health comparison ("Focus scan" on the Analysis view) lets a user pick *what* to compare the current cohort slice against via **Compare with** (`#funnelComparator`: Mature benchmark / Campaign total / Campaign rollup / Operating region). But when "Mature benchmark" is selected, the reference window it draws from is not user-controlled:

- If the active cohort slice is already 12+ months and the global **Benchmark** dropdown is left at "Match slice," the mature reference is just the current slice's own history — fine.
- If the slice is shorter than 12 months (or is the rolling "Last 30 days" window), the tool silently falls back to a hardcoded 12-month lookback (`maturityQueryString()`), ignoring whatever the user picked in the **Benchmark** dropdown.
- The global **Benchmark** dropdown already exists and already drives a *different* reference set (`state.benchmarkFunnelRows`, used for the top-line "vs Nm reliable benchmark" metric and the geography benchmarks) — but today it has no effect on the Funnel Health "Mature benchmark" comparator specifically.

There's no way today to say "compare my mature funnel health rates against the last 24 months of mature cohorts" — the window is fixed at 12 months regardless of intent.

## Goal

Make the reference window for Funnel Health's "Mature benchmark" comparator follow the same dropdown that already controls the other benchmark reference set, and rename that dropdown so its purpose reads clearly for both uses.

## Non-goals

- No change to the **Compare with** dropdown (`#funnelComparator`) itself — its four modes (mature/campaign/rollup/region) stay as-is. (Decided: reuse/rename the global dropdown rather than touch this one.)
- No change to how Campaign total / Campaign rollup / Operating region comparator modes select their reference cohorts — they already use every matching cohort-month with no cap, which is unaffected by this work.
- No new API endpoints or query params — the existing `benchmarkQueryString()`/`maturityQueryString()` fetches already carry everything needed.

## Design

### 1. Rename the dropdown

`#benchmarkFilter` (`select-wrap` label "Benchmark", `aria-label="Benchmark time period"`, options Match slice/3/6/7/12/24/36 months) becomes:
- `data-label="Comparison timeframe"`
- `aria-label="Comparison timeframe"`
- Options unchanged.

Update the two places that render its label as text:
- `filterSummaryLabel()` (~line 670): `Benchmark: ${state.benchmarkWindow} months` → `Comparison: ${state.benchmarkWindow} months`.
- Funnel view metric copy (~line 1371): `vs ${...} reliable benchmark` label wording stays — "benchmark" there refers to the statistical concept (a reliable campaign × jurisdiction rate), not the dropdown, so it's untouched.

The general "benchmark" terminology used elsewhere (`opportunityBenchmarks()`, geo `conversionDeltaVsBenchmark`, "Mature benchmark" option text on `#funnelComparator`, the guide's "reliable benchmark" language) is a distinct concept from the dropdown's timeframe control and is not renamed.

### 2. Wire the dropdown into the mature-cohort reference window

Today, `state.maturityFunnelRows` (the data behind the "Mature benchmark" comparator) is populated by this fallback chain in `loadData()`:

```
needsMaturityReference = Boolean(state.window) || Number(separateBenchmark ? state.benchmarkWindow : state.months) < 12
state.maturityFunnelRows = (maturityFunnel || state.benchmarkFunnelRows || state.funnelRows)
```

The bug: when the comparison timeframe is set to anything other than "Match slice" (`separateBenchmark` true) and that value is under 12 months, `needsMaturityReference` is true, so the tool fetches a *hardcoded* 12-month `maturityQueryString()` result and uses that — overriding the exact timeframe the user just picked with a fixed fallback.

Fix: only fall back to the hardcoded 12-month fetch when there's no separate comparison-timeframe fetch already covering the need — i.e., only in "Match slice" mode with a short active cohort window:

```
needsMaturityReference = separateBenchmark ? false : (Boolean(state.window) || Number(state.months) < 12)
```

With this change, the existing fallback chain does the right thing in every case without further edits:
- **Comparison timeframe = a specific N months:** `separateBenchmark` is true, `benchmarkFunnelRows` is already fetched via `benchmarkQueryString()` using exactly N months (plus active campaign/rollup/ahj/decisionMarket/region filters). `maturityFunnel` is `null`, so `maturityFunnelRows` falls back to `benchmarkFunnelRows` — the user's chosen window.
- **Comparison timeframe = Match slice, active cohort window ≥ 12 months:** `separateBenchmark` is false, `needsMaturityReference` is false, `maturityFunnelRows` falls back to `benchmarkFunnelRows` (which equals `funnelRows` when not separate) — the active slice supplies its own mature history, unchanged from today.
- **Comparison timeframe = Match slice, active cohort window < 12 months (or rolling 30-day window):** `needsMaturityReference` is true, hardcoded 12-month fetch fires exactly as it does today — this fallback is preserved deliberately so a short/rolling slice always has enough history to judge maturity against.

### 3. Drop the "last 3 mature months" cap when a specific timeframe is chosen (Option B)

`funnelHealthModel()` currently caps the mature reference pool to the last 3 eligible mature months, always, when `comparatorMode==="mature"`:

```
const baselineGroups = comparatorMode==="mature" ? matchingReferences.slice(-3) : matchingReferences;
```

New behavior: the cap applies only when the comparison timeframe is "Match slice" (the pre-existing default behavior, preserved). When the user has explicitly picked a timeframe, use **every** eligible mature cohort-month within that window — more months in view means the user asked for a wider reference, not a truncated one.

`funnelHealthModel(rows, referenceRows, comparatorMode, capReference)` gains a fourth parameter. Call site (`renderFunnel()`) passes `state.benchmarkWindow==="match"`:

```
const health = funnelHealthModel(rows, comparatorRows, state.funnelComparator, state.benchmarkWindow === "match");
...
const baselineGroups = (comparatorMode==="mature" && capReference) ? matchingReferences.slice(-3) : matchingReferences;
```

Non-mature comparator modes (campaign/rollup/region) are unaffected — they never had the cap.

### 4. Guide copy tie-in

The existing "Targets and benchmark periods" guide section already explains the dropdown's effect on lead-to-win targets and stage benchmarks; add one sentence noting it now also sets the mature-cohort reference window for the Funnel Health "Mature benchmark" comparison, and that picking a specific timeframe (rather than Match slice) uses every eligible mature month in that window instead of just the most recent three. This is the only guide edit in scope for this spec — the broader guide reorganization is tracked separately.

## Testing

- Unit-style check via the existing `work/verify_marketing_tool.js` harness (or a new fixture in it): confirm `funnelHealthModel()` returns the full eligible reference set (not capped to 3) when `capReference=false`, and the capped set when `capReference=true` or omitted.
- Manual verification in the running dashboard: set Comparison timeframe to 24 months, confirm the Mature benchmark row's reference label (`referenceLabel`) reflects more than 3 months of cohorts; set it back to Match slice and confirm the cap returns.
- Confirm `filterSummaryText` and the dropdown's visible label read "Comparison timeframe" / "Comparison: Nm months" throughout.
