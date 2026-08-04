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
