#!/usr/bin/env python3
"""Build the motion-clip gallery at www/motion/gallery.html.

Rendered as a plain page rather than Lovelace cards on purpose: every card
approach produced correct HTML in the DOM that this frontend build then refused
to paint (see references/dashboards.md). The motion tab is a panel view holding
one iframe onto this file.

Clips are emitted as JSON and the players are created on demand by the filter,
not baked into the markup. At ~140 events a day over a 14-day retention that is
the difference between a couple of hundred <video> elements and two thousand.

The clips live on the NAS; www/motion-clips is a bind mount, so nothing here
costs board storage beyond this one HTML file.
"""
import html
import json
import os
import re

CLIPS = '/userdata/hass/config/www/motion-clips'
OUT = '/userdata/hass/config/www/motion/gallery.html'

# Two layouts are read deliberately: ha-motion/<day>/ruh_<hhmmss>.mp4 is current,
# flat ha-motion/ruh_<yyyymmdd>_<hhmmss>.mp4 is what the automation writes
# whenever a concurrent session reverts that change - which happened four times
# on 2026-08-08. Reading both means a revert never empties the gallery.
items = []
for name in sorted(os.listdir(CLIPS)):
    full = os.path.join(CLIPS, name)
    if os.path.isdir(full) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', name):
        for f in os.listdir(full):
            m = re.fullmatch(r'ruh_(\d{2})(\d{2})(\d{2})\.mp4', f)
            if m:
                h, mi, se = m.groups()
                items.append({'d': name, 'h': int(h), 't': '%s:%s:%s' % (h, mi, se),
                              'u': '/local/motion-clips/%s/%s' % (name, f)})
    else:
        m = re.fullmatch(r'ruh_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})\.mp4', name)
        if m:
            y, mo, d, h, mi, se = m.groups()
            items.append({'d': '%s-%s-%s' % (y, mo, d), 'h': int(h),
                          't': '%s:%s:%s' % (h, mi, se),
                          'u': '/local/motion-clips/%s' % name})

items.sort(key=lambda c: (c['d'], c['t']), reverse=True)
days = sorted({c['d'] for c in items}, reverse=True)

per_day = {}
for c in items:
    per_day[c['d']] = per_day.get(c['d'], 0) + 1

day_opts = ''.join(
    '<option value="%s">%s — %d</option>' % (html.escape(d), html.escape(d), per_day[d])
    for d in days)
hour_opts = ''.join('<option value="%d">%02d:00</option>' % (h, h) for h in range(24))

page = """<!doctype html><html lang="uk"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Cache-Control" content="no-store">
<title>Рух — відеоролики</title><style>
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;padding:16px;background:#111418;color:#e1e1e1;
     font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
.bar{position:sticky;top:0;z-index:5;background:#111418;padding:10px 0 12px;
     border-bottom:1px solid #2a2f36;margin-bottom:16px;
     display:flex;flex-wrap:wrap;gap:10px;align-items:center}
label{font-size:13px;color:#9fb0c0}
select{background:#1b2027;color:#e1e1e1;border:1px solid #2f3742;border-radius:7px;
       padding:6px 9px;font-size:14px}
button{background:#1b2027;color:#e1e1e1;border:1px solid #2f3742;border-radius:7px;
       padding:6px 12px;font-size:14px;cursor:pointer}
button:hover{background:#232a33}
#count{color:#8b949e;font-size:13px;margin-left:auto}
.grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(min(100%,520px),1fr))}
figure{margin:0;background:#181c22;border-radius:10px;overflow:hidden}
video{width:100%;display:block;background:#000}
figcaption{padding:7px 10px;font-size:13px;color:#9fb0c0}
.empty{color:#8b949e;padding:20px 0}
</style></head><body>
<div class="bar">
  <label>День <select id="day">__DAYS__</select></label>
  <label>з <select id="from">__HOURS__</select></label>
  <label>до <select id="to">__HOURS__</select></label>
  <button id="reset">Уся доба</button>
  <span id="count"></span>
</div>
<div class="grid" id="grid"></div>
<script>
const CLIPS = __DATA__;
const day = document.getElementById('day'),
      from = document.getElementById('from'),
      to = document.getElementById('to'),
      grid = document.getElementById('grid'),
      count = document.getElementById('count');
from.value = 0; to.value = 23;

// A black tile says nothing about what was recorded. Loading metadata gives a
// first frame, but doing that for every clip would hit the board with a few
// hundred requests at once - so it happens per tile, just before it scrolls
// into view.
const seenObserver = ('IntersectionObserver' in window)
  ? new IntersectionObserver(function(entries, obs){
      for(const e of entries){
        if(e.isIntersecting){ e.target.preload = 'metadata'; obs.unobserve(e.target); }
      }
    }, {rootMargin: '400px'})
  : null;

function render(){
  const d = day.value, a = +from.value, b = +to.value;
  const sel = CLIPS.filter(c => c.d === d && c.h >= a && c.h <= b);
  grid.innerHTML = '';
  count.textContent = sel.length + ' з ' + CLIPS.filter(c => c.d === d).length;
  if(!sel.length){
    grid.innerHTML = '<div class="empty">За цей проміжок роликів немає.</div>';
    return;
  }
  const frag = document.createDocumentFragment();
  for(const c of sel){
    const fig = document.createElement('figure');
    const v = document.createElement('video');
    v.controls = true; v.preload = 'none'; v.src = c.u;
    if(seenObserver){ seenObserver.observe(v); } else { v.preload = 'metadata'; }
    const cap = document.createElement('figcaption');
    cap.textContent = c.t;
    fig.append(v, cap); frag.append(fig);
  }
  grid.append(frag);
}
day.onchange = from.onchange = to.onchange = render;
document.getElementById('reset').onclick = () => { from.value = 0; to.value = 23; render(); };
render();

// The Lovelace view around this page sometimes aborts its own transition and
// never paints - the cards sit in the DOM at the right size and no pixels
// arrive. Same origin, so poking the parent into a relayout is enough to make
// it paint. Harmless when the view rendered normally.
function nudgeParent(){
  try { window.parent.dispatchEvent(new Event('resize')); } catch(e) {}
}
function nudgeFor(ms){
  const stop = performance.now() + ms;
  nudgeParent();
  const id = setInterval(function(){
    nudgeParent();
    if(performance.now() > stop) clearInterval(id);
  }, 1200);
}
nudgeFor(60000);
document.addEventListener('visibilitychange', function(){
  if(!document.hidden) nudgeFor(8000);
});
</script>
</body></html>"""

page = (page.replace('__DAYS__', day_opts)
            .replace('__HOURS__', hour_opts)
            .replace('__DATA__', json.dumps(items, ensure_ascii=False)))

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, 'w', encoding='utf-8') as fh:
    fh.write(page)
print('gallery: %d days, %d clips, %d bytes' % (len(days), len(items), os.path.getsize(OUT)))
