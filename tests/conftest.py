from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from local_agent_mcp.ops import Ops

FAKE = Path(__file__).resolve().parent / "fake_harness.py"


@pytest.fixture()
def ops_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    home = tmp_path / "mcp-home"
    state = tmp_path / "fake-state"
    state.mkdir()
    # Point every harness at the fake CLI via a small wrapper script so argv[0] is a file.
    wrapper = tmp_path / "fake-cli"
    wrapper.write_text(
        f"#!/bin/sh\nexec {sys.executable} {FAKE} \"$@\"\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    env = {
        **os.environ,
        "LOCAL_AGENT_MCP_HOME": str(home),
        "LOCAL_AGENT_MCP_GROK": str(wrapper),
        "LOCAL_AGENT_MCP_CLAUDE": str(wrapper),
        "LOCAL_AGENT_MCP_OMP": str(wrapper),
        "FAKE_HARNESS_STATE": str(state),
        "FAKE_HARNESS_MODE": "ok",
        "FAKE_HARNESS_SLEEP": "0",
        "HOME": str(tmp_path / "user-home"),
    }
    (tmp_path / "user-home").mkdir()
    monkeypatch.setenv("LOCAL_AGENT_MCP_HOME", str(home))
    monkeypatch.setenv("LOCAL_AGENT_MCP_GROK", str(wrapper))
    monkeypatch.setenv("LOCAL_AGENT_MCP_CLAUDE", str(wrapper))
    monkeypatch.setenv("LOCAL_AGENT_MCP_OMP", str(wrapper))
    monkeypatch.setenv("FAKE_HARNESS_STATE", str(state))
    return {"home": home, "wrapper": wrapper, "state": state, "env": env, "cwd": tmp_path / "work"}


@pytest.fixture()
def workdir(ops_env: dict) -> Path:
    cwd = ops_env["cwd"]
    cwd.mkdir()
    return cwd


@pytest.fixture()
def ops(ops_env: dict) -> Ops:
    return Ops(home=ops_env["home"], env=ops_env["env"])
