"""MCP CONTRACT v0 — stable enums, harnesses, and recipe fields.

Do not add product tools or error names beyond this module.
"""

from __future__ import annotations

from typing import Literal

HARNESSES = ("omp", "grok", "claude")
Harness = Literal["omp", "grok", "claude"]

# Stable error/status enums from the contract.
INJECT_OK = "inject_ok"
INJECT_FAILED = "inject_failed"
WRONG_SLOT = "wrong_slot"
SESSION_DEAD = "session_dead"
AUTH_FAILED = "auth_failed"
UNSUPPORTED_HARNESS = "unsupported_harness"

ERROR_ENUMS = (
    INJECT_OK,
    INJECT_FAILED,
    WRONG_SLOT,
    SESSION_DEAD,
    AUTH_FAILED,
    UNSUPPORTED_HARNESS,
)

# launch_session recipe fields: cwd, harness, ticket?, branch?, first_prompt → slot id
LAUNCH_REQUIRED = ("cwd", "harness", "first_prompt")
LAUNCH_OPTIONAL = ("ticket", "branch")

# Slash-pair aliases (same op).
TOOL_ALIASES = {
    "steer": "inject",
    "inject": "steer",
    "read_status": "read_census_reply",
    "read_census_reply": "read_status",
    "await": "done_when",
    "done_when": "await",
}

OPS_TOOLS = (
    "list_sessions",
    "launch_session",
    "steer",
    "inject",
    "read_status",
    "read_census_reply",
    "await",
    "done_when",
)


def error_payload(error: str, **fields: object) -> dict:
    if error not in ERROR_ENUMS:
        raise ValueError(f"unknown error enum: {error}")
    out: dict = {"ok": error == INJECT_OK, "error": error}
    out.update(fields)
    return out
