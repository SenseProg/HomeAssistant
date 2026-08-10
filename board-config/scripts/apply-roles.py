#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Застосувати матрицю ролей із ROLES.md до .storage/auth.

Створити обліковий запис цей скрипт не може і не намагається - для цього
потрібен пароль. Він робить те, що після створення запису лишається зробити
руками в UI і що легко зробити непослідовно: групу, «тільки локальний доступ»
і зняття прав адміністратора.

Запускати з ЗУПИНЕНИМ Home Assistant: він переписує .storage/auth при виході,
тож правка на ходу мовчки зникне.

    sudo systemctl stop home-assistant
    python3 apply-roles.py --dry-run      # подивитись, що зміниться
    python3 apply-roles.py
    sudo systemctl start home-assistant

Невідомі імена не чіпаються взагалі - скрипт нічого не вигадує про людину,
якої немає в матриці.
"""
import argparse
import json
import shutil
import sys

AUTH = '/userdata/hass/config/.storage/auth'

# Ім'я в HA -> (група, local_only). Групи: admin / user / read_only.
# Ті, кого тут немає, лишаються як є.
MATRIX = {
    'Дім Ковтуни': ('admin', True),
    'Катерина':    ('user', True),
    'Олеся':       ('user', True),
    'Бабуся Сіма': ('read_only', True),
    'Автоматика':  ('user', True),
}

GROUP_ID = {
    'admin': 'system-admin',
    'user': 'system-users',
    'read_only': 'system-read-only',
}
GROUP_NAME = {v: k for k, v in GROUP_ID.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    with open(AUTH, encoding='utf-8') as fh:
        store = json.load(fh)
    users = store['data']['users']

    changes = []
    for u in users:
        if u.get('system_generated'):
            continue                      # Cast / Content - не наші
        name = u.get('name')
        if name not in MATRIX:
            print('  пропущено (немає в матриці): %s' % name)
            continue

        want_group, want_local = MATRIX[name]
        gid = GROUP_ID[want_group]

        # Власника ніколи не розжаловуємо - інакше в системі не лишиться
        # нікого, хто може це відкотити.
        if u.get('is_owner') and want_group != 'admin':
            print('  ВІДМОВА: %s - власник, група лишається admin' % name)
            want_group, gid = 'admin', GROUP_ID['admin']

        now_group = GROUP_NAME.get((u.get('group_ids') or [None])[0], '?')
        if now_group != want_group:
            changes.append('%s: група %s -> %s' % (name, now_group, want_group))
            u['group_ids'] = [gid]
        if bool(u.get('local_only')) != want_local:
            changes.append('%s: local_only %s -> %s'
                           % (name, bool(u.get('local_only')), want_local))
            u['local_only'] = want_local

    if not changes:
        print('нічого змінювати - усе вже відповідає матриці')
        return 0

    print('\nзміни:')
    for c in changes:
        print('  ' + c)

    if args.dry_run:
        print('\n--dry-run: нічого не записано')
        return 0

    shutil.copy(AUTH, AUTH + '.bak-roles')
    with open(AUTH, 'w', encoding='utf-8') as fh:
        json.dump(store, fh, ensure_ascii=False, indent=2)
    print('\nзаписано, копія: %s.bak-roles' % AUTH)
    return 0


if __name__ == '__main__':
    sys.exit(main())
