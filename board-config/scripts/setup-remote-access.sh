#!/bin/bash
# Підключити плату до вашого tailnet і віддати через нього Home Assistant.
#
# Все, що можна було зробити наперед, уже зроблено: пакет установлено,
# tailscaled працює і запускається сам після перезавантаження. Лишився вхід -
# його мусить зробити людина, бо це автентифікація.
#
# Чому userspace-networking: у вендорському ядрі 4.19 цієї плати немає ні
# /dev/net/tun, ні модуля tun (там узагалі три модулі на всю систему). Тому
# звичайний режим неможливий, а в userspace вхідні з'єднання приймає сам
# tailscaled - тобто дістатись HA можна лише через `tailscale serve`, а не за
# адресою 100.x.y.z:8123. Це не обмеження налаштування, це наслідок ядра.
#
# Запускати: sudo bash /userdata/hass/config/scripts-setup-remote-access.sh
set -u

echo "== стан tailscaled"
systemctl is-active --quiet tailscaled || { echo "tailscaled не працює"; exit 1; }
grep -q 'userspace-networking' /etc/default/tailscaled \
  || echo "УВАГА: FLAGS без --tun=userspace-networking, на цьому ядрі не запрацює"

echo
echo "== вхід у tailnet"
echo "Нижче з'явиться посилання. Відкрийте його в браузері й увійдіть тим"
echo "акаунтом, під яким користуватиметесь Tailscale на телефоні."
echo
tailscale up --hostname=ok3568 --accept-dns=false --accept-routes=false || exit 1

echo
echo "== публікація Home Assistant у tailnet"
if tailscale serve --bg 8123; then
  :
else
  echo
  echo "serve не вдався. Найчастіша причина - у tailnet не увімкнені HTTPS-"
  echo "сертифікати. Це один перемикач: https://login.tailscale.com/admin/dns"
  echo "-> HTTPS Certificates -> Enable. Після цього повторіть:"
  echo "  sudo tailscale serve --bg 8123"
  exit 1
fi

echo
echo "== перевірка"
tailscale serve status
NAME=$(tailscale status --json 2>/dev/null | grep -o '"DNSName": *"[^"]*"' | head -1 | cut -d'"' -f4)
NAME=${NAME%.}
echo
echo "Адреса ззовні:  https://${NAME:-<ім\'я вузла>}/"
echo "Перевірка з плати:"
curl -s -o /dev/null -w "  локально HA -> %{http_code}\n" --max-time 8 http://127.0.0.1:8123/
echo
echo "Далі: поставте застосунок Tailscale на телефон і увійдіть тим самим"
echo "акаунтом. Порт назовні не відкривається, в публічний інтернет нічого не"
echo "виставлено - адреса працює лише всередині вашого tailnet."
