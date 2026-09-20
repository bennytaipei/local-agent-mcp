"""stdio MCP server. Product surface is MCP CONTRACT v0.1 — nothing else."""

from __future__ import annotations

import logging
import sys

from mcp.server.fastmcp import FastMCP

from local_agent_mcp.contract import OPS_TOOLS
from local_agent_mcp.ops import Ops

log = logging.getLogger("local-agent-mcp")


def create_server(ops: Ops | None = None) -> FastMCP:
    ops = ops or Ops.from_env()
    mcp = FastMCP(
        "local-agent-mcp",
        instructions=(
            "Ops Floor contract v0.1. Tools: list_sessions, launch_session, "
            "steer/inject, read_status/read_census_reply, await/done_when, "
            "read_transcript. list_sessions includes transcript_path + log_bytes. "
            "Harnesses: omp | grok | claude. Errors: inject_ok | inject_failed | "
            "wrong_slot | session_dead | auth_failed | unsupported_harness."
        ),
    )

    @mcp.tool(name="list_sessions", description="List Floor-managed agent slots.")
    def list_sessions() -> dict:
        return ops.list_sessions()

    @mcp.tool(
        name="launch_session",
        description="Launch a slot. Recipe: cwd, harness, ticket?, branch?, first_prompt → slot_id.",
    )
    def launch_session(
        cwd: str,
        harness: str,
        first_prompt: str,
        ticket: str | None = None,
        branch: str | None = None,
    ) -> dict:
        return ops.launch_session(
            cwd=cwd,
            harness=harness,
            first_prompt=first_prompt,
            ticket=ticket,
            branch=branch,
        )

    @mcp.tool(name="steer", description="Inject one follow-up payload into a slot (alias: inject).")
    def steer(slot_id: str, payload: str) -> dict:
        return ops.steer(slot_id, payload)

    @mcp.tool(name="inject", description="Inject one follow-up payload into a slot (alias: steer).")
    def inject(slot_id: str, payload: str) -> dict:
        return ops.inject(slot_id, payload)

    @mcp.tool(name="read_status", description="Read slot status (alias: read_census_reply).")
    def read_status(slot_id: str) -> dict:
        return ops.read_status(slot_id)

    @mcp.tool(
        name="read_census_reply",
        description="Read the latest census reply / last assistant output (alias: read_status).",
    )
    def read_census_reply(slot_id: str) -> dict:
        return ops.read_census_reply(slot_id)

    @mcp.tool(name="await", description="Wait until the slot is idle (alias: done_when).")
    def await_tool(slot_id: str, timeout_s: float = 30.0) -> dict:
        return ops.await_done(slot_id, timeout_s=timeout_s)

    @mcp.tool(
        name="done_when",
        description="Wait until status matches `when` (idle|dead|running) or `when` appears in output.",
    )
    def done_when(slot_id: str, when: str, timeout_s: float = 30.0) -> dict:
        return ops.done_when(slot_id, when=when, timeout_s=timeout_s)


    @mcp.tool(
        name="read_transcript",
        description=(
            "Read a slot's stdout.log transcript. "
            "Args: slot_id, offset_bytes?=0, max_bytes?=65536. "
            "Returns path, text, truncated, mtime, log_bytes."
        ),
    )
    def read_transcript(
        slot_id: str,
        offset_bytes: int = 0,
        max_bytes: int = 65536,
    ) -> dict:
        return ops.read_transcript(
            slot_id, offset_bytes=offset_bytes, max_bytes=max_bytes
        )

    # Keep a handle for tests; FastMCP does not expose ops otherwise.
    mcp._local_agent_ops = ops  # type: ignore[attr-defined]
    mcp._local_agent_tool_names = OPS_TOOLS  # type: ignore[attr-defined]
    return mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(name)s %(levelname)s %(message)s")
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
