"""CLI fallback for the project MCP tools."""

from __future__ import annotations

import argparse
import json

from project_tools import (
    board_health,
    energy_flow_health,
    git_status,
    incidents,
    irrigation_health,
    network_inventory,
    project_summary,
    recent_logs,
    repo_board_sync,
    validate_config,
    well_pump_health,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Home Assistant project diagnostics")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("summary")
    sub.add_parser("health")
    sub.add_parser("irrigation-health")
    sub.add_parser("well-pump-health")
    sub.add_parser("energy-flow-health")
    sync_parser = sub.add_parser("sync")
    sync_parser.add_argument("files", nargs="*")
    sub.add_parser("validate")
    log_parser = sub.add_parser("logs")
    log_parser.add_argument("--lines", type=int, default=100)
    log_parser.add_argument("--pattern")
    sub.add_parser("git")
    inventory_parser = sub.add_parser("inventory")
    inventory_parser.add_argument("query", nargs="?")
    incidents_parser = sub.add_parser("incidents")
    incidents_parser.add_argument(
        "status", nargs="?", default="open", choices=["open", "resolved", "all"]
    )
    args = parser.parse_args()

    if args.command == "summary":
        result = project_summary()
    elif args.command == "health":
        result = board_health()
    elif args.command == "irrigation-health":
        result = irrigation_health()
    elif args.command == "well-pump-health":
        result = well_pump_health()
    elif args.command == "energy-flow-health":
        result = energy_flow_health()
    elif args.command == "sync":
        result = repo_board_sync(args.files or None)
    elif args.command == "validate":
        result = validate_config()
    elif args.command == "logs":
        result = recent_logs(args.lines, args.pattern)
    elif args.command == "git":
        result = git_status()
    elif args.command == "incidents":
        result = incidents(args.status)
    else:
        result = network_inventory(args.query)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
