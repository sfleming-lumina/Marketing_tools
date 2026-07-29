const { installFakeDom, loadDashboardScript } = require("./dom_fake");

installFakeDom();
global.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) });

const script = loadDashboardScript();
const run = new Function(`${script}
state.campaignRows = [
  { campaign: "Efficient Search", campaignRollup: "Paid Search", month: "2026-05-01", leads: 100, wins: 20, spend: 20000, revenue: 200000 },
  { campaign: "Efficient Search", campaignRollup: "Paid Search", month: "2026-06-01", leads: 100, wins: 20, spend: 20000, revenue: 200000 },
  { campaign: "Expensive Events", campaignRollup: "Events", month: "2026-06-01", leads: 100, wins: 20, spend: 45000, revenue: 90000 },
  { campaign: "No Sample", campaignRollup: "Partner", month: "2026-06-01", leads: 0, wins: 0, spend: 5000, revenue: 0 }
];
state.campaignObjective = "Balanced decision score";
state.campaignDetail = "All campaign details";
const aggregateRows = campaignAggregateRows();
const benchmarks = campaignBenchmarks(aggregateRows);
const rows = campaignDecisionRows();
const trend = campaignTrendRows(rows);
const context = dashboardContextForClaude();
return {
  aggregateRows,
  benchmarks,
  rows,
  trend,
  sampleRanks: {
    sufficient: campaignSampleConfidenceRank("Sufficient Sample"),
    low: campaignSampleConfidenceRank("Low Sample"),
    none: campaignSampleConfidenceRank("No Same-Period Sample")
  },
  campaignPlannerContext: context.campaign_planner
};`);

const output = run();
const expectedCpw = 85000 / 60;
if (Math.abs(output.benchmarks.cpw - expectedCpw) > 0.001) {
  console.error(`Expected blended CPW benchmark of ${expectedCpw}, got ${output.benchmarks.cpw}.`);
  process.exit(1);
}

const efficient = output.rows.find(row => row.campaign === "Efficient Search");
if (!efficient || efficient.decision !== "Scale") {
  console.error(`Expected Efficient Search to resolve to Scale, got ${efficient && efficient.decision}.`);
  process.exit(1);
}

const noSample = output.rows.find(row => row.campaign === "No Sample");
if (!noSample || noSample.decision !== "Avoid") {
  console.error(`Expected No Sample to resolve to Avoid, got ${noSample && noSample.decision}.`);
  process.exit(1);
}

if (output.trend.length !== 2 || output.trend[0].month !== "2026-05-01") {
  console.error("campaignTrendRows did not preserve the two chronological monthly rows.");
  console.error(JSON.stringify(output.trend));
  process.exit(1);
}

if (output.sampleRanks.sufficient !== 2 || output.sampleRanks.low !== 1 || output.sampleRanks.none !== 0) {
  console.error("campaignSampleConfidenceRank returned unexpected values.");
  process.exit(1);
}

const planner = output.campaignPlannerContext;
if (!Array.isArray(planner.active_campaigns) || !planner.active_campaigns.includes("Efficient Search")) {
  console.error("campaign_planner.active_campaigns did not include live campaign names.");
  process.exit(1);
}
const top = planner.top_recommendations[0];
if (!top || typeof top.cost_per_win === "undefined" || typeof top.sample_size_bucket === "undefined") {
  console.error("campaign_planner.top_recommendations is missing live-data fields.");
  console.error(JSON.stringify(top));
  process.exit(1);
}
if (!Array.isArray(planner.selected_campaign_trend) || planner.selected_campaign_trend.length !== 2) {
  console.error("campaign_planner.selected_campaign_trend did not contain month-grained live rows.");
  process.exit(1);
}
if ("cost_spend_diagnostics" in planner || "budget" in planner || "grain" in planner) {
  console.error("Retired allocator fields remain in campaign_planner context.");
  process.exit(1);
}

console.log(JSON.stringify({
  blendedCpw: output.benchmarks.cpw,
  leadToWinBenchmark: output.benchmarks.leadToWinRate,
  campaignCount: output.rows.length,
  efficientDecision: efficient.decision,
  noSampleDecision: noSample.decision,
  trendMonths: output.trend.length
}, null, 2));
