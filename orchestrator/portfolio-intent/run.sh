#!/usr/bin/env bash
set -e
export PYTHONUNBUFFERED=1
export PORT=${PORT:-8080}
uvicorn app:app --host 0.0.0.0 --port $PORT --reload
