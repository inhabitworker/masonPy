import { Tabs } from "./tabs.js";

/** Events and lazy JSON inspector, sharing logical stone selection with both viewers. */
export class DetailsPanel {

  /** @param {ApiClient} api @param {Function} onSelect */
  constructor(api, onSelect) {
    this.api = api;
    this.eventList = document.querySelector("#events");
    this.latestState = null;
    this.selectedStoneId = null;
    this.playbackVisibleCount = 0;
    this.infoRevision = 0;
    this.infoScope = null;
    this.expandedInfoPaths = new Set();
    this.diagnosticMessage = null;
    this.followLatest = true;
    this.scrollFrame = null;
    this.eventList.addEventListener("scroll", () => this.recordScroll());
    this.eventList.addEventListener("click", event => {
      const link = event.target.closest(".event-stone-link");
      if (!link) return;
      event.preventDefault();
      onSelect(Number(link.dataset.stoneId), { toggle: true, scrollLog: false });
    });
    this.tabs = new Tabs({ events: document.querySelector("#events-tab"), info: document.querySelector("#info-tab") }, name => {
      document.querySelector("#events").hidden = name !== "events";
      document.querySelector("#info").hidden = name !== "info";
      this.setSelection(this.selectedStoneId, false);
    });
  }

  /** @param {Object} data @param {number} visibleStoneCount Replace history from the Python session. */
  render(data, visibleStoneCount) {
    this.prepareEvents("wall");
    this.stageData = null;
    this.latestState = data;
    this.playbackVisibleCount = visibleStoneCount;
    this.diagnosticMessage = null;
    const { events } = data;
    this.eventList.replaceChildren(...events.map((event, index) => {
      const li = document.createElement("li");
      li.dataset.stoneId = event.stone.id;
      li.hidden = index >= visibleStoneCount;
      const link = document.createElement("a");
      link.href = `#stone-${event.stone.id}`;
      link.className = "event-stone-link";
      link.dataset.stoneId = event.stone.id;
      link.textContent = `${event.stone.id}.`;
      link.setAttribute("aria-label", `Stone ${event.stone.id}`);
      const description = document.createElement("span");
      description.className = "event-description";
      description.dataset.summary = `Added at [${event.stone.x}, ${event.stone.y}]: ${event.stone.width} × ${event.stone.height}${event.stone.traits.is_sneck ? " · sneck" : ""}`;
      description.dataset.full = event.explanation;
      li.append(link, description);
      return li;
    }));
    if (data.failure) {
      const item = document.createElement("li");
      item.className = "construction-failure";
      item.textContent = data.failure.message;
      this.eventList.append(item);
    }
    if (data.wall_report) {
      const item = document.createElement('li');
      item.className = 'wall-analysis-summary';
      item.hidden = visibleStoneCount < data.wall.stones.length;
      item.textContent = data.wall_report.summary;
      this.eventList.append(item);
    }
    this.renderAnalysis(data.wall_report);

    document.querySelector("#event-count").textContent = `${events.length} placement${events.length === 1 ? "" : "s"}`;
    this.settleEvents();
  }

  /** Show a downstream stage's own log and inherited description without live-source queries. */
  renderStage(stage, metadata, snapshot, geometry = null) {
    this.renderAnalysis(null);
    this.prepareEvents(stage);
    this.infoRevision++;
    this.stageData = { stage, metadata, snapshot, geometry };
    this.eventList.replaceChildren(...metadata.events.map(message => {
      const item = document.createElement("li");
      item.className = "diagnostic-message";
      item.textContent = message;
      return item;
    }));
    if (!metadata.events.length) {
      const item = document.createElement("li");
      item.className = "diagnostic-message";
      item.textContent = stage === "shape" ? "No Shape applied yet." : "No 3D build yet.";
      this.eventList.append(item);
    }
    document.querySelector("#event-count").textContent = metadata.current ? "Current result"
      : snapshot ? "Previous result · stale" : "No result";
    this.refreshInfo();
    this.settleEvents();
  }

  /** Compact full-specimen metrics use the exact report produced by the batch runner. */
  renderAnalysis(report) {
    const panel = document.querySelector('#wall-analysis');
    panel.hidden = !report;
    if (!report) return;
    const metrics = [
      ['Coverage', `${(report.fill*100).toFixed(1)}%`], ['Stones', report.stone_count],
      ['Snecks', `${report.sneck_count} (${(report.sneck_share*100).toFixed(1)}%) · ${report.deliberate_snecks} deliberate`],
      ['Sneck area', `${(report.sneck_area_share*100).toFixed(1)}% of placed area`],
      ['Joint stack', `${report.max_joint_stack} / ${report.joint_stack_limit ?? 'off'}`],
      ['Longest joint', `${report.longest_joint} units`],
      ['Sneck aspect', report.max_sneck_aspect ? `${Number(report.max_sneck_aspect.toFixed(2))}:1 max` : '—'],
      ['Layout checks', report.invariant_errors.length ? `${report.invariant_errors.length} issue(s)` : 'Within limits'],
    ];
    document.querySelector('#analysis-metrics').replaceChildren(...metrics.map(([label,value]) => {
      const row = document.createElement('div'), key = document.createElement('dt'), item = document.createElement('dd');
      key.textContent = label; item.textContent = value; row.append(key,item); return row;
    }));
    for (const [role,colour] of Object.entries(report.colours)) {
      const swatch = document.querySelector(`#analysis-legend .${role}`);
      if (swatch) swatch.style.backgroundColor = colour;
    }
  }

  /** A new placement action resumes following; manual scrolling may pause it. */
  beginGeneration() {
    this.followLatest = true;
  }

  /** Remember reading position; scrolling back to the bottom resumes following. */
  recordScroll() {
    if (this.updatingEvents) return;
    this.savedScrollTop = this.eventList.scrollTop;
    this.followLatest = this.eventList.scrollHeight - this.savedScrollTop - this.eventList.clientHeight <= 24;
  }

  /** Preserve manual inspection through a rebuild, including its scroll events. */
  prepareEvents(scope) {
    if (this.eventScope !== scope) this.followLatest = true;
    this.eventScope = scope;
    this.savedScrollTop = this.eventList.scrollTop;
    this.updatingEvents = true;
  }

  /** Scroll after event text and the selected explanation have been laid out. */
  settleEvents() {
    if (this.scrollFrame !== null) cancelAnimationFrame(this.scrollFrame);
    this.scrollFrame = requestAnimationFrame(() => {
      this.scrollFrame = null;
      if (!this.eventList.hidden) this.eventList.scrollTop = this.followLatest
        ? this.eventList.scrollHeight : this.savedScrollTop ?? this.eventList.scrollTop;
      this.updatingEvents = false;
    });
  }

  /** @param {number|null} id Expand only the selected event and refresh contextual Info. */
  setSelection(id, scrollLog = false) {
    this.selectedStoneId = id;
    this.eventList.querySelectorAll("li").forEach(item => {
      const selected = item.dataset.stoneId !== undefined && Number(item.dataset.stoneId) === id;
      item.classList.toggle("selected", selected);
      const description = item.querySelector(".event-description");
      if (description) description.textContent = selected ? description.dataset.full : description.dataset.summary;
    });
    this.refreshInfo();
    if (scrollLog && id !== null && !this.eventList.hidden) {
      const item = this.eventList.querySelector(`li[data-stone-id="${id}"]`);
      if (item) {
        const top = item.getBoundingClientRect().top - this.eventList.getBoundingClientRect().top + this.eventList.scrollTop;
        this.eventList.scrollTop = Math.max(0, top - (this.eventList.clientHeight - item.offsetHeight) / 2);
        this.savedScrollTop = this.eventList.scrollTop;
        this.followLatest = false;
      }
    }
    this.settleEvents();
  }

  /** @param {number} count Hide future replay events while retaining their original data. */
  updateVisibility(count) {
    this.playbackVisibleCount = count;
    this.eventList.querySelectorAll("li[data-stone-id]").forEach((item, index) => { item.hidden = index >= count; });
    const summary = this.eventList.querySelector('.wall-analysis-summary');
    if (summary) summary.hidden = count < this.latestState.wall.stones.length;
  }

  /** @param {string} message Append one explicit diagnostic report, replacing its predecessor. */
  report(message) {
    this.diagnosticMessage = message;
    this.renderDiagnosticMessage();
  }

  /** @param {string} key @param {*} value @returns {HTMLElement} Lazily expandable safe data tree. */
  infoNode(key, value, path, root = false) {
    if (value === null || typeof value !== "object") {
      const leaf = document.createElement("div");
      leaf.className = "info-leaf";
      leaf.textContent = `${key}: ${JSON.stringify(value)}`;
      return leaf;
    }
    const node = document.createElement("details");
    const summary = document.createElement("summary");
    const entries = Object.entries(value);
    summary.textContent = `${key} ${Array.isArray(value) ? `[${entries.length}]` : `{${entries.length}}`}`;
    node.append(summary);
    let populated = false;
    const populate = () => {
      if (populated) return;
      populated = true;
      entries.forEach(([childKey, childValue]) => node.append(this.infoNode(childKey, childValue, `${path}/${childKey}`)));
    };
    node.addEventListener("toggle", () => {
      if (node.open) { this.expandedInfoPaths.add(path); populate(); }
      else this.expandedInfoPaths.delete(path);
    });
    if (root || this.expandedInfoPaths.has(path)) { populate(); node.open = true; }
    return node;
  }

  /** Fetch current wall/stone analytics lazily; discard stale selection replies. */
  async refreshInfo() {
    const revision = ++this.infoRevision;
    const panel = document.querySelector("#info");
    if (panel.hidden) return;
    if (this.stageData) {
      const { stage, metadata, snapshot, geometry } = this.stageData;
      const id = this.selectedStoneId;
      const treatment = geometry?.stones?.find(stone => stone.id === id)?.treatment;
      const data = id === null ? { ...metadata, result: snapshot }
        : { stage, current: metadata.current, stone_id: id,
            source: snapshot?.source?.stones.find(stone => stone.id === id),
            contour: snapshot?.stones?.find(stone => stone.id === id),
            ...(treatment ? { treatment } : {}),
            source_configuration: snapshot?.source_configuration ?? metadata.source_configuration,
            settings: metadata.settings ?? snapshot?.settings ?? { joint_width: snapshot?.joint_width } };
      panel.replaceChildren(this.infoNode(stage, data, stage, true));
      return;
    }
    if (!this.latestState) return;
    const scope = this.selectedStoneId === null ? "wall" : `stone ${this.selectedStoneId}`;
    if (scope !== this.infoScope) { this.expandedInfoPaths.clear(); panel.textContent = "Loading…"; }
    this.infoScope = scope;
    try {
      const data = await this.api.post("/api/info", {
        stone_id: this.selectedStoneId, visible_count: this.playbackVisibleCount
      });
      if (revision !== this.infoRevision) return;
      panel.replaceChildren(this.infoNode(scope, data, scope, true));
    } catch (error) {
      if (revision === this.infoRevision) panel.textContent = error.message;
    }
  }

  /** Render a snapshot report without duplicating it during incremental updates. */
  renderDiagnosticMessage() {
    this.prepareEvents(this.eventScope);
    this.eventList.querySelector(".diagnostic-message")?.remove();
    if (this.diagnosticMessage) {
      const item = document.createElement("li");
      item.className = "diagnostic-message";
      item.textContent = this.diagnosticMessage;
      this.eventList.append(item);
    }
    this.settleEvents();
  }
}
