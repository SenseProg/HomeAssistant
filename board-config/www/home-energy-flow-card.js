/* Контури MDI вставлені дослівно, а не через <ha-icon>.
 * Причина: у shadow DOM цієї картки ha-icon лишається порожньою оболонкою —
 * заміряно 22.08.2026, усі шість іконок мали розмір 38x38 і жодного <svg>
 * усередині. Елемент вставляється рядком через innerHTML, і коли iconset HA
 * ще не готовий, апгрейд custom element уже не відбувається. Inline-контур не
 * залежить ні від чого й малюється завжди.
 * Шляхи взяті з самого Home Assistant, а не переписані з пам'яті. */
/* Батарея показує рівень, а не абстрактний значок: контур обирається за SOC,
 * як це зроблено в sunsynk-схемі. Під час заряду — окремий контур із блискавкою,
 * щоб напрямок читався навіть без анімації лінії. */
function batteryIcon(soc, power) {
  if (Number.isFinite(Number(power)) && Number(power) > 5) return "battery-charging";
  const level = Number(soc);
  if (!Number.isFinite(level)) return "battery-outline";
  if (level >= 97) return "battery-full";
  if (level >= 80) return "battery-90";
  if (level >= 60) return "battery-70";
  if (level >= 40) return "battery-50";
  if (level >= 20) return "battery-30";
  if (level >= 5) return "battery-10";
  return "battery-outline";
}

const MDI = {
  "mdi:transmission-tower": "M8.28,5.45L6.5,4.55L7.76,2H16.23L17.5,4.55L15.72,5.44L15,4H9L8.28,5.45M18.62,8H14.09L13.3,5H10.7L9.91,8H5.38L4.1,10.55L5.89,11.44L6.62,10H17.38L18.1,11.45L19.89,10.56L18.62,8M17.77,22H15.7L15.46,21.1L12,15.9L8.53,21.1L8.3,22H6.23L9.12,11H11.19L10.83,12.35L12,14.1L13.16,12.35L12.81,11H14.88L17.77,22M11.4,15L10.5,13.65L9.32,18.13L11.4,15M14.68,18.12L13.5,13.64L12.6,15L14.68,18.12Z",
  "mdi:current-ac": "M12.43 11C12.28 10.84 10 7 7 7S2.32 10.18 2 11V13H11.57C11.72 13.16 14 17 17 17S21.68 13.82 22 13V11H12.43M7 9C8.17 9 9.18 9.85 10 11H4.31C4.78 10.17 5.54 9 7 9M17 15C15.83 15 14.82 14.15 14 13H19.69C19.22 13.83 18.46 15 17 15Z",
  "mdi:home-lightning-bolt": "M12 3L2 12H5V20H19V12H22L12 3M11.5 18V14H9L12.5 7V11H15L11.5 18Z",
  "mdi:solar-power-variant": "M3.33 16H11V13H4L3.33 16M13 16H20.67L20 13H13V16M21.11 18H13V22H22L21.11 18M2 22H11V18H2.89L2 22M11 8H13V11H11V8M15.76 7.21L17.18 5.79L19.3 7.91L17.89 9.33L15.76 7.21M4.71 7.91L6.83 5.79L8.24 7.21L6.12 9.33L4.71 7.91M3 2H6V4H3V2M18 2H21V4H18V2M12 7C14.76 7 17 4.76 17 2H7C7 4.76 9.24 7 12 7Z",
  "mdi:battery-high": "M16 20H8V6H16M16.67 4H15V2H9V4H7.33C6.6 4 6 4.6 6 5.33V20.67C6 21.4 6.6 22 7.33 22H16.67C17.41 22 18 21.41 18 20.67V5.33C18 4.6 17.4 4 16.67 4M15 16H9V19H15V16M15 7H9V10H15V7M15 11.5H9V14.5H15V11.5Z",
  "battery-outline": "M16,20H8V6H16M16.67,4H15V2H9V4H7.33A1.33,1.33 0 0,0 6,5.33V20.67C6,21.4 6.6,22 7.33,22H16.67A1.33,1.33 0 0,0 18,20.67V5.33C18,4.6 17.4,4 16.67,4Z",
  "battery-10": "M16,18H8V6H16M16.67,4H15V2H9V4H7.33A1.33,1.33 0 0,0 6,5.33V20.67C6,21.4 6.6,22 7.33,22H16.67A1.33,1.33 0 0,0 18,20.67V5.33C18,4.6 17.4,4 16.67,4Z",
  "battery-30": "M16,15H8V6H16M16.67,4H15V2H9V4H7.33A1.33,1.33 0 0,0 6,5.33V20.67C6,21.4 6.6,22 7.33,22H16.67A1.33,1.33 0 0,0 18,20.67V5.33C18,4.6 17.4,4 16.67,4Z",
  "battery-50": "M16,13H8V6H16M16.67,4H15V2H9V4H7.33A1.33,1.33 0 0,0 6,5.33V20.67C6,21.4 6.6,22 7.33,22H16.67A1.33,1.33 0 0,0 18,20.67V5.33C18,4.6 17.4,4 16.67,4Z",
  "battery-70": "M16,10H8V6H16M16.67,4H15V2H9V4H7.33A1.33,1.33 0 0,0 6,5.33V20.67C6,21.4 6.6,22 7.33,22H16.67A1.33,1.33 0 0,0 18,20.67V5.33C18,4.6 17.4,4 16.67,4Z",
  "battery-90": "M16,8H8V6H16M16.67,4H15V2H9V4H7.33A1.33,1.33 0 0,0 6,5.33V20.67C6,21.4 6.6,22 7.33,22H16.67A1.33,1.33 0 0,0 18,20.67V5.33C18,4.6 17.4,4 16.67,4Z",
  "battery-full": "M16.67,4H15V2H9V4H7.33A1.33,1.33 0 0,0 6,5.33V20.67C6,21.4 6.6,22 7.33,22H16.67A1.33,1.33 0 0,0 18,20.67V5.33C18,4.6 17.4,4 16.67,4Z",
  "battery-charging": "M12 20H4V6H12M12.67 4H11V2H5V4H3.33C2.6 4 2 4.6 2 5.33V20.67C2 21.4 2.6 22 3.33 22H12.67C13.41 22 14 21.41 14 20.67V5.33C14 4.6 13.4 4 12.67 4M11 16H5V19H11V16M11 7H5V10H11V7M11 11.5H5V14.5H11V11.5M23 10H20V3L15 13H18V21",
  "mdi:home-import-outline": "M15 13L11 17V14H2V12H11V9L15 13M5 20V16H7V18H17V10.19L12 5.69L7.21 10H4.22L12 3L22 12H19V20H5Z",
};

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

    /* Гілка «жива», коли крізь неї реально щось іде. Поріг у 5 Вт відсікає
     * шум лічильників, інакше нульова лінія повзла б безкінечно. Тривалість
     * циклу обернена до потужності й затиснута в межі 0.55–5 с: швидше око не
     * читає як напрямок, повільніше виглядає як зупинка. */
    const flowLine = (power, cls, reverseWhenNegative = false) => {
      const value = Number(power);
      const magnitude = Number.isFinite(value) ? Math.abs(value) : 0;
      if (magnitude < 5) return { cls: `connector ${cls} inactive`, style: "" };
      const duration = Math.min(5, Math.max(0.55, 3200 / magnitude));
      const reverse = reverseWhenNegative && value < 0 ? " reverse" : "";
      return {
        cls: `connector ${cls} flowing${reverse}`,
        style: ` style="--flow-duration:${duration.toFixed(2)}s"`,
      };
    };
    const liveNode = (power, threshold = 5) => {
      const value = Number(power);
      return Number.isFinite(value) && Math.abs(value) >= threshold ? " live" : "";
    };

    const gridIn = flowLine(mainPower, "grid");
    const toInverter = flowLine(inverterInput, "grid");
    const toHouse = flowLine(housePower, "load");
    const toOutside = flowLine(outsidePower, "grid");
    /* Батарея — єдина двонапрямна гілка: додатне значення означає заряд,
     * тож при розряді анімація йде у зворотний бік. */
    const batteryFlow = flowLine(batteryPower, "battery", true);
    const solarFlow = flowLine(solarPower, "solar");

    const node = ({ cls, entity, icon, title, value, meta = "", live = "" }) => `
      <button class="flow-node ${cls}${live}" data-entity="${this._escape(entity || "")}" type="button">
        <svg class="node-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="${MDI[icon] || ''}"></path></svg>
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
          stroke-width: 2.4;
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
          opacity: 0.45;
        }
        /* Рух по лінії показує напрямок і силу потоку одночасно: тривалість
         * циклу задається інлайном як --flow-duration і обернено залежить від
         * потужності. Малюється поверх суцільної лінії окремим шаром, щоб сама
         * лінія лишалася на місці, коли потік зупиняється. */
        .connector.flowing {
          stroke-dasharray: 10 14;
          animation: flow-dash var(--flow-duration, 2.5s) linear infinite;
        }
        .connector.flowing.reverse { animation-direction: reverse; }
        @keyframes flow-dash {
          from { stroke-dashoffset: 24; }
          to { stroke-dashoffset: 0; }
        }
        /* Пульсація вузла, крізь який зараз іде помітна потужність. */
        .flow-node.live { border-color: color-mix(in srgb, currentColor 45%, transparent); }
        .flow-node.live .node-icon { animation: node-pulse 2.4s ease-in-out infinite; }
        @keyframes node-pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.72; transform: scale(0.94); }
        }
        @media (prefers-reduced-motion: reduce) {
          .connector.flowing { animation: none; }
          .flow-node.live .node-icon { animation: none; }
        }
        .junction {
          fill: var(--blue-color, #4f9de8);
          stroke: var(--ha-card-background, var(--card-background-color));
          stroke-width: 3;
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
        .flow-node .node-icon {
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
        .meter .node-icon,
        .inverter .node-icon { fill: var(--blue-color, #4f9de8); }
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
        .house .node-icon { fill: var(--teal-color, #5cc8bd); }
        .solar {
          left: 36.5%;
          top: 8px;
          width: 16%;
          border-color: color-mix(in srgb, var(--amber-color, #f3b33d) 65%, transparent);
        }
        .solar .node-icon { fill: var(--amber-color, #f3b33d); }
        .battery {
          left: 36.5%;
          bottom: 8px;
          width: 16%;
          border-color: color-mix(in srgb, var(--pink-color, #ef9ab0) 65%, transparent);
        }
        .battery .node-icon { fill: var(--pink-color, #ef9ab0); }
        .outside {
          left: 14%;
          bottom: 8px;
          width: 22%;
          border-color: color-mix(in srgb, var(--blue-color, #4f9de8) 45%, transparent);
        }
        .outside .node-icon { fill: var(--blue-color, #4f9de8); }
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
          .mobile-sources .flow-node .node-icon {
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
                <marker id="arrow-grid" markerWidth="9" markerHeight="9" refX="7" refY="2.6" orient="auto" markerUnits="userSpaceOnUse">
                  <path d="M0,0 L0,5.2 L7.5,2.6 z" fill="var(--blue-color, #4f9de8)"></path>
                </marker>
                <marker id="arrow-load" markerWidth="14" markerHeight="14" refX="11" refY="4" orient="auto" markerUnits="userSpaceOnUse">
                  <path d="M0,0 L0,8 L12,4 z" fill="var(--teal-color, #5cc8bd)"></path>
                </marker>
                <marker id="arrow-solar" markerWidth="14" markerHeight="14" refX="11" refY="4" orient="auto" markerUnits="userSpaceOnUse">
                  <path d="M0,0 L0,8 L12,4 z" fill="var(--amber-color, #f3b33d)"></path>
                </marker>
                <marker id="arrow-battery-start" markerWidth="9" markerHeight="9" refX="2" refY="2.6" orient="auto" markerUnits="userSpaceOnUse">
                  <path d="M7.5,0 L7.5,5.2 L0,2.6 z" fill="var(--pink-color, #ef9ab0)"></path>
                </marker>
                <marker id="arrow-battery-end" markerWidth="14" markerHeight="14" refX="11" refY="4" orient="auto" markerUnits="userSpaceOnUse">
                  <path d="M0,0 L0,8 L12,4 z" fill="var(--pink-color, #ef9ab0)"></path>
                </marker>
              </defs>
              <path class="${gridIn.cls}" d="M210 250 H255" marker-end="url(#arrow-grid)"${gridIn.style}></path>
              <path class="${toInverter.cls}" d="M255 250 H340" marker-end="url(#arrow-grid)"${toInverter.style}></path>
              <path class="${toHouse.cls}" d="M550 250 H760" marker-end="url(#arrow-load)"${toHouse.style}></path>
              <path class="${toOutside.cls}" d="M255 250 V390" marker-end="url(#arrow-grid)"${toOutside.style}></path>
              <path class="${solarFlow.cls}" d="M445 120 V180" ${solarPower && solarPower > 1 ? 'marker-end="url(#arrow-solar)"' : ""}${solarFlow.style}></path>
              <path class="${batteryFlow.cls}" d="M445 312 V390" marker-start="url(#arrow-battery-start)" marker-end="url(#arrow-battery-end)"${batteryFlow.style}></path>
              <circle class="junction" cx="255" cy="250" r="6"></circle>
            </svg>
            ${node({
              cls: "meter",
              live: liveNode(mainPower),
              entity: entities.main_power,
              icon: "mdi:transmission-tower",
              title: "Основний лічильник",
              value: this._formatPower(mainPower),
              meta: "увесь ввід у будинок",
            })}
            ${node({
              cls: "inverter",
              live: liveNode(inverterInput),
              entity: entities.inverter_status,
              icon: "mdi:current-ac",
              title: "Інвертор",
              value: `Вхід ${this._formatPower(inverterInput)}`,
              meta: `${inverterConnected ? inverterState : "немає зв’язку"}${inverterMeta ? ` · ${inverterMeta}` : ""}`,
            })}
            ${node({
              cls: "house",
              live: liveNode(housePower),
              entity: entities.house_power,
              icon: "mdi:home-lightning-bolt",
              title: "Будинок через інвертор",
              value: this._formatPower(housePower),
              meta: "захищене навантаження",
            })}
            ${node({
              cls: "solar",
              live: liveNode(solarPower),
              entity: entities.pv1_power || entities.pv1_voltage,
              icon: "mdi:solar-power-variant",
              title: "Сонячні панелі",
              value: pvText,
            })}
            ${node({
              cls: "battery",
              live: liveNode(batteryPower),
              entity: entities.battery_soc,
              icon: batteryIcon(batterySoc, batteryPower),
              title: "Батарея",
              value: batteryText,
              meta: "заряд ↕ розряд",
            })}
            ${node({
              cls: "outside",
              live: liveNode(outsidePower),
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
              live: liveNode(mainPower),
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
              live: liveNode(inverterInput),
              entity: entities.inverter_status,
              icon: "mdi:current-ac",
              title: "Інвертор",
              value: `Вхід ${this._formatPower(inverterInput)}`,
              meta: `${inverterConnected ? inverterState : "немає зв’язку"}${inverterMeta ? ` · ${inverterMeta}` : ""}`,
            })}
            <div class="mobile-sources">
              ${node({
                cls: "solar",
              live: liveNode(solarPower),
                entity: entities.pv1_power || entities.pv1_voltage,
                icon: "mdi:solar-power-variant",
                title: "Сонячні панелі",
                value: pvText,
              })}
              ${node({
                cls: "battery",
              live: liveNode(batteryPower),
                entity: entities.battery_soc,
                icon: batteryIcon(batterySoc, batteryPower),
                title: "Батарея",
                value: batteryText,
                meta: "заряд ↕ розряд",
              })}
            </div>
            <div class="mobile-arrow" aria-hidden="true">↓</div>
            ${node({
              cls: "house",
              live: liveNode(housePower),
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
              live: liveNode(outsidePower),
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
