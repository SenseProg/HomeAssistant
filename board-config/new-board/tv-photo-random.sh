#!/bin/bash
# Prints ONE random photo as a media-source URI. Reads the cache built by
# tv-photo-cache.sh, so it answers instantly even though the album has 377910
# files. Argument is the album chosen in input_select, or "Усі роки".
set -u
OUT=/userdata/hass/tv-photos
ALBUM="${1:-Усі роки}"
case "$ALBUM" in
  "Усі роки"|""|"unknown"|"unavailable") LIST="$OUT/__all.list" ;;
  *) LIST="$OUT/$ALBUM.list" ;;
esac
[ -s "$LIST" ] || LIST="$OUT/__all.list"
[ -s "$LIST" ] || exit 0
# A Home Assistant sensor state is capped at 255 characters and 223 photos on
# this NAS sit in folder trees deep enough to blow past it. A truncated URI
# would simply fail to play and leave the TV on the previous picture, so skip
# them: draw again, up to 12 times, then give up rather than return junk.
for _ in $(seq 1 12); do
  p=$(shuf -n1 "$LIST")
  [ -n "$p" ] || exit 0
  uri="media-source://media_source/local/${p#/userdata/hass/config/media/}"
  if [ "${#uri}" -le 250 ]; then
    printf '%s
' "$uri"
    exit 0
  fi
done
exit 0
