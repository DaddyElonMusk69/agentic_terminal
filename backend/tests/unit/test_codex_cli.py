from pathlib import Path

import pytest

from app.infrastructure.external.codex_cli import CodexCliError, execute_codex_cli


@pytest.mark.asyncio
async def test_execute_codex_cli_parses_json_usage_and_last_message(monkeypatch, tmp_path: Path):
    captured = {}

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        captured["cmd"] = cmd

        class _Process:
            returncode = 0

            async def communicate(self, input=None):
                captured["stdin"] = input
                output_path = cmd[cmd.index("--output-last-message") + 1]
                Path(output_path).write_text("OK", encoding="utf-8")
                stdout = '{"type":"turn.completed","usage":{"input_tokens":5,"output_tokens":7}}\n'
                return stdout.encode("utf-8"), b""

        return _Process()

    monkeypatch.setattr(
        "app.infrastructure.external.codex_cli.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    result = await execute_codex_cli(
        prompt_text="Say OK",
        model="gpt-5.3-codex",
        images=[str(tmp_path / "chart.png")],
        cli_path="codex",
        timeout_seconds=30,
    )

    assert result.content == "OK"
    assert result.tokens_used == 12
    assert captured["stdin"] == b"Say OK"
    assert "--json" in captured["cmd"]
    assert "--image" in captured["cmd"]
    assert "--model" in captured["cmd"]


@pytest.mark.asyncio
async def test_execute_codex_cli_raises_on_nonzero_exit(monkeypatch):
    async def fake_create_subprocess_exec(*cmd, **kwargs):
        class _Process:
            returncode = 1

            async def communicate(self, input=None):
                return b"", b"boom"

        return _Process()

    monkeypatch.setattr(
        "app.infrastructure.external.codex_cli.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    with pytest.raises(CodexCliError):
        await execute_codex_cli(
            prompt_text="test",
            model="gpt-5.3-codex",
            images=[],
            cli_path="codex",
            timeout_seconds=30,
        )


@pytest.mark.asyncio
async def test_execute_codex_cli_parses_turn_completed_usage_event(monkeypatch):
    async def fake_create_subprocess_exec(*cmd, **kwargs):
        class _Process:
            returncode = 0

            async def communicate(self, input=None):
                output_path = cmd[cmd.index("--output-last-message") + 1]
                Path(output_path).write_text("usage-ok", encoding="utf-8")
                stdout = (
                    '{"type":"turn.completed.usage","usage":{"input_tokens":3,"output_tokens":4}}\n'
                )
                return stdout.encode("utf-8"), b""

        return _Process()

    monkeypatch.setattr(
        "app.infrastructure.external.codex_cli.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    result = await execute_codex_cli(
        prompt_text="usage",
        model="gpt-5.3-codex",
        images=[],
        cli_path="codex",
        timeout_seconds=30,
    )

    assert result.content == "usage-ok"
    assert result.tokens_used == 7


@pytest.mark.asyncio
async def test_execute_codex_cli_retries_without_ask_for_approval(monkeypatch):
    captured_cmds = []

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        captured_cmds.append(cmd)

        class _Process:
            returncode = 0

            async def communicate(self, input=None):
                output_path = cmd[cmd.index("--output-last-message") + 1]
                if "--ask-for-approval" in cmd:
                    self.returncode = 2
                    return b"", b"error: unexpected argument '--ask-for-approval' found"
                Path(output_path).write_text("fallback-ok", encoding="utf-8")
                return b"", b""

        return _Process()

    monkeypatch.setattr(
        "app.infrastructure.external.codex_cli.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    result = await execute_codex_cli(
        prompt_text="hello",
        model="gpt-5.3-codex",
        images=[],
        cli_path="codex",
        timeout_seconds=30,
    )

    assert result.content == "fallback-ok"
    assert len(captured_cmds) == 2
    assert "--ask-for-approval" in captured_cmds[0]
    assert "--ask-for-approval" not in captured_cmds[1]
