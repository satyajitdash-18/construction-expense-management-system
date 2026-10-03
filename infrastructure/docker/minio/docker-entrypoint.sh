#!/bin/sh
set -e

# If root credentials are provided, pre-configure the local mc alias synchronously
USER="${MINIO_ROOT_USER:-${MINIO_ACCESS_KEY:-}}"
PASS="${MINIO_ROOT_PASSWORD:-${MINIO_SECRET_KEY:-}}"
if [ -n "$USER" ] && [ -n "$PASS" ]; then
    mc alias set local http://localhost:9000 "$USER" "$PASS" --api s3v4 >/dev/null 2>&1 || true
fi

case "${1}" in
    minio|mc|curl|sh|bash|/*)
        exec "$@"
        ;;
    *)
        exec minio "$@"
        ;;
esac
