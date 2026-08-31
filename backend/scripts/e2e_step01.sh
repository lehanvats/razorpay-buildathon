#!/usr/bin/env bash
# End-to-end check for step-01 — webhook ingress.
#
# Not a unit test. This runs uvicorn against a real Postgres and posts real
# HTTP, so it exercises the app factory, the session dependency, the applied
# migration, the route and the signature verifier together. `pytest` covers
# the same logic in-process; this catches the wiring pytest cannot.
#
# Usage:
#   docker run -d --name recoup-pg -e POSTGRES_PASSWORD=recoup \
#     -e POSTGRES_USER=recoup -e POSTGRES_DB=recoup -p 55432:5432 postgres:16-alpine
#   .venv/bin/alembic upgrade head
#   ./scripts/e2e_step01.sh
#
# Reads DATABASE_URL / RAZORPAY_WEBHOOK_SECRET from backend/.env by default.
set -u

BACKEND="$(cd "$(dirname "$0")/.." && pwd)"
cd "$BACKEND" || exit 1

PG_CONTAINER="${PG_CONTAINER:-recoup-pg}"
PG_USER="${PG_USER:-recoup}"
PG_DB="${PG_DB:-recoup}"
SECRET="${RAZORPAY_WEBHOOK_SECRET:-$(grep -E '^RAZORPAY_WEBHOOK_SECRET=' .env | cut -d= -f2-)}"
PORT="${PORT:-8123}"
URL="http://127.0.0.1:${PORT}/api/webhooks/razorpay"

TMP="$(mktemp -d)"
FAILURES=0
trap 'rm -rf "$TMP"' EXIT

psql_q() { docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -tAc "$1"; }
count() { psql_q "SELECT count(*) FROM webhook_events;"; }
check() {
  if [ "$2" = "$3" ]; then
    echo "  PASS  $1 ($3)"
  else
    echo "  FAIL  $1: expected $2, got $3"
    FAILURES=$((FAILURES + 1))
  fi
}

# Non-canonical JSON on purpose: whitespace that `json.dumps` would not
# reproduce. An implementation that verifies against a re-serialised dict
# fails here, which is exactly what this body is for.
printf '%s' '{"event": "payment.failed",   "account_id": "acc_E2E", "payload": {"payment": {"entity": {"id": "pay_E2E01", "order_id": "order_E2E01", "amount": 149900, "currency": "INR", "method": "upi", "error_reason": "insufficient_funds"}}}, "created_at": 1756684800}' > "$TMP/body.json"
SIG=$(openssl dgst -sha256 -hmac "$SECRET" < "$TMP/body.json" | awk '{print $NF}')

echo "== reset webhook_events =="
psql_q "TRUNCATE webhook_events;" > /dev/null

echo "== start uvicorn on :${PORT} =="
.venv/bin/uvicorn app.main:app --port "$PORT" --log-level warning > "$TMP/uvicorn.log" 2>&1 &
UVPID=$!
trap 'kill $UVPID 2>/dev/null; rm -rf "$TMP"' EXIT

for _ in $(seq 1 40); do
  curl -fsS "http://127.0.0.1:${PORT}/health" > /dev/null 2>&1 && break
  sleep 0.25
done
check "health endpoint" '{"status":"ok"}' "$(curl -fsS "http://127.0.0.1:${PORT}/health" 2>/dev/null)"

post() { # signature event-id -> writes $TMP/resp.json, echoes status code
  curl -s -o "$TMP/resp.json" -w '%{http_code}' -X POST "$URL" \
    -H "X-Razorpay-Signature: $1" -H "X-Razorpay-Event-Id: $2" \
    -H 'Content-Type: application/json' --data-binary "@$TMP/body.json"
}
body_status() { python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("status"))' "$TMP/resp.json"; }

echo "== 1. correctly signed payment.failed =="
check "status code" 200 "$(post "$SIG" evt_E2E01)"
check "response status" accepted "$(body_status)"
check "row count" 1 "$(count)"

echo "== 2. same event id redelivered =="
check "status code" 200 "$(post "$SIG" evt_E2E01)"
check "response status" duplicate "$(body_status)"
check "row count still 1" 1 "$(count)"

echo "== 3. corrupted signature =="
check "status code" 400 "$(post "$(printf '0%.0s' $(seq 64))" evt_E2E02)"
check "no row written" 1 "$(count)"

echo "== 4. stored payload is verbatim and unprocessed =="
check "event_type" payment.failed "$(psql_q "SELECT event_type FROM webhook_events;")"
check "processed_at null" t "$(psql_q "SELECT processed_at IS NULL FROM webhook_events;")"
check "payload amount preserved" 149900 \
  "$(psql_q "SELECT payload_json->'payload'->'payment'->'entity'->>'amount' FROM webhook_events;")"

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "E2E RESULT: all checks passed"
else
  echo "E2E RESULT: $FAILURES check(s) failed"
fi
exit "$FAILURES"
