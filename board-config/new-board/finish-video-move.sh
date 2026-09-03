#!/bin/bash
# Завершити перенесення відеоархіву поза дерево конфігу Home Assistant (03.09.2026).
#
# Запускає власник:  sudo bash /home/forlinx/finish-video-move.sh
#
# Навіщо. HA Core архівує в нічний бекап усе дерево конфігу разом із маунтами
# (виключення лише backups/*.tar, логи, tts, .cache). Кліпи камери жили в
# config-standalone/media/video і були ще раз підмонтовані у www/motion-clips -
# бекап важив 5-9 ГБ і щоночі обривався на кліпі, що переписувався під час
# архівування; з 11.08 HA жодного бекапу не «завершив» і не чистив старі.
#
# Що робить (усе ідемпотентно, ~1 хв простою HA):
#   1. зупиняє Home Assistant - рестарт і так потрібен для allowlist_external_dirs
#      (новий шлях /mnt/homemate_media/video) і для recorder (21 доба);
#   2. знімає bind www/motion-clips і NFS-маунт config-standalone/media/video;
#   3. ставить mnt-homemate_media-video.mount, робить media/video symlink-ом
#      (так само, як media/foto), оновлює nas-mounts.service;
#   4. переносить копії статистики з backups/statistics у MB35x8/statistics,
#      щоб 136 МБ .gz не їхали в кожен архів;
#   5. запускає HA і чекає відповіді.
# Файли-джерела кладе поруч deploy: /home/forlinx/{mnt-homemate_media-video.mount,nas-mounts.service,wait-for-clock.conf}
set -u
CS=/userdata/hass/config-standalone
NEW=/mnt/homemate_media/video
UNIT_NEW=mnt-homemate_media-video.mount
UNIT_OLD_VIDEO='userdata-hass-config\x2dstandalone-media-video.mount'
UNIT_OLD_CLIPS='userdata-hass-config\x2dstandalone-www-motion\x2dclips.mount'
SRC=/home/forlinx

[ "$(id -u)" = 0 ] || { echo "запускати через sudo"; exit 1; }
for f in "$SRC/$UNIT_NEW" "$SRC/nas-mounts.service"; do
  [ -f "$f" ] || { echo "немає $f - спершу deploy з репозиторію"; exit 1; }
done

echo "== 1. зупиняю Home Assistant"
systemctl stop home-assistant
sleep 2

echo "== 2. старі маунти"
systemctl disable --now "$UNIT_OLD_CLIPS" 2>/dev/null || true
rm -f "/etc/systemd/system/$UNIT_OLD_CLIPS"
umount "$CS/www/motion-clips" 2>/dev/null || true
[ -d "$CS/www/motion-clips" ] && rmdir "$CS/www/motion-clips" 2>/dev/null
systemctl disable --now "$UNIT_OLD_VIDEO" 2>/dev/null || true
rm -f "/etc/systemd/system/$UNIT_OLD_VIDEO"
umount "$CS/media/video" 2>/dev/null || true
if mountpoint -q "$CS/media/video"; then
  echo "!! $CS/media/video досі змонтований - хто тримає:"; fuser -vm "$CS/media/video" 2>&1 | head
  umount -l "$CS/media/video" 2>/dev/null || true
fi

echo "== 3. новий маунт і symlink"
install -m 644 "$SRC/$UNIT_NEW" "/etc/systemd/system/$UNIT_NEW"
install -m 644 "$SRC/nas-mounts.service" /etc/systemd/system/nas-mounts.service
mkdir -p "$NEW"
systemctl daemon-reload
systemctl enable --now "$UNIT_NEW" 2>&1 | grep -v "^Created symlink" || true
if mountpoint -q "$NEW"; then
  echo "   ok   $NEW ($(ls "$NEW/ha-motion" 2>/dev/null | wc -l) записів у ha-motion)"
else
  echo "!! $NEW не змонтувався - HA запущу, але кліпи не писатимуться (nas-mounts.timer пробуватиме щохвилини)"
fi
if [ -d "$CS/media/video" ] && [ ! -L "$CS/media/video" ]; then
  if [ -z "$(ls -A "$CS/media/video")" ]; then
    rmdir "$CS/media/video"
  else
    echo "!! $CS/media/video не порожній - symlink не зроблю; подивіться, що там: ls -la $CS/media/video"
  fi
fi
[ -e "$CS/media/video" ] || ln -s "$NEW" "$CS/media/video"
ls -la "$CS/media/" | sed 's/^/   /'

echo "== 4. копії статистики -> MB35x8/statistics"
if mountpoint -q "$NEW" && [ -d "$CS/backups/statistics" ]; then
  mkdir -p "$NEW/MB35x8/statistics"
  mv -n "$CS/backups/statistics/"* "$NEW/MB35x8/statistics/" 2>/dev/null || true
  rmdir "$CS/backups/statistics" 2>/dev/null || true
  echo "   у новому місці: $(ls "$NEW/MB35x8/statistics" | wc -l) файлів"
fi

echo "== 4б. HA чекає правильного годинника (drop-in wait-for-clock.conf)"
# Плата без RTC стартує з 2024 року; HA стартував раніше за NTP і писав історію
# з датою 2024 (03.09.2026 13:58 після знеструмлення). Drop-in змушує HA
# зачекати до 5 хв на правильний рік.
if [ -f "$SRC/wait-for-clock.conf" ]; then
  install -d /etc/systemd/system/home-assistant.service.d
  install -m 644 "$SRC/wait-for-clock.conf" /etc/systemd/system/home-assistant.service.d/wait-for-clock.conf
  systemctl daemon-reload
  echo "   встановлено"
fi

echo "== 4в. бан localhost в ip_bans.yaml (наслідок старту з годинником 2024)"
# Токен виглядав «ще не чинним», п'ять невдач - і HA забанив 127.0.0.1; бан
# живе в пам'яті до рестарту, а файл перечитується при старті - тому чистимо
# файл саме перед стартом.
IPB=/userdata/hass/config/ip_bans.yaml
if [ -f "$IPB" ] && grep -q "^127.0.0.1:" "$IPB"; then
  sed -i '/^127\.0\.0\.1:/,/^[^ ]/{/^127\.0\.0\.1:/d;/^  /d}' "$IPB"
  echo "   запис про 127.0.0.1 прибрано"
fi

echo "== 5. запускаю Home Assistant"
systemctl start home-assistant
c=""
for i in $(seq 1 40); do
  c=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8123/ 2>/dev/null)
  [ "$c" = "200" ] && break
  sleep 10
done
echo "   HA: ${c:-нема відповіді}"

echo "== контроль"
for m in /userdata "$NEW" "$CS/backups" /mnt/homemate_media/foto; do
  mountpoint -q "$m" && echo "   ok   $m" || echo "   DOWN $m"
done
[ -L "$CS/media/video" ] && echo "   ok   $CS/media/video -> $(readlink "$CS/media/video")"
mountpoint -q "$CS/www/motion-clips" 2>/dev/null && echo "!! www/motion-clips досі змонтований" || echo "   ok   www/motion-clips знято"
echo "Далі: завтра о ~05:00 бекап має важити десятки МБ, не гігабайти (Налаштування → Система → Резервні копії)."
