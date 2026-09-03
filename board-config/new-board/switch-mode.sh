#!/bin/bash
# Перемикач режимів другої плати.
#
#   mirror      - жива копія: усі стани приходять з робочої плати, ця нічим не
#                 керує. Адреса .168. Без робочої плати копія порожня.
#   standalone  - повноцінний дім: справжні інтеграції, реальні пристрої,
#                 адреса .141. Робоча плата при цьому має бути вимкнена.
#
# Найнебезпечніше, що тут можливе, - дві Home Assistant, які одночасно тримають
# зʼєднання з тими самими клапанами LocalTuya, насосом і камерою. Тому перехід
# у standalone блокується, поки стара плата відповідає.
set -u

MODE="${1:-}"
BASE=/userdata/hass
OLD=192.168.50.141

usage() { echo "вжиток: $0 mirror|standalone|status"; exit 1; }

current() { readlink -f "$BASE/config" | sed "s|$BASE/config-||"; }

status() {
  echo "  режим:      $(current)"
  echo "  HA:         $(systemctl is-active home-assistant) / $(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8123/ 2>/dev/null)"
  echo "  адреси:     $(ip -4 -br addr show eth0 | awk '{print $3, $4}')"
  echo -n "  стара плата: "
  if curl -s -o /dev/null --max-time 4 "http://$OLD:8123/" 2>/dev/null; then echo "ПРАЦЮЄ (HA відповідає)"; else echo "не відповідає"; fi
}

apply_net() {   # $1 = адреса/маска, $2 = dhcp|static
  if [ "$2" = "dhcp" ]; then
    printf 'network:\n        version: 2\n        ethernets:\n                eth0:\n                        dhcp4: false\n                        addresses: [%s]\n                        gateway4: 192.168.50.1\n                        nameservers:\n                                addresses: [192.168.50.1, 1.1.1.1]\n                        optional: true\n                eth1:\n                        dhcp4: true\n                        optional: true\n' "$1" | sudo tee /etc/netplan/01-netcfg.yaml >/dev/null
  else
    printf 'network:\n        version: 2\n        ethernets:\n                eth0:\n                        dhcp4: false\n                        addresses: [%s]\n                        gateway4: 192.168.50.1\n                        nameservers:\n                                addresses: [192.168.50.1, 1.1.1.1]\n                        optional: true\n                eth1:\n                        dhcp4: true\n                        optional: true\n' "$1" | sudo tee /etc/netplan/01-netcfg.yaml >/dev/null
  fi
  sudo chmod 600 /etc/netplan/01-netcfg.yaml
  sudo netplan generate || { echo "netplan generate не пройшов - мережу не чіпаю"; return 1; }
  sudo sh -c 'nohup netplan apply >/tmp/np.log 2>&1 &'
  sleep 12
}

case "$MODE" in
  status) status; exit 0 ;;
  mirror|standalone) ;;
  *) usage ;;
esac

[ -d "$BASE/config-$MODE" ] || { echo "немає теки $BASE/config-$MODE"; exit 1; }

if [ "$MODE" = "standalone" ]; then
  echo "== перевіряю, що стара плата не працює"
  if curl -s -o /dev/null --max-time 5 "http://$OLD:8123/" 2>/dev/null; then
    echo "ВІДМОВА: Home Assistant на $OLD відповідає."
    echo "Дві копії одночасно почнуть керувати тими самими клапанами й насосом."
    echo "Спершу на старій платі:  sudo systemctl disable --now home-assistant"
    exit 1
  fi
  echo "   стара плата мовчить - можна"
fi

echo "== зупиняю HA"
sudo systemctl stop home-assistant

echo "== перемикаю конфіг на $MODE"
sudo rm -f "$BASE/config"
sudo ln -s "$BASE/config-$MODE" "$BASE/config"
ls -l "$BASE/config" | sed 's/^/   /'

if [ "$MODE" = "standalone" ]; then
  echo "== беру адресу 192.168.50.141 (її вимагає експорт NFS на NAS)"
  apply_net "192.168.50.141/24" static
else
  echo "== повертаю адресу 192.168.50.168"
  apply_net "192.168.50.168/24" static
fi
ip -4 -br addr show eth0 | sed 's/^/   /'

echo "== монти NAS"
sudo systemctl start nas-mounts.service 2>/dev/null
sleep 6
for m in /mnt/homemate_media/video /userdata/hass/config-standalone/backups; do
  mountpoint -q "$m" && echo "   ok   $m" || echo "   DOWN $m"
done

echo "== запускаю HA"
sudo systemctl start home-assistant
for i in $(seq 1 30); do
  c=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8123/ 2>/dev/null)
  [ "$c" = "200" ] && break
  sleep 10
done
echo "   HA: $c"
echo
status
