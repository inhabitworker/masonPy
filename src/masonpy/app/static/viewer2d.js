/** SVG rendering, logical-to-screen coordinates, and pointer navigation only. */
export class WallViewer2D {

  /** @param {Function} colour Shared ID-to-colour lookup. @param {Function} onSelect */
  constructor(colour, onSelect, onRedraw = () => {}) {
    this.svg = document.querySelector("#wall");
    this.ns = "http://www.w3.org/2000/svg";
    this.colour = colour;
    this.onSelect = onSelect;
    this.latestState = null;
    this.selectedStoneId = null;
    this.visibleCount = 0;
    this.viewState = null;
    this.viewKey = null;
    this.viewAnimation = null;
    this.panStart = null;
    this.wrapDisplay = false;
    this.wrapToggleButton = document.querySelector("#wrap-toggle");
    document.querySelector("#zoom-in").addEventListener("click", () => this.setZoom(this.viewState.zoom * 1.35));
    document.querySelector("#zoom-out").addEventListener("click", () => this.setZoom(this.viewState.zoom / 1.35));
    document.querySelector("#fit-view").addEventListener("click", () => this.fit());
    this.wrapToggleButton.addEventListener("click", () => {
      if (!this.latestState) return;
      this.wrapDisplay = !this.wrapDisplay;
      this.render(this.latestState, this.visibleCount);
      this.setSelection(this.selectedStoneId);
      onRedraw();
    });
    document.querySelector("#hide-snecks").addEventListener("change", () => this.updateVisibility(this.visibleCount));
    document.querySelector('#analysis-colours').addEventListener('change', () => {
      document.querySelector('#analysis-legend').hidden = !document.querySelector('#analysis-colours').checked;
      if (!this.latestState) return;
      this.render(this.latestState, this.visibleCount);
      this.setSelection(this.selectedStoneId);
      onRedraw();
    });
    this.bindPointerNavigation();
    new ResizeObserver(() => {
      if (this.latestState) this.applyViewBox();
    }).observe(this.svg);
  }

  /** Bind pointer capture once; short presses select, holds/drags pan, never select text. */
  bindPointerNavigation() {
    // Pointer capture retargets release events to the SVG, so remember the pressed
    // stone and resolve selection here instead of relying on a synthetic click.
    this.svg.addEventListener("click", event => event.preventDefault());
    this.svg.addEventListener("selectstart", event => event.preventDefault());
    this.svg.addEventListener("dragstart", event => event.preventDefault());
    this.svg.addEventListener("wheel", event => {
      event.preventDefault();
      const anchor = this.clientToWall(event.clientX, event.clientY);
      this.setZoom(this.viewState.zoom * (event.deltaY < 0 ? 1.18 : 1 / 1.18), anchor);
    }, { passive: false });
    this.svg.addEventListener("pointerdown", event => {
      if (!event.isPrimary || event.button !== 0 || !this.viewState || this.panStart) return;
      event.preventDefault();
      this.stopViewAnimation();
      const point = this.clientToWall(event.clientX, event.clientY);
      this.panStart = {
        pointerId: event.pointerId,
        clientX: event.clientX,
        clientY: event.clientY,
        centerX: this.viewState.centerX,
        centerY: this.viewState.centerY,
        point,
        stoneId: event.target.closest(".stone-group")?.dataset.stoneId ?? null,
        started: performance.now(),
        dragging: false,
        holdTimer: setTimeout(() => {
          if (!this.panStart) return;
          this.panStart.dragging = true;
          this.svg.classList.add("panning");
        }, 240)
      };
      this.svg.setPointerCapture(event.pointerId);
    });
    this.svg.addEventListener("pointermove", event => {
      if (!this.panStart || event.pointerId !== this.panStart.pointerId) return;
      event.preventDefault();
      const dx = event.clientX - this.panStart.clientX;
      const dy = event.clientY - this.panStart.clientY;
      if (Math.hypot(dx, dy) > 5) this.panStart.dragging = true;
      if (!this.panStart.dragging) return;
      clearTimeout(this.panStart.holdTimer);
      const point = this.clientToWall(event.clientX, event.clientY);
      this.viewState.centerX += this.panStart.point.x - point.x;
      this.viewState.centerY += this.panStart.point.y - point.y;
      this.svg.classList.add("panning");
      this.applyViewBox();
    });
    this.svg.addEventListener("pointerup", event => this.finishPan(event));
    this.svg.addEventListener("pointercancel", event => this.finishPan(event));
    this.svg.addEventListener("lostpointercapture", event => this.finishPan(event));
    this.svg.addEventListener("keydown", event => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const stone = event.target.closest(".stone-group");
      if (!stone) return;
      event.preventDefault();
      this.onSelect(stone.dataset.stoneId, { toggle: true });
    });
  }

  /** @param {Object} data @param {number} visibleStoneCount Rebuild SVG from Python state. */
  render(data, visibleStoneCount = data.wall.stones.length) {
    const { wall } = data;
    this.latestState = data;
    this.sneckIds = new Set(data.wall_report?.sneck_ids ?? []);
    this.deliberateIds = new Set(data.wall_report?.deliberate_sneck_ids ?? []);
    this.contours = new Map((data.contours ?? []).map(stone => [stone.id, stone.vertices]));
    this.visibleCount = visibleStoneCount;
    this.configureView(wall);
    const logicalWrap = document.querySelector("#logical-wrap");
    logicalWrap.disabled = Boolean(wall.wrap_x);
    if (wall.wrap_x) logicalWrap.checked = true;
    this.drawGrid(wall);
    wall.stones.forEach((stone, index) => this.drawStone(stone, index, visibleStoneCount));
    this.svg.append(this.makeAxes(wall));
    this.wrapToggleButton.textContent = `Wrapping: ${this.wrapDisplay ? "on" : "off"}`;
    this.wrapToggleButton.setAttribute("aria-pressed", this.wrapDisplay);
    this.applyViewBox();
    requestAnimationFrame(() => this.updateStoneLabels(wall));
  }

  /** @param {Object} wall Draw the reference rectangle and discrete grid behind the stones. */
  drawGrid(wall) {
    this.svg.replaceChildren();
    this.svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
    this.svg.append(this.svgElement("rect", {
      x: 0,
      y: 0,
      width: wall.width,
      height: wall.height,
      class: "wall-background",
      "aria-hidden": "true"
    }));

    const grid = this.svgElement("g", { "aria-hidden": "true" });
    for (let x = 0; x <= wall.width; x++) {
      grid.append(this.svgElement("line", { x1: x, y1: 0, x2: x, y2: wall.height, class: "grid-line" }));
    }
    for (let y = 0; y <= wall.height; y++) {
      grid.append(this.svgElement("line", { x1: 0, y1: y, x2: wall.width, y2: y, class: "grid-line" }));
    }
    this.svg.append(grid);
  }

  /** @param {Object} stone @param {number} index @param {number} visibleStoneCount Draw all virtual pieces under one logical ID. */
  drawStone(stone, index, visibleStoneCount) {
    if (this.contours?.has(stone.id)) return this.drawContour(stone, index, visibleStoneCount);
    const wall = this.latestState.wall;
    const renderedY = wall.height - stone.y - stone.height;
    const sneck = this.stage === 'wall' ? this.sneckIds.has(stone.id) : Boolean(stone.traits.is_sneck);
    const group = this.svgElement("g", {
      class: `stone-group${index >= visibleStoneCount ? " playback-hidden" : ""}${sneck && document.querySelector("#hide-snecks").checked ? " sneck-hidden" : ""}`,
      "data-sneck": sneck,
      "data-stone-id": stone.id,
      "data-index": index,
      role: "button",
      tabindex: "0",
      "aria-label": `Stone ${stone.id}`
    });
    this.stonePieces(stone, wall).forEach(piece => {
      const renderedX = piece.x;
      const rect = this.svgElement("rect", {
        x: renderedX,
        y: renderedY,
        width: piece.width,
        height: stone.height,
        fill: this.stoneColour(stone.id),
        class: "stone"
      });
      const title = this.svgElement("title", {});
      title.textContent = `Stone ${stone.id}: (${stone.x}, ${stone.y}), ${stone.width} × ${stone.height}`;
      rect.append(title);
      const label = this.svgElement("text", {
        x: renderedX,
        y: renderedY,
        "data-x": renderedX,
        "data-y": renderedY,
        "data-piece-width": piece.width,
        "data-piece-height": stone.height,
        class: "stone-id"
      });
      label.textContent = stone.id;
      group.append(rect, label);
    });
    this.svg.append(group);
  }

  /** Use Python's shared classification and palette only in the logical Wall view. */
  stoneColour(id) {
    if (this.stage !== 'wall' || !document.querySelector('#analysis-colours').checked) return this.colour(id);
    const role = this.deliberateIds.has(id) ? 'deliberate' : this.sneckIds.has(id) ? 'fallback' : 'ordinary';
    return this.latestState.wall_report?.colours[role] ?? this.colour(id);
  }

  /** Preserve independent navigation for the two stages sharing the SVG surface. */
  setStage(stage) {
    this.stageViews ??= new Map();
    if (this.stage === stage) return;
    if (this.stage) this.stageViews.set(this.stage, {
      viewState: this.viewState, viewKey: this.viewKey, wrapDisplay: this.wrapDisplay
    });
    this.stage = stage;
    const saved = this.stageViews.get(stage);
    this.viewState = saved?.viewState ?? null;
    this.viewKey = saved?.viewKey ?? null;
    this.wrapDisplay = saved?.wrapDisplay ?? false;
  }

  /** Draw whole unwrapped polygons, repeating and clipping only for periodic display. */
  drawContour(stone, index, visibleStoneCount) {
    const wall = this.latestState.wall;
    const vertices = this.contours.get(stone.id);
    const group = this.svgElement("g", {
      class: `stone-group${index >= visibleStoneCount ? " playback-hidden" : ""}`,
      "data-stone-id": stone.id, "data-index": index,
      "data-sneck": Boolean(stone.traits.is_sneck), role: "button", tabindex: "0",
      "aria-label": `Stone ${stone.id}`
    });
    const left = Math.min(...vertices.map(p => p[0])), right = Math.max(...vertices.map(p => p[0]));
    const bottom = Math.min(...vertices.map(p => p[1])), top = Math.max(...vertices.map(p => p[1]));
    const periods = this.wrapDisplay
      ? Array.from({ length: Math.ceil(right / wall.width) - Math.floor(left / wall.width) },
        (_, i) => Math.floor(left / wall.width) + i) : [0];
    if (this.wrapDisplay) {
      const clip = this.svgElement("clipPath", { id: `shape-clip-${stone.id}`, clipPathUnits: "userSpaceOnUse" });
      clip.append(this.svgElement("rect", { x: 0, y: 0, width: wall.width, height: wall.height }));
      group.append(clip);
      group.setAttribute("clip-path", `url(#shape-clip-${stone.id})`);
    }
    for (const period of periods) {
      const offset = period * wall.width;
      const polygon = this.svgElement("polygon", {
        points: vertices.map(([x, y]) => `${x - offset},${wall.height - y}`).join(" "),
        class: "stone", fill: this.colour(stone.id)
      });
      const title = this.svgElement("title", {});
      title.textContent = `Stone ${stone.id} · applied contour; source ${stone.width} × ${stone.height}`;
      polygon.append(title);
      const label = this.svgElement("text", { x: left - offset, y: wall.height - top,
        "data-x": left - offset, "data-y": wall.height - top,
        "data-piece-width": right - left, "data-piece-height": top - bottom, class: "stone-id" });
      label.textContent = stone.id;
      group.append(polygon, label);
    }
    this.svg.append(group);
  }

  /** @param {number|null} id Highlight one logical ID across all its display pieces. */
  setSelection(id, focus = false) {
    this.selectedStoneId = id;
    this.svg.querySelectorAll(".stone-group").forEach(group => {
      group.classList.toggle("selected", Number(group.dataset.stoneId) === id);
    });
    if (focus) this.focusSelectedStone();
  }

  /** @param {number} count Change replay/sneck visibility without generating or redrawing geometry. */
  updateVisibility(count) {
    this.visibleCount = count;
    const hideSnecks = this.stage === "wall" && document.querySelector("#hide-snecks").checked;
    this.svg.querySelectorAll(".stone-group").forEach(group => {
      group.classList.toggle("playback-hidden", Number(group.dataset.index) >= count);
      group.classList.toggle("sneck-hidden", hideSnecks && group.dataset.sneck === "true");
    });
  }

  /** Restore the padded centred fit; zoom-out never proceeds below this scale. */
  fit() {
    if (!this.viewState) return;
    this.stopViewAnimation();
    this.viewState.zoom = 1;
    this.viewState.centerX = this.viewState.extent.x + this.viewState.extent.width / 2;
    this.viewState.centerY = this.viewState.extent.y + this.viewState.extent.height / 2;
    this.applyViewBox();
  }

  /** @param {string} name @param {Object} attributes @returns {SVGElement} Safe SVG factory. */
  svgElement(name, attributes) {
    const element = document.createElementNS(this.ns, name);
    Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
    return element;
  }

  /** @param {Object} wall @returns {Object} Full logical/overhang bounds plus measurement margin. */
  wallExtent(wall) {
    const gutter = Math.max(2, Math.max(wall.width, wall.height) * 0.06);
    const stones = this.wrapDisplay ? [] : wall.stones;
    let left = 0, right = wall.width;
    for (const stone of stones) { left = Math.min(left, stone.x); right = Math.max(right, stone.x + stone.width); }
    if (!this.wrapDisplay) for (const vertices of this.contours?.values() ?? []) {
      for (const [x] of vertices) { left = Math.min(left, x); right = Math.max(right, x); }
    }
    return { x: left - gutter, y: -gutter, width: right - left + 2 * gutter, height: wall.height + 2 * gutter };
  }

  /** Refit a changed source; preserve user navigation during live contour changes. */
  configureView(wall) {
    const extent = this.wallExtent(wall);
    const stones = this.wrapDisplay ? [] : wall.stones;
    const sourceLeft = stones.reduce((x, stone) => Math.min(x, stone.x), 0);
    const sourceRight = stones.reduce((x, stone) => Math.max(x, stone.x + stone.width), wall.width);
    const key = `${wall.width}:${wall.height}:${this.wrapDisplay}:${sourceLeft}:${sourceRight}`;
    if (this.viewState && key === this.viewKey) {
      const previous = this.viewState.extent;
      const fitted = this.viewState.zoom === 1
        && Math.abs(this.viewState.centerX - previous.x - previous.width / 2) < 1e-8
        && Math.abs(this.viewState.centerY - previous.y - previous.height / 2) < 1e-8;
      this.viewState.extent = extent;
      if (fitted) {
        this.viewState.centerX = extent.x + extent.width / 2;
        this.viewState.centerY = extent.y + extent.height / 2;
      }
      return;
    }
    this.stopViewAnimation();
    this.viewKey = key;
    this.viewState = {
      extent,
      zoom: 1,
      centerX: extent.x + extent.width / 2,
      centerY: extent.y + extent.height / 2
    };
  }

  /** @returns {Object} Aspect-correct screen extent in logical drawing coordinates. */
  currentViewBox() {
    // Match the actual viewport aspect, rather than relying on SVG's implicit
    // letterboxing when calculating fit, pointer anchors and containment.
    const bounds = this.svg.getBoundingClientRect();
    const aspect = Math.max(1, bounds.width) / Math.max(1, bounds.height);
    const fitWidth = Math.max(this.viewState.extent.width, this.viewState.extent.height * aspect);
    const width = fitWidth / this.viewState.zoom;
    const height = fitWidth / aspect / this.viewState.zoom;
    return {
      x: this.viewState.centerX - width / 2,
      y: this.viewState.centerY - height / 2,
      width,
      height
    };
  }

  /** Cancel an outstanding centring animation before another gesture changes the camera. */
  stopViewAnimation() {
    if (this.viewAnimation !== null) cancelAnimationFrame(this.viewAnimation);
    this.viewAnimation = null;
  }

  /** @param {number} x @param {number} y Ease to a drawing-space centre; honour reduced motion. */
  animateCenter(x, y) {
    this.stopViewAnimation();
    const startX = this.viewState.centerX;
    const startY = this.viewState.centerY;
    const started = performance.now();
    const duration = matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 260;
    const tick = now => {
      const progress = duration === 0 ? 1 : Math.min(1, (now - started) / duration);
      const eased = 1 - (1 - progress) ** 3;
      this.viewState.centerX = startX + (x - startX) * eased;
      this.viewState.centerY = startY + (y - startY) * eased;
      this.applyViewBox();
      this.viewAnimation = progress < 1 ? requestAnimationFrame(tick) : null;
    };
    this.viewAnimation = requestAnimationFrame(tick);
  }

  /** @returns {boolean} Whether the padded wall is at its containable scale. */
  wallFitsView() {
    return this.viewState.zoom <= 1;
  }

  /** Centre the largest visible piece only when zoomed beyond containment. */
  focusSelectedStone() {
    if (!this.viewState || this.wallFitsView() || this.selectedStoneId === null || this.panStart) return;
    const stone = this.latestState?.wall.stones.find(item => item.id === this.selectedStoneId);
    if (!stone) return;
    const pieces = this.stonePieces(stone, this.latestState.wall);
    const piece = pieces.reduce((largest, item) => item.width > largest.width ? item : largest);
    this.animateCenter(piece.x + piece.width / 2, this.latestState.wall.height - stone.y - stone.height / 2);
  }

  /** Apply camera state and rescale labels/ticks to stable screen-space sizes. */
  applyViewBox() {
    if (!this.viewState) return;
    const view = this.currentViewBox();
    this.svg.setAttribute("viewBox", `${view.x} ${view.y} ${view.width} ${view.height}`);
    if (this.latestState) this.updateStoneLabels(this.latestState.wall);
  }

  /** @param {number} zoom @param {?Object} anchor Cursor-anchored zoom, pulled back toward fit. */
  setZoom(zoom, anchor = null) {
    if (!this.viewState) return;
    this.stopViewAnimation();
    const previousZoom = this.viewState.zoom;
    const before = this.currentViewBox();
    const bounded = Math.max(1, Math.min(8, zoom));
    if (anchor) {
      const ratioX = (anchor.x - before.x) / before.width;
      const ratioY = (anchor.y - before.y) / before.height;
      this.viewState.zoom = bounded;
      const after = this.currentViewBox();
      this.viewState.centerX += anchor.x - (after.x + ratioX * after.width);
      this.viewState.centerY += anchor.y - (after.y + ratioY * after.height);
    } else {
      this.viewState.zoom = bounded;
    }
    if (bounded < previousZoom || bounded === 1) {
      const { extent } = this.viewState;
      const pull = previousZoom > 1 ? (bounded - 1) / (previousZoom - 1) : 0;
      const fitX = extent.x + extent.width / 2;
      const fitY = extent.y + extent.height / 2;
      this.viewState.centerX = fitX + (this.viewState.centerX - fitX) * pull;
      this.viewState.centerY = fitY + (this.viewState.centerY - fitY) * pull;
    }
    this.applyViewBox();
  }

  /** @param {number} clientX @param {number} clientY @returns {DOMPoint} SVG-space pointer. */
  clientToWall(clientX, clientY) {
    return new DOMPoint(clientX, clientY).matrixTransform(this.svg.getScreenCTM().inverse());
  }

  /** @param {Object} stone @param {Object} wall @returns {Array<Object>} Virtual display spans only. */
  stonePieces(stone, wall, wrapped = this.wrapDisplay) {
    if (!wrapped) return [{ x: stone.x, width: stone.width }];

    const pieces = [];
    let x = ((stone.x % wall.width) + wall.width) % wall.width;
    let remaining = stone.width;
    while (remaining > 0) {
      const width = Math.min(remaining, wall.width - x);
      pieces.push({ x, width });
      remaining -= width;
      x = 0;
    }
    return pieces;
  }

  /** @param {number} size @returns {number} Uncluttered 1/2/5 measurement interval. */
  majorTickStep(size) {
    const rough = Math.max(1, size / 10);
    const power = 10 ** Math.floor(Math.log10(rough));
    const scaled = rough / power;
    const multiplier = scaled <= 1 ? 1 : scaled <= 2 ? 2 : scaled <= 5 ? 5 : 10;
    return multiplier * power;
  }

  /** @param {Object} wall @returns {SVGElement} Exterior left/top measurement guides. */
  makeAxes(wall) {
    const axes = this.svgElement("g", { class: "measurement-axes", "aria-hidden": "true" });
    const xStep = this.majorTickStep(wall.width);
    const yStep = this.majorTickStep(wall.height);

    for (let x = 0; x <= wall.width; x += xStep) {
      axes.append(this.svgElement("line", { x1: x, x2: x, y1: 0, y2: 0, class: "axis-tick axis-tick-x", "data-axis-x": x }));
      const label = this.svgElement("text", { class: "axis-label axis-label-x", "data-axis-x": x, "text-anchor": "middle" });
      label.textContent = x;
      axes.append(label);
    }
    for (let y = 0; y < wall.height; y += yStep) {
      const renderedY = wall.height - y;
      axes.append(this.svgElement("line", { x1: 0, x2: 0, y1: renderedY, y2: renderedY, class: "axis-tick axis-tick-y", "data-axis-y": renderedY }));
      const label = this.svgElement("text", { class: "axis-label axis-label-y", "data-axis-y": renderedY, "text-anchor": "end", "dominant-baseline": "middle" });
      label.textContent = y;
      axes.append(label);
    }
    return axes;
  }

  /** @param {Object} wall Show IDs only when every rendered piece can fit its label. */
  updateStoneLabels(wall) {
    const bounds = this.svg.getBoundingClientRect();
    const view = this.viewState ? this.currentViewBox() : { width: wall.width, height: wall.height };
    const scale = Math.min(bounds.width / view.width, bounds.height / view.height);
    if (!Number.isFinite(scale) || scale <= 0) {
      this.svg.classList.remove("show-stone-ids");
      return;
    }
    this.updateAxisMeasurements(scale);
    if (wall.stones.length === 0) {
      this.svg.classList.remove("show-stone-ids");
      return;
    }

    const allFit = wall.stones.every(stone => {
      const labels = [...this.svg.querySelectorAll(`.stone-group[data-stone-id="${stone.id}"] .stone-id`)];
      const estimatedLabelWidth = String(stone.id).length * 6.5 + 5;
      return labels.every(label => Number(label.dataset.pieceWidth) * scale >= estimatedLabelWidth
        && Number(label.dataset.pieceHeight) * scale >= 14);
    });
    this.svg.classList.toggle("show-stone-ids", allFit);
    if (!allFit) return;

    const offset = 2.5 / scale;
    const fontSize = 10 / scale;
    this.svg.querySelectorAll(".stone-id").forEach(label => {
      label.setAttribute("x", Number(label.dataset.x) + offset);
      label.setAttribute("y", Number(label.dataset.y) + offset);
      label.setAttribute("font-size", fontSize);
      label.setAttribute("dominant-baseline", "hanging");
    });
  }

  /** @param {number} scale Maintain tick/label sizes while the world view changes. */
  updateAxisMeasurements(scale) {
    if (!Number.isFinite(scale) || scale <= 0) return;
    const tickLength = 5 / scale;
    const inset = 2.5 / scale;
    const fontSize = 9 / scale;
    this.svg.querySelectorAll(".axis-tick-x").forEach(tick => tick.setAttribute("y2", -tickLength));
    this.svg.querySelectorAll(".axis-tick-y").forEach(tick => tick.setAttribute("x2", -tickLength));
    this.svg.querySelectorAll(".axis-label-x").forEach(label => {
      label.setAttribute("x", Number(label.dataset.axisX));
      label.setAttribute("y", -tickLength - inset);
      label.setAttribute("font-size", fontSize);
    });
    this.svg.querySelectorAll(".axis-label-y").forEach(label => {
      label.setAttribute("x", -tickLength - inset);
      label.setAttribute("y", Number(label.dataset.axisY));
      label.setAttribute("font-size", fontSize);
    });
  }

  /** @param {PointerEvent} event Resolve short click versus drag/hold; recenter fitted walls. */
  finishPan(event) {
    if (!this.panStart || event.pointerId !== this.panStart.pointerId) return;
    event.preventDefault();
    const gesture = this.panStart;
    clearTimeout(gesture.holdTimer);
    this.panStart = null;
    this.svg.classList.remove("panning");
    if (this.svg.hasPointerCapture(event.pointerId)) this.svg.releasePointerCapture(event.pointerId);
    const clicked = event.type === "pointerup" && !gesture.dragging
      && performance.now() - gesture.started < 240
      && Math.hypot(event.clientX - gesture.clientX, event.clientY - gesture.clientY) <= 5;
    if (clicked && gesture.stoneId !== null) {
      this.onSelect(gesture.stoneId, { toggle: true });
    } else if (this.wallFitsView()) {
      const { extent } = this.viewState;
      this.animateCenter(extent.x + extent.width / 2, extent.y + extent.height / 2);
    }
  }
}
