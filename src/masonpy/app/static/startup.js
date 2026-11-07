import { WorkbenchApp } from "./app.js";

// Module scripts run after HTML parsing. Components bind first, then load state.
const app = new WorkbenchApp();
app.start().catch(error => app.showError(error.message));
