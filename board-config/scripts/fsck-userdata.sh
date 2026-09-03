#!/bin/bash
# Полагодити файлову систему /userdata, увімкнути журнал і повернути дім у роботу.
#
# Дефект: "Unattached inode", суперблок "not clean with errors" - наслідок
# раптових знеструмлень плати. Перша версія (22.08.2026) лише ремонтувала, і
# через тиждень помилки повернулись: розділ був ext4 БЕЗ ЖУРНАЛУ, з
# errors=continue і pass 0 у fstab, тобто кожне знеструмлення псувало його
# знову, а система далі писала у зламану структуру.
#
# Версія 03.09.2026 робить ремонт стійким до наступних знеструмлень (власник:
# «роби журнал, але передбач, що живлення може відключатись і далі»):
#   1. e2fsck -f -y            - виправити те, що є;
#   2. tune2fs -O has_journal  - журнал: після раптового вимкнення ядро просто
#                                відкочує незавершені операції, а не лишає дірки;
#   3. tune2fs -e remount-ro   - якщо помилка все ж трапиться, розділ стає
#                                read-only, а не псується далі (HA тоді впаде,
#                                і це правильно: сторож ФС і health це покажуть);
#   4. fstab: errors=remount-ro,nofail + pass 2 - при завантаженні systemd-fsck
#                                у режимі preen відкочує журнал і виправляє
#                                дрібне сам; якщо не зможе - плата все одно
#                                завантажиться (nofail), SSH буде, HA не стартує
#                                (Requires=userdata.mount) і чекає ручного fsck.
#   5. tune2fs -c 20           - повна перевірка кожні 20 монтувань, про запас.
#
# Розділ тримають HA, сторож монтів, wyoming-vosk і таймер кешу фото. Усі
# зупиняються; NFS-маунти під config-standalone відмонтовуються за списком
# findmnt, а не за жорстким переліком, бо їхні імена - зі systemd-екрануванням.
set -u
DEV=/dev/mmcblk0p8
STAMP=$(date +%Y%m%d-%H%M%S)
LOG=/home/forlinx/fsck-userdata-$STAMP.log
exec > >(tee -a "$LOG") 2>&1
echo "== $(date) fsck-userdata v2, лог $LOG"

echo "== чи не йде полив (перезапуск обірвав би цикл)"
TOKEN=$(cat /home/forlinx/.ha_token 2>/dev/null || true)
if [ -n "$TOKEN" ]; then
  for e in switch.mini_switch_k601_2_switch_1_2 binary_sensor.irrigation_unlimited_c1_m; do
    s=$(curl -s --max-time 5 -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8123/api/states/$e" | sed -n 's/.*"state": *"\([^"]*\)".*/\1/p' | head -1)
    echo "   $e = ${s:-?}"
    if [ "$s" = "on" ]; then echo "СТОП: полив активний, спробуйте пізніше."; exit 1; fi
  done
fi

echo "== зупиняю все, що тримає /userdata"
sudo systemctl stop home-assistant nas-mounts.timer tv-photo-cache.timer wyoming-vosk 2>&1 | grep -v "^$" || true

echo "== чекаю, поки процеси справді завершаться"
for i in $(seq 1 30); do
  sudo fuser -sm /userdata 2>/dev/null || break
  sleep 2
done

echo "== відмонтовую вкладені маунти (NFS/bind), потім /userdata"
for m in $(findmnt -rn -o TARGET -R /userdata | tail -n +2 | sort -r); do
  sudo umount "$m" 2>/dev/null && echo "   umount $m" || echo "   (не відмонтувався) $m"
done
sudo umount /userdata 2>/dev/null

if mountpoint -q /userdata; then
  echo "СТОП: /userdata досі змонтований, перевірку не запускаю - це зруйнувало б дані."
  sudo fuser -vm /userdata 2>&1 | head -8
  sudo systemctl start nas-mounts.service wyoming-vosk home-assistant nas-mounts.timer tv-photo-cache.timer
  exit 1
fi
echo "   /userdata відмонтовано"

echo
echo "== e2fsck (ремонт)"
sudo e2fsck -f -y "$DEV"
rc=$?
echo "   код виходу e2fsck: $rc  (0 = чисто, 1 = помилки виправлено; >=4 - треба дивитись лог)"

echo
echo "== журнал і поведінка при помилках"
if sudo tune2fs -l "$DEV" | grep -q has_journal; then
  echo "   журнал уже є"
else
  sudo tune2fs -O has_journal "$DEV" && echo "   журнал увімкнено"
fi
sudo tune2fs -e remount-ro -c 20 -i 0 "$DEV" >/dev/null && echo "   errors=remount-ro, повна перевірка кожні 20 монтувань"
echo "== контрольний e2fsck після зміни features"
sudo e2fsck -f -y "$DEV" >/dev/null; echo "   код виходу: $?"
sudo tune2fs -l "$DEV" | grep -E "features|Filesystem state|Errors behavior|FS Error count|Maximum mount count|Last checked"

echo
echo "== fstab: errors=remount-ro, nofail, pass 2"
sudo cp /etc/fstab "/home/forlinx/fstab.bak-$STAMP"
NEWLINE="$DEV\t/userdata\text4\tdefaults,errors=remount-ro,nofail,x-systemd.device-timeout=30\t0\t2"
if grep -qE "^$DEV[[:space:]]+/userdata" /etc/fstab; then
  sudo sed -i -E "s#^$DEV[[:space:]]+/userdata.*#$NEWLINE#" /etc/fstab
else
  printf '%b\n' "$NEWLINE" | sudo tee -a /etc/fstab >/dev/null
fi
grep -nE "^$DEV" /etc/fstab
sudo systemctl daemon-reload

echo
echo "== монтую і повертаю все на місце"
sudo mount /userdata && findmnt -n -o TARGET,OPTIONS /userdata
sudo systemctl start nas-mounts.service
sleep 5
sudo systemctl start nas-mounts.timer tv-photo-cache.timer wyoming-vosk home-assistant
for m in /userdata /mnt/homemate_media/video /userdata/hass/config-standalone/backups; do
  mountpoint -q "$m" && echo "   ok   $m" || echo "   DOWN $m"
done

echo
echo "== Home Assistant піднімається, чекаю"
c=000
for i in $(seq 1 24); do
  c=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8123/ 2>/dev/null)
  [ "$c" = "200" ] && break
  sleep 10
done
echo "   HA: $c ($(systemctl is-active home-assistant))"
[ "$c" = "200" ] && echo "== готово $(date)" || echo "== HA ще не відповідає: systemctl status home-assistant"
