/** Session wall choices and plain JSON attachments; Python validates all loaded data. */
export class WallLibrary {
  constructor(onChange, onSave, onError) {
    Object.assign(this, { onChange, onError, state: null });
    this.select = document.querySelector('#wall-history');
    this.input = document.querySelector('#wall-file');
    document.querySelector('#load-wall').addEventListener('click', () => this.input.click());
    document.querySelector('#save-wall').addEventListener('click', onSave);
    this.select.addEventListener('change', () => {
      if (this.select.value) this.onChange('history', {record_id:this.select.value, source_revision:this.state.wall_revision});
    });
    this.input.addEventListener('change', () => this.loadFile(this.input.files[0]));
  }

  async loadFile(file) {
    if (!file || !this.state) return;
    const revision = this.state.wall_revision;
    try {
      if (file.size > 32 * 1024 * 1024) throw new Error('Wall JSON must be no larger than 32 MiB.');
      const record = JSON.parse(await file.text());
      if (!record || typeof record !== 'object' || Array.isArray(record)) throw new Error('Wall JSON must be an object.');
      await this.onChange('load', {record, source_revision:revision});
    } catch (error) { this.onError(`Load wall: ${error.message}`); }
    finally { this.input.value = ''; }
  }

  render(state) {
    this.state = state;
    const entries = state.history?.entries ?? [];
    const key = JSON.stringify(entries);
    if (key !== this.key) {
      const empty = document.createElement('option');
      empty.value = '';
      empty.textContent = 'Session history';
      this.select.replaceChildren(empty, ...entries.map(entry => {
        const option = document.createElement('option');
        option.value = entry.id;
        option.textContent = entry.label;
        return option;
      }));
      this.key = key;
    }
    this.select.value = state.history?.active ?? '';
  }
}

/** Start a browser download without changing the applied result or navigation. */
export function saveAttachment(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
