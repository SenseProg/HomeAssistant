// v0.5.0: оптимістичний рендер, ватчдог очікування, «Не чекати», динамічний
// пошук агента й пайплайна замість зашитих ідентифікаторів.
const AGENT_ID_FALLBACK = "conversation.domashnii_asistent_claude";
const PIPELINE_ID_FALLBACK = "01kz4r9qs1qzp5hsvg9vc7c0m0";
const PANEL_CONVERSATION_ID = "claude-homemate-persistent-panel";
const TARGET_SAMPLE_RATE = 16000;
const MAX_RECORDING_SECONDS = 120;
// Бекенд обриває виклик Claude через 120 с (CONF_TIMEOUT). Даємо запас на
// чергу глобального лока і збір контексту, після чого перестаємо тримати
// композер заблокованим: відповідь однаково доїде в історію.
const REQUEST_SOFT_TIMEOUT_MS = 150000;
const ANSWER_POLL_INTERVAL_MS = 20000;
const ANSWER_POLL_MAX_MS = 600000;

class ClaudeHistoryPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._ready = false;
    this._busy = false;
    this._voiceState = "idle";
    this._audioChunks = [];
    this._levels = [];
    this._elapsedSeconds = 0;
    this._recordingStartedAt = 0;
    this._timer = null;
    this._stream = null;
    this._audioContext = null;
    this._source = null;
    this._processor = null;
    this._silentGain = null;
    this._unsubscribeVoice = null;
    this._voiceReadyResolve = null;
    this._voiceReadyReject = null;
    this._transcript = "";
    this._assistantResponse = "";
    this._ttsUrl = "";
    this._archivedPcmBytes = null;
    this._recordings = [];
    // Текстовий запит: локальне відлуння і контроль очікування.
    this._lastRecords = [];
    this._localEcho = null;
    this._awaitingAnswer = false;
    this._pendingRestoreText = "";
    this._requestToken = 0;
    this._sendStartedAt = 0;
    this._pollTimer = null;
    this._pollUntil = 0;
    this._pipelineIdResolved = null;
  }

  set hass(value) {
    this._hass = value;
    if (!this._ready) {
      this._renderShell();
      this._ready = true;
      void this._loadHistory();
      void this._loadVoiceRecordings();
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
      void this._loadVoiceRecordings();
    }
  }

  disconnectedCallback() {
    this._stopCaptureTracks();
    this._clearTimer();
    this._stopAnswerPolling();
    void this._closeVoiceSubscription();
  }

  _renderShell() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block; min-height: 100%; color: var(--primary-text-color);
          background: var(--primary-background-color);
          font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
        }
        .page { max-width: 900px; margin: 0 auto; padding: 20px; }
        .header { display: flex; gap: 12px; align-items: center; margin-bottom: 12px; }
        .header h1 { flex: 1; margin: 0; font-size: 26px; }
        .note {
          padding: 12px 14px; margin-bottom: 14px; border-radius: 12px;
          background: var(--secondary-background-color); color: var(--secondary-text-color);
          line-height: 1.45;
        }
        .archive {
          margin-bottom: 14px; padding: 12px 14px; border-radius: 14px;
          background: var(--card-background-color); border: 1px solid var(--divider-color);
        }
        .archive-head { display: flex; align-items: center; gap: 10px; }
        .archive-head h2 { flex: 1; margin: 0; font-size: 17px; }
        .recording-list { display: grid; gap: 8px; margin-top: 10px; }
        .recording-row {
          display: grid; grid-template-columns: 1fr auto; align-items: center; gap: 10px;
          padding: 9px 10px; border-radius: 10px; background: var(--secondary-background-color);
        }
        .recording-meta { color: var(--secondary-text-color); font-size: 13px; line-height: 1.4; }
        .recording-actions { display: flex; flex-wrap: wrap; gap: 6px; }
        .recording-actions button { padding: 7px 10px; font-size: 13px; }
        .archive-empty { color: var(--secondary-text-color); font-size: 13px; }
        #archive-audio { width: 100%; margin-top: 10px; }
        .history {
          min-height: 300px; max-height: calc(100vh - 390px); overflow-y: auto;
          display: flex; flex-direction: column; gap: 10px; padding: 12px;
          border-radius: 14px; background: var(--card-background-color);
          box-shadow: var(--ha-card-box-shadow, 0 2px 6px rgba(0,0,0,.15));
        }
        .message {
          max-width: 82%; padding: 10px 12px; border-radius: 14px; line-height: 1.45;
          white-space: pre-wrap; overflow-wrap: anywhere;
        }
        .user {
          align-self: flex-end; background: var(--primary-color);
          color: var(--text-primary-color, white); border-bottom-right-radius: 4px;
        }
        .assistant {
          align-self: flex-start; background: var(--secondary-background-color);
          border-bottom-left-radius: 4px;
        }
        .meta { display: block; margin-top: 6px; opacity: .72; font-size: 11px; }
        .composer { display: grid; grid-template-columns: 1fr auto; gap: 10px; margin-top: 14px; }
        .composer-actions { display: flex; flex-direction: column; gap: 8px; }
        textarea {
          min-height: 76px; resize: vertical; box-sizing: border-box; width: 100%;
          border: 1px solid var(--divider-color); border-radius: 12px; padding: 12px;
          color: var(--primary-text-color); background: var(--card-background-color); font: inherit;
        }
        button {
          border: 0; border-radius: 12px; padding: 10px 16px; cursor: pointer;
          color: var(--text-primary-color, white); background: var(--primary-color);
          font: inherit; font-weight: 600;
        }
        button.secondary { color: var(--primary-text-color); background: var(--secondary-background-color); }
        button.danger { color: white; background: var(--error-color, #db4437); }
        button:disabled { opacity: .55; cursor: wait; }
        .status { min-height: 22px; padding: 7px 2px 0; color: var(--secondary-text-color); font-size: 13px; }
        .message.pending { opacity: .85; }
        .typing { display: inline-flex; gap: 5px; align-items: center; padding: 3px 0; }
        .typing i {
          width: 7px; height: 7px; border-radius: 50%;
          background: var(--secondary-text-color); opacity: .3;
          animation: typing-blink 1.2s infinite;
        }
        .typing i:nth-child(2) { animation-delay: .2s; }
        .typing i:nth-child(3) { animation-delay: .4s; }
        @keyframes typing-blink { 40% { opacity: 1; } }
        #unwait { display: none; }
        #unwait.visible { display: block; }
        .voice-card {
          display: none; margin-top: 14px; padding: 16px; border-radius: 16px;
          background: var(--card-background-color); border: 1px solid var(--divider-color);
          box-shadow: var(--ha-card-box-shadow, 0 2px 6px rgba(0,0,0,.15));
        }
        .voice-card.visible { display: block; }
        .voice-head { display: flex; align-items: center; gap: 10px; }
        .voice-title { flex: 1; font-size: 17px; font-weight: 650; }
        .record-dot { width: 12px; height: 12px; border-radius: 50%; background: #8b8b8b; }
        .recording .record-dot { background: #ef5350; animation: pulse 1.2s infinite; }
        .voice-time { font-variant-numeric: tabular-nums; font-size: 18px; font-weight: 650; }
        @keyframes pulse { 50% { opacity: .28; transform: scale(.82); } }
        .wave-wrap {
          margin: 14px 0 10px; height: 72px; border-radius: 12px; overflow: hidden;
          background: color-mix(in srgb, var(--primary-background-color) 76%, var(--primary-color));
        }
        canvas { width: 100%; height: 72px; display: block; }
        .voice-hint { color: var(--secondary-text-color); line-height: 1.4; margin-bottom: 12px; }
        .voice-controls { display: flex; flex-wrap: wrap; gap: 8px; }
        .voice-result {
          display: none; margin: 12px 0; padding: 12px; border-radius: 10px;
          background: var(--secondary-background-color); line-height: 1.45;
        }
        .voice-result.visible { display: block; }
        .voice-result b { display: block; margin-bottom: 4px; }
        audio { width: 100%; margin-top: 10px; }
        @media (max-width: 600px) {
          .page { padding: 10px; }
          .history { max-height: calc(100vh - 430px); }
          .message { max-width: 92%; }
          .composer { grid-template-columns: 1fr; }
          .composer-actions { flex-direction: row; }
          .composer-actions button { flex: 1; }
          .voice-controls button { flex: 1 1 42%; }
          .recording-row { grid-template-columns: 1fr; }
          .recording-actions button { flex: 1; }
        }
      </style>
      <div class="page">
        <div class="header">
          <h1>Claude HomeMate</h1>
          <button id="refresh" class="secondary" type="button">Оновити</button>
        </div>
        <div class="note">
          Тут зберігається історія розмов. Голосовий запис не надсилається автоматично:
          натисніть <b>«Зупинити запис»</b>, прослухайте візуальний результат і окремо
          натисніть <b>«Надіслати запис»</b>. Максимальна тривалість — 2 хвилини.
        </div>
        <div class="archive">
          <div class="archive-head">
            <h2>Збережені голосові повідомлення</h2>
            <button id="refresh-recordings" class="secondary" type="button">Оновити</button>
          </div>
          <div id="recording-list" class="recording-list"></div>
          <audio id="archive-audio" controls hidden></audio>
        </div>
        <div id="history" class="history" aria-live="polite"></div>
        <div id="voice-card" class="voice-card" aria-live="polite">
          <div id="voice-state-class" class="voice-head">
            <span class="record-dot" aria-hidden="true"></span>
            <span id="voice-title" class="voice-title">Голосовий запис</span>
            <span id="voice-time" class="voice-time">00:00</span>
          </div>
          <div class="wave-wrap"><canvas id="wave" width="760" height="72" aria-label="Рівень звуку з мікрофона"></canvas></div>
          <div id="voice-hint" class="voice-hint"></div>
          <div id="voice-transcript" class="voice-result"></div>
          <div id="voice-response" class="voice-result"></div>
          <audio id="voice-audio" controls hidden></audio>
          <div id="voice-controls" class="voice-controls"></div>
        </div>
        <div class="composer">
          <textarea id="message" aria-label="Повідомлення Claude" placeholder="Напишіть запит до домашнього асистента…"></textarea>
          <div class="composer-actions">
            <button id="send" type="button">Надіслати</button>
            <button id="record" class="secondary" type="button">🎙 Записати голосом</button>
            <button id="unwait" class="secondary" type="button">Не чекати відповіді</button>
          </div>
        </div>
        <div id="status" class="status"></div>
      </div>
    `;
    this.shadowRoot.getElementById("refresh").addEventListener("click", () => void this._loadHistory());
    this.shadowRoot.getElementById("refresh-recordings").addEventListener("click", () => void this._loadVoiceRecordings());
    this.shadowRoot.getElementById("send").addEventListener("click", () => void this._sendMessage());
    this.shadowRoot.getElementById("record").addEventListener("click", () => void this._startRecording());
    this.shadowRoot.getElementById("unwait").addEventListener("click", () => this._softRelease(
      "Гаразд, не чекаємо. Відповідь з'явиться в історії — я перевірятиму її автоматично.",
    ));
    this.shadowRoot.getElementById("message").addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        void this._sendMessage();
      }
    });
    this._renderVoiceState();
  }

  async _loadHistory({ quiet = false } = {}) {
    if (!this._hass) return;
    if (!quiet) this._setStatus("Завантажую історію…");
    try {
      const result = await this._hass.callWS({ type: "claude_code_conversation/history", limit: 200 });
      this._lastRecords = result.records || [];
      this._noteAnswerIfArrived();
      this._renderHistory(this._lastRecords);
      if (!quiet) this._setStatus(`Збережено повідомлень: ${this._lastRecords.length}`);
    } catch (error) {
      if (!quiet) this._setStatus(`Не вдалося завантажити історію: ${this._errorText(error)}`);
    }
  }

  _noteAnswerIfArrived() {
    if (!this._awaitingAnswer || !this._sendStartedAt) return;
    const started = this._sendStartedAt;
    const arrived = this._lastRecords.some((record) => {
      if (record.role !== "assistant" || !record.timestamp) return false;
      const stamp = new Date(record.timestamp).valueOf();
      return !Number.isNaN(stamp) && stamp >= started - 5000;
    });
    if (arrived) {
      this._localEcho = null;
      this._awaitingAnswer = false;
      this._pendingRestoreText = "";
      this._stopAnswerPolling();
      this._setStatus("Відповідь отримано.");
    }
  }

  async _loadVoiceRecordings() {
    if (!this._hass) return;
    const container = this.shadowRoot.getElementById("recording-list");
    container.textContent = "Завантажую архів…";
    container.className = "recording-list archive-empty";
    try {
      const result = await this._hass.callWS({ type: "claude_code_conversation/voice_recordings" });
      this._recordings = result.recordings || [];
      this._renderVoiceRecordings();
    } catch (error) {
      container.textContent = `Не вдалося завантажити архів: ${this._errorText(error)}`;
    }
  }

  _renderVoiceRecordings() {
    const container = this.shadowRoot.getElementById("recording-list");
    container.replaceChildren();
    container.className = "recording-list";
    if (!this._recordings.length) {
      container.classList.add("archive-empty");
      container.textContent = "Архів порожній. Наступний надісланий голосовий запис буде збережено як WAV.";
      return;
    }
    for (const recording of this._recordings.slice(0, 12)) {
      const row = document.createElement("div");
      row.className = "recording-row";
      const meta = document.createElement("div");
      meta.className = "recording-meta";
      const created = new Date(recording.created * 1000);
      meta.textContent = `${created.toLocaleString("uk-UA")} · ${this._formatTime(recording.duration)} · ${this._formatBytes(recording.size)}`;
      const actions = document.createElement("div");
      actions.className = "recording-actions";
      actions.append(
        this._button("▶ Прослухати", "secondary", () => void this._playArchivedRecording(recording)),
        this._button("↻ Розпізнати знову", "", () => void this._retryArchivedRecording(recording)),
      );
      row.append(meta, actions);
      container.appendChild(row);
    }
  }

  async _signedRecordingUrl(recording) {
    const path = `/api/claude_code_conversation/voice-recording/${encodeURIComponent(recording.id)}`;
    const result = await this._hass.callWS({ type: "auth/sign_path", path, expires: 300 });
    return result.path;
  }

  async _playArchivedRecording(recording) {
    try {
      const audio = this.shadowRoot.getElementById("archive-audio");
      audio.src = await this._signedRecordingUrl(recording);
      audio.hidden = false;
      await audio.play();
    } catch (error) {
      this._setStatus(`Не вдалося відтворити запис: ${this._errorText(error)}`);
    }
  }

  async _retryArchivedRecording(recording) {
    if (this._voiceState === "recording" || this._voiceState === "sending") return;
    this._voiceState = "sending";
    this._voiceHint = "Завантажую збережений WAV для повторного розпізнавання…";
    this._voiceError = "";
    this._transcript = "";
    this._assistantResponse = "";
    this._ttsUrl = "";
    this._elapsedSeconds = recording.duration || 0;
    this._renderVoiceState();
    try {
      const response = await fetch(await this._signedRecordingUrl(recording));
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      this._archivedPcmBytes = this._pcmBytesFromWav(await response.arrayBuffer());
      this._audioChunks = [];
      this._voiceState = "recorded";
      this._voiceHint = "Збережений WAV завантажено. Запускаю повторне розпізнавання без відсікання на паузах…";
      this._renderVoiceState();
      await this._sendRecording();
    } catch (error) {
      this._voiceState = "error";
      this._voiceError = `Не вдалося повторно використати WAV: ${this._errorText(error)}`;
      this._renderVoiceState();
    }
  }

  _renderHistory(records) {
    const container = this.shadowRoot.getElementById("history");
    container.replaceChildren();
    if (!records.length && !this._localEcho && !this._awaitingAnswer) {
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
    // Історія на диску з'являється лише ПІСЛЯ повної відповіді, тому щойно
    // надіслане повідомлення домальовуємо локально, щоб воно не «зникало».
    if (this._localEcho) {
      const echo = document.createElement("div");
      echo.className = "message user pending";
      const content = document.createElement("span");
      content.textContent = this._localEcho.text;
      const meta = document.createElement("span");
      meta.className = "meta";
      meta.textContent = `Ви · ${new Date(this._localEcho.sentAt).toLocaleString("uk-UA")} · надіслано`;
      echo.append(content, meta);
      container.appendChild(echo);
    }
    if (this._awaitingAnswer) {
      const thinking = document.createElement("div");
      thinking.className = "message assistant pending";
      const dots = document.createElement("span");
      dots.className = "typing";
      dots.append(
        document.createElement("i"),
        document.createElement("i"),
        document.createElement("i"),
      );
      const meta = document.createElement("span");
      meta.className = "meta";
      meta.textContent = "Claude готує відповідь — на цій платі це триває до двох хвилин";
      thinking.append(dots, meta);
      container.appendChild(thinking);
    }
    container.scrollTop = container.scrollHeight;
  }

  _agentId() {
    const states = this._hass?.states || {};
    if (states[AGENT_ID_FALLBACK]) return AGENT_ID_FALLBACK;
    const candidates = Object.keys(states).filter((id) => id.startsWith("conversation."));
    const byId = candidates.find((id) => id.includes("claude"));
    if (byId) return byId;
    const byName = candidates.find((id) =>
      String(states[id].attributes?.friendly_name || "").toLowerCase().includes("claude"));
    return byName || AGENT_ID_FALLBACK;
  }

  async _resolvePipelineId() {
    if (this._pipelineIdResolved) return this._pipelineIdResolved;
    try {
      const result = await this._hass.callWS({ type: "assist_pipeline/pipeline/list" });
      const pipelines = result.pipelines || [];
      const agentId = this._agentId();
      const match = pipelines.find((item) => item.conversation_engine === agentId)
        || pipelines.find((item) => String(item.name || "").toLowerCase().includes("claude"));
      this._pipelineIdResolved = match ? match.id : PIPELINE_ID_FALLBACK;
    } catch (_error) {
      this._pipelineIdResolved = PIPELINE_ID_FALLBACK;
    }
    return this._pipelineIdResolved;
  }

  _softRelease(statusText) {
    if (!this._busy) return;
    this._busy = false;
    this._setComposerDisabled(false);
    this._setStatus(statusText);
    this._startAnswerPolling();
  }

  _startAnswerPolling() {
    this._stopAnswerPolling();
    this._pollUntil = Date.now() + ANSWER_POLL_MAX_MS;
    this._pollTimer = window.setInterval(() => {
      if (!this._awaitingAnswer || Date.now() > this._pollUntil) {
        this._stopAnswerPolling();
        if (this._awaitingAnswer) {
          this._awaitingAnswer = false;
          this._renderHistory(this._lastRecords);
          this._setStatus("Відповідь так і не з'явилася. Перевірте авторизацію: claude auth status на платі.");
        }
        return;
      }
      void this._loadHistory({ quiet: true });
    }, ANSWER_POLL_INTERVAL_MS);
  }

  _stopAnswerPolling() {
    if (this._pollTimer) window.clearInterval(this._pollTimer);
    this._pollTimer = null;
  }

  async _sendMessage() {
    if (!this._hass || this._busy) return;
    const input = this.shadowRoot.getElementById("message");
    const text = input.value.trim();
    if (!text) return;
    const token = ++this._requestToken;
    this._busy = true;
    this._sendStartedAt = Date.now();
    this._localEcho = { text, sentAt: this._sendStartedAt };
    this._awaitingAnswer = true;
    this._pendingRestoreText = text;
    input.value = "";
    this._setComposerDisabled(true);
    this._setStatus("Claude готує відповідь…");
    this._renderHistory(this._lastRecords);
    const watchdog = window.setTimeout(() => {
      if (token !== this._requestToken) return;
      this._softRelease(
        "Відповідь запізнюється (черга або повільна плата). Вона з'явиться в історії — перевірятиму автоматично.",
      );
    }, REQUEST_SOFT_TIMEOUT_MS);
    try {
      await this._hass.callWS({
        type: "conversation/process", text, language: "uk",
        agent_id: this._agentId(), conversation_id: PANEL_CONVERSATION_ID,
      });
      if (token === this._requestToken) this._pendingRestoreText = "";
      await this._loadHistory({ quiet: token !== this._requestToken });
      if (token === this._requestToken && this._awaitingAnswer) {
        // Відповідь завершилася, але в історії її ще не видно — дочитаємо.
        this._startAnswerPolling();
      }
    } catch (error) {
      if (token === this._requestToken) {
        this._localEcho = null;
        this._awaitingAnswer = false;
        this._stopAnswerPolling();
        if (!input.value && this._pendingRestoreText) input.value = this._pendingRestoreText;
        this._pendingRestoreText = "";
        this._renderHistory(this._lastRecords);
        this._setStatus(`Помилка запиту: ${this._errorText(error)}`);
      }
    } finally {
      window.clearTimeout(watchdog);
      if (token === this._requestToken && this._busy) {
        this._busy = false;
        this._setComposerDisabled(false);
        input.focus();
      }
    }
  }

  async _startRecording() {
    if (this._voiceState === "recording" || this._voiceState === "sending") return;
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      this._voiceState = "error";
      this._voiceError = "Браузер не дозволяє мікрофон на цій адресі. Відкрийте Home Assistant через HTTPS, застосунок або http://localhost:8123.";
      this._renderVoiceState();
      return;
    }
    this._resetVoiceData();
    this._voiceState = "requesting";
    this._renderVoiceState();
    try {
      this._stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      this._audioContext = new AudioContextClass();
      this._source = this._audioContext.createMediaStreamSource(this._stream);
      this._processor = this._audioContext.createScriptProcessor(4096, 1, 1);
      this._silentGain = this._audioContext.createGain();
      this._silentGain.gain.value = 0;
      this._processor.onaudioprocess = (event) => this._captureAudio(event);
      this._source.connect(this._processor);
      this._processor.connect(this._silentGain);
      this._silentGain.connect(this._audioContext.destination);
      this._recordingStartedAt = performance.now();
      this._voiceState = "recording";
      this._timer = window.setInterval(() => {
        this._elapsedSeconds = (performance.now() - this._recordingStartedAt) / 1000;
        if (this._elapsedSeconds >= MAX_RECORDING_SECONDS) {
          this._stopRecording("Досягнуто ліміт 2 хвилини. Запис зупинено — тепер його можна надіслати.");
          return;
        }
        this._updateRecordingDisplay();
      }, 200);
      this._renderVoiceState();
    } catch (error) {
      this._stopCaptureTracks();
      this._voiceState = "error";
      this._voiceError = `Не вдалося ввімкнути мікрофон: ${this._errorText(error)}. Перевірте дозвіл браузера.`;
      this._renderVoiceState();
    }
  }

  _captureAudio(event) {
    if (this._voiceState !== "recording") return;
    const input = event.inputBuffer.getChannelData(0);
    const copy = new Float32Array(input.length);
    copy.set(input);
    this._audioChunks.push(copy);
    let sum = 0;
    for (let index = 0; index < input.length; index += 1) sum += input[index] * input[index];
    this._levels.push(Math.min(1, Math.sqrt(sum / input.length) * 4));
    if (this._levels.length > 110) this._levels.shift();
    this._drawWave();
  }

  _stopRecording(hint = "Запис зупинено. Натисніть «Надіслати запис» або запишіть заново.") {
    if (this._voiceState !== "recording") return;
    this._elapsedSeconds = (performance.now() - this._recordingStartedAt) / 1000;
    this._stopCaptureTracks();
    this._clearTimer();
    this._voiceState = this._audioChunks.length ? "recorded" : "error";
    this._voiceError = this._audioChunks.length ? "" : "Мікрофон не передав аудіодані.";
    this._voiceHint = hint;
    this._renderVoiceState();
  }

  async _sendRecording() {
    const hasAudio = this._audioChunks.length || this._archivedPcmBytes?.length;
    if (!["recorded", "complete", "error"].includes(this._voiceState) || !hasAudio || !this._hass) return;
    this._voiceState = "sending";
    this._transcript = "";
    this._assistantResponse = "";
    this._ttsUrl = "";
    this._voiceError = "";
    this._renderVoiceState();
    try {
      const socket = this._hass.connection?.socket;
      if (!socket || socket.readyState !== WebSocket.OPEN) throw new Error("немає активного з’єднання з Home Assistant");
      const bytes = this._archivedPcmBytes || new Uint8Array(this._createPcm16().buffer);
      const handlerReady = new Promise((resolve, reject) => {
        this._voiceReadyResolve = resolve;
        this._voiceReadyReject = reject;
      });
      const pipelineId = await this._resolvePipelineId();
      this._unsubscribeVoice = await this._hass.connection.subscribeMessage(
        (event) => this._handlePipelineEvent(event),
        {
          type: "assist_pipeline/run", start_stage: "stt", end_stage: "tts",
          pipeline: pipelineId, conversation_id: PANEL_CONVERSATION_ID,
          input: { sample_rate: TARGET_SAMPLE_RATE, no_vad: true }, timeout: 180,
        },
      );
      const handlerId = await Promise.race([
        handlerReady,
        new Promise((_, reject) => window.setTimeout(() => reject(new Error("пайплайн не прийняв аудіо")), 10000)),
      ]);
      for (let offset = 0; offset < bytes.length; offset += 3200) {
        const piece = bytes.subarray(offset, Math.min(bytes.length, offset + 3200));
        const packet = new Uint8Array(piece.length + 1);
        packet[0] = handlerId;
        packet.set(piece, 1);
        socket.send(packet.buffer);
      }
      socket.send(new Uint8Array([handlerId]).buffer);
      this._voiceHint = "Аудіо надіслано. Розпізнаю мовлення…";
      this._renderVoiceState();
    } catch (error) {
      this._voiceState = "error";
      this._voiceError = `Не вдалося надіслати запис: ${this._errorText(error)}`;
      this._renderVoiceState();
      await this._closeVoiceSubscription();
    }
  }

  _handlePipelineEvent(event) {
    const type = event?.type;
    const data = event?.data || {};
    if (type === "run-start") {
      const handlerId = data.runner_data?.stt_binary_handler_id;
      if (Number.isInteger(handlerId)) this._voiceReadyResolve?.(handlerId);
    } else if (type === "stt-start") {
      this._voiceHint = "Розпізнаю мовлення…";
    } else if (type === "stt-end") {
      this._transcript = data.stt_output?.text || "";
      this._voiceHint = "Мовлення розпізнано. Claude готує відповідь…";
    } else if (type === "intent-end") {
      this._assistantResponse = data.intent_output?.response?.speech?.plain?.speech || "";
      this._voiceHint = "Відповідь готова. Готую озвучення…";
    } else if (type === "tts-end") {
      this._ttsUrl = data.tts_output?.url || "";
    } else if (type === "error") {
      this._voiceReadyReject?.(new Error(data.message || data.code || "помилка голосового пайплайна"));
      this._voiceState = "error";
      this._voiceError = data.message || data.code || "Помилка голосового пайплайна.";
      void this._closeVoiceSubscription();
    } else if (type === "run-end") {
      this._voiceState = "complete";
      this._voiceHint = "Готово. WAV збережено у приватному архіві, а розшифровку й відповідь — в історії чату.";
      void this._closeVoiceSubscription();
      void this._loadHistory();
      window.setTimeout(() => void this._loadVoiceRecordings(), 800);
    }
    this._renderVoiceState();
  }

  _createPcm16() {
    const sourceRate = this._audioContext?.sampleRate || 48000;
    const sourceLength = this._audioChunks.reduce((total, chunk) => total + chunk.length, 0);
    const source = new Float32Array(sourceLength);
    let sourceOffset = 0;
    for (const chunk of this._audioChunks) {
      source.set(chunk, sourceOffset);
      sourceOffset += chunk.length;
    }
    const outputLength = Math.max(1, Math.floor(source.length * TARGET_SAMPLE_RATE / sourceRate));
    const output = new Int16Array(outputLength);
    const ratio = sourceRate / TARGET_SAMPLE_RATE;
    for (let outputIndex = 0; outputIndex < outputLength; outputIndex += 1) {
      const start = Math.floor(outputIndex * ratio);
      const end = Math.max(start + 1, Math.floor((outputIndex + 1) * ratio));
      let sum = 0;
      for (let sourceIndex = start; sourceIndex < end && sourceIndex < source.length; sourceIndex += 1) sum += source[sourceIndex];
      const sample = Math.max(-1, Math.min(1, sum / (end - start)));
      output[outputIndex] = sample < 0 ? sample * 32768 : sample * 32767;
    }
    return output;
  }

  _pcmBytesFromWav(buffer) {
    const view = new DataView(buffer);
    const tag = (offset) => String.fromCharCode(
      view.getUint8(offset), view.getUint8(offset + 1),
      view.getUint8(offset + 2), view.getUint8(offset + 3),
    );
    if (buffer.byteLength < 44 || tag(0) !== "RIFF" || tag(8) !== "WAVE") throw new Error("файл не є WAV");
    let offset = 12;
    let format = null;
    let dataOffset = 0;
    let dataSize = 0;
    while (offset + 8 <= buffer.byteLength) {
      const chunkTag = tag(offset);
      const size = view.getUint32(offset + 4, true);
      const start = offset + 8;
      if (chunkTag === "fmt " && size >= 16) {
        format = {
          codec: view.getUint16(start, true), channels: view.getUint16(start + 2, true),
          sampleRate: view.getUint32(start + 4, true), bits: view.getUint16(start + 14, true),
        };
      } else if (chunkTag === "data") {
        dataOffset = start;
        dataSize = Math.min(size, buffer.byteLength - start);
        break;
      }
      offset = start + size + (size % 2);
    }
    if (!format || format.codec !== 1 || format.channels !== 1 || format.sampleRate !== TARGET_SAMPLE_RATE || format.bits !== 16) {
      throw new Error("потрібен PCM WAV mono 16 кГц / 16 біт");
    }
    if (!dataOffset || !dataSize) throw new Error("WAV не містить аудіоданих");
    return new Uint8Array(buffer.slice(dataOffset, dataOffset + dataSize));
  }

  _stopCaptureTracks() {
    if (this._processor) this._processor.onaudioprocess = null;
    try { this._source?.disconnect(); } catch (_error) { /* already disconnected */ }
    try { this._processor?.disconnect(); } catch (_error) { /* already disconnected */ }
    try { this._silentGain?.disconnect(); } catch (_error) { /* already disconnected */ }
    for (const track of this._stream?.getTracks?.() || []) track.stop();
    if (this._audioContext && this._audioContext.state !== "closed") void this._audioContext.close();
    this._stream = null;
    this._source = null;
    this._processor = null;
    this._silentGain = null;
  }

  async _closeVoiceSubscription() {
    const unsubscribe = this._unsubscribeVoice;
    this._unsubscribeVoice = null;
    if (unsubscribe) {
      try { await unsubscribe(); } catch (_error) { /* pipeline already ended */ }
    }
  }

  _cancelVoice() {
    this._stopCaptureTracks();
    this._clearTimer();
    void this._closeVoiceSubscription();
    this._resetVoiceData();
    this._voiceState = "idle";
    this._renderVoiceState();
  }

  _resetVoiceData() {
    this._audioChunks = [];
    this._levels = [];
    this._elapsedSeconds = 0;
    this._voiceHint = "";
    this._voiceError = "";
    this._transcript = "";
    this._assistantResponse = "";
    this._ttsUrl = "";
    this._archivedPcmBytes = null;
    this._voiceReadyResolve = null;
    this._voiceReadyReject = null;
  }

  _clearTimer() {
    if (this._timer) window.clearInterval(this._timer);
    this._timer = null;
  }

  _updateRecordingDisplay() {
    const timer = this.shadowRoot.getElementById("voice-time");
    if (timer) timer.textContent = this._formatTime(this._elapsedSeconds);
  }

  _drawWave() {
    const canvas = this.shadowRoot.getElementById("wave");
    if (!canvas) return;
    const context = canvas.getContext("2d");
    const width = canvas.width;
    const height = canvas.height;
    context.clearRect(0, 0, width, height);
    context.strokeStyle = getComputedStyle(this).getPropertyValue("--primary-color").trim() || "#03a9f4";
    context.lineWidth = 3;
    const center = height / 2;
    const spacing = width / 110;
    context.beginPath();
    for (let index = 0; index < 110; index += 1) {
      const level = this._levels[index] || 0.02;
      const amplitude = Math.max(1.5, level * (height * 0.44));
      const x = index * spacing + spacing / 2;
      context.moveTo(x, center - amplitude);
      context.lineTo(x, center + amplitude);
    }
    context.stroke();
  }

  _renderVoiceState() {
    if (!this._ready) return;
    const card = this.shadowRoot.getElementById("voice-card");
    const head = this.shadowRoot.getElementById("voice-state-class");
    const title = this.shadowRoot.getElementById("voice-title");
    const hint = this.shadowRoot.getElementById("voice-hint");
    const controls = this.shadowRoot.getElementById("voice-controls");
    const transcript = this.shadowRoot.getElementById("voice-transcript");
    const response = this.shadowRoot.getElementById("voice-response");
    const audio = this.shadowRoot.getElementById("voice-audio");
    const visible = this._voiceState !== "idle";
    card.classList.toggle("visible", visible);
    head.classList.toggle("recording", this._voiceState === "recording");
    const titles = {
      requesting: "Дозвіл на мікрофон…", recording: "Запис триває — говоріть",
      recorded: "Запис готовий до надсилання", sending: "Обробляю запис…",
      complete: "Голосовий запит виконано", error: "Помилка голосового вводу",
    };
    title.textContent = titles[this._voiceState] || "Голосовий запис";
    this._updateRecordingDisplay();
    hint.textContent = this._voiceError || this._voiceHint || (this._voiceState === "recording"
      ? "Рівень звуку рухається під час мовлення. Натисніть «Зупинити запис», коли закінчите."
      : "");
    transcript.classList.toggle("visible", Boolean(this._transcript));
    transcript.replaceChildren();
    if (this._transcript) {
      const label = document.createElement("b");
      label.textContent = "Розпізнано:";
      transcript.append(label, document.createTextNode(this._transcript));
    }
    response.classList.toggle("visible", Boolean(this._assistantResponse));
    response.replaceChildren();
    if (this._assistantResponse) {
      const label = document.createElement("b");
      label.textContent = "Відповідь Claude:";
      response.append(label, document.createTextNode(this._assistantResponse));
    }
    if (this._ttsUrl) {
      audio.src = this._ttsUrl;
      audio.hidden = false;
    } else {
      audio.removeAttribute("src");
      audio.hidden = true;
    }
    controls.replaceChildren();
    if (this._voiceState === "recording") {
      controls.append(
        this._button("■ Зупинити запис", "danger", () => this._stopRecording()),
        this._button("Скасувати", "secondary", () => this._cancelVoice()),
      );
    } else if (this._voiceState === "recorded") {
      controls.append(
        this._button("↑ Надіслати запис", "", () => void this._sendRecording()),
        this._button("Записати заново", "secondary", () => void this._startRecording()),
        this._button("Скасувати", "secondary", () => this._cancelVoice()),
      );
    } else if (this._voiceState === "sending" || this._voiceState === "requesting") {
      const disabled = this._button("Зачекайте…", "secondary", () => {});
      disabled.disabled = true;
      controls.append(disabled, this._button("Скасувати", "secondary", () => this._cancelVoice()));
    } else if (this._voiceState === "complete" || this._voiceState === "error") {
      if (this._audioChunks.length || this._archivedPcmBytes?.length) {
        controls.append(this._button("↻ Розпізнати ще раз", "", () => void this._sendRecording()));
      }
      controls.append(
        this._button("Записати ще", "secondary", () => void this._startRecording()),
        this._button("Закрити", "secondary", () => this._cancelVoice()),
      );
    }
    this._drawWave();
  }

  _button(text, className, handler) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = text;
    if (className) button.className = className;
    button.addEventListener("click", handler);
    return button;
  }

  _setComposerDisabled(disabled) {
    this.shadowRoot.getElementById("send").disabled = disabled;
    this.shadowRoot.getElementById("record").disabled = disabled;
    this.shadowRoot.getElementById("unwait").classList.toggle("visible", disabled);
  }

  _formatTime(seconds) {
    const value = Math.max(0, Math.floor(seconds || 0));
    return `${String(Math.floor(value / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`;
  }

  _formatBytes(bytes) {
    if (bytes < 1024) return `${bytes} Б`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
  }

  _errorText(error) {
    if (error?.message) return error.message;
    return String(error);
  }

  _setStatus(text) {
    this.shadowRoot.getElementById("status").textContent = text;
  }
}

if (!customElements.get("claude-history-panel")) {
  customElements.define("claude-history-panel", ClaudeHistoryPanel);
}
