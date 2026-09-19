"""Follow the registry's events.jsonl: Floor/Dock wake helper. Not an MCP tool.

Event kinds written by ops: launch, status, steer, done, state. `state` fires on
slot transitions to idle/dead. Run:

    uv run python -m local_agent_mcp.watch            # follow (tail -f)
    uv run python -m local_agent_mcp.watch --once     # drain and exit
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from local_agent_mcp.ops import default_home

POLL_S = 0.5


def follow(path: Path, *, once: bool = False) -> int:
    """Print each JSONL record as it lands; returns records seen (--once)."""
    records = 0
    try:
        pos = 0 if once else (path.stat().st_size if path.exists() else 0)
    except OSError:
        pos = 0
    if not once:
        print(f"watching {path}", file=sys.stderr)
    while True:
        try:
            size = path.stat().st_size if path.exists() else 0
        except OSError:
            size = pos
        if size < pos:
            pos = 0  # truncated or rotated
        if size > pos:
            try:
                with path.open("r", encoding="utf-8") as fh:
                    fh.seek(pos)
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        print(json.dumps(rec, separators=(",", ":")), flush=True)
                        records += 1
                    pos = fh.tell()
            except OSError:
                pass
        if once:
            return records
        time.sleep(POLL_S)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="local-agent-mcp-watch",
        description="Print local-agent-mcp events as they land (wake helper for Floor/Dock).",
    )
    parser.add_argument(
        "--home",
        help="registry home (default: LOCAL_AGENT_MCP_HOME or ~/.local/share/local-agent-mcp)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="drain existing records and exit (no follow)",
    )
    args = parser.parse_args(argv)
    home = Path(args.home).expanduser() if args.home else default_home()
    return follow(home / "events.jsonl", once=args.once)


if __name__ == "__main__":
    raise SystemExit(main())
