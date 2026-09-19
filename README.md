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

grok launches pin the model: argv always carries `-m glm-53-flash` (override with `LOCAL_AGENT_MCP_GROK_MODEL`). Credentials come from the process env or are backfilled from `~/.env` (see `scripts/dock-grok-env.sh` for the standalone-shell equivalent).

`read_status` returns slot state plus `last_reply` (clean assistant text — no usage/thought JSON wrap) and `log_tail` (raw, for debugging). `read_census_reply` returns the same clean text as `census_reply`.

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

### Floor-visible activity (interim)

**Not a Grok Bot UI card.** Until a product activity card exists, Floor sees mid-run + done beats as chat sitreps that Dock (or Floor) forwards from `events.jsonl`.

`ops` appends one JSON line per event to `<data-dir>/events.jsonl`. Kinds:

| Kind | When | Fields |
|------|------|--------|
| `launch` | slot launched | `harness`, `cwd`, `status`, `excerpt`, `ticket?`, `pid?` |
| `beat` | running slot refreshed (~every 15s) | `harness`, `status`, `excerpt`, `pid?` |
| `status` | `read_status` called | `harness`, `status`, `excerpt`, `pid?` |
| `steer` | payload injected | `via` (cli / tty) |
| `done` | `await`/`done_when` matched | `when`, `harness`, `status`, `excerpt` |
| `state` | slot transitions to `idle` or `dead` | `harness`, `status`, `last_error`, `excerpt` |
| `error` | reserved for auth/launch failures | `error`, `message?` |

Run the watcher (JSON or sitrep one-liners):

```bash
# sitrep lines Dock posts to Floor (interim CloudAgent-like babysit text)
./scripts/floor-activity-watch.sh
# or:
uv run --directory /Users/bennyf/TP-V1/local-agent-mcp \
  python -m local_agent_mcp.watch --format sitrep

# drain once:
uv run --directory /Users/bennyf/TP-V1/local-agent-mcp \
  python -m local_agent_mcp.watch --once --format sitrep

# raw JSONL:
tail -f ~/.local/share/local-agent-mcp/events.jsonl
```

**Still missing (product):** native Grok Bot activity card, auto-wake of Floor without Dock polling/posting, live token streaming into Floor chat.

Wake hooks are not MCP tools (contract v0).

### Dock / standalone-shell grok launcher

`scripts/dock-grok.sh` wraps grok for Dock Shell (zsh -ilc so `~/.env` RDSEC_* load; `scripts/dock-grok-env.sh` exports the same keys without a login shell). The MCP server does not use these; they exist for interactive Dock use.

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
