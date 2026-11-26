const STRINGS = {
  en: {
    title: "Label printer",
    connect: "Connect",
    disconnect: "Disconnect",
    placeholder: "Text for your label, e.g. [mdi:fridge] Milk",
    labels: "Labels",
    multiline: "Multiline",
    multilineHint: "Keep line breaks as typed",
    print: "Print",
    printing: "Printing…",
    printDate: "Print date",
    saveFavorite: "Save favorite",
    favorites: "Favorites — tap to print",
    removeFavorite: "Remove favorite",
    insert: "Insert",
    icon: "Icon",
    date: "Date",
    preview: "Preview",
    previewEmpty: "Type something to see the label",
    help: "Icons: [mdi:fridge] or [m3o:kitchen] · QR: [qr:https://…] · Barcode: [barcode:12345] · Emoji work too",
    missing: "No Fichero printer status entity found.",
    entity: "Printer status entity",
    titleField: "Title",
    states: {
      disconnected: "Disconnected",
      powering_on: "Powering on",
      connecting: "Connecting",
      connected: "Connected",
      printing: "Printing",
      calibrating: "Calibrating",
    },
  },
  de: {
    title: "Etikettendrucker",
    connect: "Verbinden",
    disconnect: "Trennen",
    placeholder: "Text für dein Etikett, z. B. [mdi:fridge] Milch",
    labels: "Anzahl",
    multiline: "Mehrzeilig",
    multilineHint: "Zeilenumbrüche beibehalten",
    print: "Drucken",
    printing: "Druckt…",
    printDate: "Datum drucken",
    saveFavorite: "Als Favorit",
    favorites: "Favoriten — antippen zum Drucken",
    removeFavorite: "Favorit entfernen",
    insert: "Einfügen",
    icon: "Icon",
    date: "Datum",
    preview: "Vorschau",
    previewEmpty: "Tippe einen Text, um das Etikett zu sehen",
    help: "Icons: [mdi:fridge] oder [m3o:kitchen] · QR: [qr:https://…] · Barcode: [barcode:12345] · Emojis gehen auch",
    missing: "Keine Statusentität eines Fichero-Druckers gefunden.",
    entity: "Statusentität des Druckers",
    titleField: "Titel",
    states: {
      disconnected: "Getrennt",
      powering_on: "Schaltet ein",
      connecting: "Verbinde",
      connected: "Verbunden",
      printing: "Druckt",
      calibrating: "Misst Lücke ein",
    },
  },
};

const INSERTS = [
  { key: "icon", icon: "mdi:emoticon-outline", text: "[mdi:]", cursor: 5 },
  { key: "qr", icon: "mdi:qrcode", label: "QR", text: "[qr:]", cursor: 4 },
  { key: "barcode", icon: "mdi:barcode", label: "Barcode", text: "[barcode:]", cursor: 9 },
  { key: "date", icon: "mdi:calendar-today" },
];

// Renderer messages from the integration, translated for the preview line.
const ERRORS_DE = [
  [/^(Could not connect to the printer: )?Printer not found - is it switched on\?$/, "Drucker nicht gefunden – ist er eingeschaltet?"],
  [/^Could not connect to the printer: (.+)$/, "Keine Verbindung zum Drucker: $1"],
  [/^Printer is not ready \(paper, cover, heat, or status error\)$/, "Drucker nicht bereit (Papier, Deckel, Hitze oder Statusfehler)"],
  [/^Printer did not respond$/, "Der Drucker antwortet nicht"],
  [/^Unknown icon: (.+)$/, "Unbekanntes Icon: $1"],
  [/^Text cannot fit on this label$/, "Der Text passt nicht auf das Etikett"],
  [/^Text cannot be empty$/, "Kein Text"],
  [/^QR content is too long for this label$/, "Der QR-Inhalt ist zu lang für das Etikett"],
  [/^Barcode content is too long for this label$/, "Der Barcode ist zu lang für das Etikett"],
  [/^Barcodes support printable ASCII characters only$/, "Barcodes können nur einfache Zeichen (ASCII) enthalten"],
  [/^(qr|barcode) content cannot be empty$/, "Inhalt für $1 fehlt"],
  [/^Label text is limited to (\d+) characters$/, "Höchstens $1 Zeichen"],
];

function translateError(message, lang) {
  if (lang !== "de") return message;
  for (const [pattern, replacement] of ERRORS_DE) {
    if (pattern.test(message)) return message.replace(pattern, replacement);
  }
  return message;
}

function language(hass) {
  const lang = (hass?.locale?.language || hass?.language || "en").toLowerCase();
  return lang.startsWith("de") ? "de" : "en";
}

function today(lang) {
  const now = new Date();
  const dd = String(now.getDate()).padStart(2, "0");
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  return lang === "de" ? `${dd}.${mm}.${now.getFullYear()}` : `${dd}-${mm}-${now.getFullYear()}`;
}

class FicheroPrinterCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._text = "";
    this._copies = 1;
    this._multiline = false;
    this._busy = false;
    this._hiddenFavorites = new Set();
    this._previewTimer = null;
    this._previewSeq = 0;
    this._previewKey = null;
    this._built = false;
  }

  static getStubConfig() { return {}; }
  static getConfigForm() {
    return {
      schema: [
        { name: "entity", selector: { entity: { domain: "sensor", integration: "fichero_printer" } } },
        { name: "title", selector: { text: {} } },
      ],
      computeLabel: (schema) => {
        const t = STRINGS[language(document.querySelector("home-assistant")?.hass)];
        return schema.name === "title" ? t.titleField : t.entity;
      },
    };
  }

  setConfig(config) {
    this._config = config || {};
    if (this._built) this._update();
  }

  set hass(hass) {
    this._hass = hass;
    this._t = STRINGS[language(hass)];
    const configured = this._config?.entity;
    this._entityId = configured || Object.keys(hass.states).find((id) => {
      const attributes = hass.states[id].attributes;
      return id.startsWith("sensor.") && attributes.config_entry_id && attributes.label_length_mm !== undefined;
    });
    if (!this._built) this._build();
    this._update();
  }

  getCardSize() { return 7; }
  getGridOptions() { return { columns: 12, min_columns: 6 }; }

  get _state() { return this._entityId && this._hass?.states[this._entityId]; }

  _escape(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
    })[char]);
  }

  _notify(message) {
    const event = new Event("hass-notification", { bubbles: true, composed: true });
    event.detail = { message };
    this.dispatchEvent(event);
  }

  async _call(service, data = {}) {
    const state = this._state;
    if (!state) return false;
    this._busy = true;
    this._update();
    try {
      await this._hass.callService("fichero_printer", service, {
        config_entry_id: state.attributes.config_entry_id, ...data,
      });
      return true;
    } catch (error) {
      this._notify(translateError(error?.message || String(error), language(this._hass)));
      return false;
    } finally {
      this._busy = false;
      this._update();
    }
  }

  _build() {
    const t = this._t;
    this.shadowRoot.innerHTML = `
      <style>
        [hidden] { display: none !important; }
        ha-card { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
        .missing { padding: 4px; }
        .heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
        .title { display: flex; align-items: center; gap: 10px; min-width: 0; }
        .title ha-icon { color: var(--state-icon-color, var(--primary-color)); }
        h2 { font-size: 1.15rem; font-weight: 500; margin: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .status { display: flex; align-items: center; gap: 6px; font-size: .85rem; color: var(--secondary-text-color); }
        .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--error-color, #db4437); flex: none; }
        .dot.on { background: var(--success-color, #43a047); }
        .dot.busy { background: var(--warning-color, #ffa600); animation: pulse 1s infinite alternate; }
        @keyframes pulse { to { opacity: .35; } }
        button { cursor: pointer; border: 0; border-radius: 999px; padding: 8px 14px; font: inherit; font-weight: 500;
          display: inline-flex; align-items: center; gap: 6px; color: var(--primary-text-color);
          background: var(--secondary-background-color); }
        button ha-icon { --mdc-icon-size: 18px; }
        button.primary { color: var(--text-primary-color, #fff); background: var(--primary-color); padding: 10px 18px; }
        button.ghost { background: transparent; border: 1px solid var(--divider-color); }
        button:disabled { opacity: .55; cursor: wait; }
        .error { padding: 10px 12px; color: var(--error-color, #db4437); border-radius: 10px;
          background: color-mix(in srgb, var(--error-color, #db4437) 10%, transparent); }
        .preview { display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 14px 8px;
          border-radius: 12px; background: color-mix(in srgb, var(--primary-text-color) 6%, transparent); }
        .label { position: relative; width: min(100%, 360px); background: #fff; border-radius: 8px;
          box-shadow: 0 1px 3px rgba(0,0,0,.25); display: flex; align-items: center; justify-content: center;
          aspect-ratio: 30 / 14; overflow: hidden; }
        .label img { width: 100%; image-rendering: pixelated; display: block; }
        .label .empty { color: #8a8a8a; font-size: .85rem; padding: 0 12px; text-align: center; }
        .preview-msg { font-size: .8rem; color: var(--secondary-text-color); min-height: 1em; text-align: center; }
        .preview-msg.bad { color: var(--error-color, #db4437); }
        textarea { box-sizing: border-box; width: 100%; min-height: 64px; resize: vertical;
          border: 1px solid var(--divider-color); border-radius: 10px; padding: 10px 12px;
          background: var(--card-background-color); color: var(--primary-text-color); font: inherit; }
        textarea:focus { outline: 2px solid var(--primary-color); outline-offset: -1px; }
        .chips { display: flex; flex-wrap: wrap; gap: 6px; }
        .chips button { padding: 6px 12px; font-size: .85rem; }
        .help { font-size: .78rem; color: var(--secondary-text-color); line-height: 1.4; }
        .row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
        .spacer { flex: 1; }
        .stepper { display: inline-flex; align-items: center; border: 1px solid var(--divider-color); border-radius: 999px; }
        .stepper button { background: transparent; padding: 6px 10px; border-radius: 999px; }
        .stepper span { min-width: 2ch; text-align: center; font-weight: 500; }
        .caption { font-size: .85rem; color: var(--secondary-text-color); }
        label.toggle { display: inline-flex; align-items: center; gap: 6px; color: var(--secondary-text-color); font-size: .9rem; cursor: pointer; }
        .favorites { border-top: 1px solid var(--divider-color); padding-top: 12px; display: flex; flex-direction: column; gap: 8px; }
        .favorite { display: inline-flex; align-items: stretch; border-radius: 999px; overflow: hidden;
          background: var(--secondary-background-color); }
        .favorite button { border-radius: 0; background: transparent; }
        .favorite .remove { padding: 6px 10px; color: var(--secondary-text-color); }
      </style>
      <ha-card>
        <div class="content"></div>
      </ha-card>`;
    const content = this.shadowRoot.querySelector(".content");
    content.style.display = "contents";
    content.innerHTML = `
      <div class="missing" hidden></div>
      <div class="main">
        <div class="heading">
          <div class="title">
            <ha-icon icon="mdi:printer-pos"></ha-icon>
            <div><h2 id="title"></h2><div class="status"><span class="dot"></span><span id="state"></span></div></div>
          </div>
          <button id="connection" class="ghost"></button>
        </div>
        <div class="error" id="error" hidden></div>
        <div class="preview">
          <div class="label" id="label"><span class="empty" id="empty"></span><img id="image" alt="" hidden></div>
          <div class="preview-msg" id="previewMsg"></div>
        </div>
        <textarea id="text" maxlength="500"></textarea>
        <div class="chips" id="chips"></div>
        <div class="help" id="help"></div>
        <div class="row">
          <div class="stepper"><button id="minus" aria-label="-">−</button><span id="copies">1</span><button id="plus" aria-label="+">+</button></div>
          <span class="caption" id="copiesLabel"></span>
          <label class="toggle"><input id="multiline" type="checkbox"> <span id="multilineLabel"></span></label>
          <span class="spacer"></span>
          <button id="favorite" class="ghost"><ha-icon icon="mdi:star-outline"></ha-icon><span></span></button>
          <button id="print" class="primary"><ha-icon icon="mdi:printer"></ha-icon><span></span></button>
        </div>
        <div class="favorites" id="favorites" hidden></div>
      </div>`;
    const main = content.querySelector(".main");
    main.style.display = "contents";

    const $ = (id) => this.shadowRoot.getElementById(id);
    const text = $("text");
    text.value = this._text;
    text.addEventListener("input", (event) => { this._text = event.target.value; this._schedulePreview(); });
    $("multiline").addEventListener("change", (event) => { this._multiline = event.target.checked; this._schedulePreview(0); });
    $("minus").onclick = () => { this._copies = Math.max(1, this._copies - 1); this._update(); };
    $("plus").onclick = () => { this._copies = Math.min(100, this._copies + 1); this._update(); };
    $("connection").onclick = () => this._call(this._state?.attributes.connected ? "disconnect" : "connect");
    $("print").onclick = () => this._print(this._text);
    $("favorite").onclick = () => this._call("save_favorite", { text: this._text });

    const chips = $("chips");
    for (const insert of INSERTS) {
      const button = document.createElement("button");
      button.dataset.key = insert.key;
      button.innerHTML = `<ha-icon icon="${insert.icon}"></ha-icon><span></span>`;
      button.onclick = () => this._insert(insert);
      chips.appendChild(button);
    }
    this._built = true;
  }

  _insert(insert) {
    const area = this.shadowRoot.getElementById("text");
    const snippet = insert.key === "date" ? today(language(this._hass)) : insert.text;
    const start = area.selectionStart ?? area.value.length;
    const end = area.selectionEnd ?? area.value.length;
    const before = area.value.slice(0, start);
    const pad = before && !/\s$/.test(before) && insert.key !== "date" ? " " : "";
    area.value = before + pad + snippet + area.value.slice(end);
    const cursor = start + pad.length + (insert.cursor ?? snippet.length);
    area.focus();
    area.setSelectionRange(cursor, cursor);
    this._text = area.value;
    this._schedulePreview();
  }

  async _print(text) {
    if (!text.trim()) return;
    await this._call("print_label", { text, copies: this._copies, multiline: this._multiline });
  }

  _currentPreviewKey() {
    return JSON.stringify([this._text, this._multiline, this._state?.attributes.label_length_mm]);
  }

  _schedulePreview(delay = 350) {
    clearTimeout(this._previewTimer);
    this._previewTimer = setTimeout(() => this._refreshPreview(), delay);
  }

  async _refreshPreview() {
    const state = this._state;
    const $ = (id) => this.shadowRoot.getElementById(id);
    if (!state || !this._built) return;
    const key = this._currentPreviewKey();
    if (key === this._previewKey) return;
    this._previewKey = key;
    const t = this._t;
    const image = $("image"), empty = $("empty"), message = $("previewMsg");
    $("label").style.aspectRatio = `${state.attributes.label_length_mm || 30} / 14`;
    if (!this._text.trim()) {
      image.hidden = true; empty.hidden = false; empty.textContent = t.previewEmpty;
      message.textContent = ""; message.classList.remove("bad");
      return;
    }
    const seq = ++this._previewSeq;
    try {
      const result = await this._hass.callWS({
        type: "fichero_printer/preview",
        config_entry_id: state.attributes.config_entry_id,
        text: this._text,
        multiline: this._multiline,
      });
      if (seq !== this._previewSeq) return;
      image.src = result.image; image.hidden = false; empty.hidden = true;
      message.textContent = ""; message.classList.remove("bad");
    } catch (error) {
      if (seq !== this._previewSeq) return;
      message.textContent = translateError(error?.message || String(error), language(this._hass));
      message.classList.add("bad");
    }
  }

  _update() {
    if (!this._built || !this._hass) return;
    const t = this._t;
    const $ = (id) => this.shadowRoot.getElementById(id);
    const state = this._state;
    const missing = this.shadowRoot.querySelector(".missing");
    const main = this.shadowRoot.querySelector(".main");
    if (!state) {
      missing.hidden = false; missing.textContent = t.missing; main.style.display = "none";
      return;
    }
    missing.hidden = true; main.style.display = "contents";
    const connected = state.attributes.connected === true;
    const busyState = ["powering_on", "connecting", "printing", "calibrating"].includes(state.state);
    $("title").textContent = this._config?.title || t.title;
    $("state").textContent = t.states[state.state] || state.state;
    const dot = this.shadowRoot.querySelector(".dot");
    dot.classList.toggle("on", connected && !busyState);
    dot.classList.toggle("busy", busyState);
    const connection = $("connection");
    connection.textContent = connected ? t.disconnect : t.connect;
    const error = $("error");
    error.hidden = !state.attributes.last_error;
    error.textContent = translateError(state.attributes.last_error || "", language(this._hass));

    const area = $("text");
    area.placeholder = t.placeholder;
    $("help").textContent = t.help;
    $("copies").textContent = this._copies;
    $("copiesLabel").textContent = t.labels;
    $("multiline").checked = this._multiline;
    $("multilineLabel").textContent = t.multiline;
    $("multilineLabel").parentElement.title = t.multilineHint;
    $("favorite").querySelector("span").textContent = t.saveFavorite;
    $("print").querySelector("span").textContent = this._busy || state.state === "printing" ? t.printing : t.print;
    for (const button of $("chips").children) {
      const insert = INSERTS.find((item) => item.key === button.dataset.key);
      button.querySelector("span").textContent = insert.label || t[insert.key];
    }
    const disabled = this._busy;
    for (const id of ["connection", "print", "favorite"]) $(id).disabled = disabled;

    // Favorites: re-render only when the list changes.
    const stored = Array.isArray(state.attributes.favorites) ? state.attributes.favorites : [];
    for (const favorite of this._hiddenFavorites) {
      if (!stored.includes(favorite)) this._hiddenFavorites.delete(favorite);
    }
    const favorites = stored.map((text, index) => ({ text, index })).filter(({ text }) => !this._hiddenFavorites.has(text));
    const favoritesKey = JSON.stringify([favorites, disabled, t.favorites]);
    if (favoritesKey !== this._favoritesKey) {
      this._favoritesKey = favoritesKey;
      const box = $("favorites");
      box.hidden = !favorites.length;
      box.innerHTML = favorites.length ? `<div class="caption">${this._escape(t.favorites)}</div><div class="chips">${favorites.map(({ text, index }) => `
        <span class="favorite"><button class="favorite-print" data-index="${index}" ${disabled ? "disabled" : ""}>${this._escape(text)}</button><button class="remove" title="${this._escape(t.removeFavorite)}" aria-label="${this._escape(t.removeFavorite)}" data-index="${index}" ${disabled ? "disabled" : ""}>×</button></span>`).join("")}</div>` : "";
      box.querySelectorAll(".favorite-print").forEach((button) => {
        button.onclick = () => this._print(stored[Number(button.dataset.index)]);
      });
      box.querySelectorAll(".remove").forEach((button) => {
        button.onclick = async (event) => {
          event.stopPropagation();
          const index = Number(button.dataset.index);
          const favorite = stored[index];
          if (await this._call("delete_favorite", { index })) {
            this._hiddenFavorites.add(favorite);
            this._favoritesKey = null;
            this._update();
          }
        };
      });
    }
    if (this._currentPreviewKey() !== this._previewKey) {
      this._schedulePreview(this._previewKey === null ? 0 : 350);
    }
  }
}

if (!customElements.get("fichero-printer-card")) customElements.define("fichero-printer-card", FicheroPrinterCard);
window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "fichero-printer-card")) {
  window.customCards.push({
    type: "fichero-printer-card",
    name: "Fichero Label Printer",
    description: "Print labels with icons, emoji, QR codes and barcodes, with a live preview.",
    preview: true,
  });
}
