const vm = require("vm");
const { installFakeDom, loadDashboardScript } = require("./dom_fake");

const { getElement } = installFakeDom();
const funnelRows = [
  {
    month:"2026-06-01", campaign:"Efficient Search", campaignRollup:"3rd Party Vendors LSR",
    campaignSubrollup:"Paid Search", leads:100, sets:50, runs:40, wins:20, revenue:900000,
    effectiveSpend:40000, recordedSpend:40000, activePipeline:20, activePipelineRevenue:600000,
    expectedRemainingWins:5, expectedRemainingRevenue:200000, benchmarkLeadToWinRate:.15,
    spendCompleteLeadShare:1, spendCoverageStatus:"Complete", loadedAt:"2026-07-28T12:00:00Z"
  },
  {
    month:"2026-07-01", campaign:"Co-op Maryland", campaignRollup:"Co-op",
    campaignSubrollup:"Co-op", leads:50, sets:25, runs:20, wins:8, revenue:340000,
    effectiveSpend:0, recordedSpend:0, activePipeline:12, activePipelineRevenue:300000,
    expectedRemainingWins:3, expectedRemainingRevenue:125000, benchmarkLeadToWinRate:.14,
    spendCompleteLeadShare:0, spendCoverageStatus:"Known incomplete", loadedAt:"2026-07-28T12:00:00Z"
  }
];
const geoRows = [{
  geography:"Fairfax County", geographyType:"County", county:"Fairfax", state:"VA",
  campaign:"Efficient Search", campaignRollup:"3rd Party Vendors LSR", leads:55, sets:25,
  runs:20, wins:10, revenue:450000, effectiveSpend:20000, activePipeline:9,
  expectedRemainingWins:2, benchmarkLeadToWinRate:.14, leadToWinRate:10/55,
  conversionDeltaVsBenchmark:10/55-.14, opportunityScore:76.2
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

global.fetch = url => {
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
  let payload = [];
  if (path.includes("marketing-funnel")) payload = funnelRows;
  else if (path.includes("marketing-geo")) payload = geoRows;
  else if (path.includes("marketing-reconciliation")) payload = reconciliation;
  else if (path.includes("freshness")) payload = {objects_found:4,objects_checked:4};
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
  assert(output.includes("Fairfax County") && output.includes("76.2"), "Geo opportunity ranking did not render.");
  assert(getElement("qualityMetrics").innerHTML.includes("Marketing Report 2026_Official.xlsx"), "Workbook reconciliation did not render.");
  assert(output.includes("Current baseline") && output.includes("Scenario"), "Scenario comparison did not render.");
  assert(!/NaN|undefined|null/.test(output), "Invalid numeric token found in rendered output.");
  assert(global.requestedUrls.filter(url=>url.includes("marketing-funnel")||url.includes("marketing-geo")).every(url=>url.includes("region=Operating+footprint")), "Default operating-footprint filter was not sent to both data endpoints.");
  getElement("stateFilter").value = "DMV";
  getElement("stateFilter").dispatchEvent({type:"change",target:getElement("stateFilter")});
  setImmediate(() => {
    assert(global.requestedUrls.some(url=>url.includes("marketing-funnel")&&url.includes("region=DMV")), "Changing operating region did not reload funnel data.");
    assert(global.requestedUrls.some(url=>url.includes("marketing-geo")&&url.includes("region=DMV")), "Changing operating region did not reload geography data.");
    console.log("Marketing Intelligence workspace verified OK.");
  });
});
