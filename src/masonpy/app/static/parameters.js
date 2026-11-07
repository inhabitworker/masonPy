/** Generator schema/drafts and their form; no placement or viewer logic. */
export class ParameterPanel {

  /** @param {Function} onReset Receives a validated form submission payload. */
  constructor(onReset) {
    this.toolbar = document.querySelector("#toolbar");
    this.generatorSelect = document.querySelector("#generator");
    this.generatorParameterContainer = document.querySelector("#generator-parameters");
    this.resetButton = document.querySelector("#reset");
    this.syncNote = document.querySelector("#sync-note");
    this.activeConfig = null;
    this.generatorDefinitions = new Map();
    this.generatorDrafts = new Map();
    this.selectedGeneratorId = null;
    this.toolbar.addEventListener("submit", event => {
      event.preventDefault();
      onReset(this.resetPayload());
    });
    this.toolbar.addEventListener("input", () => this.updateSyncIndicator());
    this.toolbar.addEventListener("change", () => this.updateSyncIndicator());
    this.generatorSelect.addEventListener("change", () => this.changeGenerator());
  }

  /** @param {Object} data Track the applied server configuration without discarding drafts. */
  render(data) {
    if (!this.activeConfig) {
      document.querySelector("#width").value = data.wall.width;
      document.querySelector("#height").value = data.wall.height;
    }
    this.populateGeneratorControls(data);
    this.activeConfig = this.activeConfigFrom(data);
    this.updateSyncIndicator();
  }

  /** Preserve the departing generator's draft before showing another schema. */
  changeGenerator() {
    if (this.selectedGeneratorId) {
      this.generatorDrafts.set(this.selectedGeneratorId, this.readGeneratorParameters());

  }
  this.selectedGeneratorId = this.generatorSelect.value;
  const definition = this.generatorDefinitions.get(this.selectedGeneratorId);
  const values = this.generatorDrafts.get(this.selectedGeneratorId)
    ?? (this.activeConfig?.generator === this.selectedGeneratorId ? this.activeConfig.parameters : {});
  this.renderGeneratorParameters(definition, values);
  this.updateSyncIndicator();
  }

  /** @param {Object} data @returns {Object} Applied configuration, distinct from drafts. */
  activeConfigFrom(data) {
    return {
      generator: data.generator.id,
      width: data.wall.width,
      height: data.wall.height,
      parameters: { ...data.generator.parameters }
    };
  }

  /** Loading/selecting a specimen restores its applied recipe into the Wall controls. */
  restore(data) {
    this.populateGeneratorControls(data);
    this.selectedGeneratorId = data.generator.id;
    this.generatorSelect.value = data.generator.id;
    document.querySelector('#width').value = data.wall.width;
    document.querySelector('#height').value = data.wall.height;
    this.renderGeneratorParameters(this.generatorDefinitions.get(data.generator.id), data.generator.parameters);
    this.activeConfig = this.activeConfigFrom(data);
    this.updateSyncIndicator();
  }

  /** @param {Object} data Initialise grouped choices and Python-owned schemas once. */
  populateGeneratorControls(data) {
    if (this.generatorDefinitions.size > 0) return;

    const groups = new Map();
    data.generators.forEach(definition => {
      this.generatorDefinitions.set(definition.id, definition);
      if (!groups.has(definition.category)) {
        const group = document.createElement("optgroup");
        group.label = definition.category;
        groups.set(definition.category, group);
        this.generatorSelect.append(group);
      }
      const option = document.createElement("option");
      option.value = definition.id;
      option.textContent = definition.label;
      groups.get(definition.category).append(option);
    });

    this.selectedGeneratorId = data.generator.id;
    this.generatorSelect.value = this.selectedGeneratorId;
    this.renderGeneratorParameters(
      this.generatorDefinitions.get(this.selectedGeneratorId),
      data.generator.parameters
    );
  }

  /** @param {Object} definition @param {Object} values Build bounded schema inputs. */
  renderGeneratorParameters(definition, values = {}) {
    this.generatorParameterContainer.replaceChildren();
    const advanced = document.querySelector("#advanced-parameters");
    advanced.replaceChildren();
    definition.parameters.forEach(parameter => {
      const label = document.createElement("label");
      label.textContent = parameter.label;
      if (parameter.description) label.title = parameter.description;

      const input = document.createElement("input");
      input.type = "number";
      input.id = `parameter-${parameter.id}`;
      input.dataset.generatorParameter = parameter.id;
      input.min = parameter.minimum;
      if (parameter.maximum !== null && parameter.maximum !== undefined) input.max = parameter.maximum;
      input.step = parameter.step;
      input.value = values[parameter.id] ?? parameter.default;
      if (parameter.toggle) {
        input.type = "checkbox";
        input.checked = Number(input.value) === 1;
      }
      label.append(input);
      (parameter.advanced ? advanced : this.generatorParameterContainer).append(label);
    });
  }

  /** @returns {Object<string, number>} Current draft values, including numeric toggles. */
  readGeneratorParameters() {
    return Object.fromEntries(
      [...this.toolbar.querySelectorAll("[data-generator-parameter]")]
        .map(input => [input.dataset.generatorParameter, input.type === "checkbox" ? Number(input.checked) : Number(input.value)])
    );
  }

  /** @returns {Object} Explicit reset request; editing controls alone never mutates a wall. */
  resetPayload() {
    return {
      generator: this.generatorSelect.value,
      width: Number(document.querySelector("#width").value),
      height: Number(document.querySelector("#height").value),
      parameters: this.readGeneratorParameters()
    };
  }

  /** @returns {boolean} Whether the displayed wall differs from the parameter draft. */
  parametersAreDirty() {
    if (!this.activeConfig) return false;
    const selected = this.resetPayload();
    if (
      selected.generator !== this.activeConfig.generator
      || selected.width !== this.activeConfig.width
      || selected.height !== this.activeConfig.height
    ) return true;

    const selectedKeys = Object.keys(selected.parameters);
    const activeKeys = Object.keys(this.activeConfig.parameters);
    return selectedKeys.length !== activeKeys.length
      || selectedKeys.some(key => selected.parameters[key] !== this.activeConfig.parameters[key]);
  }

  /** Refresh the dirty notice and collapsed configuration summary. */
  updateSyncIndicator() {
    const dirty = this.parametersAreDirty();
    this.syncNote.hidden = !dirty;
    this.resetButton.textContent = dirty ? "Apply & reset" : "Reset";
    this.toolbar.classList.toggle("parameters-dirty", dirty);
    const definition = this.generatorDefinitions.get(this.generatorSelect.value);
    if (definition) {
      const values = this.readGeneratorParameters();
      document.querySelector("#parameter-summary").textContent = `${definition.category} / ${definition.label} · ${document.querySelector("#width").value} × ${document.querySelector("#height").value} · `
        + definition.parameters.map(p => `${p.label}: ${values[p.id]}`).join(" · ");
    }
  }
}
