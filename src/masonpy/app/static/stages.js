import { Tabs } from "./tabs.js";

/** Stage drafts, live controls and applied settings for automatic source refresh. */
export class StagePanel {
  constructor(onSelect, onApply, onEdit) {
    Object.assign(this, { onEdit, active: "wall", state: null, busy: false, pending: false });
    this.feedback = document.querySelector("#stage-feedback");
    this.tabs = new Tabs(Object.fromEntries(["wall", "shape", "3d"].map(name =>
      [name, document.querySelector(`#stage-${name}`)])), name => {
      if (this.busy) return;
      this.active = name;
      this.update();
      onSelect(name);
    });
    for (const [stage, form] of [["shape", "shape-controls"], ["3d", "three-controls"]]) {
      document.querySelector(`#${form}`).addEventListener("submit", event => {
        event.preventDefault();
        onApply(stage === "shape" ? "shape" : "build", this.payload(stage));
      });
      document.querySelector(`#${form}`).addEventListener("input", () => this.edit(stage));
      document.querySelector(`#live-${stage}`).addEventListener("change", () => this.edit(stage));
    }
    document.querySelector("#shape-reset").addEventListener("click", () => {
      for (const [id, value] of Object.entries({ "joint-width": .2, "shape-distortion": 0, "corner-softening": 0,
        "shape-seed": 1, "variation-scale": 6 })) document.querySelector(`#${id}`).value = value;
      this.edit("shape");
    });
    // A summary's checkbox must not also collapse the Parameters panel.
    document.querySelector("#advanced-toggle").addEventListener("click", event => event.stopPropagation());
    document.querySelector("#show-advanced").addEventListener("change", () => this.update(false));
    document.querySelector("#export-scale").addEventListener("input", () => this.update(false));
  }

  /** Only downstream stages can update on input; Wall always requires an explicit action. */
  liveEnabled(stage = this.active) {
    return stage !== "wall" && document.querySelector(`#live-${stage}`).checked;
  }

  payload(stage = this.active) {
    return stage === "shape" ? {
      joint_width: Number(document.querySelector("#joint-width").value),
      distortion: Number(document.querySelector("#shape-distortion").value),
      seed: Number(document.querySelector("#shape-seed").value),
      variation_scale: Number(document.querySelector("#variation-scale").value),
      corner_softening: Number(document.querySelector("#corner-softening").value)
    } : this.settings();
  }

  valid(stage = this.active) {
    return document.querySelector(stage === "shape" ? "#shape-controls" : "#three-controls").checkValidity();
  }

  edit(stage) {
    this.update();
    const valid = this.valid(stage), enabled = this.liveEnabled(stage);
    this.onEdit(stage === "shape" ? "shape" : "build", this.payload(stage), enabled && valid);
    if (!enabled) this.update();
    if (!valid) this.message("Enter valid parameter values before applying.", true);
  }

  /** Read the 3D draft independently of the applied mesh. */
  settings() {
    return {
      mode: document.querySelector("#projection-mode").value,
      roundness: Number(document.querySelector("#projection-roundness").value),
      resolution: Number(document.querySelector("#projection-resolution").value),
      primitive: document.querySelector("#projection-primitive").value,
      tube_thickness: Number(document.querySelector("#tube-thickness").value),
      depth: Number(document.querySelector("#stone-depth").value),
      depth_variation: Number(document.querySelector("#depth-variation").value),
      bevel: Number(document.querySelector("#edge-bevel").value),
      detail_seed: Number(document.querySelector("#detail-seed").value)
    };
  }

  /** Live edits may use valid drafts; manual mode refreshes only applied settings. */
  automaticSettings(stage) {
    if (this.liveEnabled(stage) && this.valid(stage)) return this.payload(stage);
    if (stage === "shape") return { ...(this.state.shape.result?.settings ?? this.state.shape.defaults) };
    return { ...(this.state.build.settings ?? this.state.build.defaults) };
  }

  /** Persistently label retained results after an unsuccessful refresh. */
  staleNote() {
    if (this.active === "shape" && this.state?.shape.result && !this.state.shape.current)
      return " Showing the previous Shape result (stale).";
    if (this.active === "3d" && this.state?.build.present && !this.state.build.current)
      return " Showing the previous 3D build (stale).";
    return "";
  }

  render(state) {
    if (!this.initialized) {
      const shapeSettings = state.shape.result?.settings ?? state.shape.defaults
        ?? (state.shape.result ? { joint_width: state.shape.result.joint_width } : null);
      if (shapeSettings) {
        const settings = shapeSettings;
        for (const [key, id] of Object.entries({ joint_width: "joint-width", distortion: "shape-distortion",
          seed: "shape-seed", variation_scale: "variation-scale", corner_softening: "corner-softening" })) {
          if (settings[key] !== undefined) document.querySelector(`#${id}`).value = settings[key];
        }
      }
      const buildSettings = state.build.settings ?? state.build.defaults;
      if (buildSettings) {
        for (const [key, id] of Object.entries({ mode: "projection-mode", roundness: "projection-roundness",
          resolution: "projection-resolution", primitive: "projection-primitive",
          tube_thickness: "tube-thickness", depth: "stone-depth", depth_variation:"depth-variation",
          bevel:"edge-bevel", detail_seed:"detail-seed" })) {
          document.querySelector(`#${id}`).value = buildSettings[key];
        }
      }
      this.initialized = true;
    }
    this.state = state;
    this.update();
  }

  /** Restore imported downstream parameters without triggering live processing. */
  restoreConfig(state) {
    this.initialized = false;
    this.render(state);
  }

  /** SVG follows the inspected 2D description; 3D uses its current Shape contours. */
  svgStage() { return this.active === "wall" ? "wall" : "shape"; }

  /** Export the whole applied stage, never the current playback prefix. */
  exportAvailability(stage = this.active) {
    if (!this.state) return "Load a wall first";
    if (this.busy || this.pending) return "Wait for the current operation to finish";
    if (!document.querySelector("#export-scale").checkValidity()) return "Enter a positive millimetres-per-unit scale";
    if (stage === "wall") return this.state.wall.stones.length ? "" : "Place or generate stones before exporting";
    if (stage === "shape") return this.state.shape.current ? "" : "Apply Shape to the current wall before exporting";
    if (!this.state.build.current) return "Build 3D from the current Shape before exporting";
    if (this.state.build.settings.depth <= 0) return "Build with positive stone depth before exporting STL";
    return "";
  }

  update(refreshFeedback = true) {
    const shape = this.active === "shape", three = this.active === "3d", wall = this.active === "wall";
    for (const [id, visible] of Object.entries({ toolbar: wall, "shape-controls": shape,
      "three-controls": three, "wall-actions": wall, "shape-actions": shape,
      "build-actions": three, "canvas-wrap": !three, "wall-controls": !three,
      "three-wrap": three, "three-navigation": three })) document.querySelector(`#${id}`).hidden = !visible;
    const advanced = document.querySelector("#show-advanced").checked;
    document.querySelector("#shape-advanced").hidden = !advanced;
    document.querySelector("#advanced-controls").hidden = !advanced;
    document.querySelector("#build-advanced").hidden = !advanced;
    document.querySelector("#stage-workspace").setAttribute("aria-labelledby", `stage-${this.active}`);
    document.querySelector("#viewer-title").textContent = wall ? "Wall · discrete construction"
      : (shape ? "Shape · applied contours" : "3D · built geometry")
        + (this.staleNote() ? " · previous result (stale)" : "");
    document.querySelectorAll("#wall-controls .diagnostic-control, #report-seams, #seam-summary")
      .forEach(element => { element.hidden = !wall; });
    document.querySelector('#analysis-legend').hidden = !wall || !document.querySelector('#analysis-colours').checked;
    document.querySelector("#roundness-value").textContent = document.querySelector("#projection-roundness").value;
    document.querySelector("#depth-value").textContent = document.querySelector("#stone-depth").value;
    document.querySelector("#depth-variation-value").textContent = `${Math.round(Number(document.querySelector("#depth-variation").value)*100)}%`;
    document.querySelector("#distortion-value").textContent = document.querySelector("#shape-distortion").value;
    document.querySelector("#softening-value").textContent = document.querySelector("#corner-softening").value;
    this.feedback.classList.toggle("busy", this.busy || this.pending);
    if (!this.state) return;
    const s = this.state.shape, b = this.state.build;
    document.querySelector("#apply-shape").disabled = this.busy || !this.state.wall.stones.length;
    document.querySelector("#build-3d").disabled = this.busy || !s.current;
    const shapeDirty = s.result && Object.entries(this.payload("shape")).some(([key, value]) =>
      value !== (s.result.settings ?? { joint_width: s.result.joint_width, distortion: 0, seed: 1, variation_scale: 6 })[key]);
    const buildDirty = b.settings && Object.entries(this.settings()).some(([key, value]) => value !== b.settings[key]);
    const shapeNote = !s.result ? (this.state.wall.stones.length
      ? `Ready to Apply Shape to ${this.state.wall.stones.length} placed stones.`
      : "Place or generate a wall, then Apply Shape.")
      : !s.current ? "Wall changed — Apply Shape again. Showing the previous result."
      : shapeDirty ? "Parameters changed — Apply Shape to update the contours." : "Shape is current.";
    const buildNote = !s.current ? "Apply Shape to the current wall before building 3D."
      + (b.present ? " Showing the previous build." : "")
      : !b.present ? "Ready to Build 3D."
      : !b.current ? "Shape changed — Build 3D again. Showing the previous build."
      : buildDirty ? "Parameters changed — Build 3D to update the mesh." : "3D build is current.";
    if (!wall) document.querySelector("#parameter-summary").textContent = shape
      ? `Joint width: ${this.payload("shape").joint_width} · distortion: ${this.payload("shape").distortion} · corner softening: ${this.payload("shape").corner_softening}`
      : `${this.settings().mode} · depth: ${this.settings().depth} ±${Math.round(this.settings().depth_variation*100)}% · bevel: ${this.settings().bevel}`;
    for (const [id, stage] of [["export-svg", this.svgStage()], ["export-stl", "3d"]]) {
      const reason = this.exportAvailability(stage), button = document.querySelector(`#${id}`);
      button.disabled = Boolean(reason);
      button.title = reason || `Export full applied ${stage === "3d" ? "3D mesh with optional core as STL" : stage + " contours as SVG"}`;
    }
    if (refreshFeedback && !this.busy && !this.pending) this.message(wall
      ? "Wall uses applied parameters. Playback reuses placed stones." : shape ? shapeNote : buildNote);
  }

  message(text, error = false) {
    this.feedback.textContent = text;
    this.feedback.classList.toggle("error", error);
  }

  /** Live edits keep parameter inputs usable while conflicting actions remain disabled. */
  setBusy(busy, message = "Working…", { live = false } = {}) {
    this.busy = busy;
    document.querySelector("#stage-actions").setAttribute("aria-busy", String(busy));
    if (busy) {
      const selector = (live ? ".actions button, #stage-tabs button, #export-scale"
        : "#parameter-panel input, #parameter-panel select, #parameter-panel button, .actions input, .actions button, #stage-tabs button")
        + ', #wall-library button, #wall-history, #wall-file, #export-scale';
      this.disabled = [...document.querySelectorAll(selector)].map(element => [element, element.disabled]);
      for (const [element] of this.disabled) element.disabled = true;
      this.message(message);
    } else {
      for (const [element, disabled] of this.disabled ?? []) element.disabled = disabled;
    }
    this.update(!busy);
  }
}
