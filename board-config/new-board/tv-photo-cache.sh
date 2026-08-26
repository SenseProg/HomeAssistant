#!/bin/bash
# Builds the photo lists the TV screensaver picks from.
#
# The NAS album holds 377910 JPEGs and a full find takes 155 s, so scanning on
# demand is impossible - the slideshow needs a new path every 20 s. This runs
# once a day from tv-photo-cache.timer and leaves ready-made lists behind.
#
# Excluded by default: the NAS recycle bin, scanned documents, work folders,
# the unsorted pile and the sounds folder - none of them belong on a television.
# Edit EXCLUDE below to change that.
set -u
ROOT=/userdata/hass/config/media/foto
OUT=/userdata/hass/tv-photos
# Matched at ANY depth, not just the top level: QNAP drops @Recycle and
# .@__thumb inside every album, and the first version of this script only
# anchored at the root - 3260 recycle-bin photos and a stream of 8 kB
# thumbnails made it into the slideshow before that was caught.
EXCLUDE='@Recycle|\.@__thumb|@eaDir|Важливі документи|РОБОТА|Розібрати|Sounds'

mkdir -p "$OUT"
mountpoint -q /mnt/homemate_media/foto || { logger -t tv-photo-cache "NAS not mounted - keeping previous lists"; exit 0; }

tmp=$(mktemp)
find "$ROOT/" -type f \( -iname '*.jpg' -o -iname '*.jpeg' \) 2>/dev/null \
  | grep -vE "/($EXCLUDE)/" > "$tmp"

# One list per top-level album, plus the combined one. Written atomically so a
# reader never sees a half-built file.
awk -v root="$ROOT/" -v out="$OUT" '
  { rel=$0; sub(root,"",rel); split(rel,p,"/"); print > (out "/" p[1] ".list.tmp") }
' "$tmp" 2>/dev/null
mv "$tmp" "$OUT/__all.list.tmp"
for f in "$OUT"/*.list.tmp; do [ -e "$f" ] && mv "$f" "${f%.tmp}"; done

logger -t tv-photo-cache "rebuilt: $(wc -l < "$OUT/__all.list") photos in $(ls -1 "$OUT"/*.list 2>/dev/null | wc -l) lists"
