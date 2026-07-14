#!/bin/sh
set -eu

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed. Install Docker Desktop, then run this script again." >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running. Start Docker Desktop, then run this script again." >&2
  exit 1
fi

docker compose up --build --detach --wait --wait-timeout "${DOCKER_WAIT_TIMEOUT:-900}"

echo "DrayEasy Market Radar is ready: http://localhost:${APP_PORT:-3000}"
echo "Stop it with: docker compose down"
