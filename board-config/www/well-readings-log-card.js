/* Журнал показників механічного лічильника свердловини.
 *
 * Наступник read-only картки `well-readings-table-card`. Дані бере не зі слотів
 * `input_text`, а з файлового сховища через сенсор `entity` (атрибут `readings`),
 * і вміє додавати, редагувати та ховати рядки. Видалення тут завжди м'яке:
 * скрипт на боці плати лише виставляє прапорець, а попереднє значення при
 * правці лягає в історію ревізій — тому жоден показник не зникає безслідно.
 *
 * Параметри картки:
 *   entity        сенсор із атрибутом `readings` (обов'язково)
 *   limit         скільки останніх рядків показувати (0 = всі, типово 10)
 *   title         заголовок
 *   service       сервіс запису, типово shell_command.water_reading_apply
 */
const tag = 'well-readings-log-card';

if (!customElements.get(tag)) {
  class WellReadingsLogCard extends HTMLElement {
    setConfig(config) {
      if (!config || !config.entity) throw new Error('Вкажіть entity сенсора журналу');
      this.config = { limit: 10, service: 'shell_command.water_reading_apply', ...config };
      this._form = null;
      this._showDeleted = false;
      this._busy = false;
    }

    set hass(hass) {
      this._hass = hass;
      const state = hass.states[this.config.entity];
      const marker = state ? `${state.state}|${state.last_updated}` : 'missing';
      if (marker !== this._marker || this._dirty) {
        this._marker = marker;
        this._dirty = false;
        this._render();
      }
    }

    getCardSize() {
      return 8;
    }

    /* ---------- дані ---------- */

    _rows() {
      const state = this._hass?.states[this.config.entity];
      const rows = state?.attributes?.readings;
      return Array.isArray(rows) ? rows.slice().sort((a, b) => Date.parse(a.iso) - Date.parse(b.iso)) : [];
    }

    /* Витрата рахується від попереднього ЖИВОГО рядка: прихований показник не
     * повинен розривати ланцюжок, інакше сусідні дельти стануть неправдою. */
    _withDeltas(rows) {
      let prev = null;
      return rows.map((row) => {
        const out = { ...row, delta: null, days: null, perDay: null, prev };
        if (!row.deleted && prev) {
          const days = (Date.parse(row.iso) - Date.parse(prev.iso)) / 86400000;
          if (days > 0) {
            out.delta = row.value - prev.value;
            out.days = days;
            out.perDay = ((row.value - prev.value) * 1000) / days;
          }
        }
        if (!row.deleted) prev = row;
        return out;
      });
    }

    /* ---------- форматування ---------- */

    _esc(value) {
      return String(value ?? '').replace(/[&<>"']/g, (c) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
      }[c]));
    }

    _num(value, digits = 3) {
      if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
      return Number(value).toLocaleString('uk-UA', {
        minimumFractionDigits: digits, maximumFractionDigits: digits,
      });
    }

    _period(days) {
      if (!Number.isFinite(days)) return '—';
      if (days >= 1) return `${this._num(days, days < 10 ? 1 : 0)} дн`;
      return `${this._num(days * 24, 1)} год`;
    }

    _date(iso) {
      const parsed = new Date(iso);
      if (Number.isNaN(parsed.getTime())) return String(iso ?? '');
      return parsed.toLocaleString('uk-UA', {
        day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
      });
    }

    /* datetime-local хоче локальний час без зони */
    _toLocalInput(iso) {
      const parsed = iso ? new Date(iso) : new Date();
      const shifted = new Date(parsed.getTime() - parsed.getTimezoneOffset() * 60000);
      return shifted.toISOString().slice(0, 16);
    }

    _fromLocalInput(value) {
      const parsed = new Date(value);
      if (Number.isNaN(parsed.getTime())) return null;
      const offset = -parsed.getTimezoneOffset();
      const sign = offset >= 0 ? '+' : '-';
      const pad = (n) => String(Math.floor(Math.abs(n))).padStart(2, '0');
      const shifted = new Date(parsed.getTime() - parsed.getTimezoneOffset() * 60000);
      return `${shifted.toISOString().slice(0, 19)}${sign}${pad(offset / 60)}:${pad(offset % 60)}`;
    }

    /* ---------- запис ---------- */

    async _apply(body) {
      if (this._busy) return;
      this._busy = true;
      try {
        const json = JSON.stringify({ ...body, by: body.by || this._hass.user?.name || 'Користувач' });
        const payload = btoa(String.fromCharCode(...new TextEncoder().encode(json)));
        const [domain, service] = this.config.service.split('.');
        await this._hass.callService(domain, service, { payload });
        /* shell_command не повертає результату, тож сенсор просимо перечитати
         * файл одразу, інакше таблиця оновиться лише за scan_interval. */
        await new Promise((resolve) => setTimeout(resolve, 400));
        await this._hass.callService('homeassistant', 'update_entity', {
          entity_id: this.config.entity,
        });
        this._form = null;
        this._error = null;
      } catch (error) {
        this._error = String(error?.message || error);
      } finally {
        this._busy = false;
        this._dirty = true;
        this._render();
      }
    }

    /* ---------- рендер ---------- */

    _render() {
      if (!this._hass) return;
      const state = this._hass.states[this.config.entity];
      if (!state || ['unknown', 'unavailable'].includes(state.state)) {
        this.innerHTML = `<ha-card><div class="wrap"><div class="err">Сенсор ${this._esc(this.config.entity)} недоступний</div></div></ha-card>${this._style()}`;
        return;
      }

      const all = this._withDeltas(this._rows());
      const visible = this._showDeleted ? all : all.filter((row) => !row.deleted);
      const limit = Number(this.config.limit) || 0;
      const shown = limit > 0 ? visible.slice(-limit) : visible;
      const hiddenCount = all.filter((row) => row.deleted).length;
      const total = state.attributes?.count ?? all.length;

      const body = shown.map((row) => {
        const cls = row.deleted ? ' class="gone"' : '';
        const marks = [
          row.edited ? `<span class="tag" title="Редаговано, ревізій: ${row.revisions}">змінено</span>` : '',
          row.deleted ? '<span class="tag del">приховано</span>' : '',
        ].join('');
        const actions = row.deleted
          ? `<button data-act="restore" data-id="${this._esc(row.id)}" title="Повернути">↩</button>`
          : `<button data-act="edit" data-id="${this._esc(row.id)}" title="Редагувати">✎</button>`
            + `<button data-act="delete" data-id="${this._esc(row.id)}" title="Приховати (запис не видаляється)">🗑</button>`;
        return `<tr${cls}>
          <td>${this._esc(this._date(row.iso))}${marks}</td>
          <td class="n">${this._num(row.value)}</td>
          <td class="n">${this._num(row.delta)}</td>
          <td class="n">${this._period(row.days)}</td>
          <td class="n">${this._num(row.perDay, 1)}</td>
          <td>${this._esc(row.author || '—')}</td>
          <td class="act">${actions}</td>
        </tr>`;
      }).join('');

      this.innerHTML = `<ha-card><div class="wrap">
        <div class="head">
          <h2>${this._esc(this.config.title || 'Журнал показників')}</h2>
          <div class="tools">
            <button class="primary" data-act="new">+ Додати показник</button>
            ${hiddenCount ? `<button data-act="toggle">${this._showDeleted ? 'Сховати приховані' : `Показати приховані (${hiddenCount})`}</button>` : ''}
          </div>
        </div>
        ${this._error ? `<div class="err">${this._esc(this._error)}</div>` : ''}
        ${this._formHtml(all)}
        <div class="scroll"><table>
          <thead><tr>
            <th>Дата</th><th class="n">Показник, м³</th><th class="n">Витрата, м³</th>
            <th class="n">Період</th><th class="n">Середня, л/день</th><th>Хто</th><th></th>
          </tr></thead>
          <tbody>${body || '<tr><td colspan="7" class="empty">Записів ще немає</td></tr>'}</tbody>
        </table></div>
        <p>Показано ${shown.length} із ${total}. Редагування зберігає попереднє значення, видалення — лише приховує рядок.</p>
      </div></ha-card>${this._style()}`;

      this.querySelectorAll('button[data-act]').forEach((button) => {
        button.addEventListener('click', () => this._onAction(button.dataset.act, button.dataset.id, all));
      });
      const form = this.querySelector('form');
      if (form) form.addEventListener('submit', (event) => this._onSubmit(event));
    }

    _formHtml(rows) {
      if (!this._form) return '';
      const editing = this._form.id ? rows.find((row) => row.id === this._form.id) : null;
      const value = editing ? editing.value : '';
      const iso = this._toLocalInput(editing ? editing.iso : null);
      const note = editing?.note || '';
      return `<form class="form">
        <div class="grid">
          <label>Дата й час<input name="iso" type="datetime-local" value="${this._esc(iso)}" required></label>
          <label>Показник, м³<input name="value" type="number" step="0.001" min="0" value="${this._esc(value)}" required></label>
          <label>Нотатка<input name="note" type="text" value="${this._esc(note)}" placeholder="необов'язково"></label>
        </div>
        <div class="row">
          <button class="primary" type="submit">${editing ? 'Зберегти зміни' : 'Додати'}</button>
          <button type="button" data-act="cancel">Скасувати</button>
          ${editing ? `<span class="hint">Попереднє значення ${this._num(editing.value)} м³ збережеться в історії</span>` : ''}
        </div>
      </form>`;
    }

    _onAction(action, id, rows) {
      if (action === 'new') { this._form = { id: null }; this._error = null; }
      else if (action === 'cancel') this._form = null;
      else if (action === 'edit') { this._form = { id }; this._error = null; }
      else if (action === 'toggle') this._showDeleted = !this._showDeleted;
      else if (action === 'restore') return this._apply({ action: 'restore', id });
      else if (action === 'delete') {
        const row = rows.find((item) => item.id === id);
        const label = row ? `${this._date(row.iso)} — ${this._num(row.value)} м³` : id;
        if (!confirm(`Приховати запис ${label}?\n\nРядок залишиться у файлі, його можна повернути.`)) return;
        return this._apply({ action: 'delete', id });
      }
      this._render();
      return undefined;
    }

    _onSubmit(event) {
      event.preventDefault();
      const data = new FormData(event.target);
      const iso = this._fromLocalInput(data.get('iso'));
      const value = Number(data.get('value'));
      if (!iso) { this._error = 'Некоректна дата'; return this._render(); }
      if (!Number.isFinite(value)) { this._error = 'Некоректний показник'; return this._render(); }
      const note = String(data.get('note') || '');
      const author = this._hass.user?.name || 'Користувач';
      return this._apply(this._form.id
        ? { action: 'edit', id: this._form.id, iso, value, note }
        : { action: 'add', iso, value, note, author });
    }

    _style() {
      return `<style>
        .wrap{padding:16px}
        .head{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:14px}
        h2{font-size:20px;margin:0}
        .tools{display:flex;gap:8px;flex-wrap:wrap}
        button{font:inherit;font-size:13px;padding:7px 12px;border-radius:8px;cursor:pointer;
          border:1px solid var(--divider-color);background:var(--card-background-color);color:var(--primary-text-color)}
        button:hover{background:color-mix(in srgb,var(--primary-color) 12%,transparent)}
        button.primary{background:var(--primary-color);color:var(--text-primary-color,#fff);border-color:transparent}
        .scroll{overflow-x:auto}
        table{width:100%;border-collapse:collapse;font-size:14px}
        th,td{padding:9px 10px;border-bottom:1px solid var(--divider-color);text-align:left;white-space:nowrap}
        th{font-weight:700;background:color-mix(in srgb,var(--primary-color) 10%,transparent)}
        td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
        td.act{text-align:right}
        td.act button{padding:4px 8px;margin-left:4px}
        tr.gone td{opacity:.5;text-decoration:line-through}
        tr.gone td.act{text-decoration:none;opacity:1}
        .empty{text-align:center;color:var(--secondary-text-color)}
        .tag{margin-left:8px;padding:1px 7px;border-radius:999px;font-size:11px;text-decoration:none;
          background:color-mix(in srgb,var(--primary-color) 18%,transparent);color:var(--primary-text-color)}
        .tag.del{background:color-mix(in srgb,var(--error-color) 22%,transparent)}
        .form{margin:0 0 16px;padding:14px;border:1px solid var(--divider-color);border-radius:12px;
          background:color-mix(in srgb,var(--primary-color) 5%,transparent)}
        .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}
        label{display:flex;flex-direction:column;gap:5px;font-size:13px;color:var(--secondary-text-color)}
        input{font:inherit;font-size:14px;padding:8px 10px;border-radius:8px;border:1px solid var(--divider-color);
          background:var(--card-background-color);color:var(--primary-text-color)}
        .row{display:flex;align-items:center;gap:10px;margin-top:12px;flex-wrap:wrap}
        .hint{font-size:12px;color:var(--secondary-text-color)}
        p{margin:12px 0 0;color:var(--secondary-text-color);font-size:13px}
        .err{margin-bottom:12px;color:var(--error-color);font-size:13px}
      </style>`;
    }
  }

  customElements.define(tag, WellReadingsLogCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: tag,
    name: 'Журнал показників лічильника',
    description: 'Таблиця показників свердловини з додаванням, редагуванням і м\'яким видаленням',
  });
}
