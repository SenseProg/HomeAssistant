class HomeEnergyFlowCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
  }

  setConfig(config) {
    if (!config || !config.entities) {
      throw new Error("home-energy-flow-card: entities are required");
    }
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 7;
  }

  _entity(entityId) {
    return entityId && this._hass ? this._hass.states[entityId] : undefined;
  }

  _number(entityId) {
    const state = this._entity(entityId);
    if (!state || ["unknown", "unavailable", "none", ""].includes(state.state)) {
      return null;
    }
    const value = Number(String(state.state).replace(",", "."));
    return Number.isFinite(value) ? value : null;
  }

  _formatNumber(value, maximumFractionDigits = 1) {
    if (value === null || !Number.isFinite(value)) return "—";
    return new Intl.NumberFormat("uk-UA", {
      minimumFractionDigits: 0,
      maximumFractionDigits,
    }).format(value);
  }

  _formatPower(value, signed = false) {
    if (value === null || !Number.isFinite(value)) return "—";
    const sign = signed && value > 0 ? "+" : "";
    if (Math.abs(value) >= 1000) {
      return `${sign}${this._formatNumber(value / 1000, 2)} кВт`;
    }
    return `${sign}${this._formatNumber(value, 0)} Вт`;
  }

  _formatEnergy(value) {
    return value === null || !Number.isFinite(value)
      ? "—"
      : `${this._formatNumber(value, 2)} кВт·год`;
  }

  _escape(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  _render() {
    if (!this._config || !this._hass) return;

    const entities = this._config.entities;
    const mainPower = this._number(entities.main_power);
    const inverterInput = this._number(entities.inverter_input_power);
    const outsidePower = this._number(entities.outside_power);
    const housePower = this._number(entities.house_power);
    const batteryPower = this._number(entities.battery_power);
    const batterySoc = this._number(entities.battery_soc);
    const inverterVoltage = this._number(entities.inverter_voltage);
    const inverterFrequency = this._number(entities.inverter_frequency);
    const pv1Power = this._number(entities.pv1_power);
    const pv2Power = this._number(entities.pv2_power);
    const pv1Voltage = this._number(entities.pv1_voltage);
    const pv1Current = this._number(entities.pv1_current);
    const pv2Voltage = this._number(entities.pv2_voltage);
    const pv2Current = this._number(entities.pv2_current);
    const calculatedPv =
      (pv1Voltage === null || pv1Current === null ? 0 : pv1Voltage * pv1Current) +
      (pv2Voltage === null || pv2Current === null ? 0 : pv2Voltage * pv2Current);
    const hasPvReading =
      pv1Power !== null ||
      pv2Power !== null ||
      (pv1Voltage !== null && pv1Current !== null) ||
      (pv2Voltage !== null && pv2Current !== null);
    const solarPower = hasPvReading ? (pv1Power || 0) + (pv2Power || 0) || calculatedPv : null;

    const totalDay = this._number(entities.total_day_energy);
    const inverterGridDay = this._number(entities.inverter_grid_day_energy);
    const houseDay = this._number(entities.house_day_energy);
    const outsideDay =
      totalDay === null || inverterGridDay === null
        ? null
        : Math.max(totalDay - inverterGridDay, 0);
    const batteryChargeDay = this._number(entities.battery_charge_day_energy);
    const batteryDischargeDay = this._number(entities.battery_discharge_day_energy);

    const inverterStateEntity = this._entity(entities.inverter_status);
    const inverterState = inverterStateEntity?.state || "—";
    const inverterConnected = !["unknown", "unavailable", "none", "—"].includes(
      inverterState.toLowerCase(),
    );
    const pvText = hasPvReading ? this._formatPower(solarPower) : "ще не підключено";
    const batteryText =
      batterySoc === null
        ? this._formatPower(batteryPower, true)
        : `${this._formatNumber(batterySoc, 0)}% · ${this._formatPower(batteryPower, true)}`;

    const inverterMeta = [
      inverterVoltage === null ? null : `${this._formatNumber(inverterVoltage, 1)} В`,
      inverterFrequency === null ? null : `${this._formatNumber(inverterFrequency, 2)} Гц`,
    ]
      .filter(Boolean)
      .join(" · ");

    const node = ({ cls, entity, icon, title, value, meta = "" }) => `
      <button class="flow-node ${cls}" data-entity="${this._escape(entity || "")}" type="button">
        <ha-icon icon="${this._escape(icon)}" aria-hidden="true"></ha-icon>
        <span class="node-copy">
          <span class="node-title">${this._escape(title)}</span>
          <strong>${this._escape(value)}</strong>
          ${meta ? `<span class="node-meta">${this._escape(meta)}</span>` : ""}
        </span>
      </button>`;

    const dailyItem = (label, value) => `
      <div class="daily-item">
        <span>${this._escape(label)}</span>
        <strong>${this._escape(value)}</strong>
      </div>`;

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
        }
        ha-card {
          overflow: hidden;
          padding: 18px 20px 16px;
          background: var(--ha-card-background, var(--card-background-color));
          color: var(--primary-text-color);
        }
        .flow-title {
          display: flex;
          align-items: baseline;
          justify-content: space-between;
          gap: 16px;
          margin: 0 2px 8px;
        }
        .flow-title h2 {
          margin: 0;
          font-size: 20px;
          font-weight: 500;
        }
        .flow-title span {
          color: var(--secondary-text-color);
          font-size: 13px;
        }
        .stage-scroll {
          overflow-x: auto;
          overflow-y: hidden;
          scrollbar-width: thin;
        }
        .mobile-flow {
          display: none;
        }
        .flow-stage {
          position: relative;
          min-width: 900px;
          height: 500px;
        }
        .connectors {
          position: absolute;
          inset: 0;
          width: 100%;
          height: 100%;
          pointer-events: none;
        }
        .connector {
          fill: none;
          stroke: var(--divider-color, rgba(127, 127, 127, 0.45));
          stroke-width: 4;
          stroke-linecap: round;
          stroke-linejoin: round;
        }
        .connector.grid { stroke: var(--blue-color, #4f9de8); }
        .connector.load { stroke: var(--teal-color, #5cc8bd); }
        .connector.solar { stroke: var(--amber-color, #f3b33d); }
        .connector.battery { stroke: var(--pink-color, #ef9ab0); }
        .connector.inactive {
          stroke: var(--disabled-text-color);
          stroke-dasharray: 9 9;
        }
        .junction {
          fill: var(--blue-color, #4f9de8);
          stroke: var(--ha-card-background, var(--card-background-color));
          stroke-width: 5;
        }
        .flow-node {
          position: absolute;
          z-index: 2;
          box-sizing: border-box;
          display: flex;
          align-items: center;
          gap: 12px;
          min-height: 112px;
          padding: 15px 16px;
          border: 1px solid var(--divider-color);
          border-radius: 18px;
          background: color-mix(in srgb, var(--primary-background-color) 82%, transparent);
          color: var(--primary-text-color);
          font: inherit;
          text-align: left;
          cursor: pointer;
        }
        .flow-node:hover,
        .flow-node:focus-visible {
          background: var(--secondary-background-color);
          outline: 2px solid var(--primary-color);
          outline-offset: 2px;
        }
        .flow-node ha-icon {
          flex: 0 0 auto;
          width: 38px;
          height: 38px;
        }
        .node-copy {
          display: grid;
          min-width: 0;
          gap: 5px;
        }
        .node-title {
          color: var(--secondary-text-color);
          font-size: 14px;
          line-height: 1.2;
        }
        .flow-node strong {
          font-size: 24px;
          font-weight: 500;
          line-height: 1.1;
          white-space: nowrap;
        }
        .node-meta {
          color: var(--secondary-text-color);
          font-size: 13px;
          white-space: nowrap;
        }
        .meter {
          left: 1.5%;
          top: 190px;
          width: 19.5%;
          border-color: color-mix(in srgb, var(--blue-color, #4f9de8) 65%, transparent);
        }
        .meter ha-icon,
        .inverter ha-icon { color: var(--blue-color, #4f9de8); }
        .inverter {
          left: 34%;
          top: 180px;
          width: 21%;
          min-height: 132px;
          border-color: color-mix(in srgb, var(--blue-color, #4f9de8) 55%, transparent);
        }
        .house {
          right: 1.5%;
          top: 190px;
          width: 22.5%;
          border-color: color-mix(in srgb, var(--teal-color, #5cc8bd) 65%, transparent);
        }
        .house ha-icon { color: var(--teal-color, #5cc8bd); }
        .solar {
          left: 36.5%;
          top: 8px;
          width: 16%;
          border-color: color-mix(in srgb, var(--amber-color, #f3b33d) 65%, transparent);
        }
        .solar ha-icon { color: var(--amber-color, #f3b33d); }
        .battery {
          left: 36.5%;
          bottom: 8px;
          width: 16%;
          border-color: color-mix(in srgb, var(--pink-color, #ef9ab0) 65%, transparent);
        }
        .battery ha-icon { color: var(--pink-color, #ef9ab0); }
        .outside {
          left: 14%;
          bottom: 8px;
          width: 22%;
          border-color: color-mix(in srgb, var(--blue-color, #4f9de8) 45%, transparent);
        }
        .outside ha-icon { color: var(--blue-color, #4f9de8); }
        .daily-strip {
          display: grid;
          grid-template-columns: repeat(5, minmax(130px, 1fr));
          gap: 1px;
          overflow: hidden;
          margin-top: 6px;
          border-radius: 14px;
          background: var(--divider-color);
        }
        .daily-item {
          display: grid;
          gap: 5px;
          padding: 12px 14px;
          background: var(--secondary-background-color);
        }
        .daily-item span {
          color: var(--secondary-text-color);
          font-size: 12px;
        }
        .daily-item strong {
          font-size: 16px;
          font-weight: 500;
          white-space: nowrap;
        }
        @media (max-width: 700px) {
          ha-card { padding: 14px 12px; }
          .flow-title { align-items: flex-start; flex-direction: column; gap: 3px; }
          .flow-title span { font-size: 12px; }
          .stage-scroll { display: none; }
          .mobile-flow {
            display: grid;
            gap: 12px;
            padding: 14px 0 6px;
          }
          .mobile-flow .flow-node {
            position: relative;
            inset: auto;
            width: 100%;
            min-height: 92px;
          }
          .mobile-flow .flow-node strong { font-size: 21px; }
          .mobile-arrow {
            display: grid;
            place-items: center;
            height: 24px;
            color: var(--blue-color, #4f9de8);
            font-size: 23px;
            line-height: 1;
          }
          .mobile-split {
            display: grid;
            grid-template-columns: 1fr auto 1fr;
            align-items: center;
            gap: 8px;
            color: var(--secondary-text-color);
            font-size: 12px;
            text-align: center;
          }
          .mobile-split::before,
          .mobile-split::after {
            content: "";
            height: 2px;
            background: var(--blue-color, #4f9de8);
          }
          .mobile-branch {
            display: grid;
            gap: 10px;
            padding-left: 12px;
            border-left: 3px solid var(--blue-color, #4f9de8);
          }
          .mobile-branch-title {
            color: var(--secondary-text-color);
            font-size: 13px;
            font-weight: 500;
          }
          .mobile-sources {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 10px;
          }
          .mobile-sources .flow-node {
            align-items: flex-start;
            min-height: 112px;
            padding: 13px 12px;
          }
          .mobile-sources .flow-node ha-icon {
            width: 30px;
            height: 30px;
          }
          .mobile-sources .flow-node strong {
            font-size: 18px;
            white-space: normal;
          }
          .mobile-outside {
            border-left-color: color-mix(in srgb, var(--blue-color, #4f9de8) 55%, transparent);
          }
          .daily-strip { grid-template-columns: repeat(2, minmax(145px, 1fr)); }
          .daily-item:last-child { grid-column: 1 / -1; }
        }
      </style>
      <ha-card>
        <div class="flow-title">
          <h2>${this._escape(this._config.title || "Потік енергії")}</h2>
          <span>Зліва направо · потужність просто зараз</span>
        </div>
        <div class="stage-scroll" aria-label="Схема потоку енергії">
          <div class="flow-stage">
            <svg class="connectors" viewBox="0 0 1000 500" preserveAspectRatio="none" aria-hidden="true">
              <defs>
                <marker id="arrow-grid" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
                  <path d="M0,0 L0,6 L9,3 z" fill="var(--blue-color, #4f9de8)"></path>
                </marker>
                <marker id="arrow-load" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
                  <path d="M0,0 L0,6 L9,3 z" fill="var(--teal-color, #5cc8bd)"></path>
                </marker>
                <marker id="arrow-solar" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
                  <path d="M0,0 L0,6 L9,3 z" fill="var(--amber-color, #f3b33d)"></path>
                </marker>
                <marker id="arrow-battery-start" markerWidth="10" markerHeight="10" refX="2" refY="3" orient="auto" markerUnits="strokeWidth">
                  <path d="M9,0 L9,6 L0,3 z" fill="var(--pink-color, #ef9ab0)"></path>
                </marker>
                <marker id="arrow-battery-end" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
                  <path d="M0,0 L0,6 L9,3 z" fill="var(--pink-color, #ef9ab0)"></path>
                </marker>
              </defs>
              <path class="connector grid" d="M210 250 H255" marker-end="url(#arrow-grid)"></path>
              <path class="connector grid" d="M255 250 H340" marker-end="url(#arrow-grid)"></path>
              <path class="connector load" d="M550 250 H760" marker-end="url(#arrow-load)"></path>
              <path class="connector grid" d="M255 250 V390" marker-end="url(#arrow-grid)"></path>
              <path class="connector solar ${solarPower && solarPower > 1 ? "" : "inactive"}" d="M445 120 V180" ${solarPower && solarPower > 1 ? 'marker-end="url(#arrow-solar)"' : ""}></path>
              <path class="connector battery" d="M445 312 V390" marker-start="url(#arrow-battery-start)" marker-end="url(#arrow-battery-end)"></path>
              <circle class="junction" cx="255" cy="250" r="10"></circle>
            </svg>
            ${node({
              cls: "meter",
              entity: entities.main_power,
              icon: "mdi:transmission-tower",
              title: "Основний лічильник",
              value: this._formatPower(mainPower),
              meta: "увесь ввід у будинок",
            })}
            ${node({
              cls: "inverter",
              entity: entities.inverter_status,
              icon: "mdi:current-ac",
              title: "Інвертор",
              value: `Вхід ${this._formatPower(inverterInput)}`,
              meta: `${inverterConnected ? inverterState : "немає зв’язку"}${inverterMeta ? ` · ${inverterMeta}` : ""}`,
            })}
            ${node({
              cls: "house",
              entity: entities.house_power,
              icon: "mdi:home-lightning-bolt",
              title: "Будинок через інвертор",
              value: this._formatPower(housePower),
              meta: "захищене навантаження",
            })}
            ${node({
              cls: "solar",
              entity: entities.pv1_power || entities.pv1_voltage,
              icon: "mdi:solar-power-variant",
              title: "Сонячні панелі",
              value: pvText,
            })}
            ${node({
              cls: "battery",
              entity: entities.battery_soc,
              icon: "mdi:battery-high",
              title: "Батарея",
              value: batteryText,
              meta: "заряд ↕ розряд",
            })}
            ${node({
              cls: "outside",
              entity: entities.outside_power,
              icon: "mdi:home-import-outline",
              title: "Поза інвертором",
              value: this._formatPower(outsidePower),
              meta: "окрема гілка після лічильника",
            })}
          </div>
        </div>
        <div class="mobile-flow" aria-label="Схема потоку енергії для вузького екрана">
          ${node({
            cls: "meter",
            entity: entities.main_power,
            icon: "mdi:transmission-tower",
            title: "Основний лічильник",
            value: this._formatPower(mainPower),
            meta: "увесь ввід у будинок",
          })}
          <div class="mobile-arrow" aria-hidden="true">↓</div>
          <div class="mobile-split"><span>Розподіл після лічильника</span></div>
          <section class="mobile-branch" aria-label="Гілка через інвертор">
            <div class="mobile-branch-title">Основна гілка · через інвертор</div>
            ${node({
              cls: "inverter",
              entity: entities.inverter_status,
              icon: "mdi:current-ac",
              title: "Інвертор",
              value: `Вхід ${this._formatPower(inverterInput)}`,
              meta: `${inverterConnected ? inverterState : "немає зв’язку"}${inverterMeta ? ` · ${inverterMeta}` : ""}`,
            })}
            <div class="mobile-sources">
              ${node({
                cls: "solar",
                entity: entities.pv1_power || entities.pv1_voltage,
                icon: "mdi:solar-power-variant",
                title: "Сонячні панелі",
                value: pvText,
              })}
              ${node({
                cls: "battery",
                entity: entities.battery_soc,
                icon: "mdi:battery-high",
                title: "Батарея",
                value: batteryText,
                meta: "заряд ↕ розряд",
              })}
            </div>
            <div class="mobile-arrow" aria-hidden="true">↓</div>
            ${node({
              cls: "house",
              entity: entities.house_power,
              icon: "mdi:home-lightning-bolt",
              title: "Будинок через інвертор",
              value: this._formatPower(housePower),
              meta: "захищене навантаження",
            })}
          </section>
          <section class="mobile-branch mobile-outside" aria-label="Гілка поза інвертором">
            <div class="mobile-branch-title">Окрема гілка · поза інвертором</div>
            ${node({
              cls: "outside",
              entity: entities.outside_power,
              icon: "mdi:home-import-outline",
              title: "Споживання поза інвертором",
              value: this._formatPower(outsidePower),
              meta: "безпосередньо після лічильника",
            })}
          </section>
        </div>
        <div class="daily-strip" aria-label="Енергія за сьогодні">
          ${dailyItem("Весь ввід сьогодні", this._formatEnergy(totalDay))}
          ${dailyItem("Через інвертор із мережі", this._formatEnergy(inverterGridDay))}
          ${dailyItem("Поза інвертором", this._formatEnergy(outsideDay))}
          ${dailyItem("Будинок через інвертор", this._formatEnergy(houseDay))}
          ${dailyItem(
            "Батарея: заряд / розряд",
            `${this._formatEnergy(batteryChargeDay)} / ${this._formatEnergy(batteryDischargeDay)}`,
          )}
        </div>
      </ha-card>`;

    this.shadowRoot.querySelectorAll("[data-entity]").forEach((element) => {
      element.addEventListener("click", () => {
        const entityId = element.dataset.entity;
        if (!entityId) return;
        this.dispatchEvent(
          new CustomEvent("hass-more-info", {
            detail: { entityId },
            bubbles: true,
            composed: true,
          }),
        );
      });
    });
  }
}

if (!customElements.get("home-energy-flow-card")) {
  customElements.define("home-energy-flow-card", HomeEnergyFlowCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "home-energy-flow-card")) {
  window.customCards.push({
    type: "home-energy-flow-card",
    name: "Home Energy Flow Card",
    description: "Whole-site energy flow from the main meter through and around the inverter.",
    preview: false,
  });
}
