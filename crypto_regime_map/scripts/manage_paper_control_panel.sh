#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="${ROOT_DIR}/data/paper_control_panel.pid"
LOG_FILE="${ROOT_DIR}/data/paper_control_panel.log"
ERR_LOG_FILE="${ROOT_DIR}/data/paper_control_panel.err.log"
PLIST_FILE="${ROOT_DIR}/data/com.alpha.paper-control-panel.plist"
LAUNCH_LABEL="com.alpha.paper-control-panel"
LAUNCH_DOMAIN="${PAPER_PANEL_LAUNCH_DOMAIN:-gui/$(id -u)}"
SCREEN_NAME="${PAPER_PANEL_SCREEN_NAME:-paper_control_panel}"
HOST="${PAPER_PANEL_HOST:-127.0.0.1}"
PORT="${PAPER_PANEL_PORT:-8790}"
STATE_DIR="${PAPER_PANEL_STATE_DIR:-${ROOT_DIR}/data/paper_alpha_engine_v1_2}"
PYTHON_BIN="${PAPER_PANEL_PYTHON:-$(command -v python3)}"

is_running() {
  [[ -f "${PID_FILE}" ]] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null
}

use_launchctl() {
  [[ "$(uname -s)" == "Darwin" ]] && command -v launchctl >/dev/null 2>&1
}

use_screen() {
  command -v screen >/dev/null 2>&1
}

write_plist() {
  mkdir -p "${ROOT_DIR}/data"
  cat > "${PLIST_FILE}" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LAUNCH_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${PYTHON_BIN}</string>
    <string>${ROOT_DIR}/scripts/paper_control_panel.py</string>
    <string>--host</string>
    <string>${HOST}</string>
    <string>--port</string>
    <string>${PORT}</string>
    <string>--state-dir</string>
    <string>${STATE_DIR}</string>
    <string>--use-cache</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${ROOT_DIR}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${LOG_FILE}</string>
  <key>StandardErrorPath</key>
  <string>${ERR_LOG_FILE}</string>
</dict>
</plist>
PLIST
}

start_panel() {
  if is_running; then
    echo "paper_control_panel already running pid=$(cat "${PID_FILE}")"
    return
  fi
  mkdir -p "${ROOT_DIR}/data"
  if use_screen; then
    screen -S "${SCREEN_NAME}" -X quit >/dev/null 2>&1 || true
    screen -dmS "${SCREEN_NAME}" bash -lc "cd '${ROOT_DIR}' && exec '${PYTHON_BIN}' '${ROOT_DIR}/scripts/paper_control_panel.py' --host '${HOST}' --port '${PORT}' --state-dir '${STATE_DIR}' --use-cache > '${LOG_FILE}' 2> '${ERR_LOG_FILE}'"
    sleep 1
    status_panel
    return
  elif use_launchctl; then
    write_plist
    launchctl bootout "${LAUNCH_DOMAIN}" "${PLIST_FILE}" >/dev/null 2>&1 || true
    launchctl bootstrap "${LAUNCH_DOMAIN}" "${PLIST_FILE}"
    sleep 1
    status_panel
    return
  fi
  nohup python3 "${ROOT_DIR}/scripts/paper_control_panel.py" \
    --host "${HOST}" \
    --port "${PORT}" \
    --state-dir "${STATE_DIR}" \
    --use-cache \
    > "${LOG_FILE}" 2>&1 &
  echo $! > "${PID_FILE}"
  echo "paper_control_panel started pid=$(cat "${PID_FILE}") url=http://${HOST}:${PORT}"
}

stop_panel() {
  if use_screen; then
    screen -S "${SCREEN_NAME}" -X quit >/dev/null 2>&1 || true
  fi
  if use_launchctl; then
    launchctl bootout "${LAUNCH_DOMAIN}" "${PLIST_FILE}" >/dev/null 2>&1 || true
  fi
  if ! is_running; then
    echo "paper_control_panel is not running"
    return
  fi
  local pid
  pid="$(cat "${PID_FILE}")"
  kill "${pid}"
  echo "paper_control_panel stop requested pid=${pid}"
}

status_panel() {
  if is_running; then
    echo "paper_control_panel running pid=$(cat "${PID_FILE}") url=http://${HOST}:${PORT}"
  else
    echo "paper_control_panel stopped"
  fi
}

case "${1:-status}" in
  start)
    start_panel
    ;;
  stop)
    stop_panel
    ;;
  restart)
    stop_panel
    sleep 1
    start_panel
    ;;
  status)
    status_panel
    ;;
  *)
    echo "usage: $0 {start|stop|restart|status}" >&2
    exit 2
    ;;
esac
