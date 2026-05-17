#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/restart_freecad_routerking.sh [--file /path/to/file.FCStd] [--force] [--no-quit] [--no-panel] [--wait seconds]

Restarts FreeCAD on macOS, reopens the last/selected FreeCAD document, activates
the RouterKing workbench, and opens the RouterKing panel.

Document resolution order:
  1. --file PATH
  2. RouterKing restart state (~/.local/state/routerking/last_fcstd)
  3. FreeCAD RecentFiles MRU0 from ~/Library/Preferences/FreeCAD/user.cfg

Environment overrides:
  FREECAD_APP=/Applications/FreeCAD.app
  ROUTERKING_STATE_DIR=~/.local/state/routerking
USAGE
}

freecad_app="/Applications/FreeCAD.app"
state_dir="${ROUTERKING_STATE_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/routerking}"
wait_seconds=20
selected_file=""
force_quit=0
quit_first=1
open_panel=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --file)
      [[ $# -ge 2 ]] || { echo "--file requires a path" >&2; exit 2; }
      selected_file="$2"
      shift 2
      ;;
    --app)
      [[ $# -ge 2 ]] || { echo "--app requires a path" >&2; exit 2; }
      freecad_app="$2"
      shift 2
      ;;
    --force)
      force_quit=1
      shift
      ;;
    --no-quit)
      quit_first=0
      shift
      ;;
    --no-panel)
      open_panel=0
      shift
      ;;
    --wait)
      [[ $# -ge 2 ]] || { echo "--wait requires seconds" >&2; exit 2; }
      wait_seconds="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -n "${FREECAD_APP:-}" ]]; then
  freecad_app="$FREECAD_APP"
fi

mkdir -p "$state_dir"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd "$script_dir/.." && pwd)"
last_file_path="$state_dir/last_fcstd"
autoshow_marker="$state_dir/autoshow_panel"
launch_log="$state_dir/freecad-restart.log"

freecad_bin="$freecad_app/Contents/MacOS/FreeCAD"
if [[ ! -d "$freecad_app" && ! -x "$freecad_bin" ]]; then
  echo "FreeCAD.app not found. Set FREECAD_APP or pass --app." >&2
  exit 1
fi

decode_xml_text() {
  /usr/bin/python3 -c 'import html,sys; print(html.unescape(sys.stdin.read()).strip())'
}

recent_freecad_file() {
  local cfg="$HOME/Library/Preferences/FreeCAD/user.cfg"
  [[ -f "$cfg" ]] || return 1
  local value
  value="$(
    sed -n 's/.*<FCText Name="MRU[0-9][0-9]*">\([^<]*\.FCStd\)<\/FCText>.*/\1/p' "$cfg" |
      head -1 |
      decode_xml_text
  )"
  [[ -n "$value" && -f "$value" ]] || return 1
  printf '%s\n' "$value"
}

if [[ -n "$selected_file" ]]; then
  selected_file="${selected_file/#\~/$HOME}"
  if [[ ! -f "$selected_file" ]]; then
    echo "Selected FreeCAD file does not exist: $selected_file" >&2
    exit 1
  fi
  selected_file="$(cd "$(dirname "$selected_file")" && pwd)/$(basename "$selected_file")"
elif [[ -f "$last_file_path" && -f "$(cat "$last_file_path")" ]]; then
  selected_file="$(cat "$last_file_path")"
else
  selected_file="$(recent_freecad_file || true)"
fi

if [[ -n "$selected_file" ]]; then
  printf '%s\n' "$selected_file" > "$last_file_path"
fi

if [[ "$open_panel" -eq 1 ]]; then
  printf '%s\n' "${selected_file:-}" > "$autoshow_marker"
else
  rm -f "$autoshow_marker"
fi

is_freecad_running() {
  pgrep -x FreeCAD >/dev/null 2>&1 || pgrep -x freecad >/dev/null 2>&1
}

if [[ "$quit_first" -eq 1 ]] && is_freecad_running; then
  /usr/bin/osascript -e 'tell application id "org.freecad.FreeCAD" to quit' >/dev/null 2>&1 || true
  deadline=$((SECONDS + wait_seconds))
  while is_freecad_running && [[ "$SECONDS" -lt "$deadline" ]]; do
    sleep 0.5
  done
  if is_freecad_running; then
    if [[ "$force_quit" -eq 1 ]]; then
      pkill -x FreeCAD >/dev/null 2>&1 || true
      pkill -x freecad >/dev/null 2>&1 || true
      sleep 1
    else
      echo "FreeCAD is still running, probably waiting for unsaved changes. Re-run with --force only if that is intended." >&2
      exit 1
    fi
  fi
fi

launch_freecad() {
  : > "$launch_log"
  if [[ -d "$freecad_app" ]]; then
    if [[ $# -gt 0 ]]; then
      /usr/bin/open -na "$freecad_app" --args "$@" >>"$launch_log" 2>&1
    else
      /usr/bin/open -na "$freecad_app" >>"$launch_log" 2>&1
    fi
    return
  fi
  nohup "$freecad_bin" "$@" >>"$launch_log" 2>&1 &
}

wait_for_routerking_mcp() {
  local deadline=$((SECONDS + wait_seconds))
  while [[ "$SECONDS" -lt "$deadline" ]]; do
    if (
      cd "$repo_dir"
      ROUTERKING_MCP_MODE=socket \
        ROUTERKING_MCP_HOST="${ROUTERKING_MCP_HOST:-127.0.0.1}" \
        ROUTERKING_MCP_PORT="${ROUTERKING_MCP_PORT:-4400}" \
        python3 -m mcp.server.main --ping >/dev/null 2>&1
    ); then
      return 0
    fi
    sleep 1
  done
  return 1
}

routerking_tool_json() {
  local tool_name="$1"
  local payload
  if [[ $# -ge 2 ]]; then
    payload="$2"
  else
    payload="{}"
  fi
  (
    cd "$repo_dir"
    ROUTERKING_MCP_MODE=socket \
      ROUTERKING_MCP_HOST="${ROUTERKING_MCP_HOST:-127.0.0.1}" \
      ROUTERKING_MCP_PORT="${ROUTERKING_MCP_PORT:-4400}" \
      python3 -m mcp.server.main \
        --tool "$tool_name" \
        --payload "$payload"
  )
}

wait_for_selected_document() {
  [[ -n "$selected_file" ]] || return 0
  local deadline=$((SECONDS + wait_seconds))
  local state
  while [[ "$SECONDS" -lt "$deadline" ]]; do
    state="$(routerking_tool_json routerking_ui_state 2>/dev/null || true)"
    if [[ -n "$state" ]] && ROUTERKING_UI_STATE_JSON="$state" python3 - "$selected_file" <<'PY'
import json
import os
import sys

expected = os.path.realpath(sys.argv[1])
try:
    payload = json.loads(os.environ.get("ROUTERKING_UI_STATE_JSON", ""))
except Exception:
    raise SystemExit(1)

actual = ((payload.get("data") or {}).get("active_document_file") or "")
if actual and os.path.realpath(actual) == expected:
    raise SystemExit(0)
raise SystemExit(1)
PY
    then
      return 0
    fi
    sleep 1
  done
  return 1
}

try_open_routerking_panel_via_mcp() {
  routerking_tool_json routerking_open_panel >/dev/null
}

select_routerking_gcode_tab() {
  routerking_tool_json routerking_select_tab '{"tab":"G-Code"}' >/dev/null
}

routerking_panel_is_active() {
  local state
  state="$(routerking_tool_json routerking_ui_state 2>/dev/null || true)"
  [[ -n "$state" ]] || return 1
  ROUTERKING_UI_STATE_JSON="$state" python3 - <<'PY'
import json
import os
import sys

try:
    payload = json.loads(os.environ.get("ROUTERKING_UI_STATE_JSON", ""))
except Exception:
    raise SystemExit(1)

data = payload.get("data") or {}
tab_ok = any(
    tab.get("current_text") == "G-Code"
    for tab in data.get("routerking_tabs") or []
)
if data.get("active_workbench") == "RouterKingWorkbench" and data.get("routerking_dock_visible") and tab_ok:
    raise SystemExit(0)
raise SystemExit(1)
PY
}

wait_for_routerking_panel() {
  local deadline=$((SECONDS + wait_seconds))
  while [[ "$SECONDS" -lt "$deadline" ]]; do
    if try_open_routerking_panel_via_mcp; then
      select_routerking_gcode_tab || true
      sleep 1
      if routerking_panel_is_active; then
        return 0
      fi
    fi
    sleep 1
  done
  return 1
}

if [[ -n "$selected_file" ]]; then
  launch_freecad "$selected_file"
  echo "Restarted FreeCAD with: $selected_file"
else
  launch_freecad
  echo "Restarted FreeCAD without document; no previous FCStd file found."
fi
echo "RouterKing panel autoshow: $([[ "$open_panel" -eq 1 ]] && echo yes || echo no)"
if [[ "$open_panel" -eq 1 ]]; then
  if wait_for_routerking_mcp; then
    if wait_for_selected_document; then
      echo "FreeCAD document loaded and visible to RouterKing MCP."
    else
      echo "FreeCAD document did not report as loaded within ${wait_seconds}s; trying RouterKing panel anyway." >&2
    fi
    if wait_for_routerking_panel; then
      rm -f "$autoshow_marker"
      echo "RouterKing workbench/panel opened via MCP socket."
    else
      echo "RouterKing MCP socket responded, but opening the panel timed out. Marker fallback remains: $autoshow_marker" >&2
    fi
  else
    echo "RouterKing MCP socket did not become ready within ${wait_seconds}s. Marker fallback remains: $autoshow_marker" >&2
  fi
fi
echo "Launch log: $launch_log"
