from __future__ import annotations

import asyncio
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Optional


@dataclass(frozen=True)
class CodexExecResult:
    content: str
    model: Optional[str]
    tokens_used: int
    events: List[dict[str, Any]]
    stdout: str
    stderr: str


class CodexCliError(RuntimeError):
    pass


async def execute_codex_cli(
    prompt_text: str,
    *,
    model: Optional[str],
    images: Iterable[str] | None = None,
    cli_path: str = "codex",
    timeout_seconds: int = 180,
    cwd: str | None = None,
) -> CodexExecResult:
    if not prompt_text:
        raise CodexCliError("prompt_text is required for codex execution")

    last_error: CodexCliError | None = None
    for include_ask_for_approval in (True, False):
        if not include_ask_for_approval and last_error is None:
            # No fallback needed if the first attempt did not fail due to unsupported flag.
            break
        if not include_ask_for_approval and not _is_unsupported_flag_error(
            str(last_error), "--ask-for-approval"
        ):
            break

        output_file = _allocate_output_file()
        cmd = _build_codex_command(
            cli_path=cli_path,
            output_last_message=output_file,
            model=model,
            images=images or [],
            include_ask_for_approval=include_ask_for_approval,
        )

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=prompt_text.encode("utf-8")),
                timeout=max(1, int(timeout_seconds)),
            )
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.wait()
            _remove_file_safely(output_file)
            timeout_value = max(1, int(timeout_seconds))
            raise CodexCliError(
                "codex execution timed out after "
                f"{timeout_value}s (increase BACKEND_CODEX_CLI_TIMEOUT_SECONDS if needed)"
            ) from exc

        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")
        events = _parse_jsonl_events(stdout_text)
        content = _read_last_message(output_file, events)
        tokens_used = _extract_tokens(events)
        resolved_model = _extract_model(events, fallback=model)

        _remove_file_safely(output_file)

        if process.returncode != 0:
            unsupported_ask_for_approval = _contains_unsupported_flag_error(
                stderr_text=stderr_text,
                stdout_text=stdout_text,
                flag_name="--ask-for-approval",
            )
            detail = _extract_failure_detail(
                stdout_text=stdout_text,
                stderr_text=stderr_text,
                events=events,
                returncode=process.returncode,
            )
            error = CodexCliError(f"codex execution failed: {detail}")
            if include_ask_for_approval and unsupported_ask_for_approval:
                last_error = error
                continue
            raise error
        if not content:
            raise CodexCliError("codex execution produced empty output")

        return CodexExecResult(
            content=content,
            model=resolved_model,
            tokens_used=tokens_used,
            events=events,
            stdout=stdout_text,
            stderr=stderr_text,
        )

    if last_error is not None:
        raise last_error
    raise CodexCliError("codex execution failed")


def _build_codex_command(
    *,
    cli_path: str,
    output_last_message: str,
    model: Optional[str],
    images: Iterable[str],
    include_ask_for_approval: bool = True,
) -> list[str]:
    cmd = [
        cli_path,
        "exec",
        "--skip-git-repo-check",
        "--json",
        "--sandbox",
        "read-only",
        "--output-last-message",
        output_last_message,
    ]
    if include_ask_for_approval:
        cmd.extend(["--ask-for-approval", "never"])

    normalized_model = (model or "").strip()
    if normalized_model:
        cmd.extend(["--model", normalized_model])

    for image in images:
        path = str(image or "").strip()
        if not path:
            continue
        cmd.extend(["--image", path])

    # Read prompt from stdin.
    cmd.append("-")
    return cmd


def _allocate_output_file() -> str:
    with tempfile.NamedTemporaryFile(prefix="codex-last-", suffix=".txt", delete=False) as handle:
        return handle.name


def _read_last_message(path: str, events: list[dict[str, Any]]) -> str:
    candidate = Path(path)
    if candidate.exists():
        try:
            value = candidate.read_text(encoding="utf-8").strip()
            if value:
                return value
        except OSError:
            pass
    return _extract_agent_message(events)


def _remove_file_safely(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _parse_jsonl_events(stdout_text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in stdout_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _extract_failure_detail(
    *,
    stdout_text: str,
    stderr_text: str,
    events: list[dict[str, Any]],
    returncode: int,
) -> str:
    event_message = _extract_failure_message(events)
    if event_message:
        return event_message

    stderr_message = _extract_meaningful_text(stderr_text)
    if stderr_message:
        return stderr_message

    stdout_message = _extract_meaningful_text(stdout_text)
    if stdout_message:
        return stdout_message

    stripped_stderr = stderr_text.strip()
    if stripped_stderr:
        return stripped_stderr

    stripped_stdout = stdout_text.strip()
    if stripped_stdout:
        return stripped_stdout

    return f"exit code {returncode}"


def _extract_agent_message(events: list[dict[str, Any]]) -> str:
    for event in reversed(events):
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        if item.get("type") != "agent_message":
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
    return ""


def _extract_failure_message(events: list[dict[str, Any]]) -> Optional[str]:
    for event in reversed(events):
        event_type = str(event.get("type") or "").strip().lower()
        if "failed" not in event_type and "error" not in event_type and "error" not in event:
            continue

        for candidate in (
            _extract_nested_text(event.get("error")),
            _extract_nested_text(event.get("message")),
            _extract_nested_text(event.get("detail")),
            _extract_nested_text(event.get("turn")),
            _extract_nested_text(event.get("item")),
        ):
            if candidate:
                return candidate
    return None


def _extract_tokens(events: list[dict[str, Any]]) -> int:
    for event in reversed(events):
        event_type = str(event.get("type") or "").strip().lower()
        usage = _extract_usage_payload(event, event_type=event_type)
        if not isinstance(usage, dict):
            continue
        total_tokens = _safe_int(usage.get("total_tokens"))
        if total_tokens is not None:
            return total_tokens
        input_tokens = _safe_int(usage.get("input_tokens"))
        output_tokens = _safe_int(usage.get("output_tokens"))
        if input_tokens is None:
            input_tokens = _safe_int(usage.get("prompt_tokens"))
        if output_tokens is None:
            output_tokens = _safe_int(usage.get("completion_tokens"))
        if input_tokens is None and output_tokens is None:
            continue
        return int(input_tokens or 0) + int(output_tokens or 0)
    return 0


def _extract_usage_payload(event: dict[str, Any], *, event_type: str) -> Optional[dict[str, Any]]:
    if event_type == "turn.completed":
        usage = event.get("usage")
        if isinstance(usage, dict):
            return usage
        turn = event.get("turn")
        if isinstance(turn, dict):
            usage = turn.get("usage")
            if isinstance(usage, dict):
                return usage
        return None

    if event_type == "turn.completed.usage":
        usage = event.get("usage")
        if isinstance(usage, dict):
            return usage
        item = event.get("item")
        if isinstance(item, dict):
            usage = item.get("usage")
            if isinstance(usage, dict):
                return usage
        return None

    return None


def _extract_model(events: list[dict[str, Any]], fallback: Optional[str]) -> Optional[str]:
    keys = ("model", "model_name")
    for event in events:
        for key in keys:
            value = event.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        item = event.get("item")
        if isinstance(item, dict):
            for key in keys:
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    if fallback and fallback.strip():
        return fallback.strip()
    return None


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_nested_text(value: Any) -> Optional[str]:
    if isinstance(value, str):
        return _extract_meaningful_text(value) or value.strip() or None
    if isinstance(value, dict):
        for key in ("message", "detail", "reason", "stderr", "stdout", "error", "cause"):
            nested = _extract_nested_text(value.get(key))
            if nested:
                return nested
    if isinstance(value, list):
        for item in value:
            nested = _extract_nested_text(item)
            if nested:
                return nested
    return None


def _extract_meaningful_text(text: str) -> Optional[str]:
    meaningful_lines = []
    priority_line: Optional[str] = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or _is_noise_line(line):
            continue
        if priority_line is None and _is_priority_error_line(line):
            priority_line = line
        meaningful_lines.append(line)
    if priority_line:
        return priority_line
    if meaningful_lines:
        return meaningful_lines[-1]
    return None


def _is_noise_line(line: str) -> bool:
    lowered = line.strip().lower()
    if not lowered:
        return True
    return lowered.startswith("reading prompt from stdin") or (
        lowered.startswith("warning: no last agent message;")
    )


def _is_priority_error_line(line: str) -> bool:
    lowered = line.strip().lower()
    if not lowered:
        return False
    prefixes = (
        "error:",
        "failed:",
        "fatal:",
    )
    if lowered.startswith(prefixes):
        return True
    markers = (
        "unexpected argument",
        "invalid value",
        "unrecognized option",
        "unknown option",
        "requires",
        "timed out",
        "stream disconnected",
    )
    return any(marker in lowered for marker in markers)


def _contains_unsupported_flag_error(*, stderr_text: str, stdout_text: str, flag_name: str) -> bool:
    detail = "\n".join(part for part in (stderr_text, stdout_text) if part)
    return _is_unsupported_flag_error(detail, flag_name)


def _is_unsupported_flag_error(detail: str, flag_name: str) -> bool:
    lowered = (detail or "").strip().lower()
    if not lowered:
        return False
    return "unexpected argument" in lowered and flag_name.lower() in lowered
