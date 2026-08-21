const vm = require("vm");
const fs = require("fs");
const { installFakeDom, loadDashboardScript } = require("./dom_fake");
const dashboardHtml = fs.readFileSync("outputs/marketing_decision_tool.html", "utf8");

const { getElement } = installFakeDom();
const funnelRows = [
  {
    month:"2026-06-01", cohortAgeDays:70, cohortMaturityBucket:"Maturing: 60-89 days", campaign:"Efficient Search", campaignRollup:"3rd Party Vendors LSR",
    campaignSubrollup:"Paid Search", leads:100, sets:50, runs:40, wins:20, revenue:900000,
    effectiveSpend:40000, recordedSpend:40000, activePipeline:20, activePipelineRevenue:600000,
    expectedRemainingWins:5, expectedRemainingRevenue:200000, benchmarkLeadToWinRate:.15,
    spendCompleteLeadShare:1, spendCoverageStatus:"Complete", openNoSet30Plus:8,
    setNoRun30Plus:5, runNoWin60Plus:4, loadedAt:"2026-07-28T12:00:00Z"
  },
  {
    month:"2026-07-01", cohortAgeDays:40, cohortMaturityBucket:"Maturing: 30-59 days", campaign:"Co-op Maryland", campaignRollup:"Co-op",
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
const trendPayload = {
  period:"30d",label:"Last 30 days",currentLabel:"Jul 8, 2026–Aug 6, 2026",comparisonLabel:"Jun 8, 2026–Jul 7, 2026",
  current:[{date:"2026-08-05",leads:12,sets:5,runs:3,wins:1,winValue:40000,spend:1200}],
  comparison:[{date:"2026-07-07",leads:10,sets:4,runs:2,wins:1,winValue:38000,spend:1000}],
  summary:{leads:12,sets:5,runs:3,wins:1,winValue:40000,spend:1200,setsPerLead:5/12,runsPerSet:3/5,winsPerRun:1/3,costPerLead:100,costPerWin:1200},
  comparisonSummary:{leads:10,sets:4,runs:2,wins:1,winValue:38000,spend:1000,setsPerLead:.4,runsPerSet:.5,winsPerRun:.5,costPerLead:100,costPerWin:1000},
  loadedAt:"2026-08-06T12:00:00Z",definitions:{lead:"Campaign Member activity dated by Lead.Updated_Campaign_Member__c.",set:"Opportunity dated by CreatedDate.",run:"Completed SV dated by SV Start Date-Time.",win:"Qualifying stage dated by Close Date.",comparison:"Event-period activity is not fixed-cohort conversion."}
};
const journeyPayload = {
  totalRows:20630,invalidSequenceRows:69,completedWins:1325,journeyCoverage:.937,
  cohortStart:"2026-01-01",cohortEnd:"2026-07-01",
  stages:[
    {key:"leadToSet",label:"Lead to set",count:9200,medianDays:1,p75Days:8},
    {key:"setToRun",label:"Set to run",count:4100,medianDays:4,p75Days:14},
    {key:"runToWin",label:"Run to win",count:1241,medianDays:27,p75Days:92}
  ],
  leadToWin:{count:1241,medianDays:50,p75Days:186}
};

global.fetch = (url, options = {}) => {
  const path = String(url);
  global.requestedUrls = global.requestedUrls || [];
  global.requestedUrls.push(path);
  if (path.includes("/api/notes") && options.method === "POST") {
    global.lastNoteRequest = JSON.parse(options.body);
    return Promise.resolve({ok:true,json:()=>Promise.resolve({note_id:"note-1",...global.lastNoteRequest})});
  }
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
  else if (path.includes("marketing-journey")) payload = journeyPayload;
  else if (path.includes("marketing-trends")) payload = trendPayload;
  else if (path.includes("marketing-capacity")) payload = {governedOpen:420,activeCampaignOpen:310,nurturingOpen:84};
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
  assert(dashboardHtml.includes('role="dialog" aria-modal="true"') && dashboardHtml.includes('aria-hidden="true" tabindex="-1"') && dashboardHtml.includes('event.key==="Escape"'), "Drawers are missing dialog semantics or keyboard dismissal.");
  assert(dashboardHtml.includes('id="filterSummaryToggle"') && dashboardHtml.includes('id="filterSummaryText"') && dashboardHtml.includes('id="globalFilters"'), "Responsive current-slice filter disclosure is missing.");
  assert(dashboardHtml.includes('id="errorDetails"') && dashboardHtml.includes('classList.toggle("data-unavailable"') && dashboardHtml.includes("No business values are shown"), "Fatal data errors can still be confused with valid zero performance.");
  assert(dashboardHtml.includes('id="opportunityQuadrantData"') && dashboardHtml.includes("keyboard-accessible table follows the chart"), "Decision chart data parity is missing.");
  assert(dashboardHtml.includes('class="guide-toc"') && dashboardHtml.includes('href="#guide-cohorts"'), "The long usage guide is missing task-based navigation.");
  assert(dashboardHtml.includes("Cohort methodology: current state vs decision evidence") && dashboardHtml.includes("Current-state reporting") && dashboardHtml.includes("Cohort reporting"), "Current-state versus cohort methodology guidance is missing.");
  assert(dashboardHtml.includes('data-feedback-trigger') && dashboardHtml.includes("feedbackIconSvg") && dashboardHtml.includes('id="feedbackType"'), "Per-tile pen/notebook feedback controls are missing.");
  app.setFeedbackTarget({view:"command",elementKey:"command-gross-revenue",elementLabel:"Gross revenue",targetType:"tile"});
  getElement("feedbackType").value="data";getElement("noteText").value="Please validate this tile.";app.saveNote();
  assert(global.lastNoteRequest.element_key==="command-gross-revenue" && global.lastNoteRequest.target_type==="tile" && global.lastNoteRequest.feedback_type==="data", "Tile feedback did not preserve its BigQuery note target contract.");
  app.setFeedbackTarget(null);
  assert(dashboardHtml.includes('<option value="Maryland">Maryland</option>') && !dashboardHtml.includes('<option value="DMV">'), "Operating-region options do not follow the MD/PA operational contract.");
  assert(dashboardHtml.includes('yLabel:"Leads"') && dashboardHtml.includes('rightYLabel:"Residential wins"') && dashboardHtml.includes('yLabel:"Conversion rate"'), "Chart axis labels are missing.");
  assert(dashboardHtml.includes("chart-tooltip") && dashboardHtml.includes('addEventListener("mousemove"'), "Chart hover details are missing.");
  assert(dashboardHtml.includes('id="ahjFilter"') && dashboardHtml.includes('id="cacTrend"'), "AHJ filtering or CAC visualization is missing.");
  assert(dashboardHtml.includes('<script src="assets/echarts.min.js"></script>') && dashboardHtml.includes("renderEchartTrend"), "The local ECharts runtime or trend renderer is missing.");
  assert(dashboardHtml.includes('id="opportunityQuadrant"') && dashboardHtml.includes('id="funnelWaterfall"') && dashboardHtml.includes('id="campaignMultiples"'), "Decision quadrant, funnel waterfall, or campaign small multiples are missing.");
  assert(dashboardHtml.includes('id="resetFiltersButton"') && dashboardHtml.includes("refresh-spin") && dashboardHtml.includes('id="refreshStatus"'), "Reset control or animated refresh feedback is missing.");
  assert(dashboardHtml.includes('data-view="workbook"') && dashboardHtml.includes('id="workbookRefresh"') && dashboardHtml.includes('/api/official-workbook'), "Official workbook navigation, refresh control, or API wiring is missing.");
  assert(dashboardHtml.includes('data-view="trends"') && dashboardHtml.includes('id="trendPeriodFilter"') && dashboardHtml.includes('/api/marketing-trends'), "Independent calendar-trends navigation, period control, or API wiring is missing.");
  assert(dashboardHtml.includes('data-view="monitoring"') && dashboardHtml.includes('/api/marketing-decision-trends') && dashboardHtml.includes('id="monitorDecisionFilter"') && dashboardHtml.includes('markLine:decisionWeekLabel'), "Decision-anchored weekly monitoring is missing.");
  assert(dashboardHtml.includes('id="detailDrawer"') && dashboardHtml.includes('/api/marketing-detail') && dashboardHtml.includes('governed aggregate rows'), "Governed contributing-row access is missing.");
  assert(dashboardHtml.includes('data-label="Cohort window"') && dashboardHtml.includes('data-label="Comparison timeframe"') && dashboardHtml.includes('id="benchmarkFilter"'), "Discrete filter labels or comparison-timeframe control are missing.");
  assert(dashboardHtml.includes('id="matrixCampaignLimit"') && dashboardHtml.includes('id="matrixGeographyLimit"') && dashboardHtml.includes('max-height:560px'), "Configurable, frame-scrolling opportunity matrix is missing.");
  assert(dashboardHtml.includes('<strong>Observed</strong>') && dashboardHtml.includes('<strong>Why it matters</strong>') && dashboardHtml.includes('<strong>Do next</strong>'), "Findings do not translate observations into actions.");
  assert(dashboardHtml.includes('<div class="nav-label">Reporting views</div>') && dashboardHtml.includes('aria-label="Decision workspace"') && dashboardHtml.includes('aria-label="Reporting views"'), "Calendar trends and Official workbook are not grouped separately from the decision workspace.");
  assert(dashboardHtml.includes("Findings") && dashboardHtml.includes("Analysis") && dashboardHtml.includes("BigQuery-sourced event trends") && dashboardHtml.includes('id="sidebarToggle"'), "Direct-use navigation labels, BigQuery provenance, or the sidebar collapse control are missing.");
  assert(dashboardHtml.includes('globalThis.location?.protocol === "file:"') && dashboardHtml.includes("renderLocalFileNotice") && dashboardHtml.includes("http://localhost:8080/marketing_decision_tool.html"), "Local-file mode must avoid unsupported API fetches and direct users to the local server.");
  assert(dashboardHtml.includes('<script src="assets/echarts.min.js"></script>'), "The chart library path must work in both file and server modes.");
  app.setSidebarCollapsed(true,false);
  assert(getElement("appShell").classList.contains("sidebar-collapsed") && dashboardHtml.includes('aria-expanded="true"'), "Desktop sidebar did not collapse accessibly.");
  app.setSidebarCollapsed(false,false);
  app.state.benchmarkWindow="3";assert(app.benchmarkQueryString().includes("months=3") && !app.benchmarkQueryString().includes("window=30d"), "Benchmark window did not remain independent from the active slice.");app.state.benchmarkWindow="match";
  app.state.benchmarkWindow="24";assert(app.filterSummaryLabel().includes("Comparison: 24 months") && !app.filterSummaryLabel().includes("Benchmark:"), "The renamed comparison-timeframe control did not update the filter summary label.");app.state.benchmarkWindow="match";
  assert(dashboardHtml.includes('view==="trends"||view==="monitoring"||view==="workbook"') && dashboardHtml.includes('$("benchmarkPeriodFilter").hidden=reportingOnly'), "Reporting views must not show cohort or benchmark-window controls.");
  app.state.trends.data=trendPayload;app.renderMarketingTrends();
  assert(getElement("trendMetrics").innerHTML.includes("Leads") && getElement("trendMetrics").innerHTML.includes("12"), "Calendar activity metrics did not render.");
  assert(getElement("trendBoundary").textContent.includes("not fixed-cohort"), "Calendar activity did not preserve its non-cohort boundary.");
  app.state.workbook.data={months:["Jan","Feb"],summary:[{category:"Internal Marketing",state:"All",metric:"Net Revenue",months:[100,250]}],detail:[],forecast:[],refreshedAt:"2026-08-03T12:00:00Z",source:{title:"Marketing Report 2026_Official"}};
  app.state.workbook.through="Feb";
  assert(app.workbookSum("Net Revenue")===350, "Official workbook through-month aggregation is incorrect.");
  app.state.workbook.data=null;
  assert(dashboardHtml.includes('id="waterfallAction"') && dashboardHtml.includes("Improve speed-to-lead") && dashboardHtml.includes("Protect appointments"), "Actionable funnel-gap guidance is missing.");
  assert(dashboardHtml.includes(".decision-canvas-grid>.chart-card.compact .chart-host{height:100%;min-height:360px"), "The CAC/conversion scatter plot does not fill its decision-canvas column.");
  assert(dashboardHtml.includes("new ResizeObserver(()=>chart.resize())") && dashboardHtml.includes("renderCampaignMultiples(rows);renderOpportunityQuadrant(rows)"), "The scatter plot does not respond after campaign panels expand its container.");
  assert(dashboardHtml.includes("markLine") && dashboardHtml.includes("markArea") && dashboardHtml.includes("markPoint") && dashboardHtml.includes("aria:{enabled:true"), "Chart benchmarks, focus bands, annotations, or accessibility configuration are missing.");
  assert(dashboardHtml.includes("Number.isFinite(benchmarks.costPerWin)") && dashboardHtml.includes("Number.isFinite(firstValues[index-1])"), "Chart annotations do not guard missing CAC or trend coordinates.");
  assert(dashboardHtml.includes("selectedOpportunityKey") && dashboardHtml.includes("hoverOpportunityKey") && dashboardHtml.includes("setOpportunityHover"), "Cross-highlighting state is missing.");
  assert(dashboardHtml.includes("chart-fallback") && dashboardHtml.includes("paintTrend"), "Graceful canvas chart fallback is missing.");
  assert(dashboardHtml.includes('<option value="30d">Last 30 days</option>') && dashboardHtml.includes('L → S') && dashboardHtml.includes('S → R') && dashboardHtml.includes('R → W'), "30-day or stage-conversion controls are missing.");
  assert(getElement("funnelHealth").innerHTML.includes("Lead → set") && getElement("funnelFocus").innerHTML.includes("focus-callout"), "Purpose-colored funnel health did not render.");
  app.state.journey.data=journeyPayload;app.renderJourney();
  assert(getElement("journeyTimeline").innerHTML.includes("50 days lead to win") && getElement("journeyTimeline").innerHTML.includes("93.7% win-date coverage"), "Buyer journey timing or coverage did not render.");
  app.state.journey.percentile="p75Days";app.renderJourney();
  assert(getElement("journeyTimeline").innerHTML.includes("186 days lead to win"), "Buyer journey percentile control did not change the rendered timing.");
  const yieldHtml=app.expectedYieldMetric({...aggregate,benchmarkCoverage:.8});
  assert(yieldHtml.includes("Expected total wins") && yieldHtml.includes("not the current pipeline count") && yieldHtml.includes("80.0%"), "Expected-yield meaning or benchmark coverage is not disclosed.");
  assert(dashboardHtml.includes("selected slice as a bar") && dashboardHtml.includes("chosen comparison as a marker"), "Funnel bullet-comparison guidance is missing.");
  assert(dashboardHtml.includes('data-notes-panel="feedback"') && dashboardHtml.includes('id="feedbackQueuePanel"'), "Feedback queue is not reachable from Notes.");
  const maturityHealth = app.funnelHealthModel([
    {month:"2026-02-01",cohortAgeDays:190,leads:40,sets:20,runs:10,wins:2},
    {month:"2026-05-01",cohortAgeDays:101,leads:40,sets:20,runs:10,wins:2},
    {month:"2026-08-01",cohortAgeDays:9,leads:50,sets:0,runs:0,wins:0}
  ]);
  assert(Math.abs(maturityHealth.find(item=>item.key==="leadToWin").current-(4/130))<1e-9, "Funnel health did not keep the full selected slice in the observed bar.");
  assert(maturityHealth.find(item=>item.key==="leadToWin").periodLabel.includes("Feb 2026–Aug 2026") && maturityHealth.find(item=>item.key==="leadToWin").periodLabel.includes("under 90 days"), "Funnel health did not disclose the selected period and its win-stage maturity gate.");
  const sameSliceComparison=app.funnelHealthModel([
    {month:"2026-07-01",cohortAgeDays:47,leads:20,sets:8,runs:4,wins:1},
    {month:"2026-08-01",cohortAgeDays:16,leads:20,sets:6,runs:2,wins:0}
  ],[
    {month:"2026-06-01",cohortAgeDays:77,leads:100,sets:35,runs:20,wins:4},
    {month:"2026-07-01",cohortAgeDays:47,leads:100,sets:30,runs:16,wins:3},
    {month:"2026-08-01",cohortAgeDays:16,leads:100,sets:25,runs:10,wins:1}
  ],"campaign");
  assert(sameSliceComparison.find(item=>item.key==="leadToWin").referenceLabel.includes("Jul 2026–Aug 2026") && !sameSliceComparison.find(item=>item.key==="leadToWin").referenceLabel.includes("Jun 2026"), "Same-slice funnel comparator drifted outside the selected period.");
  assert(dashboardHtml.includes('class="health-period"') && dashboardHtml.includes("with its own period labeled"), "Funnel comparison does not distinguish the selected period from its reference period.");
  assert(dashboardHtml.includes("Aged unresolved (still open)") && dashboardHtml.includes("No set after 30+ days") && dashboardHtml.includes("Closed Lost</th>"), "Aged unresolved detail or Closed Lost count is not visible in Analysis.");
  const opportunities = app.opportunityRows();
  assert(opportunities.length === 1 && opportunities[0].campaign === "Efficient Search" && opportunities[0].ahj === "Fairfax County", "Campaign/AHJ opportunity rows were not created.");
  assert(opportunities[0].decisionType === "Scale" && opportunities[0].confidence === "High" && opportunities[0].estimatedWinImpact > 0, "Opportunity decision type, confidence, or impact is incorrect.");
  const decisionBenchmarks={setRate:.4,runRateFromSets:.6,winRateFromRuns:.3,leadToWinRate:.1,costPerWin:2000,revenuePerWin:45000};
  const incompleteScale=app.opportunityForRow({campaign:"Durable source",ahj:"Montgomery",leads:100,sets:45,runs:28,wins:15,leadToWinRate:.15,costPerWin:null,benchmarkLeadToWinRate:.1,benchmarkCoverage:1,spendCompleteLeadShare:.1,sampleSizeBucket:"Sufficient Sample"},decisionBenchmarks);
  assert(incompleteScale.decisionType==="Scale" && incompleteScale.evidenceFlags.some(flag=>flag.key==="spend-incomplete") && incompleteScale.evidenceFlags.some(flag=>flag.key==="cac-unavailable"), "Incomplete spend replaced a useful Scale action instead of becoming evidence cautions.");
  assert(Math.abs(incompleteScale.referenceBenchmark-.1)<1e-9 && Math.abs(incompleteScale.qualificationThreshold-.115)<1e-9 && incompleteScale.target!==incompleteScale.current, "Scale did not retain its actual benchmark and qualification threshold.");
  const conversionProtect=app.opportunityForRow({campaign:"Referral",ahj:"Dauphin",leads:80,sets:38,runs:24,wins:9,leadToWinRate:.1125,costPerWin:null,benchmarkLeadToWinRate:.1,benchmarkCoverage:1,spendCompleteLeadShare:.2,sampleSizeBucket:"Sufficient Sample"},decisionBenchmarks);
  assert(conversionProtect.decisionType==="Protect" && conversionProtect.evidenceFlags.some(flag=>flag.key==="cac-unavailable"), "Strong conversion with unavailable CAC did not remain a Protect action with a caution.");
  const lowSampleTest=app.opportunityForRow({campaign:"Emerging",ahj:"York",leads:20,sets:10,runs:7,wins:3,leadToWinRate:.15,benchmarkLeadToWinRate:.1,benchmarkCoverage:.3,spendCompleteLeadShare:1,sampleSizeBucket:"Low Sample"},decisionBenchmarks);
  assert(lowSampleTest.decisionType==="Test" && lowSampleTest.evidenceFlags.some(flag=>flag.key==="low-sample") && lowSampleTest.evidenceFlags.some(flag=>flag.key==="benchmark-developing"), "Strong low-sample evidence did not become a Test with visible cautions.");
  assert(!dashboardHtml.includes('<option value="Fix data">Fix data</option>') && dashboardHtml.includes('id="opportunityEvidenceFilter"'), "Data quality remains a primary action instead of an evidence filter.");
  assert(dashboardHtml.includes('<option value="24">24 months · history</option>') && dashboardHtml.includes('<option value="36">36 months · history</option>'), "The 24- and 36-month historical cohort lenses are missing.");
  app.state.months=24;app.renderAll();assert(getElement("historicalLensNotice").classList.contains("show") && dashboardHtml.includes("Older spend and CAC"), "Historical cohort guidance did not appear for a 24-month slice.");app.state.months=7;app.renderAll();
  const originalGeoRows=app.state.geoRows,originalBenchmarkGeoRows=app.state.benchmarkGeoRows;
  const adaptiveRows=[
    {campaign:"Search A",campaignRollup:"Paid Search",ahj:"Baltimore",geography:"Baltimore",leads:30,sets:15,runs:10,wins:4,revenue:180000,effectiveSpend:9000,benchmarkLeadToWinRate:.1,benchmarkCoverage:1,spendCompleteLeadShare:1,opportunityScore:60},
    {campaign:"Search B",campaignRollup:"Paid Search",ahj:"Baltimore",geography:"Baltimore",leads:30,sets:14,runs:9,wins:4,revenue:170000,effectiveSpend:8500,benchmarkLeadToWinRate:.1,benchmarkCoverage:1,spendCompleteLeadShare:1,opportunityScore:58},
    {campaign:"Referral",campaignRollup:"Referral",ahj:"York",geography:"York",leads:35,sets:17,runs:11,wins:4,revenue:175000,effectiveSpend:7000,benchmarkLeadToWinRate:.1,benchmarkCoverage:1,spendCompleteLeadShare:1,opportunityScore:57},
    {campaign:"Referral",campaignRollup:"Referral",ahj:"Dauphin",geography:"Dauphin",leads:35,sets:16,runs:10,wins:4,revenue:170000,effectiveSpend:7000,benchmarkLeadToWinRate:.1,benchmarkCoverage:1,spendCompleteLeadShare:1,opportunityScore:56}
  ];
  app.state.geoRows=adaptiveRows;app.state.benchmarkGeoRows=adaptiveRows;app.state.opportunityGrain="adaptive";
  const adaptive=app.adaptiveOpportunityRows();
  assert(adaptive.some(row=>row.decisionGrain==="family-county"&&row.campaign==="Paid Search"&&row.childCount===2&&row.sampleSizeBucket==="Sufficient Sample"&&row.localConsistency===1), "Adaptive grain did not pool related campaigns within a county or disclose local consistency.");
  assert(adaptive.some(row=>row.decisionGrain==="campaign-portfolio"&&row.campaign==="Referral"&&row.childCount===2&&row.sampleSizeBucket==="Sufficient Sample"), "Adaptive grain did not pool an exact campaign across selected markets.");
  assert(adaptive.length===2 && new Set(adaptive.flatMap(row=>row.childKeys)).size===4, "Adaptive grain duplicated contributing campaign × county slices.");
  const familyDecision=adaptive.find(row=>row.decisionGrain==="family-county");app.state.loading=true;app.beginOpportunity(familyDecision.key);app.state.loading=false;
  assert(app.state.rollup==="Paid Search"&&app.state.ahj==="Baltimore"&&!app.state.campaign&&app.state.activeDecision.evidence.some(item=>item.includes("2 contributing")), "A pooled family decision did not drill into its representable rollup × county scope.");
  app.state.geoRows=[{...adaptiveRows[0],wins:7,runs:12},{...adaptiveRows[1],wins:0,runs:6}];app.state.benchmarkGeoRows=app.state.geoRows;
  const mixedLocal=app.adaptiveOpportunityRows()[0];
  assert(mixedLocal.decisionType==="Test"&&mixedLocal.evidenceFlags.some(flag=>flag.key==="mixed-local-signal")&&mixedLocal.localConsistency===.5, "A contradictory pooled signal was allowed to become a broad Scale/Protect action.");
  const marketRows=[
    {campaign:"Search A",campaignRollup:"Paid Search",ahj:"Fairfax",geography:"Fairfax",decisionMarketKey:"NORTHERN VIRGINIA",decisionMarket:"Northern Virginia",decisionMarketMappingVersion:"seed_v1",leads:30,sets:15,runs:10,wins:4,revenue:180000,effectiveSpend:9000,benchmarkLeadToWinRate:.1,benchmarkCoverage:1,spendCompleteLeadShare:1,opportunityScore:60},
    {campaign:"Search A",campaignRollup:"Paid Search",ahj:"Loudoun",geography:"Loudoun",decisionMarketKey:"NORTHERN VIRGINIA",decisionMarket:"Northern Virginia",decisionMarketMappingVersion:"seed_v1",leads:30,sets:14,runs:9,wins:4,revenue:170000,effectiveSpend:8500,benchmarkLeadToWinRate:.1,benchmarkCoverage:1,spendCompleteLeadShare:1,opportunityScore:58},
    {campaign:"Social A",campaignRollup:"Paid Social",ahj:"Baltimore",geography:"Baltimore",decisionMarketKey:"BALTIMORE METRO",decisionMarket:"Baltimore Metro",decisionMarketMappingVersion:"seed_v1",leads:30,sets:15,runs:10,wins:4,revenue:180000,effectiveSpend:9000,benchmarkLeadToWinRate:.1,benchmarkCoverage:1,spendCompleteLeadShare:1,opportunityScore:57},
    {campaign:"Social B",campaignRollup:"Paid Social",ahj:"Howard",geography:"Howard",decisionMarketKey:"BALTIMORE METRO",decisionMarket:"Baltimore Metro",decisionMarketMappingVersion:"seed_v1",leads:30,sets:14,runs:9,wins:4,revenue:170000,effectiveSpend:8500,benchmarkLeadToWinRate:.1,benchmarkCoverage:1,spendCompleteLeadShare:1,opportunityScore:56},
    {campaign:"Unmapped",campaignRollup:"Referral",ahj:"Unknown One",geography:"Unknown One",decisionMarketKey:null,decisionMarket:null,leads:30,sets:15,runs:10,wins:4,revenue:180000,effectiveSpend:6000,benchmarkLeadToWinRate:.1,benchmarkCoverage:1,spendCompleteLeadShare:1,opportunityScore:55}
  ];
  app.state.campaign="";app.state.rollup="";app.state.ahj="";app.clearDecisionMarketScope({reload:false});
  app.state.geoRows=marketRows;app.state.benchmarkGeoRows=marketRows;app.state.opportunityGrain="adaptive";
  const marketAdaptive=app.adaptiveOpportunityRows();
  const campaignMarket=marketAdaptive.find(row=>row.decisionGrain==="campaign-market");
  const familyMarket=marketAdaptive.find(row=>row.decisionGrain==="family-market");
  assert(campaignMarket?.campaign==="Search A"&&campaignMarket.childGeographyCount===2&&campaignMarket.scopeDecisionMarket==="NORTHERN VIRGINIA", "Adaptive grain did not pool an exact campaign across a governed decision market.");
  assert(familyMarket?.campaign==="Paid Social"&&familyMarket.childGeographyCount===2&&familyMarket.scopeDecisionMarket==="BALTIMORE METRO", "Adaptive grain did not pool a campaign family across a governed decision market.");
  assert(!app.opportunityRowsForGrain("campaign-market").some(row=>row.campaign==="Unmapped"), "An unmapped county was silently invented into decision-market pooling.");
  app.state.loading=true;app.beginOpportunity(campaignMarket.key);app.state.loading=false;app.renderAll();
  assert(app.state.campaign==="Search A"&&!app.state.ahj&&app.state.decisionMarket==="NORTHERN VIRGINIA"&&getElement("decisionMarketNotice").classList.contains("show"), "Opening a decision-market recommendation did not activate its clearly labeled temporary scope.");
  assert(app.trendQueryString().includes("decisionMarket=NORTHERN+VIRGINIA")&&app.decisionTrackingPayload().filters.decisionMarket==="NORTHERN VIRGINIA", "Decision-market scope did not reach reporting or the frozen decision payload.");
  app.clearDecisionMarketScope({reload:false});assert(!app.state.decisionMarket&&!getElement("decisionMarketNotice").classList.contains("show"), "Return to county filters did not clear the temporary decision-market scope.");
  app.state.geoRows=[{...marketRows[0],wins:7,runs:12},{...marketRows[1],wins:0,runs:6}];app.state.benchmarkGeoRows=app.state.geoRows;
  const mixedMarket=app.opportunityRowsForGrain("campaign-market")[0];
  assert(mixedMarket.decisionType==="Test"&&mixedMarket.evidenceFlags.some(flag=>flag.key==="mixed-local-signal")&&mixedMarket.localConsistency===.5, "A mixed county signal was allowed to become a broad decision-market Scale/Protect action.");
  app.state.geoRows=originalGeoRows;app.state.benchmarkGeoRows=originalBenchmarkGeoRows;app.state.campaign="";app.state.rollup="";app.state.ahj="";app.state.opportunityGrain="adaptive";app.renderAll();
  assert(dashboardHtml.includes('id="countyQueueMode"') && dashboardHtml.includes('id="hierarchyQueueMode"') && dashboardHtml.includes('id="hierarchyGrainFilter"') && dashboardHtml.includes('aria-pressed="true"') && dashboardHtml.includes("Campaign across markets"), "County/marketing-hierarchy controls or their accessibility contract are missing.");
  assert(dashboardHtml.includes('.command-opportunity-card .section-head{display:grid') && dashboardHtml.includes('grid-template-columns:max-content minmax(168px,1.35fr)') && dashboardHtml.includes('@media(max-width:920px)') && dashboardHtml.includes('.opportunity-toolbar{grid-template-columns:minmax(0,1fr)}'), "Decision queue controls do not preserve a stable desktop row and intentional responsive wrapping.");
  app.setOpportunityMode("county");
  assert(app.state.opportunityGrain==="campaign-county"&&getElement("hierarchyGrainWrap").hidden, "County view did not switch the queue to exact campaign × county evidence.");
  app.state.opportunityHierarchyGrain="campaign-market";app.setOpportunityMode("hierarchy");
  assert(app.state.opportunityGrain==="campaign-market"&&!getElement("hierarchyGrainWrap").hidden&&getElement("hierarchyGrainFilter").value==="campaign-market", "Marketing hierarchy did not restore its selected hierarchy detail.");
  app.state.opportunityHierarchyGrain="adaptive";app.setOpportunityMode("hierarchy");
  assert(getElement("insightList").innerHTML.includes("Efficient Search") && getElement("insightList").innerHTML.includes("Fairfax County"), "Multi-campaign/AHJ opportunity queue did not render.");
  assert(getElement("opportunityMatrix").innerHTML.includes("matrix-cell") && getElement("opportunityMatrix").innerHTML.includes("Fairfax County"), "Clickable Campaign/AHJ matrix did not render.");
  assert(dashboardHtml.includes('id="matrixMetric"') && dashboardHtml.includes('id="improvementTarget"'), "Metric switching or improvement-target modeling is missing.");
  const sparseWaterfall = app.funnelWaterfallModel({leads:3,sets:0,runs:0,wins:0,benchmark:null});
  assert(sparseWaterfall.steps.length === 5 && sparseWaterfall.steps.every(Number.isFinite), "Sparse funnel drill-down did not preserve every finite waterfall stage.");
  assert(sparseWaterfall.actionTone === "neutral" && sparseWaterfall.actionCopy.includes("sample maturity"), "Sparse funnel drill-down did not explain insufficient benchmark evidence.");
  const zeroStageWaterfall = app.funnelWaterfallModel({leads:20,sets:0,runs:0,wins:0,benchmark:.1});
  assert(zeroStageWaterfall.steps[0] > 0 && zeroStageWaterfall.steps.every(Number.isFinite) && zeroStageWaterfall.actionTone === "warn", "Zero-stage drill-down collapsed despite having a usable benchmark.");
  const benchmarkWaterfall = app.funnelWaterfallModel(aggregate);
  assert(benchmarkWaterfall.steps.length === 5 && !benchmarkWaterfall.labels.includes("Lead volume") && benchmarkWaterfall.labels.includes("Lead → set gap"), "Benchmark waterfall did not remove the zero hold-volume step.");
  const decisions = app.decisionInsights();
  assert(decisions.length === 3 && decisions.every(item => item.question && item.view && item.evidence.length), "Command-center insights are not actionable decision objects.");
  assert(getElement("insightList").innerHTML.includes("Investigate") && dashboardHtml.includes("Discover → Investigate → Test → Implement"), "Guided decision workflow is not visible.");
  app.beginInvestigation("funnel-signal");
  assert(app.state.workflowStage === "investigate" && app.state.activeDecision.id === "funnel-signal", "Insight did not become an active investigation.");
  assert(getElement("decisionWorkspace").classList.contains("show") && !getElement("funnelEvidence").hidden, "Active decision context did not persist into investigation.");
  const originalEvidenceCount = app.state.activeDecision.evidence.length;
  app.addDecisionEvidence("funnel");
  assert(app.state.activeDecision.evidence.length === originalEvidenceCount + 1, "Investigation evidence was not carried forward.");
  getElement("geoEvidenceChoice").value = "Fairfax County||Efficient Search||VA||County";
  const geoEvidenceCount = app.state.activeDecision.evidence.length;
  app.addDecisionEvidence("geo");
  assert(app.state.activeDecision.evidence.length === geoEvidenceCount + 1 && app.state.activeDecision.evidence.at(-1).includes("Fairfax County · Efficient Search"), "A ranked geography could not be added without changing the header filters.");
  assert(getElement("activeDecisionEvidence").innerHTML.includes("Fairfax County") && getElement("geoEvidenceCopy").textContent.includes("Captured"), "Added geography evidence was not visibly confirmed in the decision workspace.");
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
  const presentationData = {
    scope:"region:Operating footprint",scopeLabel:"MD Ops + PA Ops",period:"Last 7 months",
    funnelRows,geoRows,summary:aggregate,decisions:[{
      question:"Scale efficient search?",action:"Run a controlled budget test.",status:"Monitoring",
      created_by_name:"Test User",operating_region:"Maryland",review_after:"2026-08-28"
    }]
  };
  const presentationSlides = app.buildPresentationSlides(presentationData);
  assert(presentationSlides.length === 6 && presentationSlides.every(slide=>slide.id&&slide.html.includes("presentation-slide")), "Selectable presentation elements did not build a complete story.");
  assert(presentationSlides.filter(slide=>["overview","funnel"].includes(slide.id)).every(slide=>slide.html.includes("<svg")&&slide.html.includes("presentation-talk-track")), "Presentation trend charts or talk tracks are missing.");
  assert(presentationSlides.filter(slide=>["campaigns","geography"].includes(slide.id)).every(slide=>slide.html.includes("presentation-bar-track")) && dashboardHtml.includes('title="Mature benchmark"'), "Campaign or geography benchmark charts are missing.");
  assert(presentationSlides.find(slide=>slide.id==="scenario").html.includes("presentation-scenario-bars") && presentationSlides.find(slide=>slide.id==="decisions").html.includes("Active decisions"), "Scenario comparison or decision-summary visuals are missing.");
  assert(presentationSlides.find(slide=>slide.id==="geography").html.includes("Ops-region rollup"), "Operating-region presentation rollup is missing.");
  assert(presentationSlides.find(slide=>slide.id==="decisions").html.includes("Scale efficient search?"), "Tracked decisions did not carry into presentation mode.");
  const statePresentationQuery = app.presentationQuery("state:VA");
  assert(statePresentationQuery.includes("state=VA") && !statePresentationQuery.includes("region="), "Physical-state presentation scope is not independent from Ops region.");
  assert(dashboardHtml.includes('data-drawer="presentation"') && dashboardHtml.includes('id="presentationDrawer"') && dashboardHtml.includes('id="presentationShell"'), "The low-clutter presentation entry point or overlay is missing.");
  assert(global.requestedUrls.filter(url=>url.includes("marketing-funnel")||url.includes("marketing-geo")).every(url=>url.includes("region=Operating+footprint")), "Default operating-footprint filter was not sent to both data endpoints.");
  assert(global.requestedUrls.some(url=>url.includes("marketing-filter-options")&&url.includes("region=Operating+footprint")), "Complete filter catalog was not requested.");
  assert(global.requestedUrls.some(url=>url.includes("marketing-capacity")&&url.includes("region=Operating+footprint")), "Governed current-state inflight context was not requested.");
  const funnelRequestsBeforeRefresh = global.requestedUrls.filter(url=>url.includes("marketing-funnel")).length;
  const refreshPromise = app.refreshData();
  assert(getElement("refreshButton").classList.contains("is-loading") && getElement("refreshButton").disabled, "Refresh control did not enter its animated loading state.");
  refreshPromise.then(() => {
    assert(global.requestedUrls.filter(url=>url.includes("marketing-funnel")).length > funnelRequestsBeforeRefresh, "Refresh did not issue a fresh funnel request.");
    assert(global.requestedUrls.filter(url=>url.includes("marketing-reconciliation")).length >= 2, "Forced refresh reused cached reconciliation data.");
    assert(!getElement("refreshButton").classList.contains("is-loading") && !getElement("refreshButton").disabled, "Refresh control did not leave its loading state.");
    app.state.campaign = "Efficient Search";getElement("campaignFilter").value = "Efficient Search";
    getElement("stateFilter").value = "Maryland";
    getElement("stateFilter").dispatchEvent({type:"change",target:getElement("stateFilter")});
    setImmediate(() => {
    assert(global.requestedUrls.some(url=>url.includes("marketing-funnel")&&url.includes("region=Maryland")), "Changing operating region did not reload funnel data.");
    assert(global.requestedUrls.some(url=>url.includes("marketing-geo")&&url.includes("region=Maryland")), "Changing operating region did not reload geography data.");
    assert(app.state.campaign==="Efficient Search"&&getElement("campaignFilter").value==="Efficient Search", "Changing operating region reset a still-compatible campaign filter.");
    assert(app.state.workbook.geography==="MD"&&getElement("workbookGeography").value==="MD", "Operating region did not map to the supported Official Plan geography.");
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
        });
      });
    });
  });
  });
});
