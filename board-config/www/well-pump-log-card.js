/* Таблиця пусків насоса свердловини: коли, скільки тривав, скільки взяв
 * енергії та скільки дав води.
 *
 * До 22.08.2026 така таблиця була б обманом: LocalTuya не опитувала розетку
 * (scan_interval не заданий), тож межі пусків HA бачив випадково — пуск на 36
 * секунд зараховувався як 10, а тридцятисекундний міг не потрапити зовсім.
 * Тепер опитування секундне, і кожен рядок тут — виміряна величина.
 *
 * Колонка «л/хв» додана навмисно: подача насоса фізично стала, тож розкид у
 * ній одразу показує або проблему з насосом, або збій обліку. Виміряно
 * секундоміром біля насоса: 18.2 / 16.5 / 16.3 л/хв, тобто близько 17.
 *
 * Параметри:
 *   entity             input_boolean стану насоса (обов'язково)
 *   energy_entity      накопичувач енергії насоса (обов'язково)
 *   coefficient_entity input_number з м³/кВт·год
 *   hours_to_show      глибина історії, типово 24
 *   limit              скільки рядків показувати, типово 15
 */
(function () {
  const tag = 'well-pump-log-card';
  if (customElements.get(tag)) return;

  class WellPumpLogCard extends HTMLElement {
    setConfig(config) {
      if (!config || !config.entity) throw new Error('Потрібна entity стану насоса');
      if (!config.energy_entity) throw new Error('Потрібна energy_entity');
      this.config = { hours_to_show: 24, limit: 15, ...config };
      this._render('Завантажую історію…');
    }

    set hass(hass) {
      this._hass = hass;
      const s = hass.states[this.config.entity];
      const marker = `${s?.state || ''}|${s?.last_updated || ''}`;
      if (marker !== this._marker) {
        this._marker = marker;
        this._load();
      }
    }

    /* Насос може стояти годинами, і тоді жодна подія не приходить. Раз на
     * хвилину перечитуємо самі, інакше таблиця «застигає» на старих даних. */
    connectedCallback() {
      if (!this._timer) this._timer = setInterval(() => this._load(), 60000);
    }

    disconnectedCallback() {
      if (this._timer) { clearInterval(this._timer); this._timer = null; }
    }

    getCardSize() { return 6; }

    _esc(v) {
      return String(v ?? '').replace(/[&<>'"]/g, (c) => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c]));
    }

    _num(v, digits) {
      if (!Number.isFinite(v)) return '—';
      return v.toLocaleString('uk-UA', { minimumFractionDigits: digits, maximumFractionDigits: digits });
    }

    _duration(seconds) {
      if (!Number.isFinite(seconds)) return '—';
      if (seconds < 90) return `${Math.round(seconds)} с`;
      const m = Math.floor(seconds / 60);
      const s = Math.round(seconds % 60);
      return s ? `${m} хв ${s} с` : `${m} хв`;
    }

    async _load() {
      if (!this._hass) return;
      try {
        const start = new Date(Date.now() - this.config.hours_to_show * 3600000).toISOString();
        const ids = [this.config.entity, this.config.energy_entity].join(',');
        const url = `history/period/${start}?filter_entity_id=${ids}&minimal_response&no_attributes`;
        const series = await this._hass.callApi('GET', url);

        const byId = {};
        for (const list of series || []) {
          if (list && list.length) byId[list[0].entity_id] = list;
        }
        this._runs = this._buildRuns(byId[this.config.entity] || [], byId[this.config.energy_entity] || []);
        this._error = null;
      } catch (e) {
        this._error = String(e?.message || e);
      }
      this._render();
    }

    /* Пуск — це відрізок, поки стан 'on'. Енергію рахуємо як приріст
     * накопичувача між його межами: беремо останнє значення на момент старту й
     * на момент зупинки, а не суму семплів усередині — так пропущений семпл не
     * зникає з підсумку, а лише злегка зсуває межу. */
    _buildRuns(stateHistory, energyHistory) {
      const energy = energyHistory
        .map((p) => ({ t: Date.parse(p.last_changed), v: parseFloat(p.state) }))
        .filter((p) => Number.isFinite(p.t) && Number.isFinite(p.v));

      const energyAt = (time) => {
        let value = null;
        for (const point of energy) {
          if (point.t <= time) value = point.v; else break;
        }
        return value;
      };

      const runs = [];
      let openedAt = null;
      for (const point of stateHistory) {
        const t = Date.parse(point.last_changed);
        if (!Number.isFinite(t)) continue;
        if (point.state === 'on' && openedAt === null) {
          openedAt = t;
        } else if (point.state !== 'on' && openedAt !== null) {
          runs.push({ from: openedAt, to: t });
          openedAt = null;
        }
      }
      if (openedAt !== null) runs.push({ from: openedAt, to: Date.now(), running: true });

      return runs.map((run) => {
        const seconds = (run.to - run.from) / 1000;
        const before = energyAt(run.from);
        const after = energyAt(run.to);
        const kwh = (before !== null && after !== null && after >= before) ? after - before : null;
        return { ...run, seconds, kwh };
      }).reverse();
    }

    _render(message) {
      const cfg = this.config || {};
      const coefficient = this._hass && cfg.coefficient_entity
        ? parseFloat(this._hass.states[cfg.coefficient_entity]?.state)
        : NaN;

      let body = '';
      let summary = '';
      if (message) {
        body = `<tr><td colspan="5" class="empty">${this._esc(message)}</td></tr>`;
      } else if (this._error) {
        body = `<tr><td colspan="5" class="err">${this._esc(this._error)}</td></tr>`;
      } else if (!this._runs || !this._runs.length) {
        body = `<tr><td colspan="5" class="empty">За ${cfg.hours_to_show} год пусків не було</td></tr>`;
      } else {
        const shown = cfg.limit > 0 ? this._runs.slice(0, cfg.limit) : this._runs;
        body = shown.map((run) => {
          const litres = Number.isFinite(coefficient) && run.kwh !== null
            ? run.kwh * coefficient * 1000 : null;
          const perMinute = litres !== null && run.seconds > 0
            ? litres / (run.seconds / 60) : null;
          const time = new Date(run.from).toLocaleTimeString('uk-UA', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
          const day = new Date(run.from).toLocaleDateString('uk-UA', { day: '2-digit', month: '2-digit' });
          return `<tr${run.running ? ' class="live"' : ''}>
            <td>${this._esc(day)} ${this._esc(time)}${run.running ? ' <span class="tag">качає</span>' : ''}</td>
            <td class="n">${this._esc(this._duration(run.seconds))}</td>
            <td class="n">${run.kwh === null ? '—' : this._num(run.kwh, 4)}</td>
            <td class="n">${litres === null ? '—' : this._num(litres, 1)}</td>
            <td class="n">${perMinute === null ? '—' : this._num(perMinute, 1)}</td>
          </tr>`;
        }).join('');

        const totalSeconds = this._runs.reduce((a, r) => a + r.seconds, 0);
        const totalKwh = this._runs.reduce((a, r) => a + (r.kwh || 0), 0);
        const totalLitres = Number.isFinite(coefficient) ? totalKwh * coefficient * 1000 : null;
        summary = `Пусків ${this._runs.length} · разом ${this._duration(totalSeconds)}`
          + ` · ${this._num(totalKwh, 3)} кВт·год`
          + (totalLitres === null ? '' : ` · ${this._num(totalLitres, 0)} л`);
      }

      this.innerHTML = `<ha-card><div class="wrap">
        <div class="head">
          <h2>${this._esc(cfg.title || 'Пуски насоса')}</h2>
          ${summary ? `<span class="sum">${this._esc(summary)}</span>` : ''}
        </div>
        <div class="scroll"><table>
          <thead><tr>
            <th>Початок</th><th class="n">Тривалість</th><th class="n">кВт·год</th>
            <th class="n">Літрів</th><th class="n">л/хв</th>
          </tr></thead>
          <tbody>${body}</tbody>
        </table></div>
        <p>Літри рахуються з енергії за поточним коефіцієнтом. Колонка «л/хв» — перевірка:
        подача насоса стала, тож помітний розкид означає збій обліку, а не примху насоса.</p>
      </div></ha-card><style>
        .wrap{padding:16px}
        .head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:12px}
        h2{margin:0;font-size:20px}
        .sum{color:var(--secondary-text-color);font-size:13px}
        .scroll{overflow-x:auto}
        table{width:100%;border-collapse:collapse;font-size:14px}
        th,td{padding:8px 10px;border-bottom:1px solid var(--divider-color);text-align:left;white-space:nowrap}
        th{font-weight:700;background:color-mix(in srgb,var(--primary-color) 10%,transparent)}
        td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
        tr.live td{color:var(--primary-color)}
        .tag{padding:1px 7px;border-radius:999px;font-size:11px;
          background:color-mix(in srgb,var(--primary-color) 22%,transparent)}
        .empty,.err{text-align:center;color:var(--secondary-text-color)}
        .err{color:var(--error-color)}
        p{margin:12px 0 0;color:var(--secondary-text-color);font-size:13px}
      </style>`;
    }
  }

  customElements.define(tag, WellPumpLogCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: tag,
    name: 'Пуски насоса свердловини',
    description: 'Таблиця пусків: час, тривалість, енергія, вода і подача',
  });
})();
