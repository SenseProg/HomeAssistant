#!/bin/bash
# Полагодити файлову систему /userdata і повернути дім у роботу.
#
# Дефект: "Unattached inode", суперблок "not clean with errors" - наслідок
# раптових знеструмлень плати. Перевірку при завантаженні знято (fstab pass 0),
# інакше розділ не монтувався і HA не стартував узагалі. Тож полагодити це може
# лише запуск вручну - автоматично більше нікому.
#
# Розділ тримають три речі, і всі три треба зупинити: сам HA, сторож монтів і
# wyoming-vosk (розпізнавання мови). Перша версія скрипта знала лише про перші
# дві й чесно відмовилась працювати - перевіряти змонтовану ФС не можна.
set -u

echo "== зупиняю все, що тримає /userdata"
sudo systemctl stop home-assistant nas-mounts.timer wyoming-vosk

echo "== чекаю, поки процеси справді завершаться"
for i in $(seq 1 30); do
  sudo fuser -sm /userdata 2>/dev/null || break
  sleep 2
done

echo "== відмонтовую"
for m in /userdata/hass/config/www/motion-clips \
         /userdata/hass/config/media/video \
         /userdata/hass/config/backups \
         /mnt/homemate_media/foto \
         /userdata; do
  sudo umount "$m" 2>/dev/null
done

if mountpoint -q /userdata; then
  echo "СТОП: /userdata досі змонтований, перевірку не запускаю - це зруйнувало б дані."
  sudo fuser -vm /userdata 2>&1 | head -8
  sudo systemctl start nas-mounts.service wyoming-vosk home-assistant
  exit 1
fi
echo "   /userdata відмонтовано"

echo
echo "== e2fsck (це і є ремонт)"
sudo e2fsck -f -y /dev/mmcblk0p8
echo "   код виходу: $?  (0 = чисто, 1 = помилки виправлено - обидва добре)"

echo
echo "== стан суперблока після ремонту"
sudo dumpe2fs -h /dev/mmcblk0p8 2>/dev/null | grep -i "filesystem state"

echo
echo "== повертаю все на місце"
sudo systemctl start nas-mounts.service
sleep 5
sudo systemctl start nas-mounts.timer wyoming-vosk home-assistant
for m in /userdata /userdata/hass/config/media/video \
         /userdata/hass/config/www/motion-clips /userdata/hass/config/backups; do
  mountpoint -q "$m" && echo "   ok   $m" || echo "   DOWN $m"
done

echo
echo "== Home Assistant піднімається, чекаю"
for i in $(seq 1 24); do
  c=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8123/ 2>/dev/null)
  [ "$c" = "200" ] && break
  sleep 10
done
echo "   HA: $c"
[ "$c" = "200" ] && echo "== готово" || echo "== HA ще не відповідає: systemctl status home-assistant"
