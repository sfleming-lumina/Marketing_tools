const { installFakeDom, loadDashboardScript } = require("./dom_fake");

installFakeDom();
global.__campaignTestActive = false;

global.fetch = url => {
  if (!String(url).includes("campaign-performance")) {
    return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
  }
  if (!global.__campaignTestActive) {
    return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
  }
  global.__campaignFetchCallCount = (global.__campaignFetchCallCount || 0) + 1;
  if (global.__campaignFetchCallCount === 1) {
    return Promise.resolve({ ok: false, status: 502 });
  }
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve([
      { campaign: "Efficient Search", campaignRollup: "Paid Search", month: "2026-06-01", leads: 100, wins: 10, spend: 10000, revenue: 50000 }
    ])
  });
};

const script = loadDashboardScript();
const run = new Function(`${script}
return (async () => {
  await new Promise(resolve => setImmediate(resolve));
  state.campaignRows = [];
  state.campaignRowsFetchKey = null;
  state.campaignLoadError = null;
  global.__campaignFetchCallCount = 0;
  global.__campaignTestActive = true;
  await ensureCampaignRowsLoaded();
  renderCampaignLoadError();
  const afterFailure = {
    error: state.campaignLoadError,
    fetchKey: state.campaignRowsFetchKey,
    bannerHidden: document.getElementById("campaignLoadError").classList.contains("hidden"),
    bannerText: document.getElementById("campaignLoadErrorText").textContent
  };

  await ensureCampaignRowsLoaded();
  renderCampaignLoadError();
  const afterRetry = {
    error: state.campaignLoadError,
    fetchKey: state.campaignRowsFetchKey,
    bannerHidden: document.getElementById("campaignLoadError").classList.contains("hidden"),
    rowCount: state.campaignRows.length
  };

  await ensureCampaignRowsLoaded();
  return { afterFailure, afterRetry, fetchCallCount: global.__campaignFetchCallCount };
})();`);

run().then(output => {
  function assert(condition, message) {
    if (!condition) {
      console.error(message);
      process.exit(1);
    }
  }
  assert(!!output.afterFailure.error, "Expected campaignLoadError after a failed fetch.");
  assert(output.afterFailure.fetchKey === null, "A failed fetch must not cache the Campaigns fetch key.");
  assert(!output.afterFailure.bannerHidden, "Campaign error banner should be visible after failure.");
  assert(output.afterFailure.bannerText.includes("Campaign data unavailable"), "Campaign error banner should explain the failure.");
  assert(output.afterRetry.error === null, "Campaign error should clear after retry.");
  assert(output.afterRetry.fetchKey === "campaign-performance:trailing", "Successful retry should cache the fetch key.");
  assert(output.afterRetry.bannerHidden, "Campaign error banner should hide after retry.");
  assert(output.afterRetry.rowCount === 1, "Successful retry should populate campaign rows.");
  assert(output.fetchCallCount === 2, "Cached Campaigns fetch should not make a third request.");
  console.log("Campaign load-error/retry state verified OK.");
}).catch(error => {
  console.error(error);
  process.exit(1);
});
