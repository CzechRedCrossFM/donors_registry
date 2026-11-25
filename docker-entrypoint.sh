#!/bin/sh
set -eu
# Backups and administrative commands do not need rendering assets.
if [ -n "${ASSET_CONTAINER_URL:-}" ] && [ "$1" = gunicorn ]; then
    python -m registry.assets
fi
exec "$@"
