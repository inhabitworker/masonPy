/** Pure component contracts; no real DOM, browser, npm or downloaded test tools. */
import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

// These pure modules have no imports. Data URLs avoid imposing Node package-type
// rules (or a package.json) on browser-native .js modules.
async function load(name) {
  return import(await moduleURL(name));
}
async function moduleURL(name) {
  let source = await readFile(new URL(`../src/masonpy/app/static/${name}.js`, import.meta.url), "utf8");
  for (const match of [...source.matchAll(/from "\.\/([^"/]+)\.js"/g)]) {
    source = source.replace(match[0], `from "${await moduleURL(match[1])}"`);
  }
  return `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;
}
const { ApiClient } = await load("api");
const { Tabs } = await load("tabs");
const { Playback } = await load("playback");
const { WallViewer2D } = await load("viewer2d");

test("JSON transport preserves payloads and reports backend errors", async () => {
  const original = globalThis.fetch;
  const requests = [];
  try {
    globalThis.fetch = async (path, options) => {
      requests.push([path, options]);
      return { ok: true, json: async () => ({ stone: 7 }) };
    };
    const api = new ApiClient();
    assert.deepEqual(await api.post("/api/step", { seed: 3 }), { stone: 7 });
    assert.equal(JSON.parse(requests[0][1].body).seed, 3);
    assert.equal(requests[0][1].method, "POST");
    globalThis.fetch = async () => ({ ok: false, json: async () => ({ error: "invalid course" }) });
    await assert.rejects(api.get("/api/state"), /invalid course/);
  } finally {
    globalThis.fetch = original;
  }
});

test("tabs keep one keyboard-focusable selection and support directional keys", () => {
  class Button {
    constructor() { this.attributes = {}; this.events = {}; }
    addEventListener(name, action) { this.events[name] = action; }
    setAttribute(key, value) { this.attributes[key] = String(value); }
    focus() { this.focused = true; }
  }
  const buttons = { events: new Button(), info: new Button() };
  let selected;
  const tabs = new Tabs(buttons, name => { selected = name; });
  tabs.select("events");
  buttons.events.events.keydown({ key: "ArrowRight", preventDefault() {} });
  assert.equal(selected, "info");
  assert.equal(buttons.info.tabIndex, 0);
  assert.equal(buttons.events.attributes["aria-selected"], "false");
  buttons.info.events.keydown({ key: "Home", preventDefault() {} });
  assert.equal(selected, "events");
});

test("playback only emits prefix counts, with deterministic forward/reverse timing", () => {
  const pending = new Map();
  let id = 0;
  globalThis.requestAnimationFrame = callback => { pending.set(++id, callback); return id; };
  globalThis.cancelAnimationFrame = key => pending.delete(key);
  try {
    for (const [direction, expected] of [[1, [0, 2, 3]], [-1, [3, 1, 0]]]) {
      const player = new Playback();
      const counts = [];
      let completed = false;
      player.play(3, direction, count => counts.push(count), () => { completed = true; });
      for (const time of [0, 1600, 3200]) {
        const [key, action] = pending.entries().next().value;
        pending.delete(key);
        action(time);
      }
      assert.deepEqual(counts, expected);
      assert.equal(completed, true);
      assert.equal(player.frame, null);
    }
    const player = new Playback();
    player.play(2, 1, () => assert.fail("cancelled playback ran"), () => {});
    player.cancel();
    assert.equal(pending.size, 0);
  } finally {
    delete globalThis.requestAnimationFrame;
    delete globalThis.cancelAnimationFrame;
  }
});

test("2D mapping folds pieces without changing identity and zoom stops at padded fit", () => {
  const viewer = Object.create(WallViewer2D.prototype);
  viewer.wrapDisplay = true;
  viewer.viewAnimation = null;
  viewer.svg = { getBoundingClientRect: () => ({ width: 800, height: 400 }) };
  viewer.applyViewBox = () => {};
  const wall = { width: 52, height: 30, stones: [] };
  viewer.configureView(wall);
  const centre = [viewer.viewState.centerX, viewer.viewState.centerY];
  const fit = viewer.currentViewBox();
  viewer.setZoom(4, { x: 0, y: 0 });
  viewer.viewState.centerX = -100;
  viewer.viewState.centerY = 100;
  for (let i = 0; i < 10; i++) viewer.setZoom(viewer.viewState.zoom / 1.35);
  assert.equal(viewer.viewState.zoom, 1);
  assert.deepEqual([viewer.viewState.centerX, viewer.viewState.centerY], centre);
  assert.deepEqual(viewer.currentViewBox(), fit);
  assert.ok(fit.width > wall.width && fit.height > wall.height);
  const stone = { id: 9, x: -2, width: 4 };
  assert.deepEqual(viewer.stonePieces(stone, wall), [{ x: 50, width: 2 }, { x: 0, width: 2 }]);
  assert.equal(stone.width, 4);
  assert.equal(stone.id, 9);
});

const { WorkbenchApp } = await load("app");

test("playback of an incomplete wall never generates or applies parameter drafts", () => {
  const app = Object.create(WorkbenchApp.prototype);
  const before = { wall: { stones: [{ id: 0 }, { id: 1 }] }, complete: false };
  app.state = before;
  app.parameters = { parametersAreDirty: () => true };
  const messages = [], counts = [];
  app.stages = { active: "wall", busy: false, message: message => messages.push(message) };
  app.api = { post: () => assert.fail("playback must not mutate the backend") };
  app.status = {};
  app.reveal = count => counts.push(count);
  app.playback = { cancel() {}, play(total, direction, reveal, done) {
    assert.equal(total, 2);
    reveal(0); reveal(2); done();
  } };
  app.play(1);
  assert.equal(app.state, before);
  assert.deepEqual(counts, [0, 2]);
  assert.match(messages[0], /no new generation/);
  assert.match(messages.at(-1), /Draft parameters remain unapplied/);
});

test("Generate on a completed wall reports reuse and leaves drafts unapplied", async () => {
  const app = Object.create(WorkbenchApp.prototype);
  const state = { wall_revision: 5, wall: { stones: [{ id: 0 }] }, complete: true };
  app.state = state;
  app.parameters = { parametersAreDirty: () => true };
  app.playback = { cancel() {} };
  app.status = {};
  const messages = [], calls = [];
  app.stages = { busy: false, setBusy() {}, message: message => messages.push(message) };
  app.api = { post: async (path, payload) => { calls.push([path, payload]); return state; } };
  app.accept = async result => { app.state = result; };
  app.updateWallActions = () => {};
  await app.mutate("generate");
  assert.deepEqual(calls, [["/api/generate", {}]]);
  assert.match(messages[0], /No new stones generated/);
  assert.match(messages[0], /Draft parameters were not used/);
});

test("stage entry changes inspection, stops playback, and invokes the refresh coordinator", () => {
  const app = Object.create(WorkbenchApp.prototype);
  const state = { wall: { stones: [] }, shape: { result: { source: { stones: [{ id: 4 }] } } } };
  app.state = state;
  app.stages = { active: "shape" };
  let cancelled = false, drawn = false;
  app.playback = { cancel() { cancelled = true; } };
  app.api = { post: () => assert.fail("navigation must use the refresh coordinator"), get: () => assert.fail("no direct fetch on navigation") };
  let refreshed;
  app.pipeline = { ensure: async stage => { refreshed = stage; return false; } };
  app.projection = { select: active => assert.equal(active, false) };
  app.draw = () => { drawn = true; };
  app.switchStage();
  assert.equal(app.state, state);
  assert.equal(app.visibleCount, 1);
  assert.equal(cancelled && drawn, true);
  assert.equal(refreshed, "shape");
});

const { LiveUpdates } = await load("live");
const { ProjectionPanel } = await load("projection");

test("downstream playback follows its own retained source, never the newer wall", () => {
  for (const stage of ["shape", "3d"]) {
    const app = Object.create(WorkbenchApp.prototype);
    const source = { stones: [{ id: 3 }, { id: 5 }, { id: 8 }] };
    app.state = { wall: { stones: [{ id: 99 }] },
      shape: { result: { source, joint_width: .2 } }, build: { settings: { depth: .5 } } };
    app.meshSnapshot = { shape: { source } };
    app.stages = { active: stage, busy: false, pending: false,
      payload: () => ({ joint_width: .2 }), settings: () => ({ depth: .5 }), message() {} };
    app.api = { post: () => assert.fail("playback must not process") };
    app.status = {};
    const counts = [];
    app.reveal = count => counts.push(count);
    app.playback = { cancel() {}, play(total, direction, reveal, done) {
      assert.equal(total, 3); reveal(0); reveal(3); done();
    } };
    app.play(1);
    assert.deepEqual(counts, [0, 3]);
  }
});

test("3D playback updates visibility in place without rebuilding buffers", () => {
  const projection = Object.create(ProjectionPanel.prototype);
  const source = { stones: [{ id: 1 }, { id: 2 }] };
  projection.snapshot = { geometry: {}, shape: { source } };
  projection.active = true;
  const visible = [];
  projection.viewer = { sync: (...args) => visible.push(args), rebuild: () => assert.fail("no geometry rebuild") };
  projection.updateVisibility(1, 1);
  assert.deepEqual(visible, [[source, 1, 1, false]]);
});

test("live edits debounce and coalesce into one serial latest-value request", async () => {
  const realSet = globalThis.setTimeout, realClear = globalThis.clearTimeout;
  const timers = new Map();
  let id = 0;
  globalThis.setTimeout = callback => { timers.set(++id, callback); return id; };
  globalThis.clearTimeout = key => timers.delete(key);
  const runTimer = () => { const [key, action] = timers.entries().next().value; timers.delete(key); action(); };
  try {
    const calls = [], completions = [];
    let allowed = true;
    const updates = new LiveUpdates((action, payload) => {
      calls.push([action, payload]);
      return new Promise(resolve => completions.push(resolve));
    }, () => allowed, () => {}, error => assert.fail(error.message));
    updates.schedule("build", { depth: .1 });
    updates.schedule("build", { depth: .2 });
    assert.equal(timers.size, 1);
    runTimer();
    assert.deepEqual(calls, [["build", { depth: .2 }]]);
    updates.schedule("build", { depth: .3 });
    runTimer(); // While the previous request is still running, no parallel call.
    updates.schedule("build", { depth: .4 });
    assert.equal(calls.length, 1);
    completions.shift()();
    await Promise.resolve();
    runTimer();
    assert.deepEqual(calls[1], ["build", { depth: .4 }]);
    completions.shift()();
    await Promise.resolve();
    updates.schedule("shape", { joint_width: .5 });
    updates.cancel();
    assert.equal(timers.size, 0);
    updates.schedule("build", { depth: .9 });
    allowed = false; // E.g. source invalidated or Live disabled before the timer fired.
    runTimer();
    assert.equal(calls.length, 2);
  } finally { globalThis.setTimeout = realSet; globalThis.clearTimeout = realClear; }
});

test("binary downloads preserve payload and filename and expose backend validation errors", async () => {
  const original = globalThis.fetch;
  try {
    const blob = new Blob([new Uint8Array([0, 1, 255])]);
    globalThis.fetch = async (path, options) => {
      assert.equal(path, "/api/export");
      assert.deepEqual(JSON.parse(options.body), { stage: "3d", scale: 2, revision: 7 });
      return { ok: true, headers: new Headers({ "Content-Disposition": 'attachment; filename="wall.stl"' }), blob: async () => blob };
    };
    const api = new ApiClient();
    const result = await api.download({ stage: "3d", scale: 2, revision: 7 });
    assert.equal(result.blob, blob);
    assert.equal(result.filename, "wall.stl");
    globalThis.fetch = async () => ({ ok: false, json: async () => ({ error: "Build with positive depth" }) });
    await assert.rejects(api.download({}), /positive depth/);
  } finally { globalThis.fetch = original; }
});

const { StagePanel } = await load("stages");
test("header exports gate SVG by its 2D source and STL independently of the active tab", () => {
  const original = globalThis.document;
  globalThis.document = { querySelector: () => ({checkValidity: () => true}) };
  try {
    const panel = Object.create(StagePanel.prototype);
    panel.active = "wall";
    panel.state = { wall:{stones:[]}, shape:{current:false}, build:{current:false} };
    assert.match(panel.exportAvailability(panel.svgStage()), /Place or generate/);
    panel.state.wall.stones.push({});
    assert.equal(panel.exportAvailability(panel.svgStage()), "");
    assert.match(panel.exportAvailability("3d"), /Build 3D/);
    panel.state.shape.current = true;
    panel.state.build = {current:true,settings:{depth:0.4}};
    assert.equal(panel.exportAvailability("3d"), "");
    panel.active = "3d";
    assert.equal(panel.svgStage(), "shape");
    assert.equal(panel.exportAvailability(panel.svgStage()), "");
    panel.state.shape.current = false;
    assert.match(panel.exportAvailability(panel.svgStage()), /Apply Shape/);
    panel.pending = true;
    assert.match(panel.exportAvailability("3d"), /Wait/);
  } finally { globalThis.document = original; }
});

test("STL export permits closed core builds while retaining depth and stale-source gates", () => {
  const original = globalThis.document;
  globalThis.document = { querySelector: selector => {
    assert.equal(selector, "#export-scale");
    return { checkValidity: () => true };
  } };
  try {
    const panel = Object.create(StagePanel.prototype);
    panel.active = "3d";
    panel.state = { build: { current: true, settings: { depth: .5, mode: "projected", primitive: "solid" } } };
    assert.equal(panel.exportAvailability(), "");
    panel.state.build.settings.primitive = "tube";
    assert.equal(panel.exportAvailability(), "");
    panel.state.build.settings.depth = 0;
    assert.match(panel.exportAvailability(), /positive stone depth/);
    panel.state.build.current = false;
    assert.match(panel.exportAvailability(), /current Shape/);
  } finally { globalThis.document = original; }
});

test("Shape drafts retain fractional parameters and an independent integer seed", () => {
  const original = globalThis.document;
  const values = { "#joint-width": "0.125", "#shape-distortion": "0.37", "#shape-seed": "12", "#variation-scale": "4.5", "#corner-softening":"0.6" };
  globalThis.document = { querySelector: selector => ({ value: values[selector] }) };
  try {
    const panel = Object.create(StagePanel.prototype);
    assert.deepEqual(panel.payload("shape"), { joint_width: .125, distortion: .37, seed: 12, variation_scale: 4.5, corner_softening: .6 });
  } finally { globalThis.document = original; }
});

test("live contour bounds include floating overhangs while preserving user pan and zoom", () => {
  const viewer = Object.create(WallViewer2D.prototype);
  viewer.wrapDisplay = false;
  viewer.viewAnimation = null;
  viewer.svg = { getBoundingClientRect: () => ({ width: 800, height: 400 }) };
  viewer.applyViewBox = () => {};
  const wall = { width: 12, height: 8, stones: [{ id: 0, x: 0, width: 4 }] };
  viewer.configureView(wall);
  viewer.setZoom(3);
  const position = [viewer.viewState.centerX, viewer.viewState.centerY];
  viewer.contours = new Map([[0, [[-.5,0],[4,0],[4,2],[-.25,2]]]]);
  viewer.configureView(wall);
  assert.equal(viewer.viewState.zoom, 3);
  assert.deepEqual([viewer.viewState.centerX, viewer.viewState.centerY], position);
  assert.ok(viewer.viewState.extent.x < -2);
  viewer.wrapDisplay = true;
  viewer.configureView(wall);
  assert.equal(viewer.viewState.extent.x, -2);
});

const { DetailsPanel } = await load("details");
const { WallDiagnostics } = await load("diagnostics");

test("transport errors replace browser-specific strings while preserving their diagnostic causes", async () => {
  const originalFetch = globalThis.fetch, originalError = console.error;
  const causes = [];
  console.error = (...args) => causes.push(args);
  try {
    const api = new ApiClient();
    globalThis.fetch = async () => { throw new TypeError("Load failed"); };
    await assert.rejects(api.post("/api/generate"), error =>
      /Could not contact.*POST \/api\/generate/.test(error.message) && !error.message.includes("Load failed"));
    globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => {
      throw new SyntaxError("The string did not match the expected pattern.");
    } });
    await assert.rejects(api.get("/api/state"), error =>
      /Could not read.*\/api\/state/.test(error.message) && !error.message.includes("expected pattern"));
    globalThis.fetch = async () => ({ ok: true, json: async () => "not an object" });
    await assert.rejects(api.get("/api/state"), /expected a JSON object/);
    assert.equal(causes.length, 2);
    assert.equal(causes[0][1].message, "Load failed");
  } finally { globalThis.fetch = originalFetch; console.error = originalError; }
});

test("successful generation stays acknowledged when only its preview fails", async () => {
  const app = Object.create(WorkbenchApp.prototype);
  app.state = { wall_revision: 1, wall: { stones: [] } };
  const result = { wall_revision: 2, wall: { stones: [{ id: 0 }] }, complete: true };
  app.parameters = { parametersAreDirty: () => false };
  app.playback = { cancel() {} };
  app.details = { beginGeneration() {} };
  const messages = [];
  app.stages = { busy: false, setBusy() {}, message: (...args) => messages.push(args) };
  app.api = { post: async () => result, get: async () => result };
  app.accept = async state => { app.state = state; throw new Error("3D preview unavailable"); };
  app.updateWallActions = () => {};
  const originalError = console.error;
  console.error = () => {};
  try { await app.mutate("generate"); }
  finally { console.error = originalError; }
  assert.equal(app.state, result);
  assert.match(messages.at(-1)[0], /Placed 1 new stone/);
  assert.match(messages.at(-1)[0], /preview could not be refreshed/);
  assert.equal(messages.at(-1)[1], true);
});

test("an interrupted action response can recover its confirmed generation result", async () => {
  const app = Object.create(WorkbenchApp.prototype);
  app.state = { wall_revision: 1, wall: { stones: [] } };
  const result = { wall_revision: 2, wall: { stones: [{ id: 0 }] }, complete: true };
  app.parameters = { parametersAreDirty: () => false };
  app.playback = { cancel() {} };
  const messages = [];
  app.stages = { busy: false, setBusy() {}, message: (...args) => messages.push(args) };
  app.api = { post: async () => { throw new Error("Response interrupted"); }, get: async () => result };
  app.accept = async state => { app.state = state; };
  app.updateWallActions = () => {};
  const originalError = console.error;
  console.error = () => {};
  try { await app.mutate("generate"); }
  finally { console.error = originalError; }
  assert.match(messages.at(-1)[0], /Placed 1 new stone.*Current state recovered/);
  assert.equal(messages.at(-1)[1], false);
});

test("background overlay errors remain beside diagnostics; explicit reports use action feedback", async () => {
  const originalDocument = globalThis.document;
  const summary = { textContent: "" };
  const controls = { "#show-seams": { checked: true }, "#show-horizontal-joints": { checked: false },
    "#logical-wrap": { checked: true }, "#seam-summary": summary };
  globalThis.document = { querySelector: selector => controls[selector] };
  try {
    const diagnostics = Object.create(WallDiagnostics.prototype);
    diagnostics.revision = 0;
    diagnostics.viewer = { svg: { querySelectorAll: () => [] } };
    diagnostics.snapshot = () => ({ state: { wall: { stones: [] } }, visibleCount: 0 });
    diagnostics.api = { post: async () => { throw new Error("Connection interrupted"); } };
    const errors = [];
    diagnostics.onError = message => errors.push(message);
    await diagnostics.refresh();
    assert.match(summary.textContent, /Seam diagnostics unavailable/);
    assert.equal(errors.length, 0);
    await diagnostics.refresh(true);
    assert.equal(errors.length, 1);
    assert.match(errors[0], /Seam diagnostics unavailable/);
  } finally { globalThis.document = originalDocument; }
});

test("event following waits for expanded text layout, preserves manual inspection, and resumes on generation", () => {
  const originalRequest = globalThis.requestAnimationFrame, originalCancel = globalThis.cancelAnimationFrame;
  const frames = new Map();
  let frameId = 0;
  globalThis.requestAnimationFrame = action => { frames.set(++frameId, action); return frameId; };
  globalThis.cancelAnimationFrame = id => frames.delete(id);
  const flush = () => { for (const [id, action] of frames) { frames.delete(id); action(); } };
  try {
    const descriptions = [0, 1].map(id => ({ textContent: "", dataset: { summary: `Stone ${id}`, full: "A long explanation. ".repeat(30) } }));
    const items = descriptions.map((description, id) => ({ dataset: { stoneId: String(id) },
      classList: { toggle() {} }, querySelector: () => description }));
    let top = 0;
    const events = { hidden: false, clientHeight: 100,
      get scrollHeight() { return 100 + descriptions.reduce((sum, d) => sum + d.textContent.length, 0); },
      get scrollTop() { return top; },
      set scrollTop(value) { top = Math.max(0, Math.min(value, this.scrollHeight - this.clientHeight)); },
      querySelectorAll: () => items };
    const panel = Object.create(DetailsPanel.prototype);
    Object.assign(panel, { eventList: events, followLatest: true, scrollFrame: null, refreshInfo() {} });
    panel.prepareEvents("wall");
    panel.setSelection(1, false);
    assert.equal(top, 0);
    flush();
    assert.equal(top, events.scrollHeight - events.clientHeight);
    events.scrollTop = 30;
    panel.recordScroll();
    assert.equal(panel.followLatest, false);
    panel.prepareEvents("wall");
    panel.setSelection(0, false);
    flush();
    assert.equal(top, 30);
    events.hidden = true;
    panel.setSelection(1, false);
    flush();
    events.hidden = false;
    panel.setSelection(1, false);
    flush();
    assert.equal(top, 30);
    panel.beginGeneration();
    panel.prepareEvents("wall");
    panel.setSelection(1, false);
    flush();
    assert.equal(top, events.scrollHeight - events.clientHeight);
  } finally { globalThis.requestAnimationFrame = originalRequest; globalThis.cancelAnimationFrame = originalCancel; }
});

test("fresh 3D controls use shared defaults while applied builds retain their settings", () => {
  const original = globalThis.document;
  const controls = Object.fromEntries(["projection-mode", "projection-roundness", "projection-resolution", "stone-depth",
    "projection-primitive", "tube-thickness", "depth-variation", "edge-bevel", "detail-seed"].map(id => [`#${id}`, { value: "" }]));
  globalThis.document = { querySelector: selector => controls[selector] };
  const defaults = { mode: "projected", roundness: .25, resolution: 8, depth: .25, primitive: "tube", tube_thickness: 1, depth_variation:0, bevel:0, detail_seed:1 };
  try {
    for (const settings of [null, { ...defaults, mode: "flat", primitive: "none", depth: .5 }]) {
      const panel = Object.create(StagePanel.prototype);
      panel.update = () => {};
      panel.render({ shape: {}, build: { settings, defaults } });
      assert.deepEqual(panel.settings(), settings ?? defaults);
    }
  } finally { globalThis.document = original; }
});

test("an interrupted binary response reports a retryable export transfer error", async () => {
  const originalFetch = globalThis.fetch, originalError = console.error;
  console.error = () => {};
  try {
    globalThis.fetch = async () => ({ ok: true, headers: new Headers(), blob: async () => { throw new TypeError("Load failed"); } });
    await assert.rejects(new ApiClient().download({}), error =>
      /export download was interrupted/.test(error.message) && !error.message.includes("Load failed"));
  } finally { globalThis.fetch = originalFetch; console.error = originalError; }
});

const { StageRefresh } = await load("pipeline");
const shapeDefaults = { joint_width: .2, distortion: 0, seed: 1, variation_scale: 6 };
const buildDefaults = { mode: "projected", roundness: .25, resolution: 8, depth: .25, primitive: "tube", tube_thickness: 1, depth_variation:0, bevel:0, detail_seed:1 };
function sourceState(revision = 1) {
  return { wall_revision: revision, wall: { stones: [{ id: revision }] },
    shape: { revision: 0, current: false, result: null, defaults: { ...shapeDefaults } },
    build: { revision: 0, current: false, present: false, settings: null, defaults: { ...buildDefaults } } };
}
function applyStage(state, action, payload) {
  const { source_revision, ...settings } = payload;
  if (action === "shape") {
    assert.equal(source_revision, state.wall_revision);
    state.shape = { ...state.shape, revision: state.shape.revision + 1, current: true,
      result: { settings, source: state.wall } };
    state.build.current = false;
  } else {
    assert.equal(action, "build");
    assert.equal(source_revision, state.shape.revision);
    state.build = { ...state.build, revision: state.build.revision + 1, current: true,
      present: true, source_revision, settings };
  }
  return true;
}

test("first 3D entry refreshes Shape then 3D, reuses current snapshots, and never generates", async () => {
  const state = sourceState();
  const originalWall = structuredClone(state.wall);
  const calls = [];
  const refresh = new StageRefresh(() => state, stage => stage === "shape" ? shapeDefaults : buildDefaults,
    async (action, payload, options) => { calls.push(action); assert.equal(options.automatic, true); return applyStage(state, action, payload); });
  assert.equal(await refresh.ensure("3d"), true);
  assert.deepEqual(calls, ["shape", "build"]);
  assert.equal(await refresh.ensure("3d"), true);
  assert.deepEqual(calls, ["shape", "build"]);
  assert.deepEqual(state.wall, originalWall);
  state.wall_revision++;
  state.wall.stones.push({ id: 9 });
  state.complete = false;
  state.failure = { message: "Stopped after accepted placements" };
  state.shape.current = state.build.current = false;
  assert.equal(await refresh.ensure("shape"), true);
  assert.deepEqual(calls, ["shape", "build", "shape"]);
  assert.equal(await refresh.ensure("3d"), true);
  assert.deepEqual(calls, ["shape", "build", "shape", "build"]);
});

test("empty walls do no automatic work; a failed Shape pass stops the 3D chain", async () => {
  const state = sourceState();
  state.wall.stones = [];
  const calls = [];
  const refresh = new StageRefresh(() => state, stage => stage === "shape" ? shapeDefaults : buildDefaults,
    async action => { calls.push(action); return false; });
  assert.equal(await refresh.ensure("3d"), false);
  assert.deepEqual(calls, []);
  state.wall.stones = [{ id: 0 }];
  state.shape.result = { settings: shapeDefaults, source: { stones: [{ id: 99 }] } };
  const previous = state.shape.result;
  assert.equal(await refresh.ensure("3d"), false);
  assert.deepEqual(calls, ["shape"]);
  assert.equal(state.shape.result, previous);
});

test("duplicate visits coalesce and a changed Wall cancels the rest of an old refresh", async () => {
  let state = sourceState();
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  const calls = [];
  const refresh = new StageRefresh(() => state, stage => stage === "shape" ? shapeDefaults : buildDefaults,
    async (action, payload) => {
      calls.push(action);
      await gate;
      if (payload.source_revision !== state.wall_revision) return false;
      return applyStage(state, action, payload);
    });
  const first = refresh.ensure("3d");
  assert.equal(refresh.ensure("3d"), first);
  state = sourceState(2);
  release();
  assert.equal(await first, false);
  assert.deepEqual(calls, ["shape"]);
  assert.equal(state.shape.result, null);
});

test("leaving a stage cancels its queued downstream build while retaining a completed Shape", async () => {
  const state = sourceState();
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  const calls = [];
  const refresh = new StageRefresh(() => state, stage => stage === "shape" ? shapeDefaults : buildDefaults,
    async (action, payload) => { calls.push(action); await gate; return applyStage(state, action, payload); });
  const first = refresh.ensure("3d");
  await refresh.ensure("wall");
  release();
  assert.equal(await first, false);
  assert.deepEqual(calls, ["shape"]);
  assert.equal(state.shape.current, true);
  assert.equal(await refresh.ensure("3d"), true);
  assert.deepEqual(calls, ["shape", "build"]);
});

test("manual mode and invalid drafts refresh applied settings without overwriting inputs", () => {
  const panel = Object.create(StagePanel.prototype);
  const state = sourceState();
  const draft = { ...shapeDefaults, joint_width: .9 };
  panel.state = state;
  panel.payload = () => draft;
  panel.liveEnabled = () => false;
  panel.valid = () => true;
  assert.deepEqual(panel.automaticSettings("shape"), shapeDefaults);
  state.shape.result = { settings: { ...shapeDefaults, joint_width: .3 } };
  assert.equal(panel.automaticSettings("shape").joint_width, .3);
  assert.equal(draft.joint_width, .9);
  panel.liveEnabled = () => true;
  assert.equal(panel.automaticSettings("shape").joint_width, .9);
  panel.valid = () => false;
  assert.equal(panel.automaticSettings("shape").joint_width, .3);
  panel.active = "shape";
  assert.match(panel.staleNote(), /previous Shape result \(stale\)/);
});

test("late mesh responses and old state snapshots cannot overwrite a newer displayed wall", async () => {
  const app = Object.create(WorkbenchApp.prototype);
  const old = sourceState(1), latest = sourceState(2);
  for (const [state, revision] of [[old, 1], [latest, 2]]) {
    state.shape = { revision, current: true, result: {} };
    state.build = { revision, source_revision: revision, current: true, present: true };
  }
  const oldMesh = { revision: 1, source_revision: 1, wall_revision: 1, shape: { source: old.wall } };
  const newMesh = { revision: 2, source_revision: 2, wall_revision: 2, shape: { source: latest.wall } };
  let release;
  const pending = new Promise(resolve => { release = resolve; });
  let calls = 0;
  app.api = { get: async () => ++calls === 1 ? pending : newMesh };
  app.stages = { active: "wall" };
  const draws = [];
  app.draw = () => draws.push(app.state.wall_revision);
  const earlier = app.accept(old);
  assert.equal(await app.accept(latest), true);
  release(oldMesh);
  assert.equal(await earlier, false);
  assert.equal(app.state, latest);
  assert.equal(app.meshSnapshot, newMesh);
  assert.deepEqual(draws, [2]);
  assert.equal(await app.accept(old), false);
});

test("mesh provenance mismatches are rejected without relabelling old buffers", async () => {
  const app = Object.create(WorkbenchApp.prototype);
  const state = sourceState(2);
  state.shape.revision = 2;
  state.build = { revision: 2, source_revision: 2, current: true, present: true };
  const previous = { geometry: "old" };
  app.meshSnapshot = previous;
  app.api = { get: async () => ({ revision: 3, source_revision: 3, wall_revision: 2 }) };
  await assert.rejects(app.accept(state), /3D source changed/);
  assert.equal(app.meshSnapshot, previous);
  assert.notEqual(app.meshRevision, 2);
});

test("a queued visit to a replacement wall processes only that wall's downstream chain", async () => {
  let state = sourceState();
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  const calls = [];
  const refresh = new StageRefresh(() => state, stage => stage === "shape" ? shapeDefaults : buildDefaults,
    async (action, payload) => {
      calls.push([action, payload.source_revision]);
      if (calls.length === 1) await gate;
      const expected = action === "shape" ? state.wall_revision : state.shape.revision;
      if (payload.source_revision !== expected) return false;
      return applyStage(state, action, payload);
    });
  const old = refresh.ensure("3d");
  state = sourceState(2);
  const latest = refresh.ensure("3d");
  release();
  assert.equal(await old, false);
  assert.equal(await latest, true);
  assert.deepEqual(calls, [["shape", 1], ["shape", 2], ["build", 1]]);
  assert.equal(state.wall_revision, 2);
  assert.equal(state.build.current, true);
});

test("an explicit backend rejection is not mistaken for success when another source changed", async () => {
  const app = Object.create(WorkbenchApp.prototype);
  app.state = sourceState();
  const latest = sourceState(2);
  latest.shape.revision = 1;
  const rejection = new Error("Wall changed before processing");
  rejection.rejected = true;
  app.parameters = { parametersAreDirty: () => false };
  app.playback = { cancel() {} };
  const messages = [];
  app.stages = { busy: false, setBusy() {}, message: (...args) => messages.push(args) };
  app.api = { post: async () => { throw rejection; }, get: async () => latest };
  app.accept = async state => { app.state = state; return true; };
  app.updateWallActions = () => {};
  const originalError = console.error;
  console.error = () => {};
  try { assert.equal(await app.mutate("shape", shapeDefaults), false); }
  finally { console.error = originalError; }
  assert.equal(app.state, latest);
  assert.match(messages.at(-1)[0], /Apply Shape: Wall changed before processing/);
  assert.equal(messages.at(-1)[1], true);
});

const { WallLibrary } = await load("library");

test("JSON loading captures its source before file reading and rejects bad files locally", async () => {
  const library = Object.create(WallLibrary.prototype);
  library.state = { wall_revision: 5 };
  library.input = { value: "selected.json" };
  const calls = [], errors = [];
  library.onChange = async (...args) => calls.push(args);
  library.onError = message => errors.push(message);
  let release;
  const text = new Promise(resolve => { release = resolve; });
  const pending = library.loadFile({ size: 50, text: () => text });
  library.state = { wall_revision: 6 };
  release('{"wall": {"width": 24}}');
  await pending;
  assert.deepEqual(calls, [["load", {record: {wall: {width:24}}, source_revision:5}]]);
  assert.equal(library.input.value, "");
  for (const text of ["not JSON", "[]", "null"]) {
    await library.loadFile({size: 5, text: async () => text});
  }
  await library.loadFile({size: 33 * 1024 * 1024, text: async () => { throw Error("must not read"); }});
  assert.equal(calls.length, 1);
  assert.equal(errors.length, 4);
  assert.match(errors.at(-1), /32 MiB/);
});

test("config loading restores parameters without processing; history refreshes the inspected stage", async () => {
  for (const action of ["load", "history"]) {
    const app = Object.create(WorkbenchApp.prototype);
    const restored = sourceState(2), calls = [];
    app.state = sourceState(1);
    app.parameters = { parametersAreDirty: () => true, restore: state => calls.push(["controls", state.wall_revision]) };
    app.playback = { cancel() {} };
    app.stages = { active: "3d", busy: false, setBusy() {}, message() {},
      restoreConfig: state => calls.push(["stage controls", state.wall_revision]),
      tabs: {select: stage => calls.push(["tab", stage])} };
    app.api = { post: async path => { calls.push(["request", path]); return restored; } };
    app.accept = async state => { app.state = state; return true; };
    app.updateWallActions = () => {};
    app.refreshStage = async stage => calls.push(["refresh", stage]);
    assert.equal(await app.mutate(action, {}), true);
    assert.deepEqual(calls, [["request", `/api/${action}`], ["controls", 2],
      ...(action === "load" ? [["stage controls", 2], ["tab", "wall"]] : [["refresh", "3d"]])]);
  }
});

test("rejected JSON preserves Wall drafts and does not start downstream processing", async () => {
  const app = Object.create(WorkbenchApp.prototype);
  app.state = sourceState(1);
  const rejection = new Error("Stone overlaps an existing stone");
  rejection.rejected = true;
  app.parameters = { parametersAreDirty: () => true, restore() { assert.fail("drafts must survive"); } };
  app.playback = { cancel() {} };
  app.stages = { active: "shape", busy: false, setBusy() {}, message() {} };
  app.api = { post: async () => { throw rejection; }, get: async () => app.state };
  app.accept = async () => true;
  app.updateWallActions = () => {};
  app.refreshStage = async () => assert.fail("must not process rejected input");
  const originalError = console.error;
  console.error = () => {};
  try { assert.equal(await app.mutate("load", {}), false); }
  finally { console.error = originalError; }
});

test("analysis colours apply only to Wall and do not alter the shared stone colours", () => {
  const original = globalThis.document;
  let checked = true;
  globalThis.document = {querySelector: () => ({checked})};
  try {
    const viewer = Object.create(WallViewer2D.prototype);
    viewer.stage = "wall";
    viewer.sneckIds = new Set([1,2]);
    viewer.deliberateIds = new Set([2]);
    viewer.latestState = { wall_report: {colours: {ordinary:"grey",fallback:"blue",deliberate:"purple"}} };
    viewer.colour = id => `original-${id}`;
    assert.deepEqual([0,1,2].map(id => viewer.stoneColour(id)), ["grey","blue","purple"]);
    viewer.stage = "shape";
    assert.equal(viewer.stoneColour(2), "original-2");
    viewer.stage = "wall";
    checked = false;
    assert.equal(viewer.stoneColour(2), "original-2");
  } finally { globalThis.document = original; }
});
