const AGENT_ID = "conversation.domashnii_asistent_claude";
const PANEL_CONVERSATION_ID = "claude-homemate-persistent-panel";

class ClaudeHistoryPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._ready = false;
    this._busy = false;
  }

  set hass(value) {
    this._hass = value;
    if (!this._ready) {
      this._renderShell();
      this._ready = true;
      void this._loadHistory();
    }
  }

  set panel(value) {
    this._panel = value;
  }

  connectedCallback() {
    if (this._hass && !this._ready) {
      this._renderShell();
      this._ready = true;
      void this._loadHistory();
    }
  }

  _renderShell() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          min-height: 100%;
          color: var(--primary-text-color);
          background: var(--primary-background-color);
          font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
        }
        .page { max-width: 900px; margin: 0 auto; padding: 20px; }
        .header { display: flex; gap: 12px; align-items: center; margin-bottom: 12px; }
        .header h1 { flex: 1; margin: 0; font-size: 26px; }
        .note {
          padding: 12px 14px; margin-bottom: 14px; border-radius: 12px;
          background: var(--secondary-background-color);
          color: var(--secondary-text-color);
          line-height: 1.45;
        }
        .history {
          min-height: 360px; max-height: calc(100vh - 330px); overflow-y: auto;
          display: flex; flex-direction: column; gap: 10px; padding: 12px;
          border-radius: 14px; background: var(--card-background-color);
          box-shadow: var(--ha-card-box-shadow, 0 2px 6px rgba(0,0,0,.15));
        }
        .message { max-width: 82%; padding: 10px 12px; border-radius: 14px; line-height: 1.45; white-space: pre-wrap; overflow-wrap: anywhere; }
        .user { align-self: flex-end; background: var(--primary-color); color: var(--text-primary-color, white); border-bottom-right-radius: 4px; }
        .assistant { align-self: flex-start; background: var(--secondary-background-color); border-bottom-left-radius: 4px; }
        .meta { display: block; margin-top: 6px; opacity: .72; font-size: 11px; }
        .composer { display: grid; grid-template-columns: 1fr auto; gap: 10px; margin-top: 14px; }
        textarea {
          min-height: 72px; resize: vertical; box-sizing: border-box; width: 100%;
          border: 1px solid var(--divider-color); border-radius: 12px; padding: 12px;
          color: var(--primary-text-color); background: var(--card-background-color);
          font: inherit;
        }
        button {
          border: 0; border-radius: 12px; padding: 10px 16px; cursor: pointer;
          color: var(--text-primary-color, white); background: var(--primary-color);
          font: inherit; font-weight: 600;
        }
        button.secondary { color: var(--primary-text-color); background: var(--secondary-background-color); }
        button:disabled { opacity: .55; cursor: wait; }
        .status { min-height: 22px; padding: 7px 2px 0; color: var(--secondary-text-color); font-size: 13px; }
        @media (max-width: 600px) {
          .page { padding: 10px; }
          .history { max-height: calc(100vh - 350px); }
          .message { max-width: 92%; }
          .composer { grid-template-columns: 1fr; }
        }
      </style>
      <div class="page">
        <div class="header">
          <h1>Claude HomeMate</h1>
          <button id="refresh" class="secondary" type="button">Оновити</button>
        </div>
        <div class="note">
          Тут показана збережена міжвіконна історія. Для голосового вводу відкрийте
          Assist через кнопку у верхній панелі. У Chrome мікрофон працює через
          <b>http://localhost:8123</b> або через HTTPS/застосунок Home Assistant.
        </div>
        <div id="history" class="history" aria-live="polite"></div>
        <div class="composer">
          <textarea id="message" aria-label="Повідомлення Claude" placeholder="Напишіть запит до домашнього асистента…"></textarea>
          <button id="send" type="button">Надіслати</button>
        </div>
        <div id="status" class="status"></div>
      </div>
    `;
    this.shadowRoot.getElementById("refresh").addEventListener("click", () => {
      void this._loadHistory();
    });
    this.shadowRoot.getElementById("send").addEventListener("click", () => {
      void this._sendMessage();
    });
    this.shadowRoot.getElementById("message").addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        void this._sendMessage();
      }
    });
  }

  async _loadHistory() {
    if (!this._hass) return;
    this._setStatus("Завантажую історію…");
    try {
      const result = await this._hass.callWS({
        type: "claude_code_conversation/history",
        limit: 200,
      });
      this._renderHistory(result.records || []);
      this._setStatus(`Збережено повідомлень: ${(result.records || []).length}`);
    } catch (error) {
      this._setStatus(`Не вдалося завантажити історію: ${String(error)}`);
    }
  }

  _renderHistory(records) {
    const container = this.shadowRoot.getElementById("history");
    container.replaceChildren();
    if (!records.length) {
      const empty = document.createElement("div");
      empty.className = "note";
      empty.textContent = "Історія поки порожня.";
      container.appendChild(empty);
      return;
    }
    for (const record of records) {
      const message = document.createElement("div");
      const isUser = record.role === "user";
      message.className = `message ${isUser ? "user" : "assistant"}`;
      const content = document.createElement("span");
      content.textContent = record.content || "";
      const meta = document.createElement("span");
      meta.className = "meta";
      const timestamp = record.timestamp ? new Date(record.timestamp) : null;
      meta.textContent = `${isUser ? "Ви" : "Claude"} · ${timestamp && !Number.isNaN(timestamp.valueOf()) ? timestamp.toLocaleString("uk-UA") : "час невідомий"}`;
      message.append(content, meta);
      container.appendChild(message);
    }
    container.scrollTop = container.scrollHeight;
  }

  async _sendMessage() {
    if (!this._hass || this._busy) return;
    const input = this.shadowRoot.getElementById("message");
    const text = input.value.trim();
    if (!text) return;
    this._busy = true;
    this.shadowRoot.getElementById("send").disabled = true;
    this._setStatus("Claude готує відповідь…");
    try {
      await this._hass.callWS({
        type: "conversation/process",
        text,
        language: "uk",
        agent_id: AGENT_ID,
        conversation_id: PANEL_CONVERSATION_ID,
      });
      input.value = "";
      await this._loadHistory();
    } catch (error) {
      this._setStatus(`Помилка запиту: ${String(error)}`);
    } finally {
      this._busy = false;
      this.shadowRoot.getElementById("send").disabled = false;
      input.focus();
    }
  }

  _setStatus(text) {
    this.shadowRoot.getElementById("status").textContent = text;
  }
}

if (!customElements.get("claude-history-panel")) {
  customElements.define("claude-history-panel", ClaudeHistoryPanel);
}
