#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
M3_USER="${M3_USER:-myno}"
M3_HOST="${M3_HOST:-myno-macbookpro}"
M3_DEST="${M3_DEST:-/Users/myno/agi-lab/runtime/xeon-shadow}"
M3_SSH_KEY="${M3_SSH_KEY:-${HOME}/.ssh/agi_xeon_to_m3}"

REMOTE="${M3_USER}@${M3_HOST}"
SSH_OPTS=(-o StrictHostKeyChecking=accept-new)
RSYNC_RSH="ssh -o StrictHostKeyChecking=accept-new"

if [[ -f "${M3_SSH_KEY}" ]]; then
  SSH_OPTS=(-i "${M3_SSH_KEY}" -o IdentitiesOnly=yes "${SSH_OPTS[@]}")
  RSYNC_RSH="ssh -i $(printf '%q' "${M3_SSH_KEY}") -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
fi

REPORT_MD="${ROOT_DIR}/reports/research/v0_futures_shadow_daily_report.md"
REPORT_JSON="${ROOT_DIR}/reports/research/v0_futures_shadow_daily_report.json"

if [[ ! -f "${REPORT_MD}" ]]; then
  echo "missing report: ${REPORT_MD}" >&2
  exit 1
fi

remote_dest_quoted="$(printf '%q' "${M3_DEST}")"

ssh "${SSH_OPTS[@]}" "${REMOTE}" "mkdir -p ${remote_dest_quoted}"
rsync -av -e "${RSYNC_RSH}" -- "${REPORT_MD}" "${REMOTE}:${M3_DEST}/"

if [[ -f "${REPORT_JSON}" ]]; then
  rsync -av -e "${RSYNC_RSH}" -- "${REPORT_JSON}" "${REMOTE}:${M3_DEST}/"
fi

ssh "${SSH_OPTS[@]}" "${REMOTE}" "cd ${remote_dest_quoted} && ls -l v0_futures_shadow_daily_report.md v0_futures_shadow_daily_report.json 2>/dev/null || ls -l v0_futures_shadow_daily_report.md"
