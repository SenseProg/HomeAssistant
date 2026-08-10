"""ОДНОРАЗОВИЙ КОМПОНЕНТ, інцидент 0cfd77b0. Видалити після застосування.

Smart Irrigation не зараховував полив зонам 1 і 2: 10.08 обидві полили по
п'ять хвилин, і bucket не змінився ні на тисячну, тоді як зона 5 того ж дня
піднялася з -3.56 до +1.08. Прив'язка клапана до зони лежить у `.storage`,
куди правила проєкту читати забороняють, а сенсор зони її в атрибутах не
віддає, тому дізнатися й полагодити її ззовні неможливо.

Цей компонент робить те саме, що зробила б панель Smart Irrigation, і тим
самим API: читає зони через `coordinator.store.async_get_zones()`, пише через
`async_update_zone`. Жодного прямого доступу до `.storage`.

Спрацьовує один раз на подію запуску Home Assistant:

1. виписує в журнал усі зони - id, назву, площу, продуктивність і поточний
   linked_entity, щоб стара прив'язка лишилася в історії й до неї можна було
   повернутися;
2. для зон 1, 2 і 5 звіряє linked_entity з фізичним клапаном LocalTuya і
   виправляє лише там, де вони різні;
3. перебудовує підписку observed watering, щоб зміна подіяла без рестарту.

Ідемпотентний: якщо прив'язка вже правильна, нічого не змінює. Зона береться
не за назвою, а за атрибутом `id` відповідного сенсора, тому перейменування
зон нічого не ламає.
"""

import asyncio
import logging

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

DOMAIN = "homemate_fixup"
CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)

_LOGGER = logging.getLogger(__name__)

SI_DOMAIN = "smart_irrigation"

# Сенсор зони Smart Irrigation -> фізичний клапан LocalTuya, який має бути до
# неї прив'язаний. Застарілі хмарні дублі switch.avtopoliv_kontroler_switch_N
# тут навмисно не згадуються: вони постійно unavailable і подій не дають.
WANTED_LINKS = {
    "sensor.smart_irrigation_zona1": "switch.avtopoliv_kontroler_avtopoliv_klapan_1",
    "sensor.smart_irrigation_zona2": "switch.avtopoliv_kontroler_avtopoliv_klapan_2",
    "sensor.smart_irrigation_zona5": "switch.avtopoliv_kontroler_avtopoliv_klapan_5",
}


async def _async_coordinator(hass: HomeAssistant):
    """Дочекатися координатора Smart Irrigation, але не назавжди."""
    for _ in range(12):
        coordinator = (hass.data.get(SI_DOMAIN) or {}).get("coordinator")
        if coordinator is not None:
            return coordinator
        await asyncio.sleep(5)
    return None


async def _async_fixup(hass: HomeAssistant) -> None:
    coordinator = await _async_coordinator(hass)
    if coordinator is None:
        _LOGGER.error("FIXUP: координатор Smart Irrigation не знайдено, нічого не роблю")
        return

    try:
        zones = await coordinator.store.async_get_zones()
    except Exception:  # noqa: BLE001 - діагностика важливіша за тип помилки
        _LOGGER.exception("FIXUP: не вдалося прочитати зони")
        return

    by_id = {}
    for zone in zones:
        zone_id = zone.get("id")
        by_id[zone_id] = zone
        _LOGGER.warning(
            "FIXUP зона id=%s name=%r size=%s throughput=%s linked_entity=%r",
            zone_id,
            zone.get("name"),
            zone.get("size"),
            zone.get("throughput"),
            zone.get("linked_entity"),
        )

    changed = 0
    for sensor_id, valve in WANTED_LINKS.items():
        state = hass.states.get(sensor_id)
        if state is None:
            _LOGGER.warning("FIXUP: сенсора %s немає, пропускаю", sensor_id)
            continue
        zone_id = state.attributes.get("id")
        zone = by_id.get(zone_id)
        if zone is None:
            _LOGGER.warning(
                "FIXUP: для %s не знайдено зони id=%s, пропускаю", sensor_id, zone_id
            )
            continue
        current = zone.get("linked_entity")
        if current == valve:
            _LOGGER.warning(
                "FIXUP: зона id=%s (%s) вже прив'язана правильно до %s",
                zone_id,
                sensor_id,
                valve,
            )
            continue
        if hass.states.get(valve) is None:
            _LOGGER.error(
                "FIXUP: клапана %s немає в системі, зону id=%s не чіпаю",
                valve,
                zone_id,
            )
            continue
        try:
            await coordinator.store.async_update_zone(zone_id, {"linked_entity": valve})
        except Exception:  # noqa: BLE001
            _LOGGER.exception("FIXUP: не вдалося оновити зону id=%s", zone_id)
            continue
        changed += 1
        _LOGGER.warning(
            "FIXUP ЗМІНЕНО: зона id=%s (%s) linked_entity %r -> %r",
            zone_id,
            sensor_id,
            current,
            valve,
        )

    if changed:
        try:
            await coordinator.async_setup_observed_watering()
        except Exception:  # noqa: BLE001
            _LOGGER.exception("FIXUP: не вдалося перебудувати підписку observed watering")
    _LOGGER.warning("FIXUP ЗАВЕРШЕНО, змінено зон: %s", changed)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Запланувати одноразове виправлення після повного старту Home Assistant."""

    async def _run(_event) -> None:
        await _async_fixup(hass)

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _run)
    return True
