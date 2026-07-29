const { installFakeDom, loadDashboardScript } = require("./dom_fake");

installFakeDom();

function ahjFixtureRow(market, campaign, index) {
  const leads = 60 + index * 10;
  const wins = 8 + index;
  const spend = wins * (900 + index * 100);
  const revenue = wins * 10000;
  return {
    market,
    campaign,
    leads,
    wins,
    spend,
    revenue,
    cpw: spend / wins,
    revenuePerSpend: revenue / spend,
    leadToWinRate: wins / leads,
    sampleSizeBucket: "Sufficient Sample"
  };
}

const markets = [
  "District of Columbia",
  "Montgomery County, MD",
  "Prince George's County, MD",
  "Fairfax County, VA",
  "Loudoun County, VA",
  "Arlington County, VA"
];
const campaigns = ["Efficient Search", "Referral Push"];
const ahjRows = [];
markets.forEach((market, marketIndex) => {
  campaigns.forEach((campaign, campaignIndex) => {
    ahjRows.push(ahjFixtureRow(market, campaign, marketIndex + campaignIndex));
  });
});

const campaignRows = [
  { campaign: "Efficient Search", campaignRollup: "Paid Search", month: "2026-05-01", leads: 100, wins: 20, spend: 18000, revenue: 200000 },
  { campaign: "Efficient Search", campaignRollup: "Paid Search", month: "2026-06-01", leads: 120, wins: 24, spend: 22000, revenue: 240000 },
  { campaign: "Referral Push", campaignRollup: "Referral", month: "2026-05-01", leads: 70, wins: 10, spend: 14000, revenue: 100000 },
  { campaign: "Referral Push", campaignRollup: "Referral", month: "2026-06-01", leads: 80, wins: 11, spend: 18000, revenue: 110000 },
  { campaign: "Unproven Partner", campaignRollup: "Partner", month: "2026-06-01", leads: 0, wins: 0, spend: 3000, revenue: 0 }
];

global.fetch = url => {
  const value = String(url);
  if (value.includes("campaign-performance")) {
    return Promise.resolve({ ok: true, json: () => Promise.resolve(campaignRows) });
  }
  if (value.includes("ahj-performance")) {
    return Promise.resolve({ ok: true, json: () => Promise.resolve(ahjRows) });
  }
  return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
};

const script = loadDashboardScript();
const run = new Function(`${script}
return (async () => {
  state.view = "campaigns";
  await renderCampaignPlanner();
  state.view = "ahj";
  state.ahjCampaign = "Efficient Search";
  await renderAhjPlanner();
  state.view = "overview";
  renderTrendExplorer();
  return {
    campaignMetrics: document.getElementById("campaignMetrics").innerHTML,
    campaignRecommendations: document.getElementById("campaignRecommendations").innerHTML,
    campaignCards: document.getElementById("campaignCards").innerHTML,
    campaignTrend: document.getElementById("campaignTrendChart").innerHTML,
    campaignTable: document.getElementById("campaignTable").innerHTML,
    campaignOptions: document.getElementById("campaignDetailSelect").innerHTML,
    ahjMetrics: document.getElementById("ahjMetrics").innerHTML,
    ahjInsights: document.getElementById("ahjImmediateInsights").innerHTML,
    ahjTable: document.getElementById("ahjAllocationTable").innerHTML,
    explorer: document.getElementById("trendExplorerChart").innerHTML,
    summary: document.getElementById("trendSummary").innerHTML
  };
})();`);

run().then(output => {
  const joined = Object.values(output).join("\n");
  if (/NaN|null|undefined/.test(joined)) {
    console.error("Invalid token found in rendered dashboard output.");
    const match = joined.match(/.{0,80}(NaN|null|undefined).{0,80}/);
    if (match) console.error(match[0]);
    process.exit(1);
  }

  if (
    !output.campaignRecommendations.includes("Scale") ||
    !output.campaignRecommendations.includes("Avoid") ||
    !output.campaignCards.includes("Efficient Search") ||
    !output.campaignTable.includes("Selected metric") ||
    !output.campaignTable.includes("Revenue/spend") ||
    !output.campaignTrend.includes("Efficient Search revenue") ||
    !output.campaignOptions.includes("Referral Push")
  ) {
    console.error("Campaign Performance did not render expected live actuals and recommendations.");
    process.exit(1);
  }

  if (/allocator|planned spend|capacity-adjusted|product mix lift/i.test(
    output.campaignMetrics + output.campaignRecommendations + output.campaignCards + output.campaignTable
  )) {
    console.error("Retired synthetic allocator concepts remain in rendered Campaigns output.");
    process.exit(1);
  }

  if (
    !output.ahjMetrics.includes("Efficient Search") ||
    !output.ahjInsights.includes("Scale") ||
    !output.ahjTable.includes("Selected metric")
  ) {
    console.error("AHJ planner regression detected.");
    process.exit(1);
  }

  if (!output.explorer.includes("Prior month") || !output.summary.includes("Latest")) {
    console.error("Overview trend explorer regression detected.");
    process.exit(1);
  }

  console.log(JSON.stringify({
    campaignMetricsLength: output.campaignMetrics.length,
    campaignRecommendationsLength: output.campaignRecommendations.length,
    campaignCardsLength: output.campaignCards.length,
    campaignTableLength: output.campaignTable.length,
    campaignTrendLength: output.campaignTrend.length,
    ahjTableLength: output.ahjTable.length,
    explorerLength: output.explorer.length
  }, null, 2));
}).catch(error => {
  console.error(error);
  process.exit(1);
});
