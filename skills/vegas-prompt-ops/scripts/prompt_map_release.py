#!/usr/bin/env python3
"""Manage vegas prompt-map snapshots, rollouts, and rollbacks."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


EXPECTED_EVENTS = (
    "new_resonance",
    "resonance_increase",
    "structure_shift",
    "position_management",
    "bb_exit_warning",
    "bb_rejection_entry",
)


@dataclass
class DbConfig:
    host: str
    port: int
    database: str


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def run_psql_csv(db_config: DbConfig, query: str) -> list[dict[str, str]]:
    command = [
        "psql",
        "-h",
        db_config.host,
        "-p",
        str(db_config.port),
        "-d",
        db_config.database,
        "-v",
        "ON_ERROR_STOP=1",
        "-P",
        "pager=off",
        "--csv",
        "-c",
        query,
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "psql failed"
        raise RuntimeError(message)
    csv_text = completed.stdout.strip()
    if not csv_text:
        return []
    return list(csv.DictReader(csv_text.splitlines()))


def run_psql(db_config: DbConfig, query: str) -> None:
    command = [
        "psql",
        "-h",
        db_config.host,
        "-p",
        str(db_config.port),
        "-d",
        db_config.database,
        "-v",
        "ON_ERROR_STOP=1",
        "-P",
        "pager=off",
        "-c",
        query,
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "psql failed"
        raise RuntimeError(message)


def to_int(raw_value: str | None) -> int:
    if raw_value is None or raw_value == "":
        return 0
    return int(raw_value)


def parse_json_field(raw_value: str | None) -> Any:
    if raw_value is None or raw_value == "":
        return None
    return json.loads(raw_value)


def fetch_current_config(db_config: DbConfig) -> dict[str, Any]:
    rows = run_psql_csv(
        db_config,
        """
        SELECT
            id,
            execution_mode,
            provider,
            model,
            vegas_prompt_configs,
            updated_at
        FROM automation_config
        ORDER BY id DESC
        LIMIT 1;
        """,
    )
    if not rows:
        raise RuntimeError("No automation_config rows found.")
    row = rows[0]
    return {
        "id": to_int(row["id"]),
        "execution_mode": row["execution_mode"],
        "provider": row["provider"],
        "model": row["model"],
        "vegas_prompt_configs": parse_json_field(row["vegas_prompt_configs"]) or {},
        "updated_at": row["updated_at"],
    }


def fetch_templates(db_config: DbConfig, template_ids: list[int]) -> list[dict[str, Any]]:
    if not template_ids:
        return []
    in_clause = ", ".join(str(template_id) for template_id in template_ids)
    rows = run_psql_csv(
        db_config,
        f"""
        SELECT
            id,
            name,
            intro,
            response_format,
            quant_fields,
            chart_defaults,
            is_default,
            updated_at
        FROM prompt_templates
        WHERE id IN ({in_clause})
        ORDER BY id;
        """,
    )
    templates: list[dict[str, Any]] = []
    for row in rows:
        templates.append(
            {
                "id": to_int(row["id"]),
                "name": row["name"],
                "intro": row["intro"],
                "response_format": row["response_format"],
                "quant_fields": parse_json_field(row["quant_fields"]),
                "chart_defaults": parse_json_field(row["chart_defaults"]),
                "is_default": row["is_default"] == "t",
                "updated_at": row["updated_at"],
            }
        )
    return templates


def validate_mapping(mapping: dict[str, Any]) -> dict[str, int]:
    if not isinstance(mapping, dict):
        raise ValueError("Mapping must be a JSON object.")
    normalized: dict[str, int] = {}
    for event_name in EXPECTED_EVENTS:
        if event_name not in mapping:
            raise ValueError(f"Missing required event key: {event_name}")
        value = mapping[event_name]
        if isinstance(value, bool):
            raise ValueError(f"Template id for {event_name} cannot be boolean.")
        try:
            normalized[event_name] = int(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Template id for {event_name} must be integer-like.") from error
    extra_keys = sorted(set(mapping.keys()) - set(EXPECTED_EVENTS))
    if extra_keys:
        raise ValueError(f"Unexpected event keys in mapping: {', '.join(extra_keys)}")
    return normalized


def resolve_snapshot_dir(output_dir: str | None) -> Path:
    if output_dir:
        return Path(output_dir)
    return Path(__file__).resolve().parents[1] / "state" / "releases"


def build_snapshot(db_config: DbConfig, output_dir: str | None) -> Path:
    current_config = fetch_current_config(db_config)
    mapping = validate_mapping(current_config["vegas_prompt_configs"])
    template_ids = sorted(set(mapping.values()))
    templates = fetch_templates(db_config, template_ids)
    snapshot = {
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "database": db_config.database,
        "automation_config": {
            "id": current_config["id"],
            "execution_mode": current_config["execution_mode"],
            "provider": current_config["provider"],
            "model": current_config["model"],
            "updated_at": current_config["updated_at"],
        },
        "vegas_prompt_configs": mapping,
        "prompt_templates": templates,
    }

    snapshot_dir = resolve_snapshot_dir(output_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    snapshot_path = snapshot_dir / f"prompt-map-snapshot-{timestamp}.json"
    snapshot_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return snapshot_path


def load_mapping_from_path(mapping_file: str) -> dict[str, int]:
    loaded = json.loads(Path(mapping_file).read_text(encoding="utf-8"))
    if isinstance(loaded, dict) and "vegas_prompt_configs" in loaded:
        loaded = loaded["vegas_prompt_configs"]
    return validate_mapping(loaded)


def apply_mapping(db_config: DbConfig, mapping: dict[str, int], dry_run: bool) -> dict[str, Any]:
    before = fetch_current_config(db_config)
    if dry_run:
        return {"before": before, "after": before, "applied": False}

    mapping_json = json.dumps(mapping, separators=(",", ":"))
    run_psql(
        db_config,
        f"""
        UPDATE automation_config
        SET vegas_prompt_configs = {sql_literal(mapping_json)}::json,
            updated_at = NOW()
        WHERE id = (SELECT id FROM automation_config ORDER BY id DESC LIMIT 1);
        """,
    )
    after = fetch_current_config(db_config)
    return {"before": before, "after": after, "applied": True}


def command_snapshot(db_config: DbConfig, output_dir: str | None) -> int:
    snapshot_path = build_snapshot(db_config, output_dir)
    print(f"[OK] Snapshot created: {snapshot_path}")
    return 0


def command_apply_map(
    db_config: DbConfig,
    map_file: str | None,
    map_json: str | None,
    dry_run: bool,
) -> int:
    if bool(map_file) == bool(map_json):
        raise ValueError("Provide exactly one of --map-file or --map-json.")

    mapping = load_mapping_from_path(map_file) if map_file else validate_mapping(json.loads(map_json or "{}"))
    outcome = apply_mapping(db_config, mapping, dry_run=dry_run)

    before_map = validate_mapping(outcome["before"]["vegas_prompt_configs"])
    after_map = validate_mapping(outcome["after"]["vegas_prompt_configs"])
    print("[INFO] Before map:", json.dumps(before_map, sort_keys=True))
    if outcome["applied"]:
        print("[OK] Applied new map.")
    else:
        print("[INFO] Dry run only. No DB update applied.")
    print("[INFO] After map:", json.dumps(after_map, sort_keys=True))
    return 0


def command_rollback(db_config: DbConfig, snapshot_path: str, dry_run: bool) -> int:
    mapping = load_mapping_from_path(snapshot_path)
    outcome = apply_mapping(db_config, mapping, dry_run=dry_run)
    if outcome["applied"]:
        print(f"[OK] Rolled back using snapshot: {snapshot_path}")
    else:
        print(f"[INFO] Dry run rollback using snapshot: {snapshot_path}")
    print("[INFO] Active map:", json.dumps(validate_mapping(outcome["after"]["vegas_prompt_configs"]), sort_keys=True))
    return 0


def command_status(db_config: DbConfig, snapshot_dir: str | None, limit: int) -> int:
    current_config = fetch_current_config(db_config)
    active_map = validate_mapping(current_config["vegas_prompt_configs"])
    print("[INFO] Active automation_config id:", current_config["id"])
    print("[INFO] Active updated_at:", current_config["updated_at"])
    print("[INFO] Active map:", json.dumps(active_map, sort_keys=True))

    base_dir = resolve_snapshot_dir(snapshot_dir)
    snapshot_files = sorted(base_dir.glob("prompt-map-snapshot-*.json"), reverse=True)[:limit]
    if not snapshot_files:
        print("[INFO] No local snapshots found in:", base_dir)
        return 0
    print("[INFO] Recent snapshots:")
    for snapshot_file in snapshot_files:
        print(f"- {snapshot_file}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage vegas prompt-map releases with rollback.")
    parser.add_argument("--host", default="localhost", help="Postgres host")
    parser.add_argument("--port", type=int, default=5432, help="Postgres port")
    parser.add_argument("--db", default="trading_backend_8101", help="Database name")

    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot_parser = subparsers.add_parser("snapshot", help="Create a prompt-map snapshot.")
    snapshot_parser.add_argument("--output-dir", help="Directory for snapshot files.")

    apply_parser = subparsers.add_parser("apply-map", help="Apply a candidate vegas prompt map.")
    apply_parser.add_argument("--map-file", help="Path to JSON file containing map object.")
    apply_parser.add_argument("--map-json", help="Inline JSON map object.")
    apply_parser.add_argument("--dry-run", action="store_true", help="Validate and print without applying.")

    rollback_parser = subparsers.add_parser("rollback", help="Rollback to map from a snapshot file.")
    rollback_parser.add_argument("--snapshot", required=True, help="Snapshot JSON file path.")
    rollback_parser.add_argument("--dry-run", action="store_true", help="Validate and print without applying.")

    status_parser = subparsers.add_parser("status", help="Show active mapping and local snapshots.")
    status_parser.add_argument("--snapshot-dir", help="Directory to search for snapshots.")
    status_parser.add_argument("--limit", type=int, default=5, help="Number of snapshots to list.")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    db_config = DbConfig(host=args.host, port=args.port, database=args.db)

    try:
        if args.command == "snapshot":
            return command_snapshot(db_config, args.output_dir)
        if args.command == "apply-map":
            return command_apply_map(db_config, args.map_file, args.map_json, dry_run=args.dry_run)
        if args.command == "rollback":
            return command_rollback(db_config, args.snapshot, dry_run=args.dry_run)
        if args.command == "status":
            return command_status(db_config, args.snapshot_dir, limit=args.limit)
    except Exception as error:  # pragma: no cover - operational script
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1

    print("[ERROR] Unknown command", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
