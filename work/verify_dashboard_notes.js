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

console.log("Notes and decision-assistant wiring verified OK.");
