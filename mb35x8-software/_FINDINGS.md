# backupSW_MB35x8.zip — що всередині

**Досліджено:** 2026-08-01
**Джерело:** `Сінхронізація/.../DM2 проект/3 DevelopmentResults/DM2  технічна документація/Dev board/backupSW_MB35x8/`
**Локальна копія:** `E:\Home\HomeAssistant\MB35x8_software\backupSW_MB35x8.zip`
**Розмір:** 2697.78 МБ архів → 7.39 ГБ розпаковано, 11 записів

## Головне

Архів містить **тільки прошивки**. Ані SDK, ані сирців, ані ПЗ застосунків там немає.

| Файл | Розмір | Що це |
|---|---|---|
| `firmware/img/ubuntu20/fullimageuartpwm/update.img` | **5649.44 МБ** | повний образ **Ubuntu 20.04** зі збіркою під UART+PWM |
| `firmware/img/linux/pwm_uarts_updateimg/update.img` | **1914.73 МБ** | Linux-образ, та сама конфігурація UART+PWM |
| `firmware/img/ubuntu20/fullimageuartpwm/config.cfg` | 6739 Б | конфіг RKDevTool — карта розділів |
| `firmware/downloadFW.txt` | 120 Б | посилання на інструкцію прошивки |

## Це спростовує «Android 11» у HANDOFF

`docs/HANDOFF-MB35x8.md` і скіл `mb35x8-bench` стверджують, що на платі Android 11
з Forlinx SDK, і тому радять `adb` як основний шлях до шела.

**Фактично на платі Ubuntu 20.04.** Докази:

- обидва образи лежать у теках `ubuntu20/` та `linux/`;
- у `config.cfg` розділ Kernel зібраний з `...\ForlinxUbuntu20\boot.img`;
- розділи Boot і Recovery — з `...\MB35x8\final\testing\img\ubuntu20\boot.img`;
- жодного Android-образу в архіві немає.

Наслідок: **`adb` не є правильним шляхом**, а `ssh` під Ubuntu працює штатно.
Це знімає залежність від дефекту U9 для звичайної роботи.

## Карта розділів (з `config.cfg`)

| Розділ | Файл-джерело на машині збирача |
|---|---|
| Loader | `D:\work\developmentBord\SOM_RK3568\Devang\MiniLoaderAll.bin` |
| Parameter | `D:\work\neoPos\Rockchip\RKDevTool_Release_v2.86\Output\Android\Image\parameter.txt` |
| Uboot | `D:\work\developmentBord\SOM_RK3568\Devang\uboot.img` |
| trust | те саме, що Uboot |
| Misc | `...\RKDevTool_Release_v2.86\Output\Android\Image\misc.img` |
| Resource | `D:\work\developmentBord\andrew\tested\IMAGES\resource.img` |
| Kernel | `D:\work\developmentBord\miniboard DM3588\final\testing\ForlinxUbuntu20\boot.img` |
| Boot | `D:\work\developmentBord\DevelopmentBoard MB35x8\final\testing\img\ubuntu20\boot.img` |
| Recovery | те саме, що Boot |
| System | `D:\work\developmentBord\miniboard DM3588\final\testing\Charles\...\boot-orangepi.img` |
| Backup | те саме, що System |

Два зауваження, які варто перевірити на живій платі:

1. **Змішані джерела.** Kernel і System узяті з дерева `miniboard DM3588`, а Boot —
   з `MB35x8`. Parameter і Misc узагалі з Android-виводу RKDevTool. Тобто образ
   зібраний з кількох гілок, і це може бути причиною запису
   `Download image file = HW Bad or SW Bad` у журналі тестування.
2. **`boot-orangepi.img` як System** — образ походить з гілки OrangePi, не Forlinx.

## Прошивка

`downloadFW.txt` містить один рядок:

```
https://wiki.t-firefly.com/en/ROC-RK3568-PC-SE/03-upgrade_firmware_with_flash.html?highlight=miniloader#download-to-emmc
```

Тобто процедура — запис у eMMC через miniloader, за інструкцією Firefly для
ROC-RK3568-PC-SE. Інструмент — `RKDevTool_Release_v2.86` (він же в `config.cfg`).

## Що це означає для Home Assistant

Ubuntu 20.04 на RK3568 — придатна база. Home Assistant ставиться як
**Home Assistant Container** (Docker) або **Supervised**. Потрібно перевірити на
живій платі: версію ядра, чи є Docker, обсяг eMMC і чи піднімається мережа.

Наступний крок — не прошивка, а **завантаження наявної системи та збір фактів по SSH**.
Прошивати варто лише якщо поточна система непридатна: запис у eMMC на цій платі
має відомий статус `HW Bad or SW Bad`.
