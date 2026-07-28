const { installFakeDom, loadDashboardScript } = require("./dom_fake");

installFakeDom();

global.fetch = url => {
  if (!String(url).includes("ahj-performance")) {
    return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
  }
  global.__fetchCallCount = (global.__fetchCallCount || 0) + 1;
  if (global.__fetchCallCount === 1) {
    return Promise.resolve({ ok: false, status: 502 });
  }
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve([
      { market: "Fairfax County, VA", campaign: "Solar Reviews", leads: 100, wins: 10, spend: 10000, revenue: 50000, cpw: 1000, revenuePerSpend: 5, leadToWinRate: 0.1, sampleSizeBucket: "Sufficient Sample" }
    ])
  });
};

const script = loadDashboardScript();
const run = new Function(`${script}
return (async () => {
  await ensureAhjRowsLoaded();
  renderAhjLoadError();
  const afterFailure = {
    error: state.ahjLoadError,
    fetchKey: state.ahjRowsFetchKey,
    bannerHidden: document.getElementById("ahjLoadError").classList.contains("hidden"),
    bannerText: document.getElementById("ahjLoadErrorText").textContent
  };

  await ensureAhjRowsLoaded();
  renderAhjLoadError();
  const afterRetry = {
    error: state.ahjLoadError,
    fetchKey: state.ahjRowsFetchKey,
    bannerHidden: document.getElementById("ahjLoadError").classList.contains("hidden"),
    rowCount: state.ahjRows.length
  };

  await ensureAhjRowsLoaded();
  const afterCachedCall = { fetchCallCount: global.__fetchCallCount };

  return { afterFailure, afterRetry, afterCachedCall };
})();`);

run().then(output => {
  function assert(condition, message) {
    if (!condition) {
      console.error(message);
      process.exit(1);
    }
  }

  assert(!!output.afterFailure.error, "Expected ahjLoadError to be set after a failed fetch.");
  assert(output.afterFailure.fetchKey === null, "A failed fetch must not cache the fetch key, or retries would never happen.");
  assert(!output.afterFailure.bannerHidden, "Error banner should be visible after a failed fetch.");
  assert(output.afterFailure.bannerText.includes("AHJ data unavailable"), "Error banner text should explain the AHJ data is unavailable.");

  assert(output.afterRetry.error === null, "Expected ahjLoadError to clear after a successful retry.");
  assert(output.afterRetry.fetchKey === "ahj-performance:trailing", "Expected fetch key to be cached after a successful fetch.");
  assert(output.afterRetry.bannerHidden, "Error banner should be hidden after a successful retry.");
  assert(output.afterRetry.rowCount === 1, "Expected the retried fetch's rows to populate state.ahjRows.");

  assert(output.afterCachedCall.fetchCallCount === 2, "A third call after a successful fetch should not trigger another network request.");

  console.log("AHJ load-error/retry state verified OK.");
}).catch(error => {
  console.error(error);
  process.exit(1);
});
