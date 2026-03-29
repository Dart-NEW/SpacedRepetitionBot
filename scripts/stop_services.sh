#!/usr/bin/env bash

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${APP_DIR}/.run"

stop_pid_file() {
    local name="$1"
    local pid_file="$2"
    local pid

    if [[ ! -f "${pid_file}" ]]; then
        echo "${name}: not running"
        return 0
    fi

    pid="$(cat "${pid_file}")"
    if ! kill -0 "${pid}" 2>/dev/null; then
        rm -f "${pid_file}"
        echo "${name}: stale pid file removed"
        return 0
    fi

    kill "${pid}"
    for _ in $(seq 1 15); do
        if ! kill -0 "${pid}" 2>/dev/null; then
            rm -f "${pid_file}"
            echo "${name}: stopped"
            return 0
        fi
        sleep 1
    done

    kill -9 "${pid}" 2>/dev/null || true
    rm -f "${pid_file}"
    echo "${name}: stopped with SIGKILL"
}

stop_pid_file "bot" "${RUN_DIR}/bot.pid"
stop_pid_file "api" "${RUN_DIR}/api.pid"
