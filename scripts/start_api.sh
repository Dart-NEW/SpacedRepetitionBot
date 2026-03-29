#!/usr/bin/env bash

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${APP_DIR}/.run"
LOG_DIR="${APP_DIR}/logs"
PID_FILE="${RUN_DIR}/api.pid"
HOST="${SRB_UVICORN_HOST:-127.0.0.1}"
PORT="${SRB_UVICORN_PORT:-8000}"

mkdir -p "${RUN_DIR}" "${LOG_DIR}"

if [[ -f "${PID_FILE}" ]] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
    echo "API already running with pid $(cat "${PID_FILE}")"
    exit 0
fi

rm -f "${PID_FILE}"

cd "${APP_DIR}"
nohup "${APP_DIR}/.venv/bin/python" -m uvicorn spaced_repetition_bot.main:app \
    --host "${HOST}" \
    --port "${PORT}" \
    >> "${LOG_DIR}/api.log" 2>&1 &
echo $! > "${PID_FILE}"

sleep 2

if ! kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
    echo "API failed to start. Check ${LOG_DIR}/api.log"
    exit 1
fi

echo "API started with pid $(cat "${PID_FILE}") on ${HOST}:${PORT}"
