/** Read-only overlay requests; the Python library owns all joint calculations. */
export class WallDiagnostics {
  /** @param {ApiClient} api @param {WallViewer2D} viewer @param {Function} snapshot */
  constructor(api, viewer, snapshot, onReport, onError) {
    Object.assign(this, { api, viewer, snapshot, onReport, onError });
    this.revision = 0;
    for (const id of ["show-seams", "show-horizontal-joints", "logical-wrap"]) {
      document.querySelector(`#${id}`).addEventListener("change", () => this.refresh());
    }
    document.querySelector("#report-seams").addEventListener("click", () => this.refresh(true));
  }

  /** @param {boolean} report Explicit reports log once; incremental overlays stay quiet. */
  async refresh(report = false) {
    const revision = ++this.revision;
    const { state, visibleCount } = this.snapshot();
    const svg = this.viewer.svg;
    svg.querySelectorAll(".seam-overlay, .horizontal-joint-overlay").forEach(node => node.remove());
    const showVertical = document.querySelector("#show-seams").checked;
    const showHorizontal = document.querySelector("#show-horizontal-joints").checked;
    const summary = document.querySelector("#seam-summary");
    summary.textContent = "";
    if (!state || (!showVertical && !showHorizontal && !report && visibleCount === state.wall.stones.length)) return;
    try {
      const data = await this.api.post("/api/diagnostics", {
        wrap_x: document.querySelector("#logical-wrap").checked,
        visible_count: visibleCount, report
      });
      if (revision !== this.revision) return;
      const wall = state.wall;
      if (showVertical || report) summary.textContent = `Max stack: ${data.max_stack} · limit: ${data.stack_limit ?? "off"}`;
      if (showVertical) {
        for (const seam of data.seams) {
          for (const x of seam.x === 0 ? [0, wall.width] : [seam.x]) {
            this.line({ x1: x, x2: x, y1: wall.height - seam.y, y2: wall.height - seam.y - seam.length },
              "seam-overlay", `Stack ${seam.stack_count} (${seam.left_count} left, ${seam.right_count} right); ${seam.length} units`);
          }
        }
      }
      if (showHorizontal) {
        for (const run of data.horizontal_joints) {
          // Overlay spans always fold into the reference grid, even with flat overhang display.
          for (const piece of this.viewer.stonePieces({ x: run.x, width: run.length }, wall, true)) {
            this.line({ x1: piece.x, x2: piece.x + piece.width, y1: wall.height - run.y, y2: wall.height - run.y },
              "horizontal-joint-overlay", `Horizontal joint at ${run.y}: ${run.length} units`);
          }
        }
      }
      if (report) this.onReport(`${data.message} Configured stack limit: ${data.stack_limit ?? "disabled"}.`);
    } catch (error) {
      if (revision !== this.revision) return;
      const message = `Seam diagnostics unavailable: ${error.message}`;
      summary.textContent = message;
      // Automatic overlays must not replace the confirmed action's result.
      // Explicit Report seams failures still belong in the action bar.
      if (report) this.onError(message);
    }
  }

  /** @param {Object} coordinates @param {string} style @param {string} description Add a non-interactive line. */
  line(coordinates, style, description) {
    const line = this.viewer.svgElement("line", { ...coordinates, class: style });
    const title = this.viewer.svgElement("title", {});
    title.textContent = description;
    line.append(title);
    this.viewer.svg.append(line);
  }
}
