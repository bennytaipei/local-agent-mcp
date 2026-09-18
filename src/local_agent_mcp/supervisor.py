"""Detached slot supervisor: run one harness turn, record pid + exit code."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def run_turn(slot_dir: Path, cwd: str, cmd: list[str]) -> int:
    slot_dir.mkdir(parents=True, exist_ok=True)
    (slot_dir / "pid").write_text(str(os.getpid()), encoding="utf-8")
    log_path = slot_dir / "stdout.log"
    with log_path.open("ab") as log:
        log.write(b"\n--- turn start ---\n")
        log.flush()
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
        )
        (slot_dir / "child_pid").write_text(str(proc.pid), encoding="utf-8")
        rc = proc.wait()
    (slot_dir / "exit_code").write_text(str(rc), encoding="utf-8")
    return rc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="local-agent-mcp-supervisor")
    parser.add_argument("--slot-dir", required=True)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("cmd", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    cmd = list(args.cmd)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print("supervisor: missing command", file=sys.stderr)
        return 2
    return run_turn(Path(args.slot_dir), args.cwd, cmd)


if __name__ == "__main__":
    raise SystemExit(main())
