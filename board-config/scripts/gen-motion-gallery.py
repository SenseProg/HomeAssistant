#!/usr/bin/env python3
"""Build a static gallery of the motion clips at www/motion/gallery.html.

Every attempt to render this list as a Lovelace card failed the same way: the
markdown card's HTML lands in the DOM - days, links, everything - but this
frontend build never paints it, in a sections grid or in masonry. That is a
rendering bug no card arrangement gets around. A plain HTML page does not go
through Lovelace at all, so it simply works.

The clips stay on the NAS: www/motion-clips is a bind mount, so this page costs
a few kilobytes and no video is copied onto the board.

Two folder layouts are read, deliberately. ha-motion/<day>/ruh_<hhmmss>.mp4 is
the current one; flat ha-motion/ruh_<yyyymmdd>_<hhmmss>.mp4 is what the
automation produces whenever a concurrent session reverts that change - which
has happened four times today. Handling both means the gallery never goes blank
because of a revert.
"""
import html
import os
import re

CLIPS = '/userdata/hass/config/www/motion-clips'
OUT = '/userdata/hass/config/www/motion/gallery.html'
PER_DAY = 60  # a full day is ~140 clips and no browser enjoys that many players

by_day = {}
for name in os.listdir(CLIPS):
    full = os.path.join(CLIPS, name)
    if os.path.isdir(full) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', name):
        for f in os.listdir(full):
            m = re.fullmatch(r'ruh_(\d{6})\.mp4', f)
            if m:
                by_day.setdefault(name, []).append((m.group(1), '%s/%s' % (name, f)))
    else:
        m = re.fullmatch(r'ruh_(\d{4})(\d{2})(\d{2})_(\d{6})\.mp4', name)
        if m:
            y, mo, d, hms = m.groups()
            by_day.setdefault('%s-%s-%s' % (y, mo, d), []).append((hms, name))

days = sorted(by_day, reverse=True)

parts = ["""<!doctype html><html lang="uk"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Рух — відеоролики</title><style>
:root{color-scheme:dark}
body{margin:0;padding:16px;background:#111418;color:#e1e1e1;
     font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
h1{font-size:19px;margin:0 0 4px}
.sub{color:#8b949e;font-size:13px;margin-bottom:20px}
h2{font-size:16px;margin:26px 0 10px;padding-bottom:6px;border-bottom:1px solid #2a2f36}
.grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(260px,1fr))}
figure{margin:0;background:#181c22;border-radius:10px;overflow:hidden}
video{width:100%;display:block;background:#000}
figcaption{padding:7px 10px;font-size:13px;color:#9fb0c0}
</style></head><body>
<h1>Рух — відеоролики</h1>
<div class="sub">Файли лежать на NAS. Найновіші зверху.</div>
<figure style="margin:0 0 22px;max-width:520px">
<img src="/local/motion/latest.jpg" style="width:100%;border-radius:10px;display:block">
<figcaption style="color:#8b949e;font-size:13px;padding-top:6px">Останній зафіксований рух</figcaption>
</figure>"""]

total = 0
for day in days:
    files = [rel for _, rel in sorted(by_day[day], reverse=True)]
    if not files:
        continue
    shown = files[:PER_DAY]
    extra = '' if len(files) <= PER_DAY else \
        ' <span style="color:#6e7681">(показано %d із %d)</span>' % (len(shown), len(files))
    parts.append('<h2>%s — %d %s%s</h2><div class="grid">'
                 % (html.escape(day), len(files),
                    'ролик' if len(files) == 1 else 'роликів', extra))
    for rel in shown:
        base = os.path.basename(rel)
        m = re.search(r'(\d{2})(\d{2})(\d{2})\.mp4$', base)
        t = '%s:%s:%s' % m.groups() if m else base
        parts.append(
            '<figure><video controls preload="none" '
            'src="/local/motion-clips/%s"></video>'
            '<figcaption>%s</figcaption></figure>'
            % (html.escape(rel), html.escape(t)))
    parts.append('</div>')
    total += len(files)

if not days:
    parts.append('<p>Роликів ще немає.</p>')

parts.append('</body></html>')

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, 'w', encoding='utf-8') as fh:
    fh.write('\n'.join(parts))
print('gallery written: %d days, %d clips, %d bytes'
      % (len(days), total, os.path.getsize(OUT)))
