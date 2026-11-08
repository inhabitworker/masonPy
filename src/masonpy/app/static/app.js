import { ApiClient } from "./api.js";
import { ParameterPanel } from "./parameters.js";
import { WallViewer2D } from "./viewer2d.js";
import { DetailsPanel } from "./details.js";
import { WallDiagnostics } from "./diagnostics.js";
import { ProjectionPanel } from "./projection.js";
import { Playback } from "./playback.js";
import { StagePanel } from "./stages.js";
import { LiveUpdates } from "./live.js";
import { StageRefresh, sameSettings } from "./pipeline.js";
import { WallLibrary, saveAttachment } from "./library.js";

/** Coordinates applied stage snapshots, source identity and shared selection. */
export class WorkbenchApp {
  constructor() {
    this.api = new ApiClient();
    this.state = null;
    this.selectedId = null;
    this.visibleCount = 0;
    this.colours = new Map();
    this.playback = new Playback();
    const select = (id, options) => this.select(id, options);
    const colour = id => this.colour(id);
    this.parameters = new ParameterPanel(payload => this.mutate("reset", payload));
    this.viewer = new WallViewer2D(colour, select, () => this.diagnostics.refresh());
    this.details = new DetailsPanel(this.api, select);
    this.projection = new ProjectionPanel(colour, select);
    this.stages = new StagePanel(() => this.switchStage(), (action, payload) => this.mutate(action, payload),
      (action, payload, enabled) => this.queueLive(action, payload, enabled));
    this.pipeline = new StageRefresh(() => this.state, stage => this.stages.automaticSettings(stage),
      (action, payload, options) => this.mutate(action, payload, options));
    this.library = new WallLibrary((action, payload) => this.mutate(action, payload),
      () => this.saveWall(), message => this.showError(message));
    this.live = new LiveUpdates((action, payload) => this.mutate(action, payload, { live: true }),
      action => this.canUpdateLive(action), pending => {
        this.stages.pending = pending;
        this.stages.update(false);
        if (this.state) this.updateWallActions();
      }, error => this.showError(error.message));
    this.diagnostics = new WallDiagnostics(this.api, this.viewer,
      () => ({ state: this.stages.active === "wall" ? this.state : null, visibleCount: this.visibleCount }),
      message => this.details.report(message), message => this.showError(message));
    for (const [id, action] of [["step", "step"], ["undo", "undo"], ["generate", "generate"]]) {
      document.querySelector(`#${id}`).addEventListener("click", () => this.mutate(action));
    }
    document.querySelector("#export-svg").addEventListener("click", () => this.exportStage(this.stages.svgStage()));
    document.querySelector("#export-stl").addEventListener("click", () => this.exportStage("3d"));
    document.querySelector("#play-forward").addEventListener("click", () => this.play(1));
    document.querySelector("#play-reverse").addEventListener("click", () => this.play(-1));
  }

  async start() {
    try { await this.accept(await this.api.get("/api/state")); }
    catch (error) { this.showError(`Loading the workbench: ${error.message}`); }
  }

  showError(message) {
    this.stages.message(message + (this.stages.staleNote?.() ?? ""), true);
  }

  colour(id) {
    if (!this.colours.has(id)) {
      this.colours.set(id, `hsl(${Math.floor(Math.random() * 360)}, ${36 + Math.floor(Math.random() * 19)}%, ${43 + Math.floor(Math.random() * 15)}%)`);
    }
    return this.colours.get(id);
  }

  /** Accept monotonic source snapshots; a late mesh fetch cannot overwrite a newer result. */
  async accept(state, { preserveSelection = false } = {}) {
    if (this.state && (state.wall_revision < this.state.wall_revision
      || state.shape.revision < this.state.shape.revision || state.build.revision < this.state.build.revision)) return false;
    const sequence = this.acceptSequence = (this.acceptSequence ?? 0) + 1;
    // A successful action response remains authoritative even if a later
    // geometry fetch or display update fails.
    this.state = state;
    if (state.build.present && this.meshRevision !== state.build.revision) {
      const snapshot = await this.api.get("/api/geometry");
      if (sequence !== this.acceptSequence) return false;
      if (snapshot.revision !== state.build.revision || snapshot.source_revision !== state.build.source_revision
        || (state.build.current && snapshot.wall_revision !== state.wall_revision)) {
        throw new Error("The 3D source changed while its preview was loading. Reopen 3D to refresh.");
      }
      this.meshSnapshot = snapshot;
      this.meshRevision = state.build.revision;
    } else if (!state.build.present) {
      this.meshSnapshot = null;
      this.meshRevision = null;
    }
    this.visibleCount = this.displayWall().stones.length;
    if (!preserveSelection) this.selectedId = state.last_stone_id;
    this.draw();
    if (this.stages.active === "3d") await this.projection.select(true);
    return sequence === this.acceptSequence;
  }

  /** Serialize requested operations; generation drafts never silently replace applied settings. */
  async mutate(action, payload = {}, { live = false, automatic = false } = {}) {
    if (this.stages.busy || !this.state) return false;
    if (!automatic) this.pipeline?.cancel();
    if (!live) this.live?.cancel();
    this.playback.cancel();
    const dirty = this.parameters.parametersAreDirty();
    const before = this.state;
    const restore = ['load', 'history'].includes(action);
    const downstream = ["shape", "build"].includes(action);
    const stage = action === "shape" ? "shape" : "3d";
    const preservedDrafts = automatic && downstream && !sameSettings(this.stages.payload(stage), payload);
    const request = downstream ? { ...payload, source_revision: payload.source_revision
      ?? (action === "shape" ? before.wall_revision : before.shape.revision) } : payload;
    if (["generate", "step"].includes(action)) this.details?.beginGeneration();
    const working = { reset: "Applying wall parameters…", step: "Placing one stone…",
      undo: "Undoing placement…", generate: "Generating with applied wall parameters…",
      shape: "Applying distortion, mortar and corner softening…", build: "Building 3D geometry…" };
    working.load = 'Loading configuration…';
    working.history = 'Restoring saved wall…';
    this.stages.setBusy(true, working[action], { live });
    let message, errorMessage, received;
    try {
      const state = received = await this.api.post(`/api/${action}`, request);
      if (restore) this.parameters.restore(state);
      if (action === "load") this.stages.restoreConfig(state);
      message = this.actionMessage(action, state, before, dirty);
      if (await this.accept(state, { preserveSelection: downstream }) === false) return false;
    } catch (error) {
      console.error(`Workbench action: ${action}`, error);
      // Failed processing is logged server-side; refresh metadata while keeping applied results.
      let recovered, refreshed = false;
      try {
        recovered = await this.api.get("/api/state");
        if (restore && !error.rejected && recovered.wall_revision !== before.wall_revision) this.parameters.restore(recovered);
        if (action === "load" && !error.rejected && recovered.wall_revision !== before.wall_revision) this.stages.restoreConfig(recovered);
        await this.accept(recovered, { preserveSelection: true });
        refreshed = true;
      } catch { /* Keep the last accepted snapshot. */ }
      const revision = action === "shape" ? state => state.shape.revision
        : action === "build" ? state => state.build.revision : state => state.wall_revision;
      const confirmed = received ?? (!error.rejected && recovered && revision(recovered) !== revision(before) ? recovered : null);
      if (confirmed) {
        message = this.actionMessage(action, confirmed, before, dirty);
        if (!refreshed) errorMessage = `${message} The preview could not be refreshed: ${error.message}`;
        else message += " Current state recovered after an interrupted response or display update.";
      } else {
        const label = { generate: "Generate wall", step: "Place one", reset: "Apply & reset",
          undo: "Undo", shape: "Apply Shape", build: "Build 3D" }[action] ?? action;
        errorMessage = `${label}: ${error.message}`;
      }
    } finally {
      this.stages.setBusy(false);
      this.updateWallActions();
    }
    if (errorMessage) this.showError(errorMessage);
    else this.stages.message(message + (preservedDrafts ? " Refreshed using applied settings; parameter drafts remain unapplied." : ""),
      Boolean(this.state.failure && ["generate", "step"].includes(action)));
    if (!errorMessage && action === "load") this.stages.tabs.select("wall");
    if (!errorMessage && action === "history") await this.refreshStage(this.stages.active);
    if (!errorMessage && action === "load") this.stages.message(message);
    return !errorMessage;
  }

  /** Describe the confirmed operation independently of subsequent rendering. */
  actionMessage(action, state, before, dirty) {
    if (action === "load") return "Configuration loaded. Generate wall to build with these parameters.";
    if (action === "history") {
      const count = state.wall.stones.length;
      const outcome = state.failure ? "stopped" : state.complete ? "complete" : "partial";
      return `Restored exact wall (${count} stone${count === 1 ? "" : "s"}, ${outcome}) and applied Wall parameters. No generation was run.`;
    }
    if (["generate", "step"].includes(action)) {
      let message = state.failure?.message ?? (state.wall_revision === before.wall_revision
        ? "No new stones generated; the existing wall is unchanged."
        : `Placed ${state.wall.stones.length - before.wall.stones.length} new stone(s) using applied parameters.`);
      if (dirty) message += " Draft parameters were not used — choose Apply & reset to use them.";
      return message;
    }
    if (action === "shape") return state.shape.events.at(-1);
    if (action === "build") return state.build.events.at(-1);
    return action === "reset" ? "Wall parameters applied. Place one or Generate wall to begin."
      : "Last placement removed; downstream results may need applying again.";
  }

  updateWallActions() {
    document.querySelector("#undo").disabled = this.stages.busy || (!this.state.events.length && !this.state.failure);
    for (const id of ["play-forward", "play-reverse"]) {
      document.querySelector(`#${id}`).disabled = this.stages.busy || this.stages.pending || !this.displayWall().stones.length;
    }
    const save = document.querySelector('#save-wall');
    if (save) save.disabled = this.stages.busy || this.stages.pending;
  }

  /** Inspect immediately, then ensure downstream snapshots describe the current Wall. */
  switchStage() {
    this.live?.cancel();
    this.playback.cancel();
    this.visibleCount = this.displayWall().stones.length;
    this.draw();
    this.projection.select(this.stages.active === "3d");
    return this.refreshStage(this.stages.active);
  }

  /** Recover missing mesh buffers without rebuilding an already current stage. */
  async refreshStage(stage) {
    try {
      const ready = await this.pipeline?.ensure(stage);
      if (ready && stage === "3d" && this.stages.active === stage
        && this.meshRevision !== this.state.build.revision) {
        await this.accept(this.state, { preserveSelection: true });
      }
    } catch (error) {
      if (this.stages.active === stage) this.showError(`Stage refresh: ${error.message}`);
    }
  }

  /** The currently inspected source may be an older, deliberately retained downstream snapshot. */
  displayWall() {
    if (this.stages.active === "wall") return this.state.wall;
    return (this.stages.active === "shape" ? this.state.shape?.result?.source : this.meshSnapshot?.shape?.source)
      ?? { ...this.state.wall, stones: [] };
  }

  draw() {
    const state = this.state, stage = this.stages.active;
    this.parameters.render(state);
    this.stages.render(state);
    this.library?.render(state);
    this.updateWallActions();
    const wall = this.displayWall();
    if (!wall.stones.some(stone => stone.id === this.selectedId)) this.selectedId = null;
    if (stage !== "3d") {
      this.viewer.setStage(stage);
      this.viewer.render({ ...state, wall, contours: stage === "shape" ? state.shape.result?.stones : null },
        this.visibleCount);
    }
    if (stage === "wall") this.details.render(state, this.visibleCount);
    else this.details.renderStage(stage, stage === "shape" ? state.shape : state.build,
      stage === "shape" ? state.shape.result : this.meshSnapshot?.shape,
      stage === "3d" ? this.meshSnapshot?.geometry : null);
    this.projection.render(this.meshSnapshot, this.meshRevision, this.selectedId,
      stage === "3d" ? this.visibleCount : this.meshSnapshot?.shape?.source.stones.length);
    this.select(this.selectedId, { scrollLog: false, focus: false });
    this.diagnostics.refresh();
  }

  select(id, { toggle = false, scrollLog = true, focus = true } = {}) {
    const next = id === null ? null : Number(id);
    this.selectedId = toggle && next === this.selectedId ? null : next;
    this.viewer.setSelection(this.selectedId, focus && this.stages.active !== "3d");
    this.details.setSelection(this.selectedId, scrollLog);
    this.projection.updateVisibility(this.visibleCount, this.selectedId);
  }

  reveal(count) {
    const wall = this.displayWall();
    const next = Math.max(0, Math.min(count, wall.stones.length));
    if (next === this.visibleCount) return;
    this.visibleCount = next;
    if (this.stages.active !== "3d") this.viewer.updateVisibility(this.visibleCount);
    if (this.stages.active === "wall") this.details.updateVisibility(this.visibleCount);
    this.select(this.visibleCount ? wall.stones[this.visibleCount - 1].id : null, { focus: false });
    this.stages.message(`Playback: ${this.visibleCount} of ${wall.stones.length} existing stones; no new generation or processing.${this.playbackNote ?? ""}`);
    this.diagnostics.refresh();
  }

  /** Replay the active stage's stored source order, including retained stale previews. */
  play(direction) {
    if (this.stages.busy || this.stages.pending || !this.state) return;
    const total = this.displayWall().stones.length;
    if (!total) return;
    this.playback.cancel();
    const dirty = this.stages.active === "wall" ? this.parameters.parametersAreDirty()
      : this.stages.active === "shape" ? Object.entries(this.stages.payload("shape")).some(([key, value]) =>
        value !== (this.state.shape.result?.settings ?? this.state.shape.result)?.[key])
      : Object.entries(this.stages.settings()).some(([key, value]) => value !== this.state.build.settings?.[key]);
    const message = `Playing ${total} existing stones; no new generation or processing.`
      + (dirty ? " Draft parameters are not applied." : "");
    this.playbackNote = dirty ? " Draft parameters are not applied." : "";
    this.stages.message(message);
    this.playback.play(total, direction, count => this.reveal(count), () => {
      this.stages.message(`Playback complete; reused existing stones.${dirty ? " Draft parameters remain unapplied." : ""}`);
    });
  }

  /** Live toggles govern edits; stage entry refreshes sources independently. */
  queueLive(action, payload, enabled) {
    if (!enabled || !this.canUpdateLive(action)) { this.live.cancel(); return; }
    this.live.schedule(action, payload);
    this.stages.message(action === "shape" ? "Live Shape update pending…" : "Live 3D update pending…");
  }

  canUpdateLive(action) {
    const stage = action === "shape" ? "shape" : "3d";
    return this.stages.active === stage && this.stages.liveEnabled(stage) && this.stages.valid(stage)
      && (action === "shape" ? Boolean(this.state?.wall.stones.length) : this.state?.shape.current);
  }

  /** Download the full applied result at a physical scale; drafts/playback are excluded. */
  async exportStage(stage = this.stages.active) {
    if (this.stages.exportAvailability(stage)) return;
    const revision = stage === "wall" ? this.state.wall_revision
      : stage === "shape" ? this.state.shape.revision : this.state.build.revision;
    const scale = Number(document.querySelector("#export-scale").value);
    this.stages.setBusy(true, `Preparing ${stage === "3d" ? "STL" : "SVG"} export…`);
    let message, errorMessage;
    try {
      const { blob, filename } = await this.api.download({ stage, scale, revision });
      saveAttachment(blob, filename);
      message = `Exported full applied ${stage === "3d" ? "3D result as separate closed shells, including any core" : stage + " contours"} at ${scale} mm/unit; playback and drafts excluded.`;
    } catch (error) { errorMessage = error.message; }
    finally { this.stages.setBusy(false); this.updateWallActions(); }
    if (errorMessage) this.showError(`Export: ${errorMessage}`);
    else this.stages.message(message);
  }

  /** Export form parameters without geometry, logs, analysis or random-state snapshots. */
  async saveWall() {
    if (!this.state || this.stages.busy || this.stages.pending) return;
    const config = { ...this.parameters.resetPayload(), shape:this.stages.payload("shape"), build:this.stages.payload("3d") };
    this.stages.setBusy(true, 'Preparing config JSON…');
    let errorMessage;
    try {
      const {blob, filename} = await this.api.download({config}, '/api/save');
      saveAttachment(blob, filename);
    } catch (error) { errorMessage = error.message; }
    finally { this.stages.setBusy(false); this.updateWallActions(); }
    if (errorMessage) this.showError('Export config: ' + errorMessage);
    else this.stages.message('Exported Wall, Shape and 3D parameters from the controls, including unapplied edits.');
  }
}
