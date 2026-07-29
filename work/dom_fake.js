const fs = require("fs");

class FakeElement {
  constructor(id = "") {
    this.id = id;
    this.value = "";
    this.innerHTML = "";
    this.textContent = "";
    this.hidden = false;
    this.disabled = false;
    this.clientWidth = 700;
    this.clientHeight = 245;
    this.style = {};
    this.dataset = {};
    this._listeners = new Map();
    this._classes = new Set();
    this.classList = {
      add: name => this._classes.add(name),
      remove: name => this._classes.delete(name),
      toggle: (name, force) => {
        const add = force == null ? !this._classes.has(name) : Boolean(force);
        if (add) this._classes.add(name);
        else this._classes.delete(name);
      },
      contains: name => this._classes.has(name),
    };
  }
  addEventListener(type, callback) {
    if (!this._listeners.has(type)) this._listeners.set(type, []);
    this._listeners.get(type).push(callback);
  }
  dispatchEvent(event) {
    const normalized = event || {};
    normalized.target = normalized.target || this;
    for (const callback of this._listeners.get(normalized.type) || []) callback(normalized);
    return true;
  }
  querySelectorAll() { return []; }
  querySelector() { return null; }
  setAttribute() {}
  focus() {}
  getBoundingClientRect() {
    return { left: 0, top: 0, width: this.clientWidth, height: this.clientHeight };
  }
  getContext() {
    return {
      scale() {}, clearRect() {}, fillText() {}, beginPath() {}, moveTo() {},
      lineTo() {}, stroke() {}, fill() {}, arc() {}, save() {}, restore() {},
      translate() {}, rotate() {},
      set fillStyle(_) {}, set strokeStyle(_) {}, set lineWidth(_) {},
      set lineJoin(_) {}, set font(_) {}, set textAlign(_) {},
    };
  }
}

function installFakeDom() {
  const elements = new Map();
  const getElement = id => {
    if (!elements.has(id)) elements.set(id, new FakeElement(id));
    return elements.get(id);
  };
  const views = ["command", "funnel", "geo", "scenario", "quality"].map(name => getElement(`view-${name}`));
  global.document = {
    getElementById: getElement,
    querySelectorAll(selector) {
      if (selector === ".view") return views;
      return [];
    },
    querySelector() { return null; },
  };
  global.window = {
    devicePixelRatio: 1,
    addEventListener() {},
    requestAnimationFrame(callback) { callback(); },
  };
  global.requestAnimationFrame = callback => callback();
  global.alert = () => {};
  return { getElement };
}

function loadDashboardScript() {
  const html = fs.readFileSync("outputs/marketing_decision_tool.html", "utf8");
  const match = html.match(/<script>([\s\S]*?)<\/script>/);
  if (!match) throw new Error("Dashboard script not found.");
  return match[1];
}

module.exports = { FakeElement, installFakeDom, loadDashboardScript };
