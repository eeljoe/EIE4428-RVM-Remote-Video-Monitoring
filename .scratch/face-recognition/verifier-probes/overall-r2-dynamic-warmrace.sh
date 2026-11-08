#!/usr/bin/env bash
# overall-r2-dynamic warmup race: POST /api/faces/known against a just-started
# server to catch the real 503 models-loading window, then keep polling until
# the first non-503 answer. Usage: bash overall-r2-dynamic-warmrace.sh PORT
PORT="${1:-8171}"
for i in $(seq 1 14); do
  T=$(date +%s.%N)
  R=$(curl -s -m 5 -o /tmp/r2warm_out.json -w "%{http_code}" -X POST \
      -H "Content-Type: application/json" -d '{"name":"Early Bird"}' \
      "http://127.0.0.1:${PORT}/api/faces/known")
  echo "$T HTTP:$R $(cat /tmp/r2warm_out.json 2>/dev/null)"
  [ "$R" != "503" ] && [ "$R" != "000" ] && break
  sleep 0.5
done
