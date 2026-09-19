from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from local_agent_mcp.contract import (
    AUTH_FAILED,
    INJECT_OK,
    OPS_TOOLS,
    SESSION_DEAD,
    UNSUPPORTED_HARNESS,
    WRONG_SLOT,
)
from local_agent_mcp.harness import (
    enriched_env,
    env_file_credentials,
    launch_argv,
    resume_argv,
)
from local_agent_mcp.ops import Ops
from local_agent_mcp.registry import Slot
from local_agent_mcp.server import create_server


def test_launch_argv_always_approve() -> None:
    grok = launch_argv("grok", "grok", cwd="/tmp", slot_id="s", prompt="hi")
    assert "--always-approve" in grok
    assert "-p" in grok or "--prompt-file" in grok
    claude = launch_argv("claude", "claude", cwd="/tmp", slot_id="s", prompt="hi")
    assert "--dangerously-skip-permissions" in claude
    omp = launch_argv("omp", "omp", cwd="/tmp", slot_id="s", prompt="hi")
    assert "--approval-mode" in omp and "yolo" in omp
    r = resume_argv("grok", "grok", cwd="/tmp", harness_session_id="s", prompt="next")
    assert "--resume" in r


def test_enriched_env_backfills_credentials_from_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".env").write_text(
        "# comment\n"
        "rdsec-ai-endpoint-url: https://example.invalid/v1\n"
        "RDSEC_API_KEY: file-key\n"
        'RDSEC_EXPERIMENTAL_API_KEY="file-exp"\n',
        encoding="utf-8",
    )
    env = enriched_env({"PATH": "/usr/bin:/bin"})
    assert env["RDSEC_API_KEY"] == "file-key"
    assert env["RDSEC_EXPERIMENTAL_API_KEY"] == "file-exp"


def test_enriched_env_prefers_existing_credentials(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".env").write_text("RDSEC_API_KEY: file-key\n", encoding="utf-8")
    env = enriched_env({"PATH": "/usr/bin:/bin", "RDSEC_API_KEY": "process-key"})
    assert env["RDSEC_API_KEY"] == "process-key"


def test_enriched_env_without_env_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    env = enriched_env({"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)})
    assert "RDSEC_API_KEY" not in env


def test_env_file_credentials_skips_lowercase_and_comments(tmp_path: Path) -> None:
    f = tmp_path / ".env"
    f.write_text(
        "# RDSEC_API_KEY: commented\n"
        "atlassian_url: https://x\n"
        "export RDSEC_API_KEY=exported\n",
        encoding="utf-8",
    )
    creds = env_file_credentials(f)
    assert creds == {"RDSEC_API_KEY": "exported"}


def test_unsupported_harness(ops: Ops, workdir: Path) -> None:
    out = ops.launch_session(cwd=str(workdir), harness="codex", first_prompt="x")
    assert out["error"] == UNSUPPORTED_HARNESS
    assert out["ok"] is False


def test_wrong_slot(ops: Ops) -> None:
    out = ops.steer("does-not-exist", "hello")
    assert out["error"] == WRONG_SLOT
    assert ops.read_status("does-not-exist")["error"] == WRONG_SLOT
    assert ops.await_done("does-not-exist", timeout_s=0.01)["error"] == WRONG_SLOT


def test_launch_steer_status_await(ops: Ops, workdir: Path) -> None:
    launched = ops.launch_session(
        cwd=str(workdir),
        harness="grok",
        first_prompt="do the thing",
        ticket="TIP-1",
    )
    assert launched["ok"] is True
    slot_id = launched["slot_id"]
    waited = ops.await_done(slot_id, timeout_s=5)
    assert waited["ok"] is True
    assert waited["status"] == "idle"
    listed = ops.list_sessions()
    assert listed["ok"] is True
    assert any(s["slot_id"] == slot_id for s in listed["sessions"])
    status = ops.read_status(slot_id)
    assert status["status"] == "idle"
    assert status["ticket"] == "TIP-1"
    assert status["harness"] == "grok"
    steered = ops.steer(slot_id, "CENSUS now")
    assert steered["error"] == INJECT_OK
    assert steered["ok"] is True
    ops.await_done(slot_id, timeout_s=5)
    census = ops.read_census_reply(slot_id)
    assert census["ok"] is True
    assert "CENSUS_REPLY" in census["census_reply"] or "idle" in census["census_reply"]


def test_inject_alias(ops: Ops, workdir: Path) -> None:
    launched = ops.launch_session(cwd=str(workdir), harness="claude", first_prompt="hi")
    ops.await_done(launched["slot_id"], timeout_s=5)
    out = ops.inject(launched["slot_id"], "follow-up")
    assert out["error"] == INJECT_OK


def test_done_when_substring(ops: Ops, workdir: Path) -> None:
    launched = ops.launch_session(
        cwd=str(workdir), harness="omp", first_prompt="hello world"
    )
    out = ops.done_when(launched["slot_id"], when="ok:", timeout_s=5)
    assert out["matched"] is True


def test_auth_failed(ops: Ops, workdir: Path, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_HARNESS_MODE", "auth")
    ops.env["FAKE_HARNESS_MODE"] = "auth"
    out = ops.launch_session(cwd=str(workdir), harness="grok", first_prompt="hi")
    if out.get("error") == AUTH_FAILED:
        assert out["ok"] is False
        return
    assert out.get("ok") is True
    waited = ops.await_done(out["slot_id"], timeout_s=5)
    assert waited["error"] == AUTH_FAILED
    assert waited["ok"] is False


def test_session_dead(ops: Ops) -> None:
    slot = Slot(
        slot_id="00000000-0000-4000-8000-deaddeaddead",
        harness="omp",
        cwd="/tmp",
        first_prompt="x",
        status="dead",
        harness_session_id=None,
    )
    ops.registry.put(slot)
    out = ops.steer(slot.slot_id, "nope")
    assert out["error"] == SESSION_DEAD


def test_branch_checkout(ops: Ops, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env=env)
    subprocess.run(
        ["git", "config", "user.email", "t@t"], cwd=repo, check=True, env=env
    )
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True, env=env)
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True, env=env
    )
    (repo / "f").write_text("a", encoding="utf-8")
    subprocess.run(["git", "add", "f"], cwd=repo, check=True, env=env)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True, env=env)
    default = subprocess.check_output(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo, text=True, env=env
    ).strip()
    subprocess.run(["git", "checkout", "-qb", "feat"], cwd=repo, check=True, env=env)
    subprocess.run(["git", "checkout", "-q", default], cwd=repo, check=True, env=env)
    out = ops.launch_session(
        cwd=str(repo), harness="grok", first_prompt="x", branch="feat"
    )
    assert out["ok"] is True
    head = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"], text=True
    ).strip()
    assert head == "feat"


def test_mcp_tool_names_are_the_contract(ops: Ops) -> None:
    mcp = create_server(ops)
    names = sorted(t.name for t in mcp._tool_manager.list_tools())
    assert names == sorted(OPS_TOOLS)
