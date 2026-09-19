"""Follow events.jsonl — Floor/Dock interim activity (not an MCP tool).

Ops appends launch/status/beat/steer/done/state/error. This helper prints
JSON (default) or human sitrep lines Dock can forward to Floor.

    uv run python -m local_agent_mcp.watch
    uv run python -m local_agent_mcp.watch --format sitrep
    uv run python -m local_agent_mcp.watch --once --format sitrep
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from local_agent_mcp.ops import default_home

POLL_S = 0.5


def _sitrep(rec: dict) -> str:
    kind = rec.get("kind", "?")
    slot = (rec.get("slot_id") or "")[:8] or "-"
    harness = rec.get("harness") or "-"
    status = rec.get("status") or rec.get("when") or "-"
    excerpt = (rec.get("excerpt") or rec.get("message") or rec.get("error") or "").strip()
    if len(excerpt) > 100:
        excerpt = excerpt[:97] + "..."
    base = f"[local-agent] {kind} slot={slot} harness={harness} status={status}"
    if excerpt:
        base += f" | {excerpt}"
    return base


def follow(path: Path, *, once: bool = False, fmt: str = "json") -> int:
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
            pos = 0
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
                        if fmt == "sitrep":
                            print(_sitrep(rec), flush=True)
                        else:
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
        description="Print local-agent-mcp events (wake helper for Floor/Dock).",
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
    parser.add_argument(
        "--format",
        choices=("json", "sitrep"),
        default="json",
        help="json (default) or sitrep one-liners for Floor chat",
    )
    args = parser.parse_args(argv)
    home = Path(args.home).expanduser() if args.home else default_home()
    return follow(home / "events.jsonl", once=args.once, fmt=args.format)


if __name__ == "__main__":
    raise SystemExit(main())
