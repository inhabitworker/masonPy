/** Stored 3D build presentation; the pipeline coordinator owns source refresh. */
export class ProjectionPanel {
  constructor(colour, onSelect) {
    Object.assign(this, { colour, onSelect });
    this.viewer = null;
    this.loading = null;
    this.active = false;
    this.snapshot = null;
    this.revision = null;
    this.displayedRevision = null;
    this.selectedId = null;
    this.message = document.querySelector("#three-status");
    document.querySelector("#three-fit").addEventListener("click", () => this.viewer?.fit());
  }

  /** Accept a previously built mesh; GPU buffers are created only when displayed. */
  render(snapshot, revision, selectedId, visibleCount) {
    this.snapshot = snapshot;
    this.revision = revision;
    this.selectedId = selectedId;
    this.visibleCount = visibleCount ?? snapshot?.shape?.source.stones.length ?? 0;
    if (this.active) this.display();
  }

  updateVisibility(count, selectedId) {
    this.visibleCount = count;
    this.selectedId = selectedId;
    if (this.active) this.sync();
  }

  sync() {
    if (this.viewer && this.snapshot?.geometry) {
      const wall = this.snapshot.shape.source;
      this.viewer.sync(wall, this.visibleCount, this.selectedId, false);
    }
  }

  display() {
    if (!this.snapshot?.geometry) {
      if (this.viewer?.renderer) this.viewer.renderer.domElement.hidden = true;
      this.message.textContent = "No 3D preview yet. Generate a wall, or check the stage feedback.";
      return;
    }
    if (!this.viewer) return;
    if (this.viewer.renderer) this.viewer.renderer.domElement.hidden = false;
    if (this.displayedRevision !== this.revision) {
      this.viewer.rebuild(this.snapshot.geometry, this.snapshot.shape.source, this.colour);
      this.displayedRevision = this.revision;
    }
    this.message.textContent = "";
    this.sync();
  }

  /** Lazy-load the renderer without processing, rebuilding or modifying stage settings. */
  async select(active) {
    this.active = active;
    if (!active) return;
    if (!this.snapshot?.geometry) { this.display(); return; }
    try {
      if (!this.viewer) {
        this.message.textContent = "Loading 3D viewer…";
        this.loading ??= import("./viewer3d.js").then(({ WallViewer3D }) => {
          this.viewer = new WallViewer3D(document.querySelector("#three-wrap"),
            id => this.onSelect(id, { toggle: true }));
        });
        await this.loading;
      }
      if (!this.active) return;
      this.viewer.resize();
      this.display();
    } catch (error) {
      this.message.textContent = `3D viewer unavailable: ${error.message}. CDN access and WebGL2 are required.`;
      this.loading = null;
    }
  }
}
