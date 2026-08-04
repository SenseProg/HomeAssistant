# Голосовий Claude HomeMate

Home Assistant використовує локальний Wyoming Vosk для розпізнавання довільної
української мови та Google Translate TTS для озвучення відповіді. Claude HomeMate
залишається conversation agent пайплайна.

## Компоненти плати

- код Wyoming Vosk: `/home/forlinx/wyoming-vosk`, pinned revision
  `335a4744d2d0d67624386338e8656f40a3294626`;
- окремий Python venv: `/home/forlinx/wyoming-vosk-venv-314` (створений
  інтерпретатором HA, але не змішується з venv Home Assistant);
- українська модель: `/home/forlinx/wyoming-vosk-data/vosk-model-small-uk-v3-small`;
- порожній каталог шаблонів `/home/forlinx/wyoming-vosk-sentences` потрібен для
  коректного попереднього завантаження моделі у поточній версії Wyoming Vosk;
- локальний endpoint: `tcp://127.0.0.1:10300`;
- systemd unit: `wyoming-vosk.service`.

Мікрофон працює у режимі push-to-talk через Assist. Постійне прослуховування та
wake word у цю схему не входять. Розпізнавання виконується на MB35x8; синтез
голосу Google Translate TTS потребує Інтернету.

У пайплайні `Claude HomeMate` мають бути встановлені:

- STT: `stt.vosk`, мова `uk`;
- conversation agent: `conversation.domashnii_asistent_claude`;
- TTS: `tts.google_translate_en_com`, мова `uk`.

## Відновлення

Запустити `board-config/scripts/install-wyoming-vosk.sh`, скопіювати unit у
`/etc/systemd/system/`, виконати `systemctl daemon-reload` та
`systemctl enable --now wyoming-vosk.service`. Потім через підтримуваний config
flow Home Assistant додати Wyoming на `127.0.0.1:10300` і вибрати його STT у
пайплайні `Claude HomeMate` для мови `uk`.

## Перевірка

`configure-voice-assist.py` повторно застосовує config flow і параметри пайплайна
без прямого редагування `.storage`. `test-voice-assist.py` генерує контрольну
українську фразу, пропускає її через STT → Claude → TTS і друкує транскрипцію,
відповідь та MIME-тип аудіо.

Під час вводу через вебінтерфейс слід вибрати `Claude HomeMate` у вікні Assist і
натиснути кнопку `Почати прослуховування`. На браузерах, що забороняють мікрофон
для звичайного HTTP у локальній мережі, використовується застосунок Home Assistant
або HTTPS-доступ.

### Chrome на керівному ПК

Chrome блокує мікрофон на `http://192.168.50.141:8123` і показує в Assist
неінформативну помилку `[object Object]`. На керівному Windows-ПК працює локальний
SSH-тунель:

```powershell
ssh -f -N -L 127.0.0.1:8123:127.0.0.1:8123 `
  -i C:\SPB_Data\.ssh\mb35x8_ed25519 `
  -o BatchMode=yes -o ExitOnForwardFailure=yes `
  -o ServerAliveInterval=30 -o ServerAliveCountMax=3 `
  forlinx@192.168.50.141
```

Після цього Home Assistant відкривається за `http://localhost:8123`. Браузери
вважають localhost довіреним контекстом для мікрофона навіть без TLS. Для цього
origin потрібно один раз увійти тим самим користувачем HA і дозволити мікрофон.
Автозапуск тунелю при вході у Windows встановлює
`board-config/client/windows/install-ha-voice-tunnel.ps1`; задача Планувальника
має назву `HomeMate HA Voice Tunnel` і працює з мінімальними правами користувача.

### Видима історія

Штатний Assist видаляє свою оперативну chat-сесію приблизно через п'ять хвилин і
не відновлює приватний JSONL-транскрипт інтеграції в новій вкладці. Панель
`Claude чат` (`/claude-home`) читає архів через authenticated admin-only WebSocket
команду `claude_code_conversation/history`, показує його між вкладками та дає
продовжувати текстовий діалог. Вона не має API очищення історії й не розкриває
файл неавторизованим клієнтам.

### Голосовий запис у панелі Claude

Панель `Claude чат` (`/claude-home`) має власний двоетапний голосовий ввід. Після
натискання `Записати голосом` вона показує таймер і живу доріжку рівня звуку.
Запис не надсилається автоматично: користувач спочатку натискає `Зупинити запис`,
а потім окремо `Надіслати запис`. Також доступні `Записати заново` та `Скасувати`.
Максимальна тривалість одного запису — 120 секунд.

Панель перетворює звук браузера на mono PCM 16 кГц і передає його штатному
`assist_pipeline/run` з пайплайном `Claude HomeMate`. Під час обробки вона явно
показує етапи розпізнавання, підготовки відповіді й синтезу, а після завершення —
розшифровку, текст відповіді та стандартний аудіопрогравач. Діалог використовує
той самий постійний `conversation_id`, тому результат потрапляє до збереженої
історії. Мікрофон, як і раніше, потребує HTTPS, застосунку HA або
`http://localhost:8123` через SSH-тунель.

Для попередньо записаної диктовки панель передає `no_vad: true`: пауза всередині
довгого повідомлення більше не завершує STT після перших слів. Після результату
кнопка `Розпізнати ще раз` повторно надсилає ті самі PCM-дані, не вимагаючи нового
запису.

`assist_pipeline.debug_recording_dir` зберігає кожен надісланий голосовий запит як
PCM WAV у приватному каталозі
`/userdata/hass/config/.private/claude-code-conversation/voice-recordings`. Панель
показує до 50 найновіших файлів лише адміністратору. Запис можна прослухати або
повторно відправити в STT навіть після перезавантаження сторінки; доступ до WAV
видається через короткочасно підписаний URL Home Assistant.
