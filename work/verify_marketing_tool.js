const vm = require("vm");
const fs = require("fs");
const { installFakeDom, loadDashboardScript } = require("./dom_fake");
const dashboardHtml = fs.readFileSync("outputs/marketing_decision_tool.html", "utf8");

const { getElement } = installFakeDom();
const funnelRows = [
  {
    month:"2026-06-01", campaign:"Efficient Search", campaignRollup:"3rd Party Vendors LSR",
    campaignSubrollup:"Paid Search", leads:100, sets:50, runs:40, wins:20, revenue:900000,
    effectiveSpend:40000, recordedSpend:40000, activePipeline:20, activePipelineRevenue:600000,
    expectedRemainingWins:5, expectedRemainingRevenue:200000, benchmarkLeadToWinRate:.15,
    spendCompleteLeadShare:1, spendCoverageStatus:"Complete", openNoSet30Plus:8,
    setNoRun30Plus:5, runNoWin60Plus:4, loadedAt:"2026-07-28T12:00:00Z"
  },
  {
    month:"2026-07-01", campaign:"Co-op Maryland", campaignRollup:"Co-op",
    campaignSubrollup:"Co-op", leads:50, sets:25, runs:20, wins:8, revenue:340000,
    effectiveSpend:0, recordedSpend:0, activePipeline:12, activePipelineRevenue:300000,
    expectedRemainingWins:3, expectedRemainingRevenue:125000, benchmarkLeadToWinRate:.14,
    spendCompleteLeadShare:0, spendCoverageStatus:"Known incomplete", openNoSet30Plus:3,
    setNoRun30Plus:2, runNoWin60Plus:1, loadedAt:"2026-07-28T12:00:00Z"
  }
];
const apiFunnelRows = [...funnelRows, {
  month:"2026-07-01", campaign:"Jonathan Bissell Test", campaignRollup:"Jonathan Bissell",
  campaignSubrollup:"Test", leads:999, sets:999, runs:999, wins:999, revenue:999,
  effectiveSpend:1, recordedSpend:1, spendCompleteLeadShare:1, spendCoverageStatus:"Complete"
}];
const geoRows = [{
  ahj:"Fairfax County", geography:"Fairfax County", geographyType:"County", county:"Fairfax", state:"VA",
  campaign:"Efficient Search", campaignRollup:"3rd Party Vendors LSR", leads:55, sets:25,
  runs:20, wins:10, revenue:450000, effectiveSpend:20000, activePipeline:9,
  expectedRemainingWins:2, benchmarkLeadToWinRate:.14, leadToWinRate:10/55,
  conversionDeltaVsBenchmark:10/55-.14, costPerWin:2000, opportunityScore:76.2,
  benchmarkCoverage:1,spendCompleteLeadShare:1,sampleSizeBucket:"Sufficient Sample"
}];
const reconciliation = {
  workbook:"Marketing Report 2026_Official.xlsx", period:"2026-01-01 through 2026-07-31",
  definitions:{funnelMetrics:"Lakehouse outcomes follow a fixed lead cohort; workbook outcomes use event dates."},
  comparisons:[{
    campaignRollup:"3rd Party Vendors LSR", officialReport:{leads:8759,spend:937555},
    lakehouseCohort:{leads:9374,spend:1094032}, leadParityStatus:"Review",
    spendParityStatus:"Review", spendCompleteLeadShare:1
  }]
};

global.fetch = (url, options = {}) => {
  const path = String(url);
  global.requestedUrls = global.requestedUrls || [];
  global.requestedUrls.push(path);
  if (path.includes("marketing-projection")) {
    return Promise.resolve({
      ok:false,
      status:403,
      json:()=>Promise.resolve({detail:"Projection source is not available to the runtime service account."})
    });
  }
  if (path.includes("marketing-decisions") && options.method === "POST") {
    const request = JSON.parse(options.body);
    return Promise.resolve({ok:true,json:()=>Promise.resolve({
      decision_id:"decision-1",created_at:"2026-07-29T12:00:00Z",created_by_name:"Test User",
      question:request.question,action:request.action,status:"Monitoring",campaign:request.filters.campaign,
      ahj:request.filters.ahj,operating_region:request.filters.operatingRegion,review_after:"2026-08-28"
    })});
  }
  if (path.includes("marketing-decision-progress")) {
    return Promise.resolve({ok:true,json:()=>Promise.resolve({decisionId:"decision-1",status:"Maturing",implementationSignal:"Outcome monitoring",progressToTarget:null})});
  }
  let payload = [];
  if (path.includes("marketing-funnel")) payload = apiFunnelRows;
  else if (path.includes("marketing-geo")) payload = geoRows;
  else if (path.includes("marketing-filter-options")) payload = {campaigns:["Co-op Maryland","Efficient Search","Jonathan Bissell Test"],rollups:["Co-op","3rd Party Vendors LSR","Jonathan Bissell"],ahjs:["Fairfax County"]};
  else if (path.includes("marketing-reconciliation")) payload = reconciliation;
  else if (path.includes("freshness")) payload = {objects_found:4,objects_checked:4};
  else if (path.includes("marketing-decisions")) payload = [];
  return Promise.resolve({ok:true,json:()=>Promise.resolve(payload)});
};

vm.runInThisContext(loadDashboardScript(), {filename:"marketing_decision_tool.html"});

setImmediate(() => {
  const app = window.MarketingOS;
  const aggregate = app.aggregate(funnelRows);
  const incomplete = app.coverageInfo(app.aggregate([funnelRows[1]]));
  const output = [
    getElement("commandMetrics").innerHTML,
    getElement("mainFunnel").innerHTML,
    getElement("campaignTable").innerHTML,
    getElement("funnelHealth").innerHTML,
    getElement("funnelFocus").innerHTML,
    getElement("geoTable").innerHTML,
    getElement("qualityRows").innerHTML,
    getElement("scenarioCompare").innerHTML,
  ].join("\n");

  function assert(condition, message) {
    if (!condition) {
      console.error(message);
      process.exit(1);
    }
  }
  assert(aggregate.leads === 150 && aggregate.wins === 28, "Cohort totals were not aggregated.");
  assert(incomplete.leadFirst && incomplete.label === "Known incomplete", "Incomplete spend did not force lead-first semantics.");
  assert(getElement("mainFunnel").innerHTML.startsWith('<div class="stage"><small>Leads'), "Auto lens should omit spend when the selected portfolio is incomplete.");
  assert(output.includes("Efficient Search") && output.includes("Co-op Maryland"), "Campaign rows did not render.");
  assert(!output.includes("Jonathan Bissell") && !getElement("rollupFilter").innerHTML.includes("Jonathan Bissell"), "Excluded Jonathan Bissell data leaked into the dashboard.");
  assert(getElement("campaignTable").innerHTML.includes('data-label="Sets"') && getElement("campaignTable").innerHTML.includes('data-label="Runs"'), "Campaign stage volumes did not render.");
  assert(getElement("campaignTable").innerHTML.includes("no set") && getElement("campaignTable").innerHTML.includes("no run") && getElement("campaignTable").innerHTML.includes("no win"), "Campaign fallout detail did not render.");
  assert(!dashboardHtml.includes("Sales capacity guardrail") && !dashboardHtml.includes('id="capacitySummary"') && !dashboardHtml.includes('id="insideCapacity"'), "Sales capacity guardrail remains in the marketing workspace.");
  assert(getElement("campaignFilter").innerHTML.includes("Efficient Search") && getElement("campaignFilter").innerHTML.includes("All active campaigns") && !getElement("campaignFilter").innerHTML.includes("Jonathan Bissell"), "Active-campaign options were not restored correctly.");
  assert(output.includes("Fairfax County") && output.includes("76.2"), "Geo opportunity ranking did not render.");
  assert(getElement("qualityMetrics").innerHTML.includes("Marketing Report 2026_Official.xlsx"), "Workbook reconciliation did not render.");
  assert(output.includes("Current baseline") && output.includes("Scenario"), "Scenario comparison did not render.");
  assert(!/NaN|undefined|null/.test(output), "Invalid numeric token found in rendered output.");
  assert(dashboardHtml.includes('id="guideDrawer"') && dashboardHtml.includes("How to use this workspace"), "Usage guide overlay is missing.");
  assert(dashboardHtml.includes('<option value="Maryland">Maryland</option>') && !dashboardHtml.includes('<option value="DMV">'), "Operating-region options do not follow the MD/PA operational contract.");
  assert(dashboardHtml.includes('yLabel:"Leads"') && dashboardHtml.includes('rightYLabel:"Residential wins"') && dashboardHtml.includes('yLabel:"Conversion rate"'), "Chart axis labels are missing.");
  assert(dashboardHtml.includes("chart-tooltip") && dashboardHtml.includes('addEventListener("mousemove"'), "Chart hover details are missing.");
  assert(dashboardHtml.includes('id="ahjFilter"') && dashboardHtml.includes('id="cacTrend"'), "AHJ filtering or CAC visualization is missing.");
  assert(dashboardHtml.includes('<script src="/assets/echarts.min.js"></script>') && dashboardHtml.includes("renderEchartTrend"), "The local ECharts runtime or trend renderer is missing.");
  assert(dashboardHtml.includes('id="opportunityQuadrant"') && dashboardHtml.includes('id="funnelWaterfall"') && dashboardHtml.includes('id="campaignMultiples"'), "Decision quadrant, funnel waterfall, or campaign small multiples are missing.");
  assert(dashboardHtml.includes('id="resetFiltersButton"') && dashboardHtml.includes("refresh-spin") && dashboardHtml.includes('id="refreshStatus"'), "Reset control or animated refresh feedback is missing.");
  assert(dashboardHtml.includes('id="waterfallAction"') && dashboardHtml.includes("Improve speed-to-lead") && dashboardHtml.includes("Protect appointments"), "Actionable funnel-gap guidance is missing.");
  assert(dashboardHtml.includes(".decision-canvas-grid>.chart-card.compact .chart-host{height:100%;min-height:360px"), "The CAC/conversion scatter plot does not fill its decision-canvas column.");
  assert(dashboardHtml.includes("new ResizeObserver(()=>chart.resize())") && dashboardHtml.includes("renderCampaignMultiples(rows);renderOpportunityQuadrant(rows)"), "The scatter plot does not respond after campaign panels expand its container.");
  assert(dashboardHtml.includes("markLine") && dashboardHtml.includes("markArea") && dashboardHtml.includes("markPoint") && dashboardHtml.includes("aria:{enabled:true"), "Chart benchmarks, focus bands, annotations, or accessibility configuration are missing.");
  assert(dashboardHtml.includes("Number.isFinite(benchmarks.costPerWin)") && dashboardHtml.includes("Number.isFinite(firstValues[index-1])"), "Chart annotations do not guard missing CAC or trend coordinates.");
  assert(dashboardHtml.includes("selectedOpportunityKey") && dashboardHtml.includes("hoverOpportunityKey") && dashboardHtml.includes("setOpportunityHover"), "Cross-highlighting state is missing.");
  assert(dashboardHtml.includes("chart-fallback") && dashboardHtml.includes("paintTrend"), "Graceful canvas chart fallback is missing.");
  assert(dashboardHtml.includes('<option value="30d">Last 30 days</option>') && dashboardHtml.includes('L → S') && dashboardHtml.includes('S → R') && dashboardHtml.includes('R → W'), "30-day or stage-conversion controls are missing.");
  assert(getElement("funnelHealth").innerHTML.includes("Lead → set") && getElement("funnelFocus").innerHTML.includes("focus-callout"), "Purpose-colored funnel health did not render.");
  const opportunities = app.opportunityRows();
  assert(opportunities.length === 1 && opportunities[0].campaign === "Efficient Search" && opportunities[0].ahj === "Fairfax County", "Campaign/AHJ opportunity rows were not created.");
  assert(opportunities[0].decisionType === "Scale" && opportunities[0].confidence === "High" && opportunities[0].estimatedWinImpact > 0, "Opportunity decision type, confidence, or impact is incorrect.");
  assert(getElement("insightList").innerHTML.includes("Efficient Search") && getElement("insightList").innerHTML.includes("Fairfax County"), "Multi-campaign/AHJ opportunity queue did not render.");
  assert(getElement("opportunityMatrix").innerHTML.includes("matrix-cell") && getElement("opportunityMatrix").innerHTML.includes("Fairfax County"), "Clickable Campaign/AHJ matrix did not render.");
  assert(dashboardHtml.includes('id="matrixMetric"') && dashboardHtml.includes('id="improvementTarget"'), "Metric switching or improvement-target modeling is missing.");
  const sparseWaterfall = app.funnelWaterfallModel({leads:3,sets:0,runs:0,wins:0,benchmark:null});
  assert(sparseWaterfall.steps.length === 6 && sparseWaterfall.steps.every(Number.isFinite), "Sparse funnel drill-down did not preserve every finite waterfall stage.");
  assert(sparseWaterfall.actionTone === "neutral" && sparseWaterfall.actionCopy.includes("sample maturity"), "Sparse funnel drill-down did not explain insufficient benchmark evidence.");
  const zeroStageWaterfall = app.funnelWaterfallModel({leads:20,sets:0,runs:0,wins:0,benchmark:.1});
  assert(zeroStageWaterfall.steps[0] > 0 && zeroStageWaterfall.steps.every(Number.isFinite) && zeroStageWaterfall.actionTone === "warn", "Zero-stage drill-down collapsed despite having a usable benchmark.");
  const benchmarkWaterfall = app.funnelWaterfallModel(aggregate);
  assert(benchmarkWaterfall.steps.length === 6 && benchmarkWaterfall.labels.includes("Lead volume"), "Benchmark waterfall does not render the fixed decomposition sequence.");
  const decisions = app.decisionInsights();
  assert(decisions.length === 3 && decisions.every(item => item.question && item.view && item.evidence.length), "Command-center insights are not actionable decision objects.");
  assert(getElement("insightList").innerHTML.includes("Investigate") && dashboardHtml.includes("Discover → Investigate → Test → Implement"), "Guided decision workflow is not visible.");
  app.beginInvestigation("funnel-signal");
  assert(app.state.workflowStage === "investigate" && app.state.activeDecision.id === "funnel-signal", "Insight did not become an active investigation.");
  assert(getElement("decisionWorkspace").classList.contains("show") && !getElement("funnelEvidence").hidden, "Active decision context did not persist into investigation.");
  const originalEvidenceCount = app.state.activeDecision.evidence.length;
  app.addDecisionEvidence("funnel");
  assert(app.state.activeDecision.evidence.length === originalEvidenceCount + 1, "Investigation evidence was not carried forward.");
  app.startScenario();
  assert(app.state.workflowStage === "test" && app.state.view === "scenario", "Investigation did not hand off to Scenario studio.");
  assert(getElement("scenarioOutputTitle").textContent.includes(app.state.activeDecision.question), "Scenario did not retain the active decision question.");
  app.openDecisionBrief();
  assert(app.state.workflowStage === "implement" && getElement("decisionBriefBody").innerHTML.includes("Expected impact"), "Scenario did not produce an implementation brief.");
  assert(app.decisionBriefText().includes("LUMINA MARKETING DECISION BRIEF") && app.decisionBriefText().includes("Evidence:"), "Copyable decision output is incomplete.");
  const trackingPayload = app.decisionTrackingPayload();
  assert(trackingPayload.baseline.wins === 28 && trackingPayload.expected.wins > trackingPayload.baseline.wins, "Automatic tracking did not freeze baseline and expected outcomes.");
  assert(trackingPayload.filters.operatingRegion === "Operating footprint" && trackingPayload.horizonDays >= 30, "Automatic tracking did not retain scope and review horizon.");
  assert(dashboardHtml.includes('id="decisionsDrawer"') && dashboardHtml.includes("No uploads or status entry required"), "Automatic decision tracker surface is missing.");
  assert(global.requestedUrls.filter(url=>url.includes("marketing-funnel")||url.includes("marketing-geo")).every(url=>url.includes("region=Operating+footprint")), "Default operating-footprint filter was not sent to both data endpoints.");
  assert(global.requestedUrls.some(url=>url.includes("marketing-filter-options")&&url.includes("region=Operating+footprint")), "Complete filter catalog was not requested.");
  assert(!global.requestedUrls.some(url=>url.includes("marketing-capacity")), "Removed capacity inventory is still requested by the marketing workspace.");
  const funnelRequestsBeforeRefresh = global.requestedUrls.filter(url=>url.includes("marketing-funnel")).length;
  const refreshPromise = app.refreshData();
  assert(getElement("refreshButton").classList.contains("is-loading") && getElement("refreshButton").disabled, "Refresh control did not enter its animated loading state.");
  refreshPromise.then(() => {
    assert(global.requestedUrls.filter(url=>url.includes("marketing-funnel")).length > funnelRequestsBeforeRefresh, "Refresh did not issue a fresh funnel request.");
    assert(global.requestedUrls.filter(url=>url.includes("marketing-reconciliation")).length >= 2, "Forced refresh reused cached reconciliation data.");
    assert(!getElement("refreshButton").classList.contains("is-loading") && !getElement("refreshButton").disabled, "Refresh control did not leave its loading state.");
    getElement("stateFilter").value = "Maryland";
    getElement("stateFilter").dispatchEvent({type:"change",target:getElement("stateFilter")});
    setImmediate(() => {
    assert(global.requestedUrls.some(url=>url.includes("marketing-funnel")&&url.includes("region=Maryland")), "Changing operating region did not reload funnel data.");
    assert(global.requestedUrls.some(url=>url.includes("marketing-geo")&&url.includes("region=Maryland")), "Changing operating region did not reload geography data.");
    assert(getElement("campaignTable").innerHTML.includes("Efficient Search"), "Expanded campaign portfolio did not render.");
    getElement("ahjFilter").value = "Fairfax County";
    getElement("ahjFilter").dispatchEvent({type:"change",target:getElement("ahjFilter")});
    setImmediate(() => {
      assert(global.requestedUrls.some(url=>url.includes("marketing-funnel")&&url.includes("ahj=Fairfax+County")), "Changing AHJ did not re-query funnel data.");
      assert(global.requestedUrls.some(url=>url.includes("marketing-geo")&&url.includes("ahj=Fairfax+County")), "Changing AHJ did not re-query geography data.");
      const selectedOpportunity = app.opportunityRows()[0];
      app.beginOpportunity(selectedOpportunity.key);
      assert(app.state.activeDecision.improvementTarget.metricKey === "leadToWinRate", "Selected opportunity did not carry its improvement target.");
      assert(getElement("improvementTarget").classList.contains("show") && getElement("improvementTarget").innerHTML.includes("Potential wins"), "Improvement target did not render in Funnel lab.");
      assert(app.decisionTrackingPayload().primaryMetric === "leadToWin", "Improvement target did not carry into automatic tracking.");
      setImmediate(() => {
        app.state.campaign = "EnergySage"; app.state.rollup = "Co-op"; app.state.ahj = "Fairfax County"; app.state.region = "Maryland"; app.state.months = 3;
        app.resetFilters().then(() => {
          assert(app.state.months === 7 && app.state.region === "Operating footprint" && !app.state.campaign && !app.state.rollup && !app.state.ahj, "Reset did not restore the default filter state.");
          assert(getElement("monthsFilter").value === "7" && getElement("stateFilter").value === "Operating footprint", "Reset did not restore visible filter controls.");
          assert(global.requestedUrls.some(url=>url.includes("marketing-funnel")&&url.includes("months=7")&&url.includes("region=Operating+footprint")), "Reset did not reload the default portfolio.");
          console.log("Marketing Intelligence workspace verified OK.");
        });
      });
    });
  });
  });
});
