#!/usr/bin/env python3
"""Готує один кадр фотозаставки телевізора і складає state.json для HA.

Чому цього не робив tv-photo-random.sh, який просто друкував шлях: телевізор
тепер показує не голе фото через Cast, а сторінку Home Assistant, і сторінці
потрібні три речі, яких у шляху немає, - URL, який відкриє браузер телевізора,
дата зйомки з EXIF і місце кадру в історії, без якого стрілки «назад» і
«вперед» нема на чому будувати.

Виклик:
    tv-photo-nav.py next ["Альбом"]   наступний кадр (з історії або новий)
    tv-photo-nav.py prev              на кадр назад
    tv-photo-nav.py refresh           перескласти state.json, кадр не міняти
"""
import json
import os
import random
import sys
import time
from datetime import datetime

from PIL import Image, ImageOps

OUT = "/userdata/hass/tv-photos"
WWW = "/userdata/hass/config/www/tv"
HIST = os.path.join(OUT, "history.json")
STATE = os.path.join(OUT, "state.json")
MEDIA = "/userdata/hass/config/media/"

# Скільки кадрів пам'ятати. 300 - це понад півтори години показу по 20 секунд;
# далі назад ніхто не гортає, а файл історії лишається дрібним.
MAXHIST = 300

# Телевізор Full HD, більше нема сенсу віддавати: файл з NAS буває 8 МБ, а
# зменшена копія важить близько 300 КБ і малюється миттєво.
TARGET = (1920, 1080)


def load_hist():
    try:
        with open(HIST, encoding="utf-8") as f:
            h = json.load(f)
        return list(h.get("items", [])), int(h.get("idx", -1))
    except Exception:
        return [], -1


def save_hist(items, idx):
    os.makedirs(OUT, exist_ok=True)
    tmp = HIST + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"items": items, "idx": idx}, f, ensure_ascii=False)
    os.replace(tmp, HIST)


def pick_random(album):
    """Випадковий шлях зі списку кешу. Списки будує tv-photo-cache.sh."""
    name = "__all.list" if album in ("Усі роки", "", "unknown", "unavailable") else album
    path = os.path.join(OUT, name if name.endswith(".list") else name + ".list")
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        path = os.path.join(OUT, "__all.list")
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return None
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    lines = [x for x in lines if x.strip()]
    return random.choice(lines) if lines else None


def exif_taken(img):
    """Дата зйомки. EXIF пишуть не всі камери, тож відповідь може бути None."""
    try:
        ex = img.getexif()
    except Exception:
        return None
    # 36867 DateTimeOriginal - момент натискання кнопки; 306 DateTime - момент
    # останнього запису файлу, тому він лише запасний.
    for tag in (36867, 306):
        raw = ex.get(tag)
        if not raw:
            # DateTimeOriginal живе в підкаталозі Exif, не в кореневому IFD.
            try:
                raw = ex.get_ifd(0x8769).get(tag)
            except Exception:
                raw = None
        if raw:
            try:
                return datetime.strptime(str(raw).strip(), "%Y:%m:%d %H:%M:%S")
            except ValueError:
                continue
    return None


def prepare(src):
    """Зменшена копія у www + дата зйомки. None, якщо файл не читається."""
    try:
        img = Image.open(src)
        # Портретні знімки лежать боком, поки не застосуєш EXIF-орієнтацію.
        img = ImageOps.exif_transpose(img)
        taken = exif_taken(Image.open(src))
        img = img.convert("RGB")
        img.thumbnail(TARGET, Image.LANCZOS)
    except Exception:
        return None

    # Кадр завжди рівно 16:9, фото вписане по центру на чорному. Інакше
    # портретний знімок розтягнув би картку вище екрана і на телевізорі
    # з'явилася б смуга прокрутки, а підписи внизу поїхали б з кожним кадром:
    # picture-elements розставляє їх у відсотках від висоти зображення.
    canvas = Image.new("RGB", TARGET, (0, 0, 0))
    canvas.paste(img, ((TARGET[0] - img.width) // 2, (TARGET[1] - img.height) // 2))
    img = canvas

    os.makedirs(WWW, exist_ok=True)
    # Ім'я міняється щокадру з двох причин: браузер телевізора інакше показував
    # би закешовану картинку, а випадковий хвіст не дає вгадати URL - тека
    # /local/ віддається без пароля, зокрема й назовні через Cloudflare.
    name = "frame-%d-%04d.jpg" % (int(time.time()), random.randint(0, 9999))
    dst = os.path.join(WWW, name)
    img.save(dst, "JPEG", quality=82, optimize=True)

    for old in os.listdir(WWW):
        if old.startswith("frame-") and old != name:
            try:
                os.remove(os.path.join(WWW, old))
            except OSError:
                pass
    return name, taken


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "next"
    album = sys.argv[2] if len(sys.argv) > 2 else "Усі роки"

    items, idx = load_hist()

    if action == "prev":
        if idx > 0:
            idx -= 1
    elif action == "next":
        if idx < len(items) - 1:
            # Стоїмо всередині історії - просто крок уперед, до вже баченого.
            idx += 1
        else:
            for _ in range(8):
                cand = pick_random(album)
                if cand and os.path.exists(cand):
                    items.append(cand)
                    idx = len(items) - 1
                    break
            if len(items) > MAXHIST:
                cut = len(items) - MAXHIST
                items = items[cut:]
                idx -= cut
    # refresh нічого не рухає

    if not items or idx < 0:
        state = {"ok": False, "url": "", "name": "", "taken": "", "idx": 0, "total": 0,
                 "album": album}
        with open(STATE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
        return

    src = items[idx]
    made = prepare(src)
    if made is None:
        # Кадр не відкрився (файл зник, або це не картинка). Стан не чіпаємо -
        # на екрані лишиться попереднє фото, а не порожнеча.
        save_hist(items, idx)
        return
    name, taken = made
    save_hist(items, idx)

    rel = src[len(MEDIA):] if src.startswith(MEDIA) else src
    state = {
        "ok": True,
        "url": "/local/tv/" + name,
        "name": rel,
        "taken": taken.strftime("%d.%m.%Y · %H:%M") if taken else "",
        "idx": idx + 1,
        "total": len(items),
        "album": album,
    }
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    os.replace(tmp, STATE)


if __name__ == "__main__":
    main()
