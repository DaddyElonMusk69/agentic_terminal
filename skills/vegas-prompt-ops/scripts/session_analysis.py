#!/usr/bin/env python3
"""Analyze automation session behavior for prompt-iteration decisions."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class DbConfig:
    host: str
    port: int
    database: str


EXPECTED_EVENTS = (
    "new_resonance",
    "resonance_increase",
    "structure_shift",
    "position_management",
    "bb_exit_warning",
    "bb_rejection_entry",
)


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


def to_int(raw_value: str | None) -> int:
    if raw_value is None or raw_value == "":
        return 0
    return int(raw_value)


def to_float(raw_value: str | None) -> float:
    if raw_value is None or raw_value == "":
        return 0.0
    return float(raw_value)


def parse_json_field(raw_value: str | None) -> Any:
    if raw_value is None or raw_value == "":
        return None
    return json.loads(raw_value)


def fetch_latest_session_id(db_config: DbConfig) -> str:
    rows = run_psql_csv(
        db_config,
        "SELECT id FROM automation_session ORDER BY started_at DESC LIMIT 1;",
    )
    if not rows:
        raise RuntimeError("No automation_session rows found.")
    return rows[0]["id"]


def fetch_session_row(db_config: DbConfig, session_id: str) -> dict[str, Any]:
    rows = run_psql_csv(
        db_config,
        f"""
        SELECT
            id,
            started_at,
            ended_at,
            execution_mode,
            provider,
            model,
            total_cycles,
            total_trades,
            total_pnl,
            prompt_count,
            config_snapshot
        FROM automation_session
        WHERE id = {sql_literal(session_id)}
        LIMIT 1;
        """,
    )
    if not rows:
        raise RuntimeError(f"Session not found: {session_id}")
    row = rows[0]
    parsed: dict[str, Any] = {
        "id": row["id"],
        "started_at": row["started_at"],
        "ended_at": row["ended_at"] or None,
        "execution_mode": row["execution_mode"],
        "provider": row["provider"],
        "model": row["model"],
        "total_cycles": to_int(row["total_cycles"]),
        "total_trades": to_int(row["total_trades"]),
        "total_pnl": to_float(row["total_pnl"]),
        "prompt_count": to_int(row["prompt_count"]),
        "config_snapshot": parse_json_field(row["config_snapshot"]) or {},
    }
    return parsed


def fetch_active_config(db_config: DbConfig) -> dict[str, Any]:
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
        raise RuntimeError("No automation_config row found.")
    row = rows[0]
    return {
        "id": to_int(row["id"]),
        "execution_mode": row["execution_mode"],
        "provider": row["provider"],
        "model": row["model"],
        "vegas_prompt_configs": parse_json_field(row["vegas_prompt_configs"]) or {},
        "updated_at": row["updated_at"],
    }


def fetch_trigger_counts(db_config: DbConfig, session_id: str) -> list[dict[str, Any]]:
    rows = run_psql_csv(
        db_config,
        f"""
        SELECT
            data->>'trigger_reason' AS trigger_reason,
            COUNT(*) AS prompts
        FROM automation_log
        WHERE session_id = {sql_literal(session_id)}
          AND log_type = 'prompt'
          AND data->>'event_type' = 'automation.prompt.requested'
        GROUP BY 1
        ORDER BY prompts DESC, trigger_reason;
        """,
    )
    return [{"trigger_reason": row["trigger_reason"], "prompts": to_int(row["prompts"])} for row in rows]


def fetch_pipeline_counts(db_config: DbConfig, session_id: str) -> list[dict[str, Any]]:
    rows = run_psql_csv(
        db_config,
        f"""
        SELECT
            data->>'event_type' AS event_type,
            COUNT(*) AS rows
        FROM automation_log
        WHERE session_id = {sql_literal(session_id)}
          AND log_type IN ('llm', 'parser', 'prompt')
        GROUP BY 1
        ORDER BY rows DESC, event_type;
        """,
    )
    return [{"event_type": row["event_type"], "rows": to_int(row["rows"])} for row in rows]


def fetch_trade_action_summary(db_config: DbConfig, session_id: str) -> list[dict[str, Any]]:
    rows = run_psql_csv(
        db_config,
        f"""
        SELECT
            action,
            COALESCE(direction, '') AS direction,
            status,
            COUNT(*) AS rows,
            ROUND(SUM(COALESCE(pnl, 0))::numeric, 8) AS pnl_sum
        FROM automation_trade
        WHERE session_id = {sql_literal(session_id)}
        GROUP BY action, direction, status
        ORDER BY rows DESC, action;
        """,
    )
    return [
        {
            "action": row["action"],
            "direction": row["direction"] or None,
            "status": row["status"],
            "rows": to_int(row["rows"]),
            "pnl_sum": to_float(row["pnl_sum"]),
        }
        for row in rows
    ]


def fetch_parser_actions_by_trigger(db_config: DbConfig, session_id: str) -> list[dict[str, Any]]:
    rows = run_psql_csv(
        db_config,
        f"""
        WITH req AS (
            SELECT
                data->>'request_id' AS request_id,
                data->>'trigger_reason' AS trigger_reason,
                (data->>'template_id')::int AS template_id
            FROM automation_log
            WHERE session_id = {sql_literal(session_id)}
              AND log_type = 'prompt'
              AND data->>'event_type' = 'automation.prompt.requested'
        ),
        par AS (
            SELECT
                data->>'request_id' AS request_id,
                data->'parse_result'->'ideas' AS ideas
            FROM automation_log
            WHERE session_id = {sql_literal(session_id)}
              AND log_type = 'parser'
              AND data->>'event_type' = 'automation.parser.completed'
        ),
        actions AS (
            SELECT
                p.request_id,
                idea->>'action' AS action
            FROM par p, json_array_elements(p.ideas) AS idea
        )
        SELECT
            r.trigger_reason,
            r.template_id,
            a.action,
            COUNT(*) AS rows
        FROM actions a
        JOIN req r ON r.request_id = a.request_id
        GROUP BY r.trigger_reason, r.template_id, a.action
        ORDER BY r.trigger_reason, rows DESC, a.action;
        """,
    )
    return [
        {
            "trigger_reason": row["trigger_reason"],
            "template_id": to_int(row["template_id"]),
            "action": row["action"],
            "rows": to_int(row["rows"]),
        }
        for row in rows
    ]


def fetch_new_resonance_conflicts(db_config: DbConfig, session_id: str) -> dict[str, int]:
    rows = run_psql_csv(
        db_config,
        f"""
        WITH req AS (
            SELECT
                data->>'request_id' AS request_id,
                data->'template_context'->>'direction' AS ctx_direction
            FROM automation_log
            WHERE session_id = {sql_literal(session_id)}
              AND log_type = 'prompt'
              AND data->>'event_type' = 'automation.prompt.requested'
              AND data->>'trigger_reason' = 'new_resonance'
        ),
        par AS (
            SELECT
                data->>'request_id' AS request_id,
                data->'parse_result'->'ideas' AS ideas
            FROM automation_log
            WHERE session_id = {sql_literal(session_id)}
              AND log_type = 'parser'
              AND data->>'event_type' = 'automation.parser.completed'
        ),
        actions AS (
            SELECT
                p.request_id,
                idea->>'action' AS action
            FROM par p, json_array_elements(p.ideas) AS idea
            WHERE idea->>'action' IN ('OPEN_SHORT', 'OPEN_LONG')
        )
        SELECT
            COUNT(*) AS total_entries,
            SUM(
                CASE
                    WHEN r.ctx_direction = 'LONG' AND a.action = 'OPEN_SHORT' THEN 1
                    WHEN r.ctx_direction = 'SHORT' AND a.action = 'OPEN_LONG' THEN 1
                    ELSE 0
                END
            ) AS conflicts
        FROM actions a
        JOIN req r ON r.request_id = a.request_id;
        """,
    )
    if not rows:
        return {"total_entries": 0, "conflicts": 0}
    row = rows[0]
    return {
        "total_entries": to_int(row["total_entries"]),
        "conflicts": to_int(row["conflicts"]),
    }


def fetch_position_management_behavior(db_config: DbConfig, session_id: str) -> dict[str, int]:
    rows = run_psql_csv(
        db_config,
        f"""
        WITH req AS (
            SELECT
                data->>'request_id' AS request_id
            FROM automation_log
            WHERE session_id = {sql_literal(session_id)}
              AND log_type = 'prompt'
              AND data->>'event_type' = 'automation.prompt.requested'
              AND data->>'trigger_reason' = 'position_management'
        ),
        par AS (
            SELECT
                data->>'request_id' AS request_id,
                data->'parse_result'->'ideas' AS ideas
            FROM automation_log
            WHERE session_id = {sql_literal(session_id)}
              AND log_type = 'parser'
              AND data->>'event_type' = 'automation.parser.completed'
        ),
        actions AS (
            SELECT
                p.request_id,
                idea->>'action' AS action
            FROM par p, json_array_elements(p.ideas) AS idea
        )
        SELECT
            COUNT(*) AS total_actions,
            SUM(CASE WHEN a.action = 'HOLD' THEN 1 ELSE 0 END) AS hold_actions,
            SUM(CASE WHEN a.action IN ('OPEN_LONG', 'OPEN_SHORT', 'ADD_TO_POSITION') THEN 1 ELSE 0 END) AS add_like_actions
        FROM actions a
        JOIN req r ON r.request_id = a.request_id;
        """,
    )
    if not rows:
        return {"total_actions": 0, "hold_actions": 0, "add_like_actions": 0}
    row = rows[0]
    return {
        "total_actions": to_int(row["total_actions"]),
        "hold_actions": to_int(row["hold_actions"]),
        "add_like_actions": to_int(row["add_like_actions"]),
    }


def fetch_worst_realized_trade(db_config: DbConfig, session_id: str) -> dict[str, Any] | None:
    rows = run_psql_csv(
        db_config,
        f"""
        SELECT
            created_at,
            cycle_number,
            symbol,
            action,
            status,
            fill_price,
            pnl,
            llm_reasoning
        FROM automation_trade
        WHERE session_id = {sql_literal(session_id)}
          AND pnl IS NOT NULL
          AND pnl <> 0
        ORDER BY pnl ASC
        LIMIT 1;
        """,
    )
    if not rows:
        return None
    row = rows[0]
    return {
        "created_at": row["created_at"],
        "cycle_number": to_int(row["cycle_number"]),
        "symbol": row["symbol"],
        "action": row["action"],
        "status": row["status"],
        "fill_price": to_float(row["fill_price"]),
        "pnl": to_float(row["pnl"]),
        "llm_reasoning": row["llm_reasoning"] or "",
    }


def fetch_sessions_after(db_config: DbConfig, iso_time: str) -> int:
    rows = run_psql_csv(
        db_config,
        f"""
        SELECT COUNT(*) AS sessions_after_update
        FROM automation_session
        WHERE started_at >= {sql_literal(iso_time)};
        """,
    )
    if not rows:
        return 0
    return to_int(rows[0]["sessions_after_update"])


def build_mapping_changes(
    session_map: dict[str, int],
    active_map: dict[str, int],
) -> list[dict[str, Any]]:
    event_order = list(EXPECTED_EVENTS)
    all_events = event_order + [event_name for event_name in sorted(set(active_map) | set(session_map)) if event_name not in event_order]
    rows: list[dict[str, Any]] = []
    for event_name in all_events:
        session_template = session_map.get(event_name)
        active_template = active_map.get(event_name)
        rows.append(
            {
                "event": event_name,
                "session_template_id": session_template,
                "active_template_id": active_template,
                "changed": session_template != active_template,
            }
        )
    return rows


def build_findings(report: dict[str, Any]) -> list[str]:
    findings: list[str] = []

    mismatch = report["metrics"]["new_resonance_direction_mismatch"]
    mismatch_total = mismatch["total_entries"]
    mismatch_conflicts = mismatch["conflicts"]
    mismatch_rate = (mismatch_conflicts / mismatch_total) if mismatch_total else 0.0
    if mismatch_total and mismatch_rate >= 0.30:
        findings.append(
            f"High new_resonance direction mismatch: {mismatch_conflicts}/{mismatch_total} ({mismatch_rate:.1%})."
        )

    management = report["metrics"]["position_management_behavior"]
    hold_total = management["total_actions"]
    hold_actions = management["hold_actions"]
    add_like_actions = management["add_like_actions"]
    hold_rate = (hold_actions / hold_total) if hold_total else 0.0
    if hold_total and hold_rate >= 0.70 and add_like_actions == 0:
        findings.append(
            f"Position-management HOLD dominance: {hold_actions}/{hold_total} ({hold_rate:.1%}) with zero add-like actions."
        )

    changed_count = sum(1 for row in report["mapping_changes"] if row["changed"])
    if changed_count > 0:
        findings.append(f"Session used a different prompt map than active config on {changed_count} vegas events.")
    else:
        findings.append("Session used the same prompt map as currently active config.")

    sessions_after_update = report["active_config"]["sessions_after_updated_at"]
    if sessions_after_update == 0:
        findings.append("No sessions started after the latest prompt-map update; impact not measurable yet.")

    worst_trade = report.get("worst_realized_trade")
    if worst_trade:
        findings.append(
            f"Worst realized trade: {worst_trade['symbol']} {worst_trade['action']} pnl={worst_trade['pnl']:.8f} at cycle {worst_trade['cycle_number']}."
        )

    return findings


def mapping_row_for_event(report: dict[str, Any], event_name: str) -> dict[str, Any]:
    for row in report["mapping_changes"]:
        if row["event"] == event_name:
            return row
    return {"event": event_name, "session_template_id": None, "active_template_id": None, "changed": False}


def build_prompt_improvement_suggestions(report: dict[str, Any]) -> dict[str, Any]:
    session = report["session"]
    mismatch = report["metrics"]["new_resonance_direction_mismatch"]
    management = report["metrics"]["position_management_behavior"]
    sessions_after_update = report["active_config"]["sessions_after_updated_at"]

    mismatch_total = mismatch["total_entries"]
    mismatch_conflicts = mismatch["conflicts"]
    mismatch_rate = (mismatch_conflicts / mismatch_total) if mismatch_total else 0.0

    hold_total = management["total_actions"]
    hold_actions = management["hold_actions"]
    hold_rate = (hold_actions / hold_total) if hold_total else 0.0
    add_like_actions = management["add_like_actions"]

    looks_healthy = (
        session["total_pnl"] >= 0
        and (mismatch_total == 0 or mismatch_rate < 0.25)
        and (hold_total == 0 or hold_rate < 0.70 or add_like_actions > 0)
    )

    suggestions: list[dict[str, str]] = []

    if mismatch_total and mismatch_rate >= 0.30:
        mapping = mapping_row_for_event(report, "new_resonance")
        if mapping["changed"]:
            suggestion = (
                "Issue observed on prior template; keep current active template unchanged and validate with "
                "at least 3 new sessions before further edits."
            )
        else:
            suggestion = (
                "Add explicit dominant-timeframe interaction-state gating (approach/rejection/acceptance/compression) "
                "before directional decision, and reduce aggression on approach-only setups."
            )
        suggestions.append(
            {
                "event": "new_resonance",
                "priority": "high",
                "rationale": f"Direction conflict rate is {mismatch_conflicts}/{mismatch_total} ({mismatch_rate:.1%}).",
                "suggestion": suggestion,
            }
        )

    if hold_total and hold_rate >= 0.70 and add_like_actions == 0:
        mapping = mapping_row_for_event(report, "position_management")
        if mapping["changed"]:
            suggestion = (
                "Issue observed on prior template; keep current active template unchanged and validate add-frequency "
                "over the next evaluation window."
            )
        else:
            suggestion = (
                "Add phase-transition logic and explicitly prefer ADD_TO_POSITION over passive HOLD when "
                "Probe→Acceptance or Acceptance→Expansion transition is confirmed."
            )
        suggestions.append(
            {
                "event": "position_management",
                "priority": "high",
                "rationale": f"HOLD dominance is {hold_actions}/{hold_total} ({hold_rate:.1%}) with zero add-like actions.",
                "suggestion": suggestion,
            }
        )

    if session["total_pnl"] < 0 and not suggestions:
        suggestions.append(
            {
                "event": "global",
                "priority": "medium",
                "rationale": f"Session pnl is negative ({session['total_pnl']:.8f}) without a single dominant prompt failure metric.",
                "suggestion": "Keep prompt text stable for one more run and prioritize market-feature diagnostics (event timing, data freshness, execution quality).",
            }
        )

    if sessions_after_update == 0 and suggestions:
        suggestions.append(
            {
                "event": "evaluation",
                "priority": "medium",
                "rationale": "No completed session exists after the latest active prompt-map update.",
                "suggestion": "Avoid additional prompt edits until post-update data exists; run at least 3 sessions, then re-evaluate.",
            }
        )

    if looks_healthy and not suggestions:
        return {
            "no_update_needed": True,
            "summary": "Session looks healthy; no prompt update needed.",
            "items": [],
        }

    if not suggestions and session["total_pnl"] >= 0:
        return {
            "no_update_needed": True,
            "summary": "No high-priority prompt issues detected; no update needed.",
            "items": [],
        }

    return {
        "no_update_needed": False,
        "summary": "Prompt updates or watchlist actions are recommended.",
        "items": suggestions,
    }


def render_markdown(report: dict[str, Any]) -> str:
    session = report["session"]
    active_config = report["active_config"]
    mismatch = report["metrics"]["new_resonance_direction_mismatch"]
    management = report["metrics"]["position_management_behavior"]

    lines: list[str] = []
    lines.append(f"# Session Analysis: {session['id']}")
    lines.append("")
    lines.append("## Session")
    lines.append(f"- started_at: {session['started_at']}")
    lines.append(f"- ended_at: {session['ended_at'] or 'running'}")
    lines.append(f"- mode/provider/model: {session['execution_mode']} / {session['provider']} / {session['model']}")
    lines.append(f"- total_cycles: {session['total_cycles']}")
    lines.append(f"- total_trades: {session['total_trades']}")
    lines.append(f"- prompt_count: {session['prompt_count']}")
    lines.append(f"- total_pnl: {session['total_pnl']:.8f}")
    lines.append("")
    lines.append("## Findings")
    for finding in report["findings"]:
        lines.append(f"- {finding}")
    lines.append("")
    lines.append("## Key Metrics")
    lines.append(
        f"- new_resonance direction mismatch: {mismatch['conflicts']}/{mismatch['total_entries']} "
        f"({(mismatch['conflicts'] / mismatch['total_entries']):.1%})"
        if mismatch["total_entries"]
        else "- new_resonance direction mismatch: no OPEN_LONG/OPEN_SHORT entries"
    )
    lines.append(
        f"- position_management HOLD/add-like: {management['hold_actions']} HOLD, {management['add_like_actions']} add-like,"
        f" out of {management['total_actions']} parser actions"
    )
    lines.append(f"- active prompt-map updated_at: {active_config['updated_at']}")
    lines.append(f"- sessions after active update: {active_config['sessions_after_updated_at']}")
    lines.append("")
    lines.append("## Prompt Improvement Suggestions")
    prompt_suggestions = report["prompt_improvement_suggestions"]
    if prompt_suggestions["no_update_needed"]:
        lines.append(f"- {prompt_suggestions['summary']}")
    else:
        lines.append(f"- {prompt_suggestions['summary']}")
        for item in prompt_suggestions["items"]:
            lines.append(
                f"- [{item['event']}] ({item['priority']}) rationale: {item['rationale']} suggestion: {item['suggestion']}"
            )
    lines.append("")
    lines.append("## Mapping Changes (Session vs Active)")
    for row in report["mapping_changes"]:
        marker = "changed" if row["changed"] else "same"
        lines.append(
            f"- {row['event']}: {row['session_template_id']} -> {row['active_template_id']} ({marker})"
        )
    lines.append("")
    lines.append("## Trigger Counts")
    for row in report["trigger_counts"]:
        lines.append(f"- {row['trigger_reason']}: {row['prompts']}")
    lines.append("")
    lines.append("## Parser Actions by Trigger")
    for row in report["parser_actions_by_trigger"]:
        lines.append(
            f"- {row['trigger_reason']} (template {row['template_id']}): {row['action']} x{row['rows']}"
        )
    lines.append("")
    lines.append("## Trade Action Summary")
    for row in report["trade_action_summary"]:
        direction = row["direction"] or "-"
        lines.append(
            f"- {row['action']} [{direction}] {row['status']}: {row['rows']} (pnl_sum={row['pnl_sum']:.8f})"
        )
    if report.get("worst_realized_trade"):
        worst_trade = report["worst_realized_trade"]
        lines.append("")
        lines.append("## Worst Realized Trade")
        lines.append(
            f"- {worst_trade['created_at']} cycle={worst_trade['cycle_number']} "
            f"{worst_trade['symbol']} {worst_trade['action']} pnl={worst_trade['pnl']:.8f}"
        )
        lines.append(f"- reasoning: {worst_trade['llm_reasoning']}")
    return "\n".join(lines).strip() + "\n"


def build_report(db_config: DbConfig, session_id: str) -> dict[str, Any]:
    session = fetch_session_row(db_config, session_id)
    active_config = fetch_active_config(db_config)
    active_map = active_config["vegas_prompt_configs"]
    session_map = session["config_snapshot"].get("vegas_prompt_configs", {})
    active_config["sessions_after_updated_at"] = fetch_sessions_after(db_config, active_config["updated_at"])

    report: dict[str, Any] = {
        "database": db_config.database,
        "session": session,
        "active_config": active_config,
        "mapping_changes": build_mapping_changes(session_map, active_map),
        "trigger_counts": fetch_trigger_counts(db_config, session_id),
        "pipeline_counts": fetch_pipeline_counts(db_config, session_id),
        "trade_action_summary": fetch_trade_action_summary(db_config, session_id),
        "parser_actions_by_trigger": fetch_parser_actions_by_trigger(db_config, session_id),
        "metrics": {
            "new_resonance_direction_mismatch": fetch_new_resonance_conflicts(db_config, session_id),
            "position_management_behavior": fetch_position_management_behavior(db_config, session_id),
        },
        "worst_realized_trade": fetch_worst_realized_trade(db_config, session_id),
    }
    report["findings"] = build_findings(report)
    report["prompt_improvement_suggestions"] = build_prompt_improvement_suggestions(report)
    return report


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze automation session behavior for prompt tuning.")
    parser.add_argument("--host", default="localhost", help="Postgres host")
    parser.add_argument("--port", type=int, default=5432, help="Postgres port")
    parser.add_argument("--db", default="trading_backend_8101", help="Database name")
    parser.add_argument("--session-id", help="Target automation_session.id (defaults to latest)")
    parser.add_argument("--output-json", help="Optional output path for JSON report")
    parser.add_argument("--output-md", help="Optional output path for Markdown report")
    return parser.parse_args()


def write_if_requested(path_value: str | None, content: str) -> None:
    if not path_value:
        return
    output_path = Path(path_value)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")


def main() -> int:
    args = parse_arguments()
    db_config = DbConfig(host=args.host, port=args.port, database=args.db)
    try:
        session_id = args.session_id or fetch_latest_session_id(db_config)
        report = build_report(db_config, session_id)
    except Exception as error:  # pragma: no cover - operational script
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1

    report_json = json.dumps(report, indent=2, ensure_ascii=False)
    report_markdown = render_markdown(report)

    write_if_requested(args.output_json, report_json + "\n")
    write_if_requested(args.output_md, report_markdown)

    print(report_markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
