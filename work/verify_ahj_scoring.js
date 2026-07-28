const { installFakeDom, loadDashboardScript } = require("./dom_fake");

installFakeDom();
global.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) });

const script = loadDashboardScript();
const run = new Function(`${script}
state.ahjRows = [
  { market: "Fairfax County, VA", campaign: "Solar Reviews", leads: 400, wins: 80, spend: 80000, revenue: 800000, cpw: 1000, revenuePerSpend: 10, leadToWinRate: 0.2, sampleSizeBucket: "Sufficient Sample" },
  { market: "Loudoun County, VA", campaign: "Solar Reviews", leads: 0, wins: 0, spend: 5000, revenue: 0, cpw: null, revenuePerSpend: 0, leadToWinRate: 0, sampleSizeBucket: "No Same-Period Sample" },
  { market: "Prince George's County, MD", campaign: "Solar Reviews", leads: 100, wins: 20, spend: 45000, revenue: 90000, cpw: 2250, revenuePerSpend: 2, leadToWinRate: 0.2, sampleSizeBucket: "Sufficient Sample" }
];
state.ahjCampaign = "Solar Reviews";
state.selectedAhj = "All AHJs";
const benchmarks = ahjBenchmarks(state.ahjRows);
const rows = ahjDecisionRows();
const context = dashboardContextForClaude();
return {
  benchmarks,
  rows,
  sampleRanks: {
    sufficient: ahjSampleConfidenceRank("Sufficient Sample"),
    low: ahjSampleConfidenceRank("Low Sample"),
    none: ahjSampleConfidenceRank("No Same-Period Sample")
  },
  ahjPlannerContext: context.ahj_planner
};`);

const output = run();

if (output.benchmarks.cpw !== 1250) {
  console.error(`Expected blended CPW benchmark of 1250, got ${output.benchmarks.cpw}.`);
  process.exit(1);
}

const fairfax = output.rows.find(row => row.market === "Fairfax County, VA");
if (!fairfax || fairfax.decision !== "Scale") {
  console.error(`Expected Fairfax County, VA to resolve to Scale, got ${fairfax && fairfax.decision}.`);
  process.exit(1);
}

const loudoun = output.rows.find(row => row.market === "Loudoun County, VA");
if (!loudoun || loudoun.decision !== "Avoid") {
  console.error(`Expected Loudoun County, VA to resolve to Avoid, got ${loudoun && loudoun.decision}.`);
  process.exit(1);
}

if (output.sampleRanks.sufficient !== 2 || output.sampleRanks.low !== 1 || output.sampleRanks.none !== 0) {
  console.error("ahjSampleConfidenceRank did not map sample-size buckets to the expected ranks.");
  console.error(JSON.stringify(output.sampleRanks));
  process.exit(1);
}

const contextMarkets = output.ahjPlannerContext.active_markets;
if (!Array.isArray(contextMarkets) || !contextMarkets.includes("Fairfax County, VA") || !contextMarkets.includes("Loudoun County, VA")) {
  console.error("ahj_planner.active_markets did not include the expected fixture markets.");
  console.error(JSON.stringify(contextMarkets));
  process.exit(1);
}

const topRecommendation = output.ahjPlannerContext.top_recommendations[0];
if (!topRecommendation || typeof topRecommendation.cost_per_win === "undefined" || typeof topRecommendation.sample_size_bucket === "undefined") {
  console.error("ahj_planner.top_recommendations did not include the expected live-data fields.");
  console.error(JSON.stringify(topRecommendation));
  process.exit(1);
}

console.log(JSON.stringify({
  blendedCpw: output.benchmarks.cpw,
  leadToWinBenchmark: output.benchmarks.leadToWinRate,
  rowCount: output.rows.length,
  fairfaxDecision: fairfax.decision,
  loudounDecision: loudoun.decision
}, null, 2));
