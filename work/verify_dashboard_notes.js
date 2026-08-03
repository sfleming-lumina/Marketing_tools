const fs = require("fs");

const html = fs.readFileSync("outputs/marketing_decision_tool.html", "utf8");

function assert(condition, message) {
  if (!condition) {
    console.error(message);
    process.exit(1);
  }
}

assert(html.includes('id="notesDrawer"'), "Notes drawer is missing.");
assert(html.includes('id="noteText"'), "Note input is missing.");
assert(html.includes('id="saveNote"'), "Save-note action is missing.");
assert(html.includes('fetchJson("/api/notes"'), "Notes POST wiring is missing.");
assert(html.includes('fetchJson(`/api/notes?view='), "View-scoped note loading is missing.");
assert(html.includes('feedback_type:"decision"'), "Decision note metadata is missing.");
assert(html.includes('context:assistantContext()'), "Notes do not include the current decision context.");
assert(html.includes('id="assistantDrawer"') && html.includes('id="askAssistant"'), "Assistant drawer wiring is missing.");
assert(html.includes('fetchJson("/api/ask-claude"'), "Assistant API wiring is missing.");
assert(html.includes('context_contract:"marketing-decision-slice-v2"') && html.includes("monthly_cohorts") && html.includes("campaign_breakdown"), "Assistant does not carry the current data slice contract.");
assert(html.includes("allowDataApiFallback:true"), "Assistant data API fallback is not enabled.");
assert(html.includes('data-scenario-money="${d.key}"'), "Scenario budget and CPL dollar inputs are missing.");
assert(html.includes('/api/marketing-decisions/archive') && html.includes('id="showArchivedDecisions"'), "Decision archive controls are missing.");
assert(html.includes('id="geoEvidenceChoice"') && html.includes('activeDecisionEvidence') && html.includes('scrollIntoView'), "Geography evidence selection or visible confirmation is missing.");
assert(html.includes('id="presentationSectionList"') && html.includes('data-presentation-section="${section.id}"'), "Selectable presentation elements are missing.");
assert(html.includes('value:"region:Maryland"') && html.includes('value:"region:Pennsylvania"') && html.includes('value:`state:${code}`'), "Presentation scope does not cover MD Ops, PA Ops, and physical states.");

console.log("Notes and decision-assistant wiring verified OK.");
