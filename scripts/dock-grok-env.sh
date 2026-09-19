#!/bin/zsh
# Dock launcher env: Grok Bot Shell is non-login, TERM=dumb, NO_COLOR=1, and does not
# load ~/.env colon-keys. glm-53-flash (RONE) needs RDSEC_* from ~/.env + a real TERM.
# Usage: source this, then exec grok ...  OR  dock-grok-env.sh grok <args>

emulate -L zsh
unset NO_COLOR
export TERM=xterm-256color

ENV_FILE="${HOME}/.env"
if [[ -f "$ENV_FILE" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%$'\r'}"
    line="${line## }"
    [[ -z "$line" || "$line" == \#* ]] && continue
    line="${line#export }"
    if [[ "$line" =~ '^([A-Z_][A-Z0-9_]*)[[:space:]]*[:=][[:space:]]*(.*)$' ]]; then
      key="${match[1]}"
      val="${match[2]}"
      val="${val%\"}"; val="${val#\"}"
      val="${val%\'}"; val="${val#\'}"
      if [[ -z "${(P)key}" ]]; then
        export "$key=$val"
      fi
    fi
  done < "$ENV_FILE"
fi

if [[ $# -gt 0 ]]; then
  exec "$@"
fi
