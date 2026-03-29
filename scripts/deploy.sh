#!/usr/bin/env bash

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE="${SRB_DEPLOY_REMOTE:-origin}"
BRANCH="${SRB_DEPLOY_BRANCH:-main}"
BACKUP_DIR="${APP_DIR}/backups"
DEFAULT_API_PREFIX="/api/v1"
DEFAULT_SQLITE_URL="sqlite:///./spaced_repetition_bot.db"
DEFAULT_PORT="8000"
GET_PIP_URL="https://bootstrap.pypa.io/get-pip.py"

read_env_value() {
    local key="$1"
    local default_value="${2:-}"
    local env_file="${APP_DIR}/.env"

    if [[ -f "${env_file}" ]]; then
        local line
        line="$(grep -E "^${key}=" "${env_file}" | tail -n 1 || true)"
        if [[ -n "${line}" ]]; then
            printf '%s\n' "${line#*=}"
            return 0
        fi
    fi

    printf '%s\n' "${default_value}"
}

sqlite_path_from_url() {
    local db_url="$1"

    if [[ "${db_url}" == sqlite:////* ]]; then
        printf '/%s\n' "${db_url#sqlite:////}"
        return 0
    fi

    if [[ "${db_url}" == sqlite:///./* ]]; then
        printf '%s/%s\n' "${APP_DIR}" "${db_url#sqlite:///./}"
        return 0
    fi

    if [[ "${db_url}" == sqlite:///* ]]; then
        printf '%s/%s\n' "${APP_DIR}" "${db_url#sqlite:///}"
        return 0
    fi

    return 1
}

backup_sqlite_database() {
    local db_url
    local db_path
    local stamp

    db_url="$(read_env_value "SRB_DATABASE_URL" "${DEFAULT_SQLITE_URL}")"
    if ! db_path="$(sqlite_path_from_url "${db_url}")"; then
        echo "Skipping backup for non-SQLite database URL"
        return 0
    fi

    if [[ ! -f "${db_path}" ]]; then
        echo "SQLite database not found at ${db_path}; skipping backup"
        return 0
    fi

    mkdir -p "${BACKUP_DIR}"
    stamp="$(date '+%Y%m%d_%H%M%S')"
    cp "${db_path}" "${BACKUP_DIR}/spaced_repetition_bot_${stamp}.db"
    echo "SQLite backup saved to ${BACKUP_DIR}/spaced_repetition_bot_${stamp}.db"
}

wait_for_api() {
    local api_prefix
    local port
    local health_url

    api_prefix="$(read_env_value "SRB_API_PREFIX" "${DEFAULT_API_PREFIX}")"
    port="${SRB_UVICORN_PORT:-${DEFAULT_PORT}}"
    health_url="http://127.0.0.1:${port}${api_prefix}/health"

    for _ in $(seq 1 30); do
        if curl -fsS "${health_url}" >/dev/null 2>&1; then
            echo "API is healthy at ${health_url}"
            return 0
        fi
        sleep 1
    done

    echo "API did not become healthy: ${health_url}"
    return 1
}

bootstrap_user_pip() {
    if python3 -m pip --version >/dev/null 2>&1; then
        return 0
    fi

    local get_pip_script
    get_pip_script="$(mktemp)"
    curl -fsSL "${GET_PIP_URL}" -o "${get_pip_script}"
    python3 "${get_pip_script}" --user
    rm -f "${get_pip_script}"
}

install_runtime() {
    if [[ -x "${APP_DIR}/.venv/bin/python" ]]; then
        "${APP_DIR}/.venv/bin/python" -m pip install --upgrade pip
        "${APP_DIR}/.venv/bin/python" -m pip install .
        return 0
    fi

    bootstrap_user_pip
    python3 -m pip install --user --upgrade pip
    python3 -m pip install --user .
}

cd "${APP_DIR}"

if [[ ! -f "${APP_DIR}/.env" ]]; then
    echo "Missing ${APP_DIR}/.env"
    exit 1
fi

bash "${APP_DIR}/scripts/stop_services.sh" || true
backup_sqlite_database

git fetch "${REMOTE}" "${BRANCH}"
git checkout "${BRANCH}"
git pull --ff-only "${REMOTE}" "${BRANCH}"

install_runtime

bash "${APP_DIR}/scripts/start_api.sh"
wait_for_api
bash "${APP_DIR}/scripts/start_bot.sh"
bash "${APP_DIR}/scripts/status_services.sh"
