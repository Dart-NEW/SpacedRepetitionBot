#!/usr/bin/env bash

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${APP_DIR}/.run"

print_status() {
    local name="$1"
    local pid_file="$2"

    if [[ ! -f "${pid_file}" ]]; then
        echo "${name}: stopped"
        return 0
    fi

    if kill -0 "$(cat "${pid_file}")" 2>/dev/null; then
        echo "${name}: running with pid $(cat "${pid_file}")"
        return 0
    fi

    echo "${name}: stale pid file ($(cat "${pid_file}"))"
}

print_status "api" "${RUN_DIR}/api.pid"
print_status "bot" "${RUN_DIR}/bot.pid"
