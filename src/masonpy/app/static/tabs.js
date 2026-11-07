/** Small accessible tab strip; component callbacks decide what becomes visible. */
export class Tabs {
  /** @param {Object<string, HTMLElement>} buttons @param {Function} onSelect */
  constructor(buttons, onSelect) {
    this.buttons = buttons;
    this.onSelect = onSelect;
    const names = Object.keys(buttons);
    for (const [name, button] of Object.entries(buttons)) {
      button.addEventListener("click", () => this.select(name));
      button.addEventListener("keydown", event => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        const index = names.indexOf(name);
        const target = event.key === "Home" ? names[0]
          : event.key === "End" ? names.at(-1)
          : names[(index + (event.key === "ArrowLeft" ? -1 : 1) + names.length) % names.length];
        this.select(target);
        buttons[target].focus();
      });
    }
  }

  /** @param {string} name Activate a tab without changing application state. */
  select(name) {
    for (const [key, button] of Object.entries(this.buttons)) {
      button.setAttribute("aria-selected", key === name);
      button.tabIndex = key === name ? 0 : -1;
    }
    this.onSelect(name);
  }
}
