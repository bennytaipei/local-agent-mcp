# local-agent-mcp

stdio MCP server for Ops Floor. **MCP CONTRACT v0 is the product surface** — tools, fields, harnesses, and error enums are not extended here.

## Contract v0

Ops:

| Tool | Alias | Role |
|------|--------|------|
| `list_sessions` | | List Floor-managed slots |
| `launch_session` | | Start a slot; returns `slot_id` |
| `steer` | `inject` | One follow-up payload per call |
| `read_status` | `read_census_reply` | Slot status / latest census reply |
| `await` | `done_when` | Wait until idle, or until `when` matches |

Harnesses: `omp` | `grok` | `claude`

`launch_session` recipe: `cwd`, `harness`, `ticket?`, `branch?`, `first_prompt` → slot id

`steer` / `inject`: prefer non-interactive CLI (`-p` / resume). TTY attach (GNU `screen`) if the CLI cannot take the payload.

Stable enums: `inject_ok` | `inject_failed` | `wrong_slot` | `session_dead` | `auth_failed` | `unsupported_harness`

Non-goals v0: war-room logic, Jira, git write as a product beyond this repo, replacing Steersman (Steersman stays the interactive census fallback).

Wake/heartbeat for Floor/Dock: ops writes `events.jsonl` under the data dir. Wake hooks are not MCP tools; they can follow once this server is in use.

Launches are `--always-approve` / `--dangerously-skip-permissions` / `--approval-mode yolo` so Floor is not blocked on TTY permission prompts.

## Run

```bash
uv sync --group dev
uv run local-agent-mcp          # stdio MCP
uv run pytest
```

Data dir: `$LOCAL_AGENT_MCP_HOME` or `~/.local/share/local-agent-mcp`.

Binary overrides: `LOCAL_AGENT_MCP_GROK`, `LOCAL_AGENT_MCP_CLAUDE`, `LOCAL_AGENT_MCP_OMP`.

### Floor / Grok config

```toml
[mcp_servers.local-agent]
command = "uv"
args = ["--directory", "/Users/bennyf/TP-V1/local-agent-mcp", "run", "local-agent-mcp"]
```

Claude Code:

```json
{
  "mcpServers": {
    "local-agent": {
      "command": "uv",
      "args": ["--directory", "/Users/bennyf/TP-V1/local-agent-mcp", "run", "local-agent-mcp"]
    }
  }
}
```
