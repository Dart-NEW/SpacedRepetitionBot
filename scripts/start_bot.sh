#!/usr/bin/env bash

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${APP_DIR}/.run"
LOG_DIR="${APP_DIR}/logs"
PID_FILE="${RUN_DIR}/bot.pid"

resolve_python() {
    if [[ -x "${APP_DIR}/.venv/bin/python" ]]; then
        printf '%s\n' "${APP_DIR}/.venv/bin/python"
        return 0
    fi

    printf '%s\n' "python3"
}

mkdir -p "${RUN_DIR}" "${LOG_DIR}"

if [[ -f "${PID_FILE}" ]] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
    echo "Bot already running with pid $(cat "${PID_FILE}")"
    exit 0
fi

rm -f "${PID_FILE}"

cd "${APP_DIR}"
nohup "$(resolve_python)" -m spaced_repetition_bot.run_telegram_bot \
    >> "${LOG_DIR}/bot.log" 2>&1 &
echo $! > "${PID_FILE}"

sleep 2

if ! kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
    echo "Bot failed to start. Check ${LOG_DIR}/bot.log"
    exit 1
fi

echo "Bot started with pid $(cat "${PID_FILE}")"
