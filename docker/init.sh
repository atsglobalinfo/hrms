#!bin/bash
set -euo pipefail

SITE_NAME="${SITE_NAME:-hrms.localhost}"
HRMS_APP_SOURCE="${HRMS_APP_SOURCE:-hrms}"
HRMS_APP_BRANCH="${HRMS_APP_BRANCH:-}"
: "${MARIADB_ROOT_PASSWORD:?MARIADB_ROOT_PASSWORD must be set (see .env)}"
: "${ADMIN_PASSWORD:?ADMIN_PASSWORD must be set (see .env)}"
DEVELOPER_MODE="${DEVELOPER_MODE:-0}"

if [ -d "/home/frappe/frappe-bench/apps/frappe" ]; then
    echo "Bench already exists, skipping init"
    cd frappe-bench
    bench start
else
    echo "Creating new bench..."
fi

export PATH="${NVM_DIR}/versions/node/v${NODE_VERSION_DEVELOP}/bin/:${PATH}"

bench init --skip-redis-config-generation frappe-bench

cd frappe-bench

# Use containers instead of localhost
bench set-mariadb-host mariadb
bench set-redis-cache-host redis://redis:6379
bench set-redis-queue-host redis://redis:6379
bench set-redis-socketio-host redis://redis:6379

# Remove redis, watch from Procfile
sed -i '/redis/d' ./Procfile
sed -i '/watch/d' ./Procfile

bench get-app erpnext
if [ -n "$HRMS_APP_BRANCH" ]; then
    bench get-app "$HRMS_APP_SOURCE" --branch "$HRMS_APP_BRANCH"
else
    bench get-app "$HRMS_APP_SOURCE"
fi

bench new-site "$SITE_NAME" \
--force \
--mariadb-root-password "$MARIADB_ROOT_PASSWORD" \
--admin-password "$ADMIN_PASSWORD" \
--no-mariadb-socket

bench --site "$SITE_NAME" install-app hrms
bench --site "$SITE_NAME" set-config developer_mode "$DEVELOPER_MODE"
bench --site "$SITE_NAME" enable-scheduler
bench --site "$SITE_NAME" clear-cache
bench use "$SITE_NAME"

bench start