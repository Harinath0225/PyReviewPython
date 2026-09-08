#!/usr/bin/env bash
set -euo pipefail

echo "Building images and starting services with Docker Compose..."

# Recommended usage in Cloud Shell or any environment with Docker
docker compose build --parallel
docker compose up -d

echo
echo "Services should be running:"
echo "- Backend: http://localhost:8000"
echo "- Frontend: http://localhost:4200"

echo "To view logs: docker compose logs -f"
