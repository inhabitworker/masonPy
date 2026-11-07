/** Refresh only the inspected downstream stages, against one captured Wall revision. */
export class StageRefresh {
  constructor(read, settings, apply) {
    Object.assign(this, { read, settings, apply, sequence: 0, running: null });
  }

  cancel() {
    this.sequence++;
    if (this.running) this.running.key = null;
  }

  /** Coalesce identical visits and serialize replacements; never regenerate the Wall. */
  ensure(stage) {
    const source = this.read();
    if (stage === "wall" || !source?.wall.stones.length) {
      this.cancel();
      return Promise.resolve(false);
    }
    const shape = this.settings("shape");
    const build = stage === "3d" ? this.settings("3d") : null;
    const wallRevision = source.wall_revision;
    const key = JSON.stringify([stage, wallRevision, shape, build]);
    if (this.running?.key === key) return this.running.promise;
    const sequence = ++this.sequence;
    const previous = this.running?.promise;
    const valid = () => this.sequence === sequence && this.read()?.wall_revision === wallRevision;
    const run = async () => {
      if (previous) { try { await previous; } catch { /* Newer visits can retry. */ } }
      if (!valid()) return false;
      let state = this.read();
      if (!state.shape.current || !sameSettings(shape, state.shape.result?.settings)) {
        if (!await this.apply("shape", { ...shape, source_revision: wallRevision }, { automatic: true })) return false;
      }
      if (!valid()) return false;
      state = this.read();
      if (!state.shape.current || !sameSettings(shape, state.shape.result?.settings)) return false;
      if (stage === "3d" && (!state.build.current || !sameSettings(build, state.build.settings))) {
        if (!await this.apply("build", { ...build, source_revision: state.shape.revision }, { automatic: true })) return false;
      }
      const latest = this.read();
      return valid() && latest.shape.current && sameSettings(shape, latest.shape.result?.settings)
        && (stage !== "3d" || (latest.build.current && sameSettings(build, latest.build.settings)));
    };
    const promise = run().finally(() => {
      if (this.running?.sequence === sequence) this.running = null;
    });
    this.running = { key, sequence, promise };
    return promise;
  }
}

/** Compare requested settings with an applied snapshot, independently of object key order. */
export function sameSettings(requested, applied) {
  return Boolean(applied) && Object.entries(requested).every(([key, value]) => value === applied[key]);
}
