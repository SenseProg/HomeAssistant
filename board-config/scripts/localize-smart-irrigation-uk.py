#!/usr/bin/env python3
"""Apply the HomeMate Ukrainian display-name overlay to Smart Irrigation."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


UKRAINIAN_NAME = "Розумний полив"
UPSTREAM_NAME = "Smart Irrigation"


def replace_brand(value):
    if isinstance(value, str):
        return value.replace(UPSTREAM_NAME, UKRAINIAN_NAME)
    if isinstance(value, list):
        return [replace_brand(item) for item in value]
    if isinstance(value, dict):
        return {key: replace_brand(item) for key, item in value.items()}
    return value


def update_json(path: Path, *, set_manifest_name: bool = False) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data = replace_brand(data)
    if set_manifest_name:
        data["name"] = UKRAINIAN_NAME
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def iter_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from iter_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from iter_strings(item)


def update_frontend_bundle(component_root: Path, uk_catalog: dict) -> None:
    """Patch only Ukrainian brand strings in the precompiled frontend bundle."""
    bundle_path = component_root / "frontend/dist/smart-irrigation.js"
    bundle = bundle_path.read_text(encoding="utf-8")

    # Full Ukrainian sentences are unique in the multilingual bundle. Derive
    # both forms so the operation works on a pristine or already-overlaid JSON
    # catalogue, and leave every other language untouched.
    for value in iter_strings(uk_catalog):
        upstream_value = value.replace(UKRAINIAN_NAME, UPSTREAM_NAME)
        ukrainian_value = upstream_value.replace(UPSTREAM_NAME, UKRAINIAN_NAME)
        if upstream_value == UPSTREAM_NAME or upstream_value == ukrainian_value:
            continue
        old_literal = json.dumps(upstream_value, ensure_ascii=False)
        new_literal = json.dumps(ukrainian_value, ensure_ascii=False)
        if old_literal in bundle:
            bundle = bundle.replace(old_literal, new_literal)
        elif new_literal not in bundle:
            raise SystemExit(
                "Could not find Ukrainian frontend string in compiled bundle: "
                + upstream_value
            )

    # The standalone title is identical in every language, so anchor the
    # replacement between two Ukrainian-only strings instead of replacing all
    # occurrences in the multilingual bundle.
    old_title_pattern = re.compile(
        r'(title:"Зони"\}\},[A-Za-z_$][\w$]*=)"Smart Irrigation"'
        r'(,[A-Za-z_$][\w$]*=\{title:"Тригери запуску зрошення")'
    )
    new_title_pattern = re.compile(
        r'(title:"Зони"\}\},[A-Za-z_$][\w$]*=)"Розумний полив"'
        r'(,[A-Za-z_$][\w$]*=\{title:"Тригери запуску зрошення")'
    )
    bundle, replacements = old_title_pattern.subn(
        rf'\1"{UKRAINIAN_NAME}"\2', bundle, count=1
    )
    if replacements == 0 and new_title_pattern.search(bundle) is None:
        raise SystemExit("Could not find Ukrainian panel title in compiled bundle")

    bundle_path.write_text(bundle, encoding="utf-8")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: localize-smart-irrigation-uk.py COMPONENT_ROOT")

    component_root = Path(sys.argv[1]).resolve()
    required_files = (
        component_root / "frontend/localize/languages/uk.json",
        component_root / "translations/uk.json",
        component_root / "manifest.json",
        component_root / "const.py",
    )
    missing = [str(path) for path in required_files if not path.is_file()]
    if missing:
        raise SystemExit("Missing Smart Irrigation files: " + ", ".join(missing))

    uk_catalog = json.loads(required_files[0].read_text(encoding="utf-8"))
    update_frontend_bundle(component_root, uk_catalog)
    update_json(required_files[0])
    update_json(required_files[1])
    update_json(required_files[2], set_manifest_name=True)

    const_path = required_files[3]
    source = const_path.read_text(encoding="utf-8")
    old_line = "PANEL_TITLE = NAME"
    new_line = f'PANEL_TITLE = "{UKRAINIAN_NAME}"'
    if old_line in source:
        source = source.replace(old_line, new_line, 1)
    elif new_line not in source:
        raise SystemExit("Unexpected Smart Irrigation PANEL_TITLE definition")

    # Use a HomeMate-specific asset URL so browsers cannot retain the upstream
    # pre-overlay module under its old cache key after Home Assistant restarts.
    old_url = 'PANEL_URL = f"/api/panel_custom/{DOMAIN}"'
    new_url = 'PANEL_URL = f"/api/panel_custom/{DOMAIN}-homemate-uk-v1"'
    if old_url in source:
        source = source.replace(old_url, new_url, 1)
    elif new_url not in source:
        raise SystemExit("Unexpected Smart Irrigation PANEL_URL definition")
    const_path.write_text(source, encoding="utf-8")

    print(f"Applied Ukrainian Smart Irrigation overlay to {component_root}")


if __name__ == "__main__":
    main()
