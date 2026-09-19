#!/bin/bash
# Dock launcher: match Floor repro that works — zsh -ilc (loads ~/.env RDSEC_*).
# bash -lc does NOT. Used for Dock Shell / screen dock-mcp only. Never attach ttys014.
set -euo pipefail
GROK_BIN="${GROK_BIN:-/Users/bennyf/.grok/bin/grok}"
if [[ $# -eq 0 ]]; then
  set -- -m glm-53-flash --always-approve -p "Reply with exactly: PONG"
fi
# Pass args safely into zsh -ilc
quoted=$(printf '%q ' "$@")
exec /bin/zsh -ilc "unset NO_COLOR; export TERM=xterm-256color; exec $(printf %q "$GROK_BIN") $quoted"
