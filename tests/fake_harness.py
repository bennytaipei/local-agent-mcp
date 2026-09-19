#!/usr/bin/env python3
"""Stand-in for grok/claude/omp CLIs in tests. Speaks the same flag subset."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def _parse(argv: list[str]) -> dict:
    prompt = ""
    session_id = None
    resume = None
    prompt_file = None
    i = 0
    value_flags = {
        "--cwd",
        "--output-format",
        "--approval-mode",
        "--mode",
        "--session-id",
        "-s",
        "--resume",
        "-r",
        "--prompt-file",
        "-m",
        "-p",
        "--print",
        "--single",
    }
    skip_flags = {
        "--always-approve",
        "--dangerously-skip-permissions",
        "-p",
    }
    positional: list[str] = []
    while i < len(argv):
        a = argv[i]
        if (
            a in ("-p", "--print", "--single")
            and i + 1 < len(argv)
            and not argv[i + 1].startswith("-")
        ):
            prompt = argv[i + 1]
            i += 2
            continue
        if a in ("-s", "--session-id") and i + 1 < len(argv):
            session_id = argv[i + 1]
            i += 2
            continue
        if a in ("-r", "--resume") and i + 1 < len(argv):
            resume = argv[i + 1]
            i += 2
            continue
        if a == "--prompt-file" and i + 1 < len(argv):
            prompt_file = argv[i + 1]
            i += 2
            continue
        if a in value_flags and i + 1 < len(argv):
            i += 2
            continue
        if a.startswith("-"):
            if a in skip_flags:
                i += 1
                continue
            i += 1
            continue
        positional.append(a)
        i += 1
    if prompt.startswith("@") and Path(prompt[1:]).is_file():
        prompt = Path(prompt[1:]).read_text(encoding="utf-8")
    if prompt_file:
        prompt = Path(prompt_file).read_text(encoding="utf-8")
    if not prompt and positional:
        prompt = positional[-1]
    return {"prompt": prompt, "session_id": session_id, "resume": resume}


def main() -> int:
    mode = os.environ.get("FAKE_HARNESS_MODE", "ok")
    sleep_s = float(os.environ.get("FAKE_HARNESS_SLEEP", "0") or 0)
    parsed = _parse(sys.argv[1:])
    if sleep_s:
        time.sleep(sleep_s)
    sid = (
        parsed["resume"]
        or parsed["session_id"]
        or "00000000-0000-4000-8000-000000000000"
    )
    if mode == "auth":
        print("Please run grok login: authentication failed", flush=True)
        return 1
    if mode == "crash":
        print("boom", flush=True)
        return 2
    text = f"ok:{parsed['prompt']}"
    if "CENSUS" in parsed["prompt"]:
        text = "CENSUS_REPLY\nharness=fake status=idle"
    print(
        json.dumps({"text": text, "sessionId": sid, "stopReason": "end_turn"}),
        flush=True,
    )
    state = Path(os.environ.get("FAKE_HARNESS_STATE", "/tmp/fake-harness-state"))
    state.mkdir(parents=True, exist_ok=True)
    with (state / "calls.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {"sid": sid, "resume": parsed["resume"], "prompt": parsed["prompt"]}
            )
            + "\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
