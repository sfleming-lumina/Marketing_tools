const { installFakeDom, loadDashboardScript } = require("./dom_fake");

installFakeDom(["feedbackFilter", "feedbackTable"]);
global.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve([]) });

const script = loadDashboardScript();
const run = new Function(`${script}
allNotes = [
  { note_id: "1", created_at: "2026-07-15T10:00:00Z", author_name: "Jane", view: "campaigns", element_key: "campaign:Paid Search:Google Nonbrand Search", element_label: "Google Nonbrand Search", note_text: "Great campaign card", context: {} },
  { note_id: "2", created_at: "2026-07-15T11:00:00Z", author_name: "Sam", view: "overview", element_key: "metric:projected-revenue", element_label: "Projected revenue", note_text: "Confusing metric", context: {} }
];
state.view = "campaigns";
renderCampaignPlanner();
state.view = "overview";
renderMetrics();
renderObjects();
return {
  cards: document.getElementById("campaignCards").innerHTML,
  recommendations: document.getElementById("campaignRecommendations").innerHTML,
  metrics: document.getElementById("metrics").innerHTML,
  objects: document.getElementById("objectTable").innerHTML
};`);

const output = run();

function assert(condition, message) {
  if (!condition) {
    console.error(message);
    process.exit(1);
  }
}

assert(output.cards.includes('data-note-key="campaign:Paid Search:Google Nonbrand Search"'), "Campaign card is missing its note chip key.");
assert(output.cards.includes('<span class="note-chip-count">1</span>'), "Campaign card note badge should show a count of 1.");
assert(output.recommendations.includes('data-note-key="campaign:Paid Search:Google Nonbrand Search"'), "Campaign recommendation should reuse the same entity key as the campaign card.");
assert(output.metrics.includes('data-note-key="metric:projected-revenue"'), "Projected revenue metric is missing its note chip key.");
assert(output.objects.includes('data-note-key="object:analytics_rpt.rpt_marketing_lead_cohort_performance"'), "Object row is missing its note chip key.");

console.log("Dashboard notes key wiring verified OK.");
