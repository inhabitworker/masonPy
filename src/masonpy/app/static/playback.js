/** Shallow playback clock: visibility only; never places, removes or edits stones. */
export class Playback {
  /** @param {number} duration Total animation time in milliseconds. */
  constructor(duration = 3200) {
    this.duration = duration;
    this.frame = null;
  }

  /** Cancel a running clock before a real mutation or another replay. */
  cancel() {
    if (this.frame !== null) cancelAnimationFrame(this.frame);
    this.frame = null;
  }

  /** @param {number} total @param {number} direction @param {Function} onFrame @param {Function} onComplete */
  play(total, direction, onFrame, onComplete) {
    this.cancel();
    let started = null;
    const tick = timestamp => {
      started ??= timestamp;
      const progress = Math.min(1, (timestamp - started) / this.duration);
      const count = Math.ceil(progress * total);
      onFrame(direction === 1 ? count : total - count);
      if (progress < 1) this.frame = requestAnimationFrame(tick);
      else { this.frame = null; onComplete(); }
    };
    this.frame = requestAnimationFrame(tick);
  }
}
