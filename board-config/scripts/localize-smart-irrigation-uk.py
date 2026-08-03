#!/usr/bin/env python3
"""Apply the HomeMate Ukrainian display-name overlay to Smart Irrigation."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


UKRAINIAN_NAME = "Розумний полив"
UPSTREAM_NAME = "Smart Irrigation"


def add_frontend_help(data):
    """Add concise, practical explanations to the Ukrainian configuration UI."""
    common_labels = data.setdefault("common", {}).setdefault("labels", {})
    common_labels["module"] = (
        "Модуль розрахунку — PyETO за погодою, Static за сталою нормою"
    )

    zones = data.setdefault("panels", {}).setdefault("zones", {})
    zones["description"] = (
        "Площа та витрата не задають час напряму: вони переводять дефіцит води "
        "в міліметрах у секунди. Для 250 м² і 40 л/хв інтенсивність становить "
        "9,6 мм/год: 4 мм дефіциту — це 25 хвилин, а 0,05 мм — близько 19 секунд."
    )
    zone_labels = zones.setdefault("labels", {})
    zone_labels.update(
        {
            "name": "Назва — довільне ім’я зони",
            "size": "Площа ділянки, що поливається",
            "throughput": "Загальна витрата води через усю зону",
            "drainage_rate": "Дренаж насиченого ґрунту",
            "state": "Режим роботи зони (Автоматичний = PyETO)",
            "mapping": "Група погодних датчиків (0 = Open-Meteo)",
            "bucket": "Водний баланс ґрунту (− дефіцит, + запас)",
            "maximum-bucket": "Максимальний запас води у ґрунті",
            "et-deficiency": "Добовий дефіцит евапотранспірації (довідково)",
            "lead-time": "Додатковий час до розрахованої тривалості",
            "maximum-duration": "Гранична тривалість одного запуску",
            "multiplier": "Коефіцієнт тривалості",
            "duration": "Розрахована тривалість поливу",
            "linked-entity-hint": (
                "Фізичний клапан або реле цієї зони. У замкненому контурі "
                "Розумний полив лише спостерігає, скільки часу цей перемикач "
                "реально був увімкнений, і за витратою зони додає подану воду "
                "до водного балансу. Пряме керування клапаном для HomeMate "
                "залишається вимкненим — безпечну послідовність виконує "
                "Irrigation Unlimited."
            ),
            "flow-sensor-hint": (
                "Необов’язковий фізичний водомір із постійно зростаючим "
                "підсумком (л або м³), а не датчик миттєвої витрати. Зараз його "
                "немає, тому поле слід залишити порожнім: вода вже рахується як "
                "40 л/хв × фактичний час роботи клапана. Віртуальний лічильник "
                "лише дублював би цей самий розрахунок."
            ),
            "size-hint": (
                "Фактична площа, яку поливає саме ця зона. Для зони 1 і зони 2 "
                "встановлено по 250 м²."
            ),
            "throughput-hint": (
                "Сумарна витрата всіх форсунок цієї зони, не паспортна подача "
                "насоса. Зараз прийнято 40 л/хв; уточнити можна заміром відра "
                "або фізичним водоміром."
            ),
            "drainage-rate-hint": (
                "Швидкість природного відтоку лише за надлишку води, коли "
                "баланс додатний. Не скорочує полив при дефіциті. 50,8 мм/год — "
                "типове початкове значення; змінювати після визначення типу ґрунту."
            ),
            "bucket-hint": (
                "Поточний накопичений водний баланс: мінус — нестача води й "
                "потреба в поливі, нуль — баланс, плюс — запас після дощу або поливу."
            ),
            "maximum-bucket-hint": (
                "Верхня межа додатного запасу води, який може втримати ґрунт. "
                "Надлишок вище цієї межі вважається стоком; від’ємний дефіцит "
                "цим значенням не обмежується."
            ),
            "et-deficiency-hint": (
                "Розрахована PyETO добова втрата води через випаровування та "
                "рослини, без накопиченого балансу. Поле лише для читання."
            ),
            "lead-time-hint": (
                "Секунди, які безумовно додаються до ненульового розрахунку "
                "після всіх обмежень. Потрібні лише для заповнення труб або "
                "виходу системи на тиск; для HomeMate залишити 0."
            ),
            "maximum-duration-hint": (
                "Запобіжна верхня межа одного запуску зони. 3600 с = 60 хв. "
                "Окремий захист насоса на 3 години залишається додатковим бар’єром."
            ),
            "multiplier-hint": (
                "Калібрувальний множник розрахованого часу: 1,0 — без змін; "
                "0,8 скорочує на 20 %, 1,2 збільшує на 20 %."
            ),
            "duration-hint": (
                "Фінальний час поливу в секундах після водного балансу, "
                "множника, максимальної тривалості та додаткового часу."
            ),
        }
    )
    states = zone_labels.setdefault("states", {})
    states.update(
        {
            "automatic": "Автоматичний — використовувати розрахунок модуля",
            "disabled": "Вимкнено — не розраховувати й не поливати",
            "manual": "Ручний — використовувати задану тривалість",
        }
    )

    calcmodules = data.setdefault("calcmodules", {})
    calcmodules.setdefault("pyeto", {})["description"] = (
        "PyETO: розраховує щоденний дефіцит за температурою, вологістю, "
        "вітром, сонячною радіацією та опадами (FAO-56)."
    )
    calcmodules.setdefault("static", {})["description"] = (
        "Static: щодня додає задану сталу зміну водного балансу. Від’ємне "
        "значення означає дефіцит; −4 мм для 250 м² і 40 л/хв дає 25 хвилин."
    )
    calcmodules.setdefault("passthrough", {})["description"] = (
        "Passthrough: бере готову добову зміну водного балансу із зовнішнього "
        "датчика евапотранспірації."
    )

    modules = data.setdefault("panels", {}).setdefault("modules", {})
    modules["description"] = (
        "PyETO автоматично обчислює зміну водного балансу з погоди. Static "
        "використовує одну сталу норму: поле Delta задається в мм за цикл "
        "розрахунку; мінус означає нестачу води. Для цієї системи Delta = −4 "
        "мм відповідає приблизно 25 хвилинам поливу. У PyETO залиште "
        "«Прибережна місцевість» вимкнено і «Днів прогнозу» = 0."
    )

    mappings = data.setdefault("panels", {}).setdefault("mappings", {})
    mappings["description"] = (
        "Група 0 вже використовується обома зонами й отримує з Open-Meteo всі "
        "дев’ять потрібних показників: точку роси, евапотранспірацію, вологість, "
        "опади, поточні опади, тиск, сонячну радіацію, температуру та вітер. "
        "Додаткова група потрібна лише для окремої локальної метеостанції або "
        "іншого мікроклімату."
    )
    mappings.setdefault("labels", {})["mapping-name"] = (
        "Назва групи погодних датчиків"
    )

    observed = data.setdefault("observed_watering", {})
    observed["title"] = "Облік фактичного поливу (замкнений контур)"
    observed["description"] = (
        "Замкнений контур означає зворотний зв’язок: інтеграція бачить реальний "
        "стан прив’язаного клапана, рахує подану воду за часом і витратою та "
        "поповнює водний баланс. Це облік, а не пряме керування клапаном."
    )
    observed["enabled_label"] = "Увімкнути облік фактичного поливу"
    observed["direct_control_label"] = (
        "Дозволити Smart Irrigation напряму керувати клапаном (небезпечно)"
    )
    observed["direct_control_description"] = (
        "Для HomeMate залишити вимкненим: клапанами й насосом керує Irrigation "
        "Unlimited, який забезпечує правильний порядок запуску та зупинки."
    )
    return data


def replace_ukrainian_terms(value):
    """Replace untranslated irrigation jargon in Ukrainian display strings."""
    if isinstance(value, str):
        exact = {
            "«Фіктивний» модуль зі статичною налаштовуваною delta":
                "Статичний модуль із заданою вручну добовою зміною водного балансу",
            "Транзитний модуль, який повертає значення датчика евапотранспірації як delta":
                "Модуль, який використовує значення датчика евапотранспірації як добову зміну водного балансу",
            "delta": "Добова зміна водного балансу",
            "Дельта": "Добова зміна водного балансу",
            "Daily ET deficiency": "Добовий дефіцит евапотранспірації",
        }
        if value in exact:
            return exact[value]
        value = re.sub(r"(?<![A-Za-z0-9_])Bucket(?![A-Za-z0-9_])", "Водний баланс ґрунту", value)
        value = re.sub(r"(?<![A-Za-z0-9_])bucket(?![A-Za-z0-9_])", "водний баланс ґрунту", value)
        # Upgrade an overlay applied by an earlier version of this script.
        # The negative look-ahead keeps repeated runs idempotent.
        value = re.sub(r"Водний баланс(?! ґрунту)", "Водний баланс ґрунту", value)
        value = re.sub(r"водний баланс(?! ґрунту)", "водний баланс ґрунту", value)
        value = value.replace(
            "Daily ET deficiency", "Добовий дефіцит евапотранспірації"
        )
        value = re.sub(
            r"(?<![A-Za-z0-9_])(?:delta|Дельта)(?![A-Za-z0-9_])",
            "добова зміна водного балансу",
            value,
        )
        value = re.sub(r"(?<![A-Za-z0-9_])drainage(?![A-Za-z0-9_])", "дренаж", value)
        return value
    if isinstance(value, list):
        return [replace_ukrainian_terms(item) for item in value]
    if isinstance(value, dict):
        return {key: replace_ukrainian_terms(item) for key, item in value.items()}
    return value


def replace_brand(value):
    if isinstance(value, str):
        return value.replace(UPSTREAM_NAME, UKRAINIAN_NAME)
    if isinstance(value, list):
        return [replace_brand(item) for item in value]
    if isinstance(value, dict):
        return {key: replace_brand(item) for key, item in value.items()}
    return value


def update_json(path: Path, *, set_manifest_name: bool = False) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data = replace_ukrainian_terms(replace_brand(data))
    if path.name == "uk.json" and path.parent.name == "languages":
        data = add_frontend_help(data)
    if path.name == "uk.json" and path.parent.name == "translations":
        sensor_names = data.setdefault("entity", {}).setdefault("sensor", {})
        sensor_names.update(
            {
                "duration": {"name": "Тривалість поливу"},
                "bucket": {"name": "Водний баланс ґрунту"},
                "et_value": {"name": "Застосована евапотранспірація"},
                "et_deficiency": {"name": "Добовий дефіцит евапотранспірації"},
                "current_drainage": {"name": "Поточний дренаж"},
                "last_irrigation": {"name": "Останній полив"},
                "water_used": {"name": "Використано води"},
            }
        )
    if set_manifest_name:
        data["name"] = UKRAINIAN_NAME
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def iter_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from iter_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from iter_strings(item)


def iter_string_pairs(old_value, new_value):
    if isinstance(old_value, str) and isinstance(new_value, str):
        yield old_value, new_value
    elif isinstance(old_value, list) and isinstance(new_value, list):
        for old_item, new_item in zip(old_value, new_value):
            yield from iter_string_pairs(old_item, new_item)
    elif isinstance(old_value, dict) and isinstance(new_value, dict):
        for key in old_value.keys() & new_value.keys():
            yield from iter_string_pairs(old_value[key], new_value[key])


def replace_exact(bundle, old, new, expected_count, label):
    """Apply one pinned-frontend patch once and validate its cardinality."""
    old_count = bundle.count(old)
    new_count = bundle.count(new)
    if old_count:
        if old_count != expected_count:
            raise SystemExit(
                f"Unexpected {label} occurrence count: {old_count} "
                f"(expected {expected_count})"
            )
        return bundle.replace(old, new)
    if new_count != expected_count:
        raise SystemExit(
            f"Could not find pristine or patched {label} "
            f"(patched count {new_count}, expected {expected_count})"
        )
    return bundle


def add_inline_frontend_help(bundle):
    """Render practical zone and module help in the existing small hint style."""
    bundle = replace_exact(
        bundle,
        '"mapping-name":"Назва — довільне ім’я зони"',
        '"mapping-name":"Назва групи погодних датчиків"',
        1,
        "sensor-group name label",
    )
    old_num_signature = '_numRow(e,a,t,i,n=1,r=!1){'
    new_num_signature = '_numRow(e,a,t,i,n=1,r=!1,h=""){'  # Pinned bundle form.
    bundle = replace_exact(
        bundle,
        old_num_signature,
        new_num_signature,
        4,
        "numeric-row hint parameter",
    )
    bundle = replace_exact(
        bundle,
        '${e}${a?q` <span class="unit">(${a})</span>`:""}\n        </div>\n        <div class="num-field">',
        '${e}${a?q` <span class="unit">(${a})</span>`:""}${h?q`<div class="setting-hint">${h}</div>`:""}\n        </div>\n        <div class="num-field">',
        4,
        "numeric-row hint markup",
    )
    bundle = replace_exact(
        bundle,
        '_textRow(e,a,t,i){',
        '_textRow(e,a,t,i,h=""){',
        4,
        "text-row hint parameter",
    )
    bundle = replace_exact(
        bundle,
        '${e}${a?q` <span class="unit">(${a})</span>`:""}\n        </div>\n        <input\n          class="field"',
        '${e}${a?q` <span class="unit">(${a})</span>`:""}${h?q`<div class="setting-hint">${h}</div>`:""}\n        </div>\n        <input\n          class="field"',
        4,
        "text-row hint markup",
    )

    zone_hints = {
        "size": "Фактична площа саме цієї зони; зараз 250 м².",
        "throughput": (
            "Сумарна витрата всіх форсунок зони; зараз 40 л/хв, а не "
            "паспортна подача насоса."
        ),
        "drainage_rate": (
            "Відтік лише за додатного запасу води. 50,8 мм/год — початкове "
            "значення до уточнення типу ґрунту."
        ),
        "bucket": (
            "Накопичений баланс: мінус — дефіцит, плюс — запас після дощу "
            "або поливу."
        ),
        "maximum-bucket": (
            "Максимальний додатний запас, який утримує ґрунт; усе вище "
            "вважається стоком."
        ),
        "et-deficiency": (
            "Добова втрата води за PyETO без накопиченого балансу; поле лише "
            "для читання."
        ),
        "lead-time": (
            "Секунди, що додаються до ненульового часу для заповнення труб; "
            "для HomeMate залишити 0."
        ),
        "maximum-duration": (
            "Межа одного запуску зони; 3600 с = 60 хв."
        ),
        "multiplier": (
            "Калібрування часу: 1,0 без змін; 0,8 = −20 %, 1,2 = +20 %."
        ),
        "duration": (
            "Фінальний час після розрахунку, множника, обмеження й додаткових секунд."
        ),
    }
    zone_calls = {
        "size": 'this._numRow(Bo("panels.zones.labels.size",r),$a(this.config,la),e.size,(t=>this.handleEditZone(a,Object.assign(Object.assign({},e),{[la]:parseFloat(t)}))),.1)',
        "throughput": 'this._numRow(Bo("panels.zones.labels.throughput",r),$a(this.config,da),e.throughput,(t=>this.handleEditZone(a,Object.assign(Object.assign({},e),{[da]:parseFloat(t)}))),.1)',
        "drainage_rate": 'this._numRow(Bo("panels.zones.labels.drainage_rate",r),$a(this.config,ka),e.drainage_rate,(t=>this.handleEditZone(a,Object.assign(Object.assign({},e),{[ka]:parseFloat(t)}))),.1)',
        "bucket": 'this._numRow(Bo("panels.zones.labels.bucket",r),$a(this.config,ma),Number(e.bucket).toFixed(1),(t=>this.handleEditZone(a,Object.assign(Object.assign({},e),{[ma]:parseFloat(t)}))),.1)',
        "maximum-bucket": 'this._numRow(Bo("panels.zones.labels.maximum-bucket",r),$a(this.config,ma),Number(e.maximum_bucket).toFixed(1),(t=>this.handleEditZone(a,Object.assign(Object.assign({},e),{[ba]:parseFloat(t)}))),.1)',
        "et-deficiency": 'this._numRow(Bo("panels.zones.labels.et-deficiency",r),$a(this.config,ma),null!=e.et_deficiency?Number(e.et_deficiency).toFixed(2):"",(()=>{}),.01,!0)',
        "lead-time": 'this._numRow(Bo("panels.zones.labels.lead-time",r),"s",e.lead_time,(t=>this.handleEditZone(a,Object.assign(Object.assign({},e),{[va]:parseInt(t,10)}))),1)',
        "maximum-duration": 'this._numRow(Bo("panels.zones.labels.maximum-duration",r),"s",e.maximum_duration,(t=>this.handleEditZone(a,Object.assign(Object.assign({},e),{[fa]:parseInt(t,10)}))),1)',
        "multiplier": 'this._numRow(Bo("panels.zones.labels.multiplier",r),"",e.multiplier,(t=>this.handleEditZone(a,Object.assign(Object.assign({},e),{[ga]:parseFloat(t)}))),.1)',
        "duration": 'this._numRow(Bo("panels.zones.labels.duration",r),"s",e.duration,(t=>this.handleEditZone(a,Object.assign(Object.assign({},e),{[ca]:parseInt(t,10)}))),1,o)',
    }
    for key, old_call in zone_calls.items():
        hint = json.dumps(zone_hints[key], ensure_ascii=False)
        if key == "et-deficiency":
            new_call = old_call[:-1] + f",{hint})"
        elif key == "duration":
            new_call = old_call[:-1] + f",{hint})"
        else:
            new_call = old_call[:-1] + f",!1,{hint})"
        bundle = replace_exact(bundle, old_call, new_call, 1, f"{key} hint")

    old_module_header = (
        'const i=t.schema[a],n=i.name,r=function(e){if(e)return(e=e.replace("_"," ")).charAt(0).toUpperCase()+e.slice(1)}(n);let s="";'
    )
    new_module_header = (
        'const i=t.schema[a],n=i.name,l={coastal:["Прибережна місцевість","Увімкнути лише для ділянки біля великої водойми й лише коли немає даних сонячної радіації. Для Київщини залишити вимкненим."],forecast_days:["Днів прогнозу","Кількість майбутніх днів, що усереднюються з поточним розрахунком. Для HomeMate залишити 0: використовувати фактичні дані дня."],delta:["Зміна водного балансу за цикл (Delta)","Від’ємне значення створює дефіцит. У довідковому Static −4 мм відповідає приблизно 25 хв при 250 м² і 40 л/хв."]}[n],r=l?l[0]:function(e){if(e)return(e=e.replace("_"," ")).charAt(0).toUpperCase()+e.slice(1)}(n),d=l?l[1]:"";let s="";'
    )
    bundle = replace_exact(
        bundle, old_module_header, new_module_header, 1, "module field labels"
    )
    bundle = replace_exact(
        bundle,
        '<div class="setting-label">${o}</div>\n          <input\n            type="checkbox"',
        '<div class="setting-label">${o}${d?q`<div style="font-size:.8rem;font-weight:normal;color:var(--secondary-text-color);margin-top:2px;max-width:460px">${d}</div>`:""}</div>\n          <input\n            type="checkbox"',
        1,
        "module checkbox hint",
    )
    old_module_number = 'this._numRow(o,"",t.config[n],(a=>this.handleEditConfig(e,Object.assign(Object.assign({},t),{config:Object.assign(Object.assign({},t.config),{[n]:a})}))),1)'
    new_module_number = old_module_number[:-1] + ',!1,d)'
    bundle = replace_exact(
        bundle, old_module_number, new_module_number, 1, "module numeric hint"
    )
    old_module_text = 'this._textRow(o,"",s,(a=>this.handleEditConfig(e,Object.assign(Object.assign({},t),{config:Object.assign(Object.assign({},t.config),{[n]:a})}))))'
    new_module_text = old_module_text[:-1] + ',d)'
    bundle = replace_exact(
        bundle, old_module_text, new_module_text, 1, "module text hint"
    )
    return bundle


def update_frontend_bundle(
    component_root: Path, old_catalog: dict, new_catalog: dict
) -> None:
    """Patch Ukrainian display strings in the precompiled frontend bundle."""
    bundle_path = component_root / "frontend/dist/smart-irrigation.js"
    bundle = bundle_path.read_text(encoding="utf-8")

    # Full Ukrainian sentences are unique in the multilingual bundle. Derive
    # both forms so the operation works on a pristine or already-overlaid JSON
    # catalogue, and leave every other language untouched.
    for upstream_value, ukrainian_value in iter_string_pairs(old_catalog, new_catalog):
        if upstream_value == ukrainian_value:
            continue
        # This short value is shared by several catalogue entries. A previous
        # global replacement made the sensor-group name look like a zone name;
        # patch its anchored object property in add_inline_frontend_help instead.
        if (
            upstream_value == "Назва"
            and ukrainian_value == "Назва групи погодних датчиків"
        ):
            continue
        old_literal = json.dumps(upstream_value, ensure_ascii=False)
        new_literal = json.dumps(ukrainian_value, ensure_ascii=False)
        if old_literal in bundle:
            bundle = bundle.replace(old_literal, new_literal)
        elif new_literal not in bundle:
            raise SystemExit(
                "Could not find Ukrainian frontend string in compiled bundle: "
                + upstream_value
            )

    # This field label is hard-coded by the integration instead of coming
    # from the localization catalogue.
    bundle = bundle.replace(
        '"Daily ET deficiency"',
        '"Добовий дефіцит евапотранспірації"',
    )

    bundle = add_inline_frontend_help(bundle)

    # The standalone title is identical in every language, so anchor the
    # replacement between two Ukrainian-only strings instead of replacing all
    # occurrences in the multilingual bundle.
    old_title_pattern = re.compile(
        r'(title:"Зони"\}\},[A-Za-z_$][\w$]*=)"Smart Irrigation"'
        r'(,[A-Za-z_$][\w$]*=\{title:"Тригери запуску зрошення")'
    )
    new_title_pattern = re.compile(
        r'(title:"Зони"\}\},[A-Za-z_$][\w$]*=)"Розумний полив"'
        r'(,[A-Za-z_$][\w$]*=\{title:"Тригери запуску зрошення")'
    )
    bundle, replacements = old_title_pattern.subn(
        rf'\1"{UKRAINIAN_NAME}"\2', bundle, count=1
    )
    if replacements == 0 and new_title_pattern.search(bundle) is None:
        raise SystemExit("Could not find Ukrainian panel title in compiled bundle")

    bundle_path.write_text(bundle, encoding="utf-8")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: localize-smart-irrigation-uk.py COMPONENT_ROOT")

    component_root = Path(sys.argv[1]).resolve()
    required_files = (
        component_root / "frontend/localize/languages/uk.json",
        component_root / "translations/uk.json",
        component_root / "manifest.json",
        component_root / "const.py",
    )
    missing = [str(path) for path in required_files if not path.is_file()]
    if missing:
        raise SystemExit("Missing Smart Irrigation files: " + ", ".join(missing))

    uk_catalog = json.loads(required_files[0].read_text(encoding="utf-8"))
    localized_catalog = add_frontend_help(
        replace_ukrainian_terms(replace_brand(uk_catalog))
    )
    update_frontend_bundle(component_root, uk_catalog, localized_catalog)
    update_json(required_files[0])
    update_json(required_files[1])
    update_json(required_files[2], set_manifest_name=True)

    const_path = required_files[3]
    source = const_path.read_text(encoding="utf-8")
    old_line = "PANEL_TITLE = NAME"
    new_line = f'PANEL_TITLE = "{UKRAINIAN_NAME}"'
    if old_line in source:
        source = source.replace(old_line, new_line, 1)
    elif new_line not in source:
        raise SystemExit("Unexpected Smart Irrigation PANEL_TITLE definition")

    # Use a HomeMate-specific asset URL so browsers cannot retain the upstream
    # pre-overlay module under its old cache key after Home Assistant restarts.
    old_urls = (
        'PANEL_URL = f"/api/panel_custom/{DOMAIN}"',
        'PANEL_URL = f"/api/panel_custom/{DOMAIN}-homemate-uk-v1"',
        'PANEL_URL = f"/api/panel_custom/{DOMAIN}-homemate-uk-v2"',
        'PANEL_URL = f"/api/panel_custom/{DOMAIN}-homemate-uk-v3"',
        'PANEL_URL = f"/api/panel_custom/{DOMAIN}-homemate-uk-v4"',
        'PANEL_URL = f"/api/panel_custom/{DOMAIN}-homemate-uk-v5"',
    )
    new_url = 'PANEL_URL = f"/api/panel_custom/{DOMAIN}-homemate-uk-v6"'
    for old_url in old_urls:
        if old_url in source:
            source = source.replace(old_url, new_url, 1)
            break
    else:
        if new_url not in source:
            raise SystemExit("Unexpected Smart Irrigation PANEL_URL definition")
    if new_url not in source:
        raise SystemExit("Unexpected Smart Irrigation PANEL_URL definition")
    const_path.write_text(source, encoding="utf-8")

    print(f"Applied Ukrainian Smart Irrigation overlay to {component_root}")


if __name__ == "__main__":
    main()
