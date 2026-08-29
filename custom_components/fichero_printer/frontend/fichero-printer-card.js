class FicheroPrinterCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._text = "";
    this._copies = 1;
    this._busy = false;
  }

  static getStubConfig() { return {}; }
  static getConfigForm() {
    return {
      schema: [{ name: "entity", selector: { entity: { domain: "sensor", integration: "fichero_printer" } } }],
      computeLabel: () => "Printer status entity",
    };
  }

  setConfig(config) { this._config = config || {}; }
  set hass(hass) {
    this._hass = hass;
    const configured = this._config?.entity;
    this._entityId = configured || Object.keys(hass.states).find((id) =>
      id.startsWith("sensor.") && hass.states[id].attributes.config_entry_id
    );
    this._render();
  }

  getCardSize() { return 5; }

  _escape(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
    })[char]);
  }

  async _call(service, data = {}) {
    const state = this._hass.states[this._entityId];
    if (!state) return;
    this._busy = true;
    this._render();
    try {
      await this._hass.callService("fichero_printer", service, {
        config_entry_id: state.attributes.config_entry_id, ...data,
      });
    } catch (error) {
      const event = new Event("hass-notification", { bubbles: true, composed: true });
      event.detail = { message: error?.message || String(error) };
      this.dispatchEvent(event);
    } finally {
      this._busy = false;
      this._render();
    }
  }

  _render() {
    if (!this._hass || !this.shadowRoot) return;
    const state = this._entityId && this._hass.states[this._entityId];
    if (!state) {
      this.shadowRoot.innerHTML = `<ha-card><div class="missing">No Fichero printer status entity found.</div></ha-card>`;
      return;
    }
    const connected = state.attributes.connected === true;
    const favorites = Array.isArray(state.attributes.favorites) ? state.attributes.favorites : [];
    const disabled = this._busy ? "disabled" : "";
    this.shadowRoot.innerHTML = `
      <style>
        ha-card { padding: 18px; }
        .heading { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:16px; }
        h2 { font-size:1.25rem; margin:0; }
        .status { display:flex; align-items:center; gap:7px; color:var(--secondary-text-color); text-transform:capitalize; }
        .dot { width:10px; height:10px; border-radius:50%; background:${connected ? "var(--success-color,#43a047)" : "var(--error-color,#db4437)"}; }
        textarea { box-sizing:border-box; width:100%; min-height:76px; resize:vertical; border:1px solid var(--divider-color); border-radius:10px; padding:12px; background:var(--card-background-color); color:var(--primary-text-color); font:inherit; }
        .row { display:flex; align-items:center; gap:10px; margin-top:12px; flex-wrap:wrap; }
        button { cursor:pointer; border:0; border-radius:10px; padding:10px 14px; color:var(--primary-text-color); background:var(--secondary-background-color); font:inherit; font-weight:500; }
        button.primary { color:var(--text-primary-color); background:var(--primary-color); }
        button:disabled { opacity:.55; cursor:wait; }
        label { display:flex; align-items:center; gap:8px; color:var(--secondary-text-color); }
        input[type=number] { width:64px; padding:8px; border:1px solid var(--divider-color); border-radius:8px; background:var(--card-background-color); color:var(--primary-text-color); }
        .favorites { margin-top:16px; border-top:1px solid var(--divider-color); padding-top:14px; }
        .favorites-title { font-size:.9rem; color:var(--secondary-text-color); margin-bottom:8px; }
        .error { margin:12px 0; padding:10px 12px; color:var(--error-color,#db4437); background:color-mix(in srgb,var(--error-color,#db4437) 10%,transparent); border-radius:8px; }
        .favorite { display:inline-flex; align-items:stretch; margin:0 8px 8px 0; background:var(--secondary-background-color); border-radius:10px; overflow:hidden; }
        .favorite button { border-radius:0; margin:0; }
        .favorite .remove { padding:8px; color:var(--secondary-text-color); }
        .missing { padding:20px; }
      </style>
      <ha-card>
        <div class="heading">
          <div><h2>Fichero label printer</h2><div class="status"><span class="dot"></span>${this._escape(state.state)}</div></div>
          <button id="connection" ${disabled}>${connected ? "Disconnect" : "Connect"}</button>
        </div>
        ${state.attributes.last_error ? `<div class="error">${this._escape(state.attributes.last_error)}</div>` : ""}
        <textarea id="text" maxlength="500" placeholder="Text for your label">${this._escape(this._text)}</textarea>
        <div class="row">
          <label>Labels <input id="copies" type="number" min="1" max="100" value="${this._copies}"></label>
          <button class="primary" id="print" ${disabled}>Print</button>
          <button id="today" ${disabled}>Print today</button>
          <button id="favorite" ${disabled}>☆ Save favorite</button>
        </div>
        ${favorites.length ? `<div class="favorites"><div class="favorites-title">Favorites — click to print</div>${favorites.map((favorite, index) => `
          <span class="favorite"><button class="favorite-print" data-index="${index}" ${disabled}>${this._escape(favorite)}</button><button class="remove" title="Remove favorite" data-index="${index}" ${disabled}>×</button></span>
        `).join("")}</div>` : ""}
      </ha-card>`;

    const text = this.shadowRoot.getElementById("text");
    const copies = this.shadowRoot.getElementById("copies");
    text.addEventListener("input", (event) => { this._text = event.target.value; });
    copies.addEventListener("input", (event) => { this._copies = Math.max(1, Math.min(100, Number(event.target.value) || 1)); });
    this.shadowRoot.getElementById("connection").onclick = () => this._call(connected ? "disconnect" : "connect");
    this.shadowRoot.getElementById("print").onclick = () => this._call("print_label", { text: this._text, copies: this._copies });
    this.shadowRoot.getElementById("favorite").onclick = () => this._call("save_favorite", { text: this._text });
    this.shadowRoot.getElementById("today").onclick = () => {
      const now = new Date();
      const value = `${String(now.getDate()).padStart(2, "0")}-${String(now.getMonth() + 1).padStart(2, "0")}-${now.getFullYear()}`;
      this._text = value;
      this._call("print_label", { text: value, copies: this._copies });
    };
    this.shadowRoot.querySelectorAll(".favorite-print").forEach((button) => {
      button.onclick = () => this._call("print_label", { text: favorites[Number(button.dataset.index)], copies: this._copies });
    });
    this.shadowRoot.querySelectorAll(".remove").forEach((button) => {
      button.onclick = () => this._call("delete_favorite", { text: favorites[Number(button.dataset.index)] });
    });
  }
}

if (!customElements.get("fichero-printer-card")) customElements.define("fichero-printer-card", FicheroPrinterCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "fichero-printer-card",
  name: "Fichero Label Printer",
  description: "Connect, fit text, print copies, and use favorite label shortcuts.",
  preview: true,
});
