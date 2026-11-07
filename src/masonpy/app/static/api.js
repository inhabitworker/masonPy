/** JSON and attachment transport. Callers own status text, state and stale replies. */
export class ApiClient {
  /** Keep browser-specific transport wording out of the notification bar. */
  async fetchResponse(path, options = {}) {
    try {
      return await fetch(path, options);
    } catch (cause) {
      console.error(`Workbench connection: ${options.method ?? "GET"} ${path}`, cause);
      throw new Error(`Could not contact the local workbench (${options.method ?? "GET"} ${path}). Check the server connection; the operation may have completed.`);
    }
  }

  /** Report unreadable/HTML responses separately from backend validation errors. */
  async readJSON(response, path) {
    let data;
    try {
      data = await response.json();
    } catch (cause) {
      console.error(`Workbench response: ${path}`, cause);
      throw new Error(`Could not read the workbench response (${path}${response.status ? "; HTTP " + response.status : ""}). Refresh to check the current result.`);
    }
    if (!data || typeof data !== "object" || Array.isArray(data)) {
      throw new Error(`Unexpected workbench response (${path}); expected a JSON object.`);
    }
    if (!response.ok) {
      const error = new Error(typeof data.error === "string" ? data.error : response.statusText || `Request failed (${path}).`);
      error.rejected = true;
      throw error;
    }
    return data;
  }

  /** @returns {Promise<Object>} Parsed JSON, or throws the backend error message. */
  async request(path, options = {}) {
    const response = await this.fetchResponse(path, options);
    return this.readJSON(response, path);
  }

  /** Fetch an attachment without interpreting a binary STL or SVG body as JSON. */
  async download(payload, path = "/api/export") {
    const response = await this.fetchResponse(path, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
    });
    if (!response.ok) {
      await this.readJSON(response, path);
    }
    const filename = response.headers.get("Content-Disposition")?.match(/filename="([^"\r\n]+)"/)?.[1] ?? "masonpy-export";
    try {
      return { blob: await response.blob(), filename };
    } catch (cause) {
      console.error("Workbench export transfer", cause);
      throw new Error("The export download was interrupted. Retry Export; the applied result is unchanged.");
    }
  }

  /** @param {string} path @returns {Promise<Object>} Current resource snapshot. */
  get(path) { return this.request(path); }

  /** @param {string} path @param {Object} payload @returns {Promise<Object>} API response. */
  post(path, payload = {}) {
    return this.request(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
  }
}
