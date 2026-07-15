const fs = require("fs");

class FakeElement {
  constructor(id = "") {
    this.id = id;
    this.value = "";
    this.innerHTML = "";
    this.textContent = "";
    this.disabled = false;
    this.clientWidth = 700;
    this.clientHeight = 280;
    this.firstChild = null;
    this.attributes = {};
    this._classes = new Set();
    this.classList = {
      add: name => this._classes.add(name),
      remove: name => this._classes.delete(name),
      toggle: (name, force) => {
        const shouldAdd = force == null ? !this._classes.has(name) : Boolean(force);
        if (shouldAdd) this._classes.add(name);
        else this._classes.delete(name);
      },
      contains: name => this._classes.has(name)
    };
  }
  addEventListener() {}
  insertAdjacentHTML(_position, html) { this.innerHTML += html; }
  closest() { return null; }
  removeChild() {}
  querySelectorAll() { return []; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] || null; }
}

function installFakeDom(extraIds = []) {
  const elements = new Map();
  function getElement(id) {
    if (!elements.has(id)) elements.set(id, new FakeElement(id));
    return elements.get(id);
  }

  global.document = {
    getElementById: getElement,
    querySelectorAll(selector) {
      if (selector === ".view") return [getElement("overview"), getElement("campaigns")];
      return [];
    },
    querySelector(selector) {
      if (selector.startsWith("#")) return getElement(selector.slice(1));
      return null;
    }
  };
  global.window = {
    addEventListener() {},
    LUMINA_NOTES_API_BASE: "http://fake-notes-api.test",
    google: {
      accounts: {
        id: {
          initialize() {},
          renderButton() {},
          prompt() {}
        }
      }
    }
  };
  global.localStorage = {
    getItem() { return null; },
    setItem() {}
  };

  [
    "appShell", "sideToggle", "campaignBudget", "campaignObjective", "campaignGrain",
    "campaignDetailSelect", "rangeSelect", "regionSelect", "sourceSelect",
    "refreshBqButton", "freshnessTitle", "freshnessMeta",
    "trendExplorerMetric", "trendCompareMode", "trendExplorerChart", "trendSummary",
    "noteDrawer", "noteDrawerBackdrop", "noteDrawerClose", "noteDrawerForm",
    "noteDrawerText", "noteDrawerAuthor", "noteDrawerStatus", "noteDrawerLabel", "noteDrawerView",
    "noteDrawerSigninPrompt", "noteDrawerGoogleSignInButton", "noteDrawerSignInAction",
    "googleSignInButton", "signedInAs",
    ...extraIds
  ].forEach(id => getElement(id));

  return { getElement };
}

function loadDashboardScript() {
  const html = fs.readFileSync("outputs/marketing_decision_tool.html", "utf8");
  return html.match(/<script>([\s\S]*)<\/script>/)[1];
}

module.exports = { FakeElement, installFakeDom, loadDashboardScript };
