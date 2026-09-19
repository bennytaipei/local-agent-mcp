#!/bin/bash
# Interim Floor-visible activity: follow events.jsonl as sitrep lines.
# Dock (or Floor) runs this while Ops launches slots; Dock posts lines to Floor.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOME_DIR="${LOCAL_AGENT_MCP_HOME:-$HOME/.local/share/local-agent-mcp}"
exec uv --directory "$ROOT" run python -m local_agent_mcp.watch --home "$HOME_DIR" --format sitrep "$@"
