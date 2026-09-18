"""TTY attach fallback via GNU screen. Used when a harness CLI cannot take -p."""

from __future__ import annotations

import shutil
import subprocess


def screen_bin() -> str | None:
    return shutil.which("screen")


def session_name(slot_id: str) -> str:
    return f"lam-{slot_id}"


def spawn(slot_id: str, command: list[str], *, cwd: str, env: dict[str, str]) -> bool:
    binary = screen_bin()
    if not binary:
        return False
    name = session_name(slot_id)
    # screen -dmS name cmd... starts detached with a PTY.
    proc = subprocess.run(
        [binary, "-dmS", name, *command],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0


def alive(slot_id: str) -> bool:
    binary = screen_bin()
    if not binary:
        return False
    name = session_name(slot_id)
    proc = subprocess.run(
        [binary, "-ls", name],
        capture_output=True,
        text=True,
        check=False,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return name in out and "No Sockets found" not in out


def stuff(slot_id: str, payload: str) -> bool:
    binary = screen_bin()
    if not binary:
        return False
    name = session_name(slot_id)
    # One follow-up payload per call. Trailing newline submits in TUI.
    text = payload if payload.endswith("\n") else payload + "\n"
    proc = subprocess.run(
        [binary, "-S", name, "-X", "stuff", text],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0
