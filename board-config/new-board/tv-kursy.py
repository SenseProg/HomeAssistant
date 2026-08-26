#!/usr/bin/env python3
"""Курси долара, євро і біткоїна в гривні - одним JSON для sensor.kursy_valiut.

Долар і євро беруться з готівкових курсів ПриватБанку, а не з офіційного курсу
НБУ: на екрані має стояти те число, яке людина побачить в обміннику, а вони
розходяться на відсоток-другий. Біткоїн НБУ не публікує взагалі, тому він
приходить з CoinGecko.

Останній вдалий результат лишається в кеші і віддається, якщо мережа мовчить -
інакше при кожному збої на телевізорі зʼявлялася б порожня смуга.
"""
import json
import os
import urllib.request

CACHE = "/userdata/hass/tv-photos/kursy.json"
PRIVAT = "https://api.privatbank.ua/p24api/pubinfo?json&exchange&coursid=5"
COINGECKO = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=uah"


def fetch(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": "home-assistant/tv-kursy"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def hrn(v):
    """44.75 -> «44,75». Кома, бо на екрані український текст."""
    return ("%.2f" % v).replace(".", ",")


def main():
    out = {}
    try:
        for row in fetch(PRIVAT):
            if row.get("ccy") == "USD":
                out["usd"] = round(float(row["sale"]), 2)
            elif row.get("ccy") == "EUR":
                out["eur"] = round(float(row["sale"]), 2)
    except Exception:
        pass

    try:
        out["btc"] = int(fetch(COINGECKO)["bitcoin"]["uah"])
    except Exception:
        pass

    if not {"usd", "eur", "btc"} <= set(out):
        try:
            with open(CACHE, encoding="utf-8") as f:
                old = json.load(f)
            for k in ("usd", "eur", "btc"):
                out.setdefault(k, old.get(k))
        except Exception:
            pass

    if out.get("usd") is None or out.get("eur") is None:
        print(json.dumps({"ok": False, "line": ""}, ensure_ascii=False))
        return

    out["usd_txt"] = hrn(out["usd"])
    out["eur_txt"] = hrn(out["eur"])
    # Біткоїн коштує мільйони гривень: повне число з'їдає пів смуги і читається
    # гірше, ніж «3,50 млн».
    out["btc_txt"] = (hrn(out["btc"] / 1e6) + " млн") if out.get("btc") else "—"
    out["line"] = "$ %s   € %s   ₿ %s" % (out["usd_txt"], out["eur_txt"], out["btc_txt"])
    out["ok"] = True

    try:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        with open(CACHE, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
    except OSError:
        pass

    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
