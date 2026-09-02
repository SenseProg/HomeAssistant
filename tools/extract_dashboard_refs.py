"""List what a Lovelace YAML view depends on: custom card types and entity ids.

Usage:
    python tools/extract_dashboard_refs.py board-config/devices_dashboard.yaml links
    python tools/extract_dashboard_refs.py board-config/overview_dashboard.yaml overview --states states.json

Without `--states` it prints the references; with a JSON dump of /api/states
(a list of state objects) it also flags entities that do not exist on the board.
Pair it with `python mcp-server/cli.py states '<regex>'` to fetch real states.

Why a file in tools/: the dashboard-design skill used to point at a scratchpad
copy that vanished with its session. This one is versioned.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from typing import Any, Iterable

import yaml

ENTITY_RE = re.compile(r"\b((?:sensor|binary_sensor|switch|input_\w+|automation|script|climate|fan|"
                       r"water_heater|select|number|person|camera|weather|media_player|device_tracker|"
                       r"counter|timer|light|cover|button|zone|sun|update)\.[a-z0-9_]+)\b")
ENTITY_KEYS = {"entity", "entity_id", "camera_image"}


def walk(node: Any, out_types: set[str], out_entities: set[str]) -> None:
    if isinstance(node, dict):
        card_type = node.get("type")
        if isinstance(card_type, str) and card_type.startswith("custom:"):
            out_types.add(card_type)
        for key, value in node.items():
            if key in ENTITY_KEYS:
                if isinstance(value, str):
                    out_entities.add(value)
                elif isinstance(value, list):
                    out_entities.update(v for v in value if isinstance(v, str))
            if key == "entities" and isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        out_entities.add(item)
                    elif isinstance(item, dict) and isinstance(item.get("entity"), str):
                        out_entities.add(item["entity"])
            walk(value, out_types, out_entities)
    elif isinstance(node, list):
        for item in node:
            walk(item, out_types, out_entities)
    elif isinstance(node, str) and ("{{" in node or "{%" in node):
        out_entities.update(ENTITY_RE.findall(node))


def find_view(views: Iterable[dict], path: str) -> dict | None:
    for view in views:
        if view.get("path") == path:
            return view
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file")
    parser.add_argument("path", nargs="?", help="view path; omit for the whole file")
    parser.add_argument("--states", help="JSON list from /api/states to check existence against")
    args = parser.parse_args()

    data = yaml.safe_load(io.open(args.file, encoding="utf-8"))
    views = data.get("views", []) if isinstance(data, dict) else []
    target: Any = data
    if args.path:
        target = find_view(views, args.path)
        if target is None:
            print(f"view '{args.path}' not found; available: {[v.get('path') for v in views]}")
            return 2
    types: set[str] = set()
    entities: set[str] = set()
    walk(target, types, entities)

    print("custom card types:")
    for t in sorted(types):
        print("  ", t)
    print(f"entities ({len(entities)}):")
    known: set[str] | None = None
    if args.states:
        known = {s["entity_id"] for s in json.load(io.open(args.states, encoding="utf-8"))}
    missing = 0
    for e in sorted(entities):
        flag = ""
        if known is not None and e not in known:
            flag = "   <-- MISSING on board"
            missing += 1
        print("  ", e + flag)
    if known is not None:
        print(f"missing: {missing}")
        return 1 if missing else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
