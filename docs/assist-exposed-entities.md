# Список exposed-сутностей для Assist

## Що таке exposed і чому це список керування, а не читання

`exposed_entities` — штатний перелік Home Assistant, який визначає, до чого має
доступ голосовий/текстовий асистент через LLM API. Він єдиний і не поділяється
на «читати» та «керувати»: якщо сутність відкрита, вбудовані інструменти
`HassTurnOn`, `HassSetPosition` тощо можуть її змінювати.

У нашій збірці читання влаштоване **не** через цей список. Інтеграція
`claude_code_conversation` вкладає в кожен запит власний зріз станів усіх
сутностей (`_state_snapshot`, до 1000 рядків), тому агент бачить увесь будинок
незалежно від exposed. Через це exposed у нас має єдиний сенс — **перелік того,
чим агенту дозволено керувати**.

## Стан до 8 серпня 2026: 101 сутність, зокрема насос і клапани

До звуження серед exposed були:

- `switch.mini_switch_k601_2_switch_1_2` — насос поливу;
- `switch.avtopoliv_kontroler_avtopoliv_klapan_1` … `_8` — вісім клапанів;
- `switch.avtopoliv_kontroler_switch_1` … `_8` — застарілі хмарні дублі;
- `switch.zariadka_7_5kvt`, `switch.zariadka_7_5kvt_switch` — зарядка авто;
- `switch.energy_meter_switch`, `switch.mini_switch_k601_switch_1` тощо.

Це небезпечно навіть без нашого агента: у системі є другий пайплайн
`Home Assistant` зі штатним `conversation.home_assistant`, який exposed
використовує. Тобто фраза «увімкни насос», сказана штатному Assist, могла
запустити насос повз усі інтерлоки поливу — сухий хід при закритих клапанах,
обхід послідовності «клапан першим, насос другим».

## Стан після звуження: вісім керованих сутностей

| Сутність | Що це |
|---|---|
| `climate.terneo_1` | тепла підлога, контур 1 |
| `climate.terneo_2` | тепла підлога, кухня |
| `fan.2_floor_supply_fan` | PRANA, притік |
| `fan.2_floor_extract_fan` | PRANA, витяжка |
| `fan.siku_blauberg_fan_192_168_50_27` | Blauberg, кімната хлопців |
| `fan.siku_blauberg_fan_192_168_50_123` | Blauberg, кімната Олесі |
| `switch.2_floor_heater` | PRANA, нагрівач |
| `switch.2_floor_winter` | PRANA, зимовий режим |

Рішення користувача 8 серпня 2026: читати — все, керувати — лише ці вісім.

## Що навмисно НЕ відкрито

Насос, усі клапани поливу, зарядка авто, перемикачі інвертора та лічильників.
Полив має жорсткі інтерлоки (клапан відкривається першим, насос зупиняється
першим, максимум три години безперервної роботи), і мовна модель не повинна
мати технічної можливості їх обійти. Керування поливом лишається за
дашбордом, скриптами та Irrigation Unlimited.

## Повний список, який був до звуження (для відкату)

```text
binary_sensor.cam1_motion
binary_sensor.sonoff_a48001bcc7
climate.terneo_1
climate.terneo_2
cover.sonoff_1001338bf7
cover.sonoff_10016e1b2d
fan.2_floor_extract_fan
fan.2_floor_supply_fan
fan.siku_blauberg_fan_192_168_50_123
fan.siku_blauberg_fan_192_168_50_27
fan.sonoff_100135bdf6
light.sonoff_1000dbc5aa
light.sonoff_1000dbe843
light.sonoff_10011fd722
light.sonoff_100135bdf6_1
media_player.32_odyssey_g7
media_player.32_odyssey_g7_2
media_player.32_odyssey_g7_ls32dg700ezxua
media_player.odyssey_g7
media_player.odyssey_g7_2
media_player.televizor_tcl
sensor.2_floor_carbon_dioxide
sensor.2_floor_humidity
sensor.2_floor_inside_temperature
sensor.2_floor_outside_temperature
sensor.2_floor_outside_temperature_2
sensor.2i_poverkh_t_h_humidity
sensor.2i_poverkh_t_h_temperature
sensor.inverter_battery_temperature
sensor.inverter_temperature
sensor.kimnata_olesi_sonoff_a480144e06_humidity
sensor.kimnata_olesi_sonoff_a480144e06_temperature
sensor.na_dvori_t_h_humidity
sensor.na_dvori_t_h_temperature
sensor.siku_blauberg_fan_192_168_50_123_humidity
sensor.siku_blauberg_fan_192_168_50_27_humidity
sensor.sonoff_1001360105_humidity
sensor.sonoff_1001360105_temperature
sensor.sonoff_a48001c18f_humidity
sensor.sonoff_a48001c18f_temperature
sensor.sonoff_a48005a66a_humidity
sensor.sonoff_a48005a66a_temperature
sensor.sonoff_a48005e8ed_humidity
sensor.sonoff_a48005e8ed_temperature
sensor.sonoff_a4800819f3_humidity
sensor.sonoff_a4800819f3_temperature
sensor.t_h_sensor_2_humidity
sensor.t_h_sensor_2_temperature
sensor.t_h_sensor_humidity
sensor.t_h_sensor_temperature
sensor.terneo_1_floor_temperature
sensor.terneo_1_target_temperature
sensor.terneo_2_air_temperature
sensor.terneo_2_floor_temperature
sensor.terneo_2_target_temperature
sensor.zariadka_7_5kvt_device_temperature
switch.2_floor_auto
switch.2_floor_auto_plus
switch.2_floor_bound
switch.2_floor_heater
switch.2_floor_winter
switch.avtopoliv_kontroler_avtopoliv_klapan_1
switch.avtopoliv_kontroler_avtopoliv_klapan_2
switch.avtopoliv_kontroler_avtopoliv_klapan_3
switch.avtopoliv_kontroler_avtopoliv_klapan_4
switch.avtopoliv_kontroler_avtopoliv_klapan_5
switch.avtopoliv_kontroler_avtopoliv_klapan_6
switch.avtopoliv_kontroler_avtopoliv_klapan_7
switch.avtopoliv_kontroler_avtopoliv_klapan_8
switch.avtopoliv_kontroler_switch_1
switch.avtopoliv_kontroler_switch_2
switch.avtopoliv_kontroler_switch_3
switch.avtopoliv_kontroler_switch_4
switch.avtopoliv_kontroler_switch_5
switch.avtopoliv_kontroler_switch_6
switch.avtopoliv_kontroler_switch_7
switch.avtopoliv_kontroler_switch_8
switch.energy_meter_switch
switch.energy_meter_switch_2
switch.mini_switch_k601_2_switch_1
switch.mini_switch_k601_2_switch_1_2
switch.mini_switch_k601_switch_1
switch.sonoff_1000e7c6eb
switch.sonoff_1001360105
switch.sonoff_100143263e
switch.sonoff_10020db3dd
switch.terneo_1_children_lock
switch.terneo_1_cooling_mode
switch.terneo_1_night_brightness
switch.terneo_1_power
switch.zariadka_7_5kvt
switch.zariadka_7_5kvt_switch
todo.shopping_list
```

Решта рядків списку — сенсори температури й вологості тих самих пристроїв;
повний перелік відновлюється командою нижче.

## Як переглянути або змінити

Читання поточного стану з консолі браузера під адміністратором:

```js
const hass = document.querySelector('home-assistant').hass;
const r = await hass.callWS({type: 'homeassistant/expose_entity/list'});
Object.entries(r.exposed_entities).filter(([, v]) => v?.conversation).map(([id]) => id);
```

Зміна — тим самим штатним API, а не редагуванням `.storage`:

```js
await hass.callWS({
  type: 'homeassistant/expose_entity/expose',
  assistants: ['conversation'],
  entity_ids: ['switch.example'],
  should_expose: false,
});
```

В інтерфейсі те саме доступне в Налаштування → Голосові асистенти → Expose.
