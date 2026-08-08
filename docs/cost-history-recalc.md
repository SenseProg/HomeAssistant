# Перерахунок історії витрат за тарифом

## Навіщо

Тарифні лічильники `utility_meter` створені 8 серпня 2026 і за задумом рахують
лише вперед. Через це графіки витрат стартували порожніми, хоча довгострокова
статистика споживання в кВт-год уже існувала з 1 серпня.

Історію витрат відновлено з цієї статистики: кожну годину віднесено до дня або
ночі за київським часом і помножено на чинну ставку. Результат записано у
статистику сенсорів вартості через `recorder/import_statistics`, а живі
лічильники відкалібровано так, щоб продовжити з тієї самої точки без розриву.

## Що саме означають отримані цифри

Це реконструкція **за нинішніми ставками**, а не історична бухгалтерія.
Energy-дашборд за той самий період показує помітно меншу суму, бо до 3 серпня
2026 в ньому діяла плоска ціна 2,50 грн на цілу добу. Обидві цифри правильні,
але відповідають на різні питання:

- вкладка «Витрати» — скільки це коштувало б за сьогоднішнім двозонним тарифом;
- Energy-дашборд — скільки система нарахувала тоді.

Результат перерахунку на 8 серпня 2026: 120,2 кВт-год удень і 38,6 кВт-год
уночі, разом 158,8 кВт-год і 697,50 грн за період з 1 серпня.

## Межа можливого

Глибше 1 серпня 2026 даних немає — там закінчується довгострокова статистика
споживання. Розділити ще давнішу історію на день і ніч неможливо: у базі
збережена лише сумарна вартість без розбиття за тарифом.

## Коли повторювати

- Після зміни ставок, якщо потрібно перерахувати минуле за новими цінами.
- Після додавання нового пристрою з власним лічильником енергії.
- Після відновлення бази з резервної копії, якщо статистика вартості загубилась.

Повторний запуск безпечний: `import_statistics` перезаписує точки з тими самими
мітками часу, а не додає дублікати.

## Як запустити

Скрипт виконується в консолі браузера на будь-якій сторінці Home Assistant під
адміністратором. Він нічого не пише в конфігурацію — лише в статистику і в
показання лічильників.

Порядок обов'язковий: спершу імпорт статистики, потім калібрування. Якщо
зробити навпаки, HA запише проміжну точку зі старим значенням і в графіку
з'явиться сходинка.

### Крок 1. Імпорт історії у статистику

```js
const hass = document.querySelector('home-assistant').hass;
const DAY = 5.0, NIGHT = 2.5;
const kyivHour = iso => parseInt(new Date(iso).toLocaleString('en-GB',
  {timeZone:'Europe/Kyiv', hour:'2-digit', hour12:false}), 10);
const isDay = h => h >= 7 && h < 23;

const MAP = [
  {src:'sensor.inverter_total_energy_import', dst:'sensor.vitrati_vden_razom',       name:'Витрати вдень разом',       only:'day'},
  {src:'sensor.inverter_total_energy_import', dst:'sensor.vitrati_vnochi_razom',     name:'Витрати вночі разом',       only:'night'},
  {src:'sensor.inverter_total_energy_import', dst:'sensor.vitrati_na_merezhu_razom', name:'Витрати на мережу разом',   only:'both'},
  {src:'sensor.boiler_spozhito',              dst:'sensor.vitrati_boiler',           name:'Витрати - бойлер',          only:'both'},
  {src:'sensor.zariadka_avto_spozhito',       dst:'sensor.vitrati_zariadka_avto',    name:'Витрати - зарядка авто',    only:'both'},
  {src:'sensor.terneo_1_heating_energy',      dst:'sensor.vitrati_tepla_pidloga_1',  name:'Витрати - тепла підлога 1', only:'both'},
  {src:'sensor.terneo_2_heating_energy',      dst:'sensor.vitrati_tepla_pidloga_2',  name:'Витрати - тепла підлога 2', only:'both'},
  {src:'sensor.nasos_polivu_spozhito',        dst:'sensor.vitrati_nasos_polivu',     name:'Витрати - насос поливу',    only:'both'},
];

const srcIds = [...new Set(MAP.map(m => m.src))];
const raw = await hass.callWS({type:'recorder/statistics_during_period',
  start_time:'2026-07-25T00:00:00.000Z', statistic_ids: srcIds, period:'hour'});

for (const m of MAP) {
  const arr = raw[m.src] || [];
  if (!arr.length) continue;
  let sum = 0; const stats = [];
  for (const b of arr) {
    const day = isDay(kyivHour(b.start));
    let ch = (b.change != null && b.change > 0) ? b.change : 0;
    if (m.only === 'day' && !day) ch = 0;
    if (m.only === 'night' && day) ch = 0;
    sum += ch * (day ? DAY : NIGHT);
    stats.push({start: new Date(b.start).toISOString(),
                state: Math.round(sum*100)/100, sum: Math.round(sum*100)/100});
  }
  await hass.callWS({type:'recorder/import_statistics',
    metadata:{has_mean:false, has_sum:true, statistic_id:m.dst, source:'recorder',
              name:m.name, unit_of_measurement:'UAH'},
    stats});
  console.log(m.dst, 'imported', stats.length, 'hours, sum', sum.toFixed(2));
}
```

### Крок 2. Калібрування лічильників під імпортовану історію

```js
const hass = document.querySelector('home-assistant').hass;
const kyivHour = iso => parseInt(new Date(iso).toLocaleString('en-GB',
  {timeZone:'Europe/Kyiv', hour:'2-digit', hour12:false}), 10);
const kyivDate = iso => new Date(iso).toLocaleDateString('en-CA', {timeZone:'Europe/Kyiv'});
const isDay = h => h >= 7 && h < 23;
const today = new Date().toLocaleDateString('en-CA', {timeZone:'Europe/Kyiv'});

const SRC = {
  merezha:   'sensor.inverter_total_energy_import',
  boiler:    'sensor.boiler_spozhito',
  zariadka:  'sensor.zariadka_avto_spozhito',
  pidloha_1: 'sensor.terneo_1_heating_energy',
  pidloha_2: 'sensor.terneo_2_heating_energy',
  nasos:     'sensor.nasos_polivu_spozhito',
};
const raw = await hass.callWS({type:'recorder/statistics_during_period',
  start_time:'2026-07-25T00:00:00.000Z', statistic_ids: Object.values(SRC), period:'hour'});

const split = (src, f) => {
  let d = 0, n = 0;
  for (const b of (raw[src] || [])) {
    if (b.change == null || b.change <= 0) continue;
    if (f && !f(b)) continue;
    if (isDay(kyivHour(b.start))) d += b.change; else n += b.change;
  }
  return {d: Math.round(d*1000)/1000, n: Math.round(n*1000)/1000};
};

const targets = [];
for (const [key, src] of Object.entries(SRC)) {
  const a = split(src);
  targets.push(['sensor.' + key + '_za_tarifom_den', a.d],
               ['sensor.' + key + '_za_tarifom_nich', a.n]);
}
const td = split(SRC.merezha, b => kyivDate(b.start) === today);
const mo = split(SRC.merezha, b => kyivDate(b.start).slice(0,7) === today.slice(0,7));
targets.push(['sensor.merezha_dobovyi_den', td.d], ['sensor.merezha_dobovyi_nich', td.n],
             ['sensor.merezha_misiachnyi_den', mo.d], ['sensor.merezha_misiachnyi_nich', mo.n]);

for (const [ent, val] of targets) {
  const cur = parseFloat((hass.states[ent] || {}).state) || 0;
  const total = Math.round((val + cur) * 1000) / 1000;
  await hass.callWS({type:'call_service', domain:'utility_meter', service:'calibrate',
    target:{entity_id: ent}, service_data:{value: String(total)}});
  console.log(ent, '=', total);
}
```

Поточне значення лічильника додається до історичного навмисно: між створенням
лічильників і перерахунком вони встигають щось накопичити, і без цього доданку
той залишок загубився б.

## Пастки, на які вже наступили

**Сервісу `utility_meter.select_tariff` не існує.** У цій версії Home Assistant
домен `utility_meter` має лише `reset` і `calibrate`. Тариф перемикається через
`select.select_option` на сутностях `select.<ім'я_лічильника>`, і саме так
написана автоматизація «Тариф - перемкнути лічильники день/ніч». Помилковий
виклик падає мовчки: автоматизація числиться увімкненою, у «Проблемах» висить
`service_not_found`, а лічильники назавжди лишаються в тому тарифі, який був
активний під час їх створення. Розподіл день/ніч при цьому виглядає
правдоподібно, але неправильний.

**Нові лічильники стартують у стані `unknown`** і чекають першої зміни джерела.
Лічильник імпорту має крок 0,1 кВт-год, тому при малому споживанні очікування
може тривати годинами, і всі похідні сенсори вартості весь цей час недоступні.
`utility_meter.calibrate` зі значенням 0 виводить їх із цього стану одразу.

**`import_statistics` треба виконувати до `calibrate`, а не після.** Інакше HA
встигає записати проміжну точку зі старим значенням, і в графіку з'являється
сходинка.

## Якщо результат неправильний

Статистику окремого сенсора можна стерти й імпортувати заново:

```js
await hass.callWS({type:'recorder/clear_statistics',
  statistic_ids:['sensor.vitrati_vden_razom']});
```

Після цього повторити обидва кроки. Конфігурацію це не зачіпає — лічильники й
шаблонні сенсори лишаються на місці.
