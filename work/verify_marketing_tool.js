const { installFakeDom, loadDashboardScript } = require("./dom_fake");

installFakeDom();
global.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) });

const script = loadDashboardScript();
const run = new Function(`${script}
state.view = "campaigns";
renderCampaignPlanner();
state.view = "overview";
renderTrendExplorer();
return {
  heatmap: document.getElementById("campaignHeatmap").innerHTML,
  cards: document.getElementById("campaignCards").innerHTML,
  moves: document.getElementById("campaignMoves").innerHTML,
  suite: document.getElementById("decisionMetricSuite").innerHTML,
  table: document.getElementById("campaignTable").innerHTML,
  metrics: document.getElementById("campaignMetrics").innerHTML,
  trend: document.getElementById("campaignTrendChart").innerHTML,
  explorer: document.getElementById("trendExplorerChart").innerHTML,
  summary: document.getElementById("trendSummary").innerHTML
};`);

const output = run();
const joined = Object.values(output).join("\\n");
if (/NaN|null|undefined/.test(joined)) {
  console.error("Invalid token found in rendered campaign planner output.");
  const match = joined.match(/.{0,80}(NaN|null|undefined).{0,80}/);
  if (match) console.error(match[0]);
  process.exit(1);
}

const retiredRegionPattern = /Texas|Northeast|Mid-Atlantic|Southeast(?! PA)|\bWest\b/;
if (retiredRegionPattern.test(output.heatmap)) {
  console.error("Retired national region labels should not render in the campaign heatmap.");
  process.exit(1);
}

const heatmapScores = [...output.heatmap.matchAll(/<strong>(\d+)<\/strong>/g)].map(match => Number(match[1]));
if (heatmapScores.length !== 30) {
  console.error(`Expected 30 campaign heatmap scores for six DMV/PA markets, found ${heatmapScores.length}.`);
  process.exit(1);
}

if (new Set(heatmapScores).size < 3) {
  console.error("Campaign heatmap scores are not varied enough.");
  console.error(heatmapScores.join(", "));
  process.exit(1);
}

if (!output.explorer.includes("Prior month") || !output.summary.includes("Latest")) {
  console.error("Trend explorer did not render expected MOM comparison content.");
  process.exit(1);
}

console.log(JSON.stringify({
  heatmapLength: output.heatmap.length,
  heatmapScoreCount: heatmapScores.length,
  uniqueHeatmapScores: new Set(heatmapScores).size,
  cardsLength: output.cards.length,
  movesLength: output.moves.length,
  suiteLength: output.suite.length,
  tableLength: output.table.length,
  metricsLength: output.metrics.length,
  trendLength: output.trend.length,
  explorerLength: output.explorer.length,
  summaryLength: output.summary.length
}, null, 2));
