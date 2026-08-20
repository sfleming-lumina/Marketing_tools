# Funnel Comparison Timeframe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the global "Benchmark" dropdown to "Comparison timeframe" and make it drive the mature-cohort reference window used by Funnel Health's "Mature benchmark" comparator, dropping the hardcoded 12-month fallback and the always-on 3-month cap whenever the user picks a specific timeframe.

**Architecture:** All changes live in the single-file dashboard `outputs/marketing_decision_tool.html` (inline `<script>`, vanilla JS, no build step). Three independent fixes: (1) a markup/copy rename of `#benchmarkFilter`, (2) a one-line fallback-condition fix in `loadData()`, (3) a new `capReference` parameter on `funnelHealthModel()` wired from its one call site in `renderFunnel()`. A fourth task adds one sentence to existing guide copy. Each is independently testable and independently committable.

**Tech Stack:** Vanilla JS (ES2020+), no framework, no bundler. Tests run against a Node-based fake-DOM harness at `work/verify_marketing_tool.js` (uses `vm.runInThisContext` to execute the dashboard's inline script plus a mocked `global.fetch`). There is no `package.json`; run the harness directly.

## Global Constraints

- No new API endpoints or query params — reuse the existing `benchmarkQueryString()` / `maturityQueryString()` fetches exactly as they are today.
- `#funnelComparator` ("Compare with": mature/campaign/rollup/region) is unchanged — do not touch its markup, options, or query-string builders.
- The Funnel view's `vs ${...} reliable benchmark` metric copy (~line 1371) is NOT renamed — "benchmark" there names a statistical concept, distinct from the dropdown.
- Non-mature comparator modes (campaign/rollup/region) never had the 3-month cap and must stay uncapped — only the `mature` mode's cap logic changes.
- `funnelHealthModel()`'s new 4th parameter must default to `true` so every existing call site that doesn't pass it (including three calls already in `work/verify_marketing_tool.js`) keeps today's capped behavior unchanged.
- Run tests with: `node work/verify_marketing_tool.js` from the `Marketing_tools` repo root. Expect final stdout line `Marketing Intelligence workspace verified OK.` on success; the harness `assert()` helper prints an error and calls `process.exit(1)` on failure (no exception is thrown).
- Commit only the specific files you touch (`outputs/marketing_decision_tool.html`, `work/verify_marketing_tool.js`) — never `git add -A`.

---

### Task 1: Rename the dropdown to "Comparison timeframe"

**Files:**
- Modify: `outputs/marketing_decision_tool.html` (~line 291, the `#benchmarkPeriodFilter`/`#benchmarkFilter` markup)
- Modify: `outputs/marketing_decision_tool.html` (~line 670, `filterSummaryLabel()`)
- Modify: `outputs/marketing_decision_tool.html` (~line 2196, the `window.MarketingOS` test-exposure object)
- Test: `work/verify_marketing_tool.js` (~line 164, ~line 174)

**Interfaces:**
- Produces: `filterSummaryLabel()` becomes callable as `app.filterSummaryLabel()` from the test harness (it is a pure function of `state`, already defined at ~line 669 — this task only adds it to the exposed `window.MarketingOS` object, no logic changes).

- [ ] **Step 1: Write the failing tests**

In `work/verify_marketing_tool.js`, replace the existing label assertion (~line 164):

```js
  assert(dashboardHtml.includes('data-label="Cohort window"') && dashboardHtml.includes('data-label="Benchmark"') && dashboardHtml.includes('id="benchmarkFilter"'), "Discrete filter labels or benchmark-window control are missing.");
```

with:

```js
  assert(dashboardHtml.includes('data-label="Cohort window"') && dashboardHtml.includes('data-label="Comparison timeframe"') && dashboardHtml.includes('id="benchmarkFilter"'), "Discrete filter labels or comparison-timeframe control are missing.");
```

Then, immediately after the existing benchmark-window independence check (~line 174):

```js
  app.state.benchmarkWindow="3";assert(app.benchmarkQueryString().includes("months=3") && !app.benchmarkQueryString().includes("window=30d"), "Benchmark window did not remain independent from the active slice.");app.state.benchmarkWindow="match";
```

add a new line directly below it:

```js
  app.state.benchmarkWindow="24";assert(app.filterSummaryLabel().includes("Comparison: 24 months") && !app.filterSummaryLabel().includes("Benchmark:"), "The renamed comparison-timeframe control did not update the filter summary label.");app.state.benchmarkWindow="match";
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node work/verify_marketing_tool.js`
Expected: FAIL — either the `data-label="Comparison timeframe"` assertion fails (markup not yet renamed) or `app.filterSummaryLabel is not a function` (not yet exposed), whichever the harness reaches first.

- [ ] **Step 3: Rename the dropdown markup**

In `outputs/marketing_decision_tool.html`, find (~line 291):

```html
<div class="select-wrap" data-label="Benchmark" id="benchmarkPeriodFilter"><select id="benchmarkFilter" aria-label="Benchmark time period">
```

Replace with:

```html
<div class="select-wrap" data-label="Comparison timeframe" id="benchmarkPeriodFilter"><select id="benchmarkFilter" aria-label="Comparison timeframe">
```

(Options inside the `<select>` are unchanged — only the two label attributes on this line change.)

- [ ] **Step 4: Update `filterSummaryLabel()`'s text**

Find (~line 670):

```js
    const labels=[state.window==="30d"?"Last 30 days":`${state.months} months`,state.campaign||"All campaigns",state.rollup&&`Rollup: ${state.rollup}`,state.decisionMarketLabel?`Market: ${state.decisionMarketLabel}`:state.ahj&&`County: ${state.ahj}`,state.region||"All geographies",state.benchmarkWindow!=="match"&&`Benchmark: ${state.benchmarkWindow} months`];
```

Replace with:

```js
    const labels=[state.window==="30d"?"Last 30 days":`${state.months} months`,state.campaign||"All campaigns",state.rollup&&`Rollup: ${state.rollup}`,state.decisionMarketLabel?`Market: ${state.decisionMarketLabel}`:state.ahj&&`County: ${state.ahj}`,state.region||"All geographies",state.benchmarkWindow!=="match"&&`Comparison: ${state.benchmarkWindow} months`];
```

- [ ] **Step 5: Expose `filterSummaryLabel` for testing**

In `outputs/marketing_decision_tool.html` (~line 2196), find this fragment inside the `window.MarketingOS={...}` assignment:

```js
coverageInfo,funnelHtml,funnelHealthModel,loadFunnelComparator
```

Replace with:

```js
coverageInfo,funnelHtml,funnelHealthModel,filterSummaryLabel,loadFunnelComparator
```

(This is a small, unique anchor inside the single long `window.MarketingOS={...}` line — do not retype the whole line.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `node work/verify_marketing_tool.js`
Expected: PASS through at least this point (later tasks add more assertions further down the file; the full run will still fail until Tasks 2–4 land — that's expected).

- [ ] **Step 7: Commit**

```bash
git add outputs/marketing_decision_tool.html work/verify_marketing_tool.js
git commit -m "Rename Benchmark dropdown to Comparison timeframe"
```

---

### Task 2: Fix the mature-reference fallback to respect a chosen comparison timeframe

**Files:**
- Modify: `outputs/marketing_decision_tool.html` (~line 783, inside `loadData()`)
- Test: `work/verify_marketing_tool.js` (inside the nested `resetFilters().then()` callback, ~line 365)

**Interfaces:**
- Consumes: `state.benchmarkWindow` (string, e.g. `"match"`, `"3"`, `"6"`, ...), `state.months` (number), `state.window` (string, `""` or `"30d"`), `separateBenchmark` (local `const`, already computed one line above as `state.benchmarkWindow!=="match"`).
- No new exports — this is a pure control-flow fix inside an existing function.

- [ ] **Step 1: Write the failing test**

In `work/verify_marketing_tool.js`, find the innermost `resetFilters().then()` callback (it currently ends with a single `console.log` call):

```js
        app.resetFilters().then(() => {
          assert(app.state.months === 7 && app.state.region === "Operating footprint" && !app.state.campaign && !app.state.rollup && !app.state.ahj, "Reset did not restore the default filter state.");
          assert(getElement("monthsFilter").value === "7" && getElement("stateFilter").value === "Operating footprint", "Reset did not restore visible filter controls.");
          assert(global.requestedUrls.some(url=>url.includes("marketing-funnel")&&url.includes("months=7")&&url.includes("region=Operating+footprint")), "Reset did not reload the default portfolio.");
          console.log("Marketing Intelligence workspace verified OK.");
        });
```

Replace the closing `console.log(...)` line with a new nested async check (keep everything above it unchanged):

```js
          global.requestedUrls = [];
          app.state.benchmarkWindow = "6";
          app.loadData({force:true}).then(() => {
            assert(!global.requestedUrls.some(url=>url.includes("marketing-funnel")&&url.includes("months=12")), "A short comparison timeframe still triggered the hardcoded 12-month maturity fallback.");
            assert(global.requestedUrls.some(url=>url.includes("marketing-funnel")&&url.includes("months=6")), "A 6-month comparison timeframe did not fetch its own window.");
            global.requestedUrls = [];
            app.state.benchmarkWindow = "match";
            app.loadData({force:true}).then(() => {
              assert(global.requestedUrls.some(url=>url.includes("marketing-funnel")&&url.includes("months=12")), "Match slice with a short active cohort window lost its 12-month maturity fallback.");
              console.log("Marketing Intelligence workspace verified OK.");
            });
          });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node work/verify_marketing_tool.js`
Expected: FAIL on `"A short comparison timeframe still triggered the hardcoded 12-month maturity fallback."` — with today's code, `state.months` defaults to 7 (< 12) after reset, and the buggy `needsMaturityReference` formula ignores `separateBenchmark` in that branch, so it still fires the hardcoded `months=12` fetch even though `benchmarkWindow` is `"6"`.

- [ ] **Step 3: Fix the fallback condition**

In `outputs/marketing_decision_tool.html` (~line 783), find:

```js
      const needsMaturityReference=Boolean(state.window)||Number(separateBenchmark?state.benchmarkWindow:state.months)<12;
```

Replace with:

```js
      const needsMaturityReference=separateBenchmark?false:(Boolean(state.window)||Number(state.months)<12);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node work/verify_marketing_tool.js`
Expected: PASS through this point (full-file pass depends on Task 3 and Task 4 also being done, since assertions run in file order).

- [ ] **Step 5: Commit**

```bash
git add outputs/marketing_decision_tool.html work/verify_marketing_tool.js
git commit -m "Stop overriding a chosen comparison timeframe with the hardcoded 12-month maturity fallback"
```

---

### Task 3: Drop the last-3-month cap when a specific timeframe is chosen

**Files:**
- Modify: `outputs/marketing_decision_tool.html` (~line 599, `funnelHealthModel()` signature)
- Modify: `outputs/marketing_decision_tool.html` (~line 611, cap logic)
- Modify: `outputs/marketing_decision_tool.html` (~line 1377, `renderFunnel()` call site)
- Test: `work/verify_marketing_tool.js` (new assertions after the existing funnel-health tests, ~line 216)

**Interfaces:**
- Produces: `funnelHealthModel(rows, referenceRows, comparatorMode="mature", capReference=true)` — new 4th parameter, defaults to `true`. Existing 2-arg and 3-arg call sites (including the three already in `work/verify_marketing_tool.js`) are unaffected by the default.
- Consumes (at the `renderFunnel()` call site): `state.benchmarkWindow` (string) — passes `state.benchmarkWindow==="match"` as `capReference`.

- [ ] **Step 1: Write the failing test**

In `work/verify_marketing_tool.js`, immediately after the existing `sameSliceComparison` assertions (~line 216, right before the aged-fallout assertion `assert(dashboardHtml.includes("Aged unresolved (still open)")...)`), insert:

```js
  const cappedMatureHealth = app.funnelHealthModel([
    {month:"2026-08-01",cohortAgeDays:9,leads:50,sets:0,runs:0,wins:0}
  ],[
    {month:"2026-01-01",cohortAgeDays:200,leads:20,sets:10,runs:6,wins:2},
    {month:"2026-02-01",cohortAgeDays:200,leads:20,sets:10,runs:6,wins:2},
    {month:"2026-03-01",cohortAgeDays:200,leads:20,sets:10,runs:6,wins:2},
    {month:"2026-04-01",cohortAgeDays:200,leads:20,sets:10,runs:6,wins:2},
    {month:"2026-05-01",cohortAgeDays:200,leads:20,sets:10,runs:6,wins:2}
  ],"mature",true);
  assert(cappedMatureHealth.find(item=>item.key==="leadToWin").referenceLabel.includes("Mar 2026–May 2026") && !cappedMatureHealth.find(item=>item.key==="leadToWin").referenceLabel.includes("Jan 2026"), "Match-slice comparison did not keep the last-3-month mature reference cap.");
  const uncappedMatureHealth = app.funnelHealthModel([
    {month:"2026-08-01",cohortAgeDays:9,leads:50,sets:0,runs:0,wins:0}
  ],[
    {month:"2026-01-01",cohortAgeDays:200,leads:20,sets:10,runs:6,wins:2},
    {month:"2026-02-01",cohortAgeDays:200,leads:20,sets:10,runs:6,wins:2},
    {month:"2026-03-01",cohortAgeDays:200,leads:20,sets:10,runs:6,wins:2},
    {month:"2026-04-01",cohortAgeDays:200,leads:20,sets:10,runs:6,wins:2},
    {month:"2026-05-01",cohortAgeDays:200,leads:20,sets:10,runs:6,wins:2}
  ],"mature",false);
  assert(uncappedMatureHealth.find(item=>item.key==="leadToWin").referenceLabel.includes("Jan 2026–May 2026"), "A chosen comparison timeframe did not use every eligible mature reference month.");
  const defaultMatureHealth = app.funnelHealthModel([
    {month:"2026-08-01",cohortAgeDays:9,leads:50,sets:0,runs:0,wins:0}
  ],[
    {month:"2026-01-01",cohortAgeDays:200,leads:20,sets:10,runs:6,wins:2},
    {month:"2026-02-01",cohortAgeDays:200,leads:20,sets:10,runs:6,wins:2},
    {month:"2026-03-01",cohortAgeDays:200,leads:20,sets:10,runs:6,wins:2},
    {month:"2026-04-01",cohortAgeDays:200,leads:20,sets:10,runs:6,wins:2},
    {month:"2026-05-01",cohortAgeDays:200,leads:20,sets:10,runs:6,wins:2}
  ],"mature");
  assert(defaultMatureHealth.find(item=>item.key==="leadToWin").referenceLabel.includes("Mar 2026–May 2026"), "Omitting capReference did not default to the capped mature reference set.");
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node work/verify_marketing_tool.js`
Expected: FAIL on `"A chosen comparison timeframe did not use every eligible mature reference month."` — today's code caps to the last 3 months unconditionally whenever `comparatorMode==="mature"`, ignoring the (currently nonexistent) 4th argument, so `uncappedMatureHealth`'s reference label is still `"Mar 2026–May 2026"` instead of the full `"Jan 2026–May 2026"` range.

- [ ] **Step 3: Add the `capReference` parameter and gate the cap on it**

In `outputs/marketing_decision_tool.html` (~line 599), find:

```js
  function funnelHealthModel(rows,referenceRows=state.maturityFunnelRows,comparatorMode="mature"){
```

Replace with:

```js
  function funnelHealthModel(rows,referenceRows=state.maturityFunnelRows,comparatorMode="mature",capReference=true){
```

Then (~line 611), find:

```js
      const baselineGroups=comparatorMode==="mature"?matchingReferences.slice(-3):matchingReferences;
```

Replace with:

```js
      const baselineGroups=(comparatorMode==="mature"&&capReference)?matchingReferences.slice(-3):matchingReferences;
```

- [ ] **Step 4: Wire the call site to the dropdown**

In `outputs/marketing_decision_tool.html` (~line 1377), find:

```js
    const health=funnelHealthModel(rows,comparatorRows,state.funnelComparator);
```

Replace with:

```js
    const health=funnelHealthModel(rows,comparatorRows,state.funnelComparator,state.benchmarkWindow==="match");
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `node work/verify_marketing_tool.js`
Expected: PASS through this point.

- [ ] **Step 6: Commit**

```bash
git add outputs/marketing_decision_tool.html work/verify_marketing_tool.js
git commit -m "Use every eligible mature reference month when a specific comparison timeframe is chosen"
```

---

### Task 4: Guide copy tie-in

**Files:**
- Modify: `outputs/marketing_decision_tool.html` (~line 460, "Targets and benchmark periods" guide section)
- Test: `work/verify_marketing_tool.js` (new assertion near the other guide-content checks, e.g. next to the existing `dashboardHtml.includes(...)` checks around line 190)

**Interfaces:** None — static HTML copy change only, no JS behavior.

- [ ] **Step 1: Write the failing test**

In `work/verify_marketing_tool.js`, add this assertion anywhere after `dashboardHtml` is defined (e.g. directly below the line-164 label assertion touched in Task 1):

```js
  assert(dashboardHtml.includes("uses every eligible mature cohort-month in that window rather than only the most recent three"), "The comparison-timeframe guide copy does not explain its effect on the Funnel Health mature-benchmark reference window.");
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node work/verify_marketing_tool.js`
Expected: FAIL — the sentence does not exist yet in the guide markup.

- [ ] **Step 3: Add the sentence**

In `outputs/marketing_decision_tool.html` (~line 460), find:

```html
    <div class="guide-section"><h3>Targets and benchmark periods</h3><p>The benchmark selector changes the reference window without changing the active cohort slice. Lead-to-win targets use lead-weighted, upstream reliable campaign × jurisdiction benchmarks from that reference window. Stage targets use the selected portfolio’s observed stage rate during the reference window when no governed upstream stage benchmark exists. Potential wins hold current volume constant and close only the identified rate gap; they are decision anchors, not forecasts. Sample size, maturity, benchmark coverage, and spend quality determine confidence. The 24- and 36-month choices are historical cohort lenses for conversion durability and maturity—not default allocation windows. Older spend, CAC, campaign taxonomy, and vendor economics may not be comparable, so coverage cautions remain authoritative.</p></div>
```

Replace with (only the added sentence, inserted before the closing `</p></div>`):

```html
    <div class="guide-section"><h3>Targets and benchmark periods</h3><p>The benchmark selector changes the reference window without changing the active cohort slice. Lead-to-win targets use lead-weighted, upstream reliable campaign × jurisdiction benchmarks from that reference window. Stage targets use the selected portfolio’s observed stage rate during the reference window when no governed upstream stage benchmark exists. Potential wins hold current volume constant and close only the identified rate gap; they are decision anchors, not forecasts. Sample size, maturity, benchmark coverage, and spend quality determine confidence. The 24- and 36-month choices are historical cohort lenses for conversion durability and maturity—not default allocation windows. Older spend, CAC, campaign taxonomy, and vendor economics may not be comparable, so coverage cautions remain authoritative. The same dropdown also sets the mature-cohort reference window for the Funnel Health “Mature benchmark” comparison on Analysis; choosing a specific timeframe instead of Match slice uses every eligible mature cohort-month in that window rather than only the most recent three.</p></div>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node work/verify_marketing_tool.js`
Expected: PASS — full file should now print `Marketing Intelligence workspace verified OK.` with no failed assertions, assuming Tasks 1–3 are already committed.

- [ ] **Step 5: Commit**

```bash
git add outputs/marketing_decision_tool.html work/verify_marketing_tool.js
git commit -m "Document the comparison-timeframe dropdown's effect on the mature-benchmark reference window"
```

---

## Manual Verification (after all tasks)

- Open the dashboard against the local server. Confirm the dropdown now reads "Comparison timeframe" and the filter-summary chip reads "Comparison: N months" (not "Benchmark:") when set to a non-"Match slice" value.
- On Analysis, set Comparison timeframe to 24 months, set Compare with to "Mature benchmark," and confirm the Lead → win health row's reference tooltip/label spans more than 3 months.
- Set Comparison timeframe back to "Match slice" and confirm the reference label reverts to at most 3 months.
