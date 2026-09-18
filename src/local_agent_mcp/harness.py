"""Harness CLI argv + auth/session discovery. Product harnesses: omp | grok | claude."""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

from local_agent_mcp.contract import AUTH_FAILED, HARNESSES, UNSUPPORTED_HARNESS

HARNESS_ENV = {
    "grok": "LOCAL_AGENT_MCP_GROK",
    "claude": "LOCAL_AGENT_MCP_CLAUDE",
    "omp": "LOCAL_AGENT_MCP_OMP",
}

AUTH_RE = re.compile(
    r"(not logged in|authentication failed|please run (grok|claude|omp) login"
    r"|invalid api key|unauthoriz(?:ed|ation)|auth_failed)",
    re.IGNORECASE,
)

SESSION_ID_RE = re.compile(
    r'"session[_-]?id"\s*:\s*"([0-9a-fA-F-]{8,})"',
    re.IGNORECASE,
)


def which_harness(harness: str, env: dict[str, str] | None = None) -> str | None:
    env = env or os.environ
    override = env.get(HARNESS_ENV.get(harness, ""), "").strip()
    if override:
        return override
    extras = [
        str(Path.home() / ".grok" / "bin"),
        str(Path.home() / ".local" / "bin"),
        str(Path.home() / ".bun" / "bin"),
        "/opt/homebrew/bin",
        "/usr/local/bin",
    ]
    path = os.pathsep.join(extras + [env.get("PATH", "")])
    return shutil.which(harness, path=path)


def enriched_env(base: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(base or os.environ)
    extras = [
        str(Path.home() / ".grok" / "bin"),
        str(Path.home() / ".local" / "bin"),
        str(Path.home() / ".bun" / "bin"),
        "/opt/homebrew/bin",
        "/usr/local/bin",
    ]
    env["PATH"] = os.pathsep.join([p for p in extras if Path(p).is_dir()] + [env.get("PATH", "")])
    return env


def launch_argv(
    harness: str,
    binary: str,
    *,
    cwd: str,
    slot_id: str,
    prompt: str,
    prompt_file: Path | None = None,
) -> list[str]:
    if harness not in HARNESSES:
        raise ValueError(UNSUPPORTED_HARNESS)
    if harness == "grok":
        cmd = [
            binary,
            "--always-approve",
            "--cwd",
            cwd,
            "--session-id",
            slot_id,
            "--output-format",
            "json",
        ]
        if prompt_file is not None:
            cmd.extend(["--prompt-file", str(prompt_file)])
        else:
            cmd.extend(["-p", prompt])
        return cmd
    if harness == "claude":
        return [
            binary,
            "--dangerously-skip-permissions",
            "--output-format",
            "json",
            "--session-id",
            slot_id,
            "-p",
            prompt,
        ]
    # omp
    cmd = [binary, "--cwd", cwd, "--approval-mode", "yolo", "--mode", "json"]
    if prompt_file is not None:
        cmd.extend(["-p", f"@{prompt_file}"])
    else:
        cmd.extend(["-p", prompt])
    return cmd


def resume_argv(
    harness: str,
    binary: str,
    *,
    cwd: str,
    harness_session_id: str,
    prompt: str,
    prompt_file: Path | None = None,
) -> list[str]:
    if harness not in HARNESSES:
        raise ValueError(UNSUPPORTED_HARNESS)
    sid = harness_session_id
    if harness == "grok":
        cmd = [
            binary,
            "--always-approve",
            "--cwd",
            cwd,
            "--resume",
            sid,
            "--output-format",
            "json",
        ]
        if prompt_file is not None:
            cmd.extend(["--prompt-file", str(prompt_file)])
        else:
            cmd.extend(["-p", prompt])
        return cmd
    if harness == "claude":
        return [
            binary,
            "--dangerously-skip-permissions",
            "--output-format",
            "json",
            "--resume",
            sid,
            "-p",
            prompt,
        ]
    cmd = [binary, "--cwd", cwd, "--approval-mode", "yolo", "--mode", "json", "-r", sid]
    if prompt_file is not None:
        cmd.extend(["-p", f"@{prompt_file}"])
    else:
        cmd.extend(["-p", prompt])
    return cmd


def classify_log(text: str) -> str | None:
    if AUTH_RE.search(text or ""):
        return AUTH_FAILED
    return None


def extract_session_id(text: str, fallback: str | None = None) -> str | None:
    if not text:
        return fallback
    m = SESSION_ID_RE.search(text)
    if m:
        return m.group(1)
    try:
        obj = json.loads(text.strip().splitlines()[-1])
        for key in ("sessionId", "session_id", "id"):
            if isinstance(obj, dict) and obj.get(key):
                return str(obj[key])
    except (json.JSONDecodeError, IndexError):
        pass
    return fallback


def extract_reply_text(text: str) -> str:
    if not text:
        return ""
    lines = [
        ln
        for ln in text.strip().splitlines()
        if ln.strip() and not ln.startswith("--- turn")
    ]
    for ln in reversed(lines):
        try:
            obj = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            for key in ("text", "result", "message", "census_reply"):
                val = obj.get(key)
                if isinstance(val, str) and val.strip():
                    return val
    return "\n".join(lines)[-8000:]


def omp_session_dir(cwd: Path) -> Path:
    home = Path.home()
    resolved = cwd.resolve()
    try:
        rel = resolved.relative_to(home)
        name = "-" + str(rel).replace("/", "-")
    except ValueError:
        name = str(resolved).replace("/", "-")
    return home / ".omp" / "agent" / "sessions" / name


def discover_omp_session(cwd: Path, since: float) -> str | None:
    d = omp_session_dir(cwd)
    if not d.is_dir():
        return None
    newest: tuple[float, Path] | None = None
    for path in d.glob("*.jsonl"):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime + 0.05 < since:
            continue
        if newest is None or mtime >= newest[0]:
            newest = (mtime, path)
    if newest is None:
        return None
    path = newest[1]
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") == "session" and obj.get("id"):
                return str(obj["id"])
            if obj.get("id") and "session" in path.name:
                sid = str(obj["id"])
                if len(sid) >= 8:
                    return sid
    except OSError:
        return None
    # filename: 2026-09-08T19-44-48-932Z_<id>.jsonl
    stem = path.stem
    if "_" in stem:
        return stem.split("_", 1)[-1]
    return None
