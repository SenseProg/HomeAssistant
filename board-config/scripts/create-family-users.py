#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Створити облікові записи сім'ї одним запуском, за матрицею з ROLES.md.

Пароль питається прихованим вводом і нікуди не потрапляє: ні в аргументи
команди (їх видно в `ps`), ні в історію оболонки, ні в лог. Скрипт його не
зберігає й не показує - лише передає хешувальнику самої Home Assistant.

Чому не просто `hass --script auth add`: та команда створює **тільки логін**.
Обліковий запис з'являється при першому вході, і - несподівано - у групі
**Administrators**: `async_get_or_create_user` підставляє `GROUP_ID_ADMIN`,
коли провайдер не назвав групу, а провайдер `homeassistant` повертає
`UserMeta(name=..., is_active=True)` без групи. Тобто Бабуся Сіма увійшла б
адміністратором і лишалась ним, доки хтось не помітить.

Тому скрипт створює логін, обліковий запис і зв'язок між ними одразу, з
потрібною групою і `local_only`, та ще й прив'язує особу. При вході HA знайде
готовий обліковий запис (пошук іде за нормалізованим іменем користувача) і
нічого створювати не буде.

Запускати з ЗУПИНЕНИМ Home Assistant.
"""
import asyncio
import getpass
import json
import os
import shutil
import sys
import uuid

CONFIG = '/userdata/hass/config'
AUTH = os.path.join(CONFIG, '.storage/auth')
PERSON = os.path.join(CONFIG, '.storage/person')

# логін, ім'я облікового запису, група, ім'я особи для прив'язки
ACCOUNTS = [
    ('kateryna', 'Катерина',    'system-users',     'Катерина'),
    ('olesia',   'Олеся',       'system-users',     'Олеся'),
    ('sima',     'Бабуся Сіма', 'system-read-only', 'Бабуся Сіма'),
]


def ask_password(login):
    while True:
        a = getpass.getpass('  пароль для %s: ' % login)
        if len(a) < 8:
            print('  замало - треба щонайменше 8 символів')
            continue
        b = getpass.getpass('  ще раз:            ')
        if a != b:
            print('  не збігається, спробуйте ще раз')
            continue
        return a


async def add_logins(pending):
    """Створити логіни силами самої HA - хешування її, не наше."""
    from homeassistant.auth.providers import homeassistant as hass_auth
    from homeassistant.core import HomeAssistant

    hass = HomeAssistant(CONFIG)
    provider = hass_auth.HassAuthProvider(
        hass, None, {'type': 'homeassistant'})  # type: ignore[arg-type]
    await provider.async_initialize()

    existing = {u['username'] for u in provider.data.users}
    created = []
    for login, name, group, person in pending:
        if login in existing:
            print('  %s - логін уже існує, пропускаю' % login)
            continue
        provider.data.add_auth(login, ask_password(login))
        created.append((login, name, group, person))
    if created:
        await provider.data.async_save()
    return created


def wire_up(created):
    """Створити обліковий запис, прив'язати логін і особу - у потрібній групі."""
    shutil.copy(AUTH, AUTH + '.bak-create')
    store = json.load(open(AUTH, encoding='utf-8'))
    data = store['data']
    by_username = {c['data'].get('username'): c for c in data['credentials']}

    people = json.load(open(PERSON, encoding='utf-8'))
    persons = {p['name']: p for p in people['data']['items']}

    for login, name, group, person_name in created:
        if login in by_username:
            print("  %s - зв'язок уже є, пропускаю" % login)
            continue
        user_id = uuid.uuid4().hex
        data['users'].append({
            'id': user_id,
            'group_ids': [group],
            'is_owner': False,
            'is_active': True,
            'name': name,
            'system_generated': False,
            'local_only': True,
        })
        data['credentials'].append({
            'id': uuid.uuid4().hex,
            'user_id': user_id,
            'auth_provider_type': 'homeassistant',
            'auth_provider_id': None,
            'data': {'username': login},
        })
        person = persons.get(person_name)
        if person is None:
            print('  %s - особи «%s» немає, обліковий запис лишиться без неї'
                  % (login, person_name))
        elif person.get('user_id'):
            print("  %s - особа «%s» вже прив'язана до іншого запису"
                  % (login, person_name))
        else:
            person['user_id'] = user_id
        print('  %s -> %s, група %s, local_only, особа %s'
              % (login, name, group, person_name))

    json.dump(store, open(AUTH, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
    json.dump(people, open(PERSON, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
    print('\nзаписано; копія: %s.bak-create' % AUTH)


def main():
    if os.system('systemctl is-active --quiet home-assistant') == 0:
        print("Home Assistant запущений - зупиніть його, інакше він перепише "
              "ці файли з пам'яті:")
        print("  sudo systemctl stop home-assistant")
        return 1

    print('Паролі не зберігаються й не виводяться. Мінімум 8 символів.\n')
    from homeassistant import runner
    asyncio.set_event_loop_policy(runner.HassEventLoopPolicy(False))
    created = asyncio.run(add_logins(ACCOUNTS))
    if not created:
        print('\nнових логінів не створено')
        return 0
    print()
    wire_up(created)
    print('\nтепер: sudo systemctl start home-assistant')
    return 0


if __name__ == '__main__':
    sys.exit(main())
