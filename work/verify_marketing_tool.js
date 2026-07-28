const { installFakeDom, loadDashboardScript } = require("./dom_fake");

installFakeDom();

function fixtureRow(market, campaign, marketIndex, campaignIndex) {
  const costPerLead = [60, 75, 90, 105, 120][campaignIndex];
  const winRate = [0.05, 0.07, 0.09, 0.05, 0.07][campaignIndex];
  const leads = 40 + marketIndex * 11 + campaignIndex * 7;
  const wins = Math.max(1, Math.round(leads * winRate));
  const spend = leads * costPerLead;
  const revenue = wins * (9000 + marketIndex * 300);
  const cpw = spend / wins;
  const revenuePerSpend = revenue / spend;
  const leadToWinRate = wins / leads;
  const sampleSizeBucket = leads >= 20 && wins >= 3 ? "Sufficient Sample" : "Low Sample";
  return { market, campaign, leads, wins, spend, revenue, cpw, revenuePerSpend, leadToWinRate, sampleSizeBucket };
}

const MARKETS = [
  "District of Columbia",
  "Montgomery County, MD",
  "Prince George's County, MD",
  "Fairfax County, VA",
  "Loudoun County, VA",
  "Arlington County, VA",
  "Baltimore County, MD",
  "Baltimore City, MD",
  "Chester County, PA",
  "Bucks County, PA",
  "Lancaster County, PA",
  "Dauphin County, PA"
];
const CAMPAIGNS = ["Solar Reviews", "Google Brand Defense", "Customer Referral Bonus", "EnergySage", "Home Shows"];

const ahjFixtureRows = [];
MARKETS.forEach((market, marketIndex) => {
  CAMPAIGNS.forEach((campaign, campaignIndex) => {
    ahjFixtureRows.push(fixtureRow(market, campaign, marketIndex, campaignIndex));
  });
});

Object.assign(
  ahjFixtureRows.find(row => row.market === "Fairfax County, VA" && row.campaign === "Solar Reviews"),
  { leads: 500, wins: 100, spend: 80000, revenue: 900000, cpw: 800, revenuePerSpend: 11.25, leadToWinRate: 0.2, sampleSizeBucket: "Sufficient Sample" }
);

Object.assign(
  ahjFixtureRows.find(row => row.market === "Dauphin County, PA" && row.campaign === "Solar Reviews"),
  { leads: 10, wins: 0, spend: 15000, revenue: 0, cpw: null, revenuePerSpend: 0, leadToWinRate: 0, sampleSizeBucket: "Low Sample" }
);

global.fetch = url => {
  if (String(url).includes("ahj-performance")) {
    return Promise.resolve({ ok: true, json: () => Promise.resolve(ahjFixtureRows) });
  }
  return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
};

const script = loadDashboardScript();
const run = new Function(`${script}
return (async () => {
  state.view = "campaigns";
  renderCampaignPlanner();
  state.view = "ahj";
  await renderAhjPlanner();
  state.view = "overview";
  renderTrendExplorer();
  return {
    heatmap: document.getElementById("campaignHeatmap").innerHTML,
    ahjHeatmap: document.getElementById("ahjHeatmap").innerHTML,
    ahjMetrics: document.getElementById("ahjMetrics").innerHTML,
    ahjInsights: document.getElementById("ahjImmediateInsights").innerHTML,
    ahjTable: document.getElementById("ahjAllocationTable").innerHTML,
    ahjDetail: document.getElementById("ahjDetail").innerHTML,
    ahjCanvas: document.getElementById("ahjInvestigationCanvas").innerHTML,
    ahjBreakdown: document.getElementById("ahjPerformanceBreakdown").innerHTML,
    cards: document.getElementById("campaignCards").innerHTML,
    moves: document.getElementById("campaignMoves").innerHTML,
    suite: document.getElementById("decisionMetricSuite").innerHTML,
    table: document.getElementById("campaignTable").innerHTML,
    metrics: document.getElementById("campaignMetrics").innerHTML,
    trend: document.getElementById("campaignTrendChart").innerHTML,
    explorer: document.getElementById("trendExplorerChart").innerHTML,
    summary: document.getElementById("trendSummary").innerHTML
  };
})();`);

run().then(output => {
  const joined = Object.values(output).join("\n");
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

  const ahjScores = [...output.ahjHeatmap.matchAll(/<strong>(\d+)<\/strong>/g)].map(match => Number(match[1]));
  if (ahjScores.length !== 60) {
    console.error(`Expected 60 AHJ heatmap scores for twelve markets and five campaigns, found ${ahjScores.length}.`);
    process.exit(1);
  }

  if (new Set(ahjScores).size < 5) {
    console.error("AHJ heatmap scores are not varied enough.");
    console.error(ahjScores.join(", "));
    process.exit(1);
  }

  const renderedMarketCount = (output.ahjTable.match(/<strong>[^<]+County|<strong>District of Columbia/g) || []).length;
  if (
    renderedMarketCount < 6 ||
    !output.ahjDetail.includes("Solar Reviews") ||
    !output.ahjTable.includes("CPW") ||
    !output.ahjTable.includes("Selected metric") ||
    !output.ahjCanvas.includes("Solar Reviews") ||
    !output.ahjCanvas.includes("ahj-click-card") ||
    !output.ahjInsights.includes("Scale") ||
    !output.ahjTable.includes("Avoid") ||
    !output.ahjBreakdown.includes("rev/spend")
  ) {
    console.error("AHJ planner did not render expected market recommendations and drilldown.");
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
    ahjHeatmapLength: output.ahjHeatmap.length,
    ahjHeatmapScoreCount: ahjScores.length,
    uniqueAhjHeatmapScores: new Set(ahjScores).size,
    ahjTableLength: output.ahjTable.length,
    ahjDetailLength: output.ahjDetail.length,
    ahjCanvasLength: output.ahjCanvas.length,
    ahjBreakdownLength: output.ahjBreakdown.length,
    cardsLength: output.cards.length,
    movesLength: output.moves.length,
    suiteLength: output.suite.length,
    tableLength: output.table.length,
    metricsLength: output.metrics.length,
    trendLength: output.trend.length,
    explorerLength: output.explorer.length,
    summaryLength: output.summary.length
  }, null, 2));
}).catch(error => {
  console.error(error);
  process.exit(1);
});
