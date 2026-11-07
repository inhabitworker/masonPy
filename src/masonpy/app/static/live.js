/** Debounced, serial downstream processing: retain only the newest pending edit. */
export class LiveUpdates {
  constructor(apply, allowed, onPending, onError, delay = 160) {
    Object.assign(this, { apply, allowed, onPending, onError, delay });
    this.pending = null;
    this.running = false;
    this.timer = null;
  }

  schedule(action, payload) {
    this.pending = { action, payload };
    this.arm();
    this.notify();
  }

  arm() {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = setTimeout(() => { this.timer = null; this.flush(); }, this.delay);
  }

  cancel() {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
    this.pending = null;
    this.notify();
  }

  notify() { this.onPending(this.running || this.pending !== null); }

  async flush() {
    if (this.running || !this.pending) return;
    const task = this.pending;
    this.pending = null;
    if (!this.allowed(task.action)) { this.notify(); return; }
    this.running = true;
    this.notify();
    try { await this.apply(task.action, task.payload); }
    catch (error) { this.onError(error); }
    finally {
      this.running = false;
      this.notify();
      if (this.pending && this.timer === null) this.arm();
    }
  }
}
