#!/usr/bin/env bash
# Run the whole Vicoa stack from a checkout and publish it at ONE public URL,
# so a branch can be reviewed from another machine or from the Vicoa app.
#
#   stack-preview.sh up [--env-file FILE] [--allow-signup] [--provider cloudflare|ngrok]
#   stack-preview.sh status
#   stack-preview.sh env                  # shell exports for seed scripts and curl
#   stack-preview.sh token owner|viewer   # bearer token for a seeded account
#   stack-preview.sh seed FILE            # run a seed script (.py or shell) against the preview
#   stack-preview.sh run NAME -- CMD...   # start a side process (webhook forwarder, ...) that `down` stops
#   stack-preview.sh restart [backend|server|web]...  # pick up code changes; the public URL stays
#   stack-preview.sh down [--purge]       # --purge also deletes the database and the state dir
#
#   --repo DIR   checkout to preview (default: the git checkout of the current directory)
#
#   Postgres (Docker) -> backend + server (uvicorn) -> web (next dev)
#     -> proxy.mjs (one origin) -> cloudflared or ngrok (one public URL)
#
# Every process binds 127.0.0.1; only the tunnel is public. Python processes run
# with an empty environment from an empty directory, so no checkout `.env`
# (which may hold real credentials) is ever loaded.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
STATE_ROOT=${VICOA_PREVIEW_STATE_ROOT:-/tmp/vicoa-stack-preview}
PG_IMAGE=postgres:16-alpine
SERVICES="tunnel proxy server backend web"
BASE_PATH=/usr/bin:/bin:/usr/sbin:/sbin
OWNER_EMAIL=ada@example.com
VIEWER_EMAIL=bea@example.com

UP_IN_PROGRESS=0

log() { echo "stack-preview: $*" >&2; }

die() {
  echo "stack-preview: error: $*" >&2
  if [ "$UP_IN_PROGRESS" = 1 ]; then
    UP_IN_PROGRESS=0
    log "stopping what this run started (logs stay in $STATE)"
    stop_all
  fi
  exit 1
}

# A failed `up` must not leave half a stack behind.
set -E
trap '[ "$UP_IN_PROGRESS" != 1 ] || die "command failed at line $LINENO"' ERR

usage() {
  sed -n '2,13p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

# --- arguments ---------------------------------------------------------------

CMD=${1:-}
[ $# -gt 0 ] && shift
REPO="" ENV_FILE="" ALLOW_SIGNUP=0 PROVIDER="" PURGE=0
ARGS=()
while [ $# -gt 0 ]; do
  case $1 in
    --repo) REPO=${2:?--repo needs a directory}; shift 2 ;;
    --env-file) ENV_FILE=${2:?--env-file needs a file}; shift 2 ;;
    --allow-signup) ALLOW_SIGNUP=1; shift ;;
    --provider) PROVIDER=${2:?--provider needs cloudflare or ngrok}; shift 2 ;;
    --purge) PURGE=1; shift ;;
    -h | --help) usage ;;
    --) shift; ARGS+=("$@"); break ;;
    *) ARGS+=("$1"); shift ;;
  esac
done
case $CMD in up | status | env | token | seed | run | restart | down) ;; -h | --help | help) usage ;; *) usage 2 ;; esac
case $PROVIDER in "" | cloudflare | ngrok) ;; *) die "unknown --provider $PROVIDER (cloudflare or ngrok)" ;; esac

if [ -z "$REPO" ]; then
  REPO=$(git rev-parse --show-toplevel 2>/dev/null) || die "not inside a git checkout; pass --repo"
fi
REPO=$(cd "$REPO" && pwd -P)
[ -f "$REPO/backend/src/backend/main.py" ] && [ -f "$REPO/apps/web/package.json" ] ||
  die "$REPO is not a Vicoa checkout (expected backend/src/backend/main.py and apps/web)"

SLUG=$(printf '%s-%s' "$(basename "$(dirname "$REPO")")" "$(basename "$REPO")" |
  tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9-' '-')
STATE="$STATE_ROOT/$SLUG"
PG_CONTAINER="vicoa-preview-$SLUG"
PY=${VICOA_PREVIEW_PYTHON:-$REPO/backend/.venv/bin/python}

# --- process helpers ---------------------------------------------------------

port_open() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

# launch NAME DIR CMD... — background CMD in its own process group, log to
# DIR/NAME.log, record its pid and start time (the start time guards `down`
# against a recycled pid).
launch() {
  local name=$1 dir=$2 pid
  shift 2
  set -m
  nohup "$@" >"$dir/$name.log" 2>&1 </dev/null &
  pid=$!
  disown "$pid" 2>/dev/null || true
  set +m
  echo "$pid" >"$dir/$name.pid"
  ps -p "$pid" -o lstart= >"$dir/$name.start" 2>/dev/null || true
}

alive() { # NAME [DIR]
  local f="${2:-$STATE}/$1.pid"
  [ -f "$f" ] && kill -0 "$(cat "$f")" 2>/dev/null
}

pid_of() { cat "${2:-$STATE}/$1.pid" 2>/dev/null || echo null; }

stop() { # NAME [DIR]
  local name=$1 dir=${2:-$STATE} pid started
  [ -f "$dir/$name.pid" ] || return 0
  pid=$(cat "$dir/$name.pid")
  if kill -0 "$pid" 2>/dev/null; then
    started=$(ps -p "$pid" -o lstart= 2>/dev/null || true)
    if [ -f "$dir/$name.start" ] && [ "$started" != "$(cat "$dir/$name.start")" ]; then
      log "$name: pid $pid now belongs to another process, leaving it alone"
    else
      kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
      for _ in $(seq 1 20); do
        kill -0 -- "-$pid" 2>/dev/null || kill -0 "$pid" 2>/dev/null || break
        sleep 0.5
      done
      kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
    fi
  fi
  rm -f "$dir/$name.pid" "$dir/$name.start"
}

stop_all() {
  local f svc
  for f in "$STATE"/extra/*.pid; do
    [ -e "$f" ] && stop "$(basename "$f" .pid)" "$STATE/extra"
  done
  for svc in web backend server proxy tunnel; do stop "$svc"; done
  if command -v docker >/dev/null 2>&1 && docker container inspect "$PG_CONTAINER" >/dev/null 2>&1; then
    docker stop "$PG_CONTAINER" >/dev/null 2>&1 || true
  fi
}

any_alive() {
  local svc
  for svc in $SERVICES; do alive "$svc" && return 0; done
  return 1
}

# wait_http NAME URL SECONDS — until URL answers below 500 (or NAME dies).
wait_http() {
  local name=$1 url=$2 timeout=$3 code
  for _ in $(seq 1 "$timeout"); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$url" 2>/dev/null || true)
    if [ -n "$code" ] && [ "$code" != 000 ] && [ "$code" -lt 500 ]; then return 0; fi
    if ! alive "$name"; then
      tail -n 25 "$STATE/$name.log" >&2 || true
      die "$name exited during startup (log: $STATE/$name.log)"
    fi
    sleep 1
  done
  tail -n 25 "$STATE/$name.log" >&2 || true
  die "$name did not answer at $url within ${timeout}s (log: $STATE/$name.log)"
}

load_state() {
  [ -f "$STATE/ports" ] || die "no preview state for $REPO (run: stack-preview.sh up)"
  # shellcheck disable=SC1091
  . "$STATE/ports"
  # shellcheck disable=SC1091
  [ -f "$STATE/public" ] && . "$STATE/public"
  # shellcheck disable=SC1091
  [ -f "$STATE/accounts" ] && . "$STATE/accounts"
  DATABASE_URL="postgresql://vicoa:vicoa@127.0.0.1:$PG_PORT/vicoa"
  PUBLIC_URL=${PUBLIC_URL:-}
}

json_field() { # FIELD — read JSON on stdin, print one top-level field
  "$PY" -c 'import json, sys; print(json.load(sys.stdin).get(sys.argv[1], ""))' "$1"
}

backend_auth() { # sign-in|sign-up EMAIL PASSWORD [DISPLAY_NAME] -> prints "<code> <body>"
  local body
  body=$("$PY" -c 'import json, sys; d = {"email": sys.argv[1], "password": sys.argv[2]}
if len(sys.argv) > 3: d["display_name"] = sys.argv[3]
print(json.dumps(d))' "${@:2}")
  curl -s -w '\n%{http_code}' -X POST "http://127.0.0.1:$BACKEND_PORT/api/v1/auth/builtin/$1" \
    -H 'content-type: application/json' -d "$body"
}

token_for() { # owner|viewer
  local email password out
  case $1 in
    owner) email=$OWNER_EMAIL password=${OWNER_PASSWORD:-} ;;
    viewer) email=$VIEWER_EMAIL password=${VIEWER_PASSWORD:-} ;;
    *) die "token: expected owner or viewer" ;;
  esac
  [ -n "$password" ] || die "no seeded accounts recorded in $STATE/accounts"
  out=$(backend_auth sign-in "$email" "$password")
  [ "${out##*$'\n'}" = 200 ] || die "sign-in as $email failed (HTTP ${out##*$'\n'})"
  printf '%s' "${out%$'\n'*}" | json_field access_token
}

# VAR=value pairs describing the running preview, for seeds and side processes.
preview_vars() {
  printf '%s\n' \
    "PREVIEW_REPO=$REPO" \
    "PREVIEW_STATE=$STATE" \
    "PREVIEW_URL=$PUBLIC_URL" \
    "PREVIEW_BACKEND=http://127.0.0.1:$BACKEND_PORT" \
    "PREVIEW_SERVER=http://127.0.0.1:$SERVER_PORT" \
    "PREVIEW_BACKEND_PORT=$BACKEND_PORT" \
    "PREVIEW_SERVER_PORT=$SERVER_PORT" \
    "PREVIEW_WEB_PORT=$WEB_PORT" \
    "PREVIEW_PYTHON=$PY" \
    "PYTHONPATH=$REPO/backend/src" \
    "DATABASE_URL=$DATABASE_URL" \
    "OWNER_EMAIL=$OWNER_EMAIL" \
    "OWNER_PASSWORD=${OWNER_PASSWORD:-}" \
    "VIEWER_EMAIL=$VIEWER_EMAIL" \
    "VIEWER_PASSWORD=${VIEWER_PASSWORD:-}"
}

# --- up ----------------------------------------------------------------------

alloc_ports() {
  local hash base p busy
  hash=$(printf '%s' "$REPO" | cksum | cut -d' ' -f1)
  base=$((20000 + (hash % 900) * 10))
  for _ in $(seq 1 30); do
    busy=0
    for p in $((base + 1)) $((base + 2)) $((base + 3)) $((base + 4)); do
      if port_open "$p"; then busy=1; fi
    done
    # The Postgres port only has to be free when the container is created.
    if [ "$busy" = 0 ] && { [ "$PG_EXISTS" = 1 ] || ! port_open "$base"; }; then
      PG_PORT=$base BACKEND_PORT=$((base + 1)) SERVER_PORT=$((base + 2))
      WEB_PORT=$((base + 3)) PROXY_PORT=$((base + 4))
      return 0
    fi
    base=$((base + 10))
    [ "$base" -gt 29990 ] && base=20000
  done
  die "could not find five free ports in 20000-29999"
}

preflight() {
  local cmd
  for cmd in docker node curl openssl git; do
    command -v "$cmd" >/dev/null 2>&1 || die "$cmd is required"
  done
  docker info >/dev/null 2>&1 || die "Docker is not running"
  [ -x "$PY" ] || die "no backend venv at $PY (run backend/scripts/dev-setup.sh, or set VICOA_PREVIEW_PYTHON)"
  "$PY" -c 'import alembic, fastapi, psycopg2, sqlalchemy, uvicorn' 2>/dev/null ||
    die "$PY is missing backend dependencies (run backend/scripts/dev-setup.sh)"
  # Settings reads `.env` from the working directory, and alembic has to run
  # from backend/src/shared.
  [ ! -e "$REPO/backend/src/shared/.env" ] ||
    die "$REPO/backend/src/shared/.env exists; alembic would load it. Move it aside first."
  if [ -n "$ENV_FILE" ]; then
    [ -f "$ENV_FILE" ] || die "--env-file $ENV_FILE does not exist"
    ENV_FILE=$(cd "$(dirname "$ENV_FILE")" && pwd -P)/$(basename "$ENV_FILE")
  fi
}

other_next_dev() { # pids of next dev servers already serving this checkout's apps/web
  local pid cwd
  for pid in $(pgrep -f 'next dev|next-server|next/dist/bin/next' 2>/dev/null || true); do
    if [ -e "/proc/$pid/cwd" ]; then
      cwd=$(readlink "/proc/$pid/cwd" 2>/dev/null || true)
    else
      cwd=$(lsof -a -d cwd -p "$pid" -Fn 2>/dev/null | sed -n 's/^n//p' | head -n1)
    fi
    [ "$cwd" = "$REPO/apps/web" ] && echo "$pid"
  done
  return 0
}

start_postgres() {
  if [ "$PG_EXISTS" = 1 ]; then
    docker start "$PG_CONTAINER" >/dev/null
    PG_PORT=$(docker port "$PG_CONTAINER" 5432/tcp | head -n1 | awk -F: '{print $NF}')
    log "postgres: reusing container $PG_CONTAINER on 127.0.0.1:$PG_PORT"
  else
    docker run -d --name "$PG_CONTAINER" --label "vicoa-stack-preview=$REPO" \
      -p "127.0.0.1:$PG_PORT:5432" \
      -e POSTGRES_USER=vicoa -e POSTGRES_PASSWORD=vicoa -e POSTGRES_DB=vicoa \
      "$PG_IMAGE" >/dev/null
    rm -f "$STATE/seeded"
    log "postgres: created container $PG_CONTAINER on 127.0.0.1:$PG_PORT"
  fi
  for _ in $(seq 1 60); do
    # TCP, not the socket: the image's init server is socket-only, so this
    # only succeeds once the real server is up.
    docker exec "$PG_CONTAINER" pg_isready -h 127.0.0.1 -U vicoa -d vicoa >/dev/null 2>&1 && return 0
    sleep 1
  done
  die "postgres did not become ready (docker logs $PG_CONTAINER)"
}

migrate() {
  log "migrating the database (alembic upgrade head)"
  (cd "$REPO/backend/src/shared" &&
    env -i "HOME=$HOME" "PATH=$BASE_PATH" "LANG=${LANG:-en_US.UTF-8}" \
      "PYTHONPATH=$REPO/backend/src" "DATABASE_URL=$DATABASE_URL" \
      "$PY" -m alembic upgrade head >"$STATE/migrate.log" 2>&1) ||
    { tail -n 25 "$STATE/migrate.log" >&2; die "migration failed (log: $STATE/migrate.log)"; }
}

start_tunnel() {
  local provider url
  for provider in ${PROVIDER:-cloudflare ngrok}; do
    url=""
    case $provider in
      cloudflare)
        command -v cloudflared >/dev/null 2>&1 || { log "cloudflared is not installed"; continue; }
        launch tunnel "$STATE" cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:$PROXY_PORT"
        for _ in $(seq 1 60); do
          url=$(grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' "$STATE/tunnel.log" 2>/dev/null |
            grep -v '^https://api\.' | head -n1 || true)
          [ -n "$url" ] && break
          alive tunnel || break
          sleep 1
        done
        CLIENT_IP_HEADER=Cf-Connecting-Ip
        ;;
      ngrok)
        command -v ngrok >/dev/null 2>&1 || { log "ngrok is not installed"; continue; }
        # Read the URL from our own log, not :4040 — another ngrok may own that port.
        launch tunnel "$STATE" ngrok http "127.0.0.1:$PROXY_PORT" --log stdout --log-format logfmt
        for _ in $(seq 1 60); do
          url=$(grep -Eo 'url=https://[^ ]+' "$STATE/tunnel.log" 2>/dev/null | head -n1 | sed 's/^url=//' || true)
          [ -n "$url" ] && break
          alive tunnel || break
          sleep 1
        done
        CLIENT_IP_HEADER=X-Forwarded-For
        ;;
      *) die "unknown --provider $provider (cloudflare or ngrok)" ;;
    esac
    if [ -n "$url" ]; then
      PUBLIC_URL=$url TUNNEL_PROVIDER=$provider
      return 0
    fi
    tail -n 15 "$STATE/tunnel.log" >&2 || true
    log "$provider tunnel did not come up"
    stop tunnel
  done
  die "no tunnel could be started (install cloudflared, e.g. brew install cloudflared; or authenticate ngrok: ngrok config add-authtoken <token>)"
}

write_backend_env() { # true|false — BUILTIN_ALLOW_SIGNUP
  (
    umask 077
    cat >"$STATE/backend.env" <<EOF
ENVIRONMENT='preview'
AUTH_PROVIDER='builtin'
BUILTIN_ALLOW_SIGNUP='$1'
DATABASE_URL='$DATABASE_URL'
JWT_PRIVATE_KEY_FILE='$STATE/keys/jwt_private.pem'
JWT_PUBLIC_KEY_FILE='$STATE/keys/jwt_public.pem'
FRONTEND_URLS='["$PUBLIC_URL"]'
WEB_APP_URL='$PUBLIC_URL'
VICOA_WS_URL='$WS_URL'
INTERNAL_BROADCAST_URL='http://127.0.0.1:$SERVER_PORT/_internal/broadcast'
INTERNAL_BROADCAST_TOKEN='$BROADCAST_TOKEN'
CLIENT_IP_HEADER='$CLIENT_IP_HEADER'
PYTHONPATH="$REPO/backend/src\${PYTHONPATH:+:\$PYTHONPATH}"
EOF
  )
}

# start_py NAME PORT APP [VAR=value...] — uvicorn with an empty environment,
# from an empty directory. --env-file is sourced first so the preview's own
# values always win.
start_py() {
  local name=$1 port=$2 app=$3
  shift 3
  # shellcheck disable=SC2016  # the single-quoted script is expanded by the inner shell
  launch "$name" "$STATE" env -i "HOME=$HOME" "PATH=$BASE_PATH" "LANG=${LANG:-en_US.UTF-8}" \
    /bin/bash -c 'cd "$1" || exit 1
set -a
if [ -n "$2" ]; then . "$2"; fi
. "$3"
set +a
shift 3
exec "$@"' stack-preview "$STATE/run" "$ENV_FILE" "$STATE/backend.env" \
    env "$@" "$PY" -m uvicorn "$app" --host 127.0.0.1 --port "$port"
}

start_backend() { start_py backend "$BACKEND_PORT" backend.main:app; }

start_server() {
  start_py server "$SERVER_PORT" servers.app:app ENABLE_WEBSOCKET=true "MCP_SERVER_PORT=$SERVER_PORT"
}

start_web() {
  local node next f key
  node=$(command -v node)
  next="$REPO/apps/web/node_modules/next/dist/bin/next"
  if [ ! -f "$next" ]; then
    command -v pnpm >/dev/null 2>&1 || die "apps/web has no node_modules and pnpm is not on PATH"
    log "installing web dependencies (pnpm install --frozen-lockfile)"
    (cd "$REPO/apps/web" && pnpm install --frozen-lockfile) >&2 || die "pnpm install failed"
  fi
  # Next loads apps/web/.env* itself, but never over a variable that is already
  # set — so blank every key those files define (hosted Supabase, PostHog,
  # Stripe, ...) and set only what the preview needs.
  local web_env=()
  for f in .env .env.local .env.development .env.development.local; do
    [ -f "$REPO/apps/web/$f" ] || continue
    while IFS= read -r key; do
      web_env+=("$key=")
    done < <(sed -n -E 's/^[[:space:]]*(export[[:space:]]+)?([A-Za-z_][A-Za-z0-9_]*)=.*/\2/p' "$REPO/apps/web/$f")
  done
  web_env+=(
    "NEXT_TELEMETRY_DISABLED=1"
    "NEXT_PUBLIC_AUTH_PROVIDER=builtin"
    "NEXT_PUBLIC_BACKEND_API_URL=$PUBLIC_URL"
    "NEXT_PUBLIC_VICOA_WS_URL=$WS_URL"
    "BACKEND_INTERNAL_URL=http://127.0.0.1:$BACKEND_PORT"
    "BASE_URL=$PUBLIC_URL"
  )
  (cd "$REPO/apps/web" &&
    launch web "$STATE" env -i "HOME=$HOME" "PATH=$(dirname "$node"):$BASE_PATH" \
      "LANG=${LANG:-en_US.UTF-8}" "TMPDIR=${TMPDIR:-/tmp}" "${web_env[@]}" \
      "$node" "$next" dev --turbopack -H 127.0.0.1 -p "$WEB_PORT")
}

seed_accounts() {
  if [ ! -f "$STATE/accounts" ]; then
    (
      umask 077
      printf "OWNER_PASSWORD='%s'\nVIEWER_PASSWORD='%s'\n" \
        "$(openssl rand -hex 8)" "$(openssl rand -hex 8)" >"$STATE/accounts"
    )
  fi
  # shellcheck disable=SC1091
  . "$STATE/accounts"
  local pair email password name out code
  for pair in "owner:$OWNER_EMAIL:$OWNER_PASSWORD:Ada" "viewer:$VIEWER_EMAIL:$VIEWER_PASSWORD:Bea"; do
    IFS=: read -r _ email password name <<<"$pair"
    out=$(backend_auth sign-up "$email" "$password" "$name")
    code=${out##*$'\n'}
    if [ "$code" != 200 ]; then
      out=$(backend_auth sign-in "$email" "$password")
      code=${out##*$'\n'}
      [ "$code" = 200 ] || die "could not create or sign in $email (HTTP $code). Reset with: stack-preview.sh down --purge"
    fi
  done
  touch "$STATE/seeded"
}

# public_probe PATH — status code through the tunnel; tolerates the few seconds
# before a fresh quick-tunnel hostname resolves.
public_probe() {
  local code
  for _ in $(seq 1 45); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 120 "$PUBLIC_URL$1" 2>/dev/null || true)
    if [ -n "$code" ] && [ "$code" != 000 ] && [ "$code" != 530 ] && [ "$code" != 502 ]; then
      echo "$code"
      return 0
    fi
    sleep 2
  done
  echo "${code:-000}"
}

ws_probe() { # TOKEN — handshake through the tunnel exactly as the browser does
  curl -s --http1.1 -o /dev/null -w '%{http_code}' --max-time 8 \
    -H 'Connection: Upgrade' -H 'Upgrade: websocket' -H 'Sec-WebSocket-Version: 13' \
    -H "Sec-WebSocket-Key: $(openssl rand -base64 16)" \
    -H "Sec-WebSocket-Protocol: vicoa-ws, vicoa-supabase.$1" \
    -H "Origin: $PUBLIC_URL" "$PUBLIC_URL/ws" 2>/dev/null || true
}

cmd_up() {
  if [ -f "$STATE/ports" ] && any_alive; then
    log "a preview of $REPO is already running; showing its status (\`down\` first to restart it)"
    cmd_status
    return 0
  fi
  preflight
  local others
  others=$(other_next_dev)
  [ -z "$others" ] || die "a next dev server (pid $(echo "$others" | tr '\n' ' ')) already serves $REPO/apps/web, and two dev servers would fight over apps/web/.next. Stop it if it is yours, or preview from another worktree."

  mkdir -p "$STATE/run" "$STATE/extra"
  chmod 700 "$STATE"
  UP_IN_PROGRESS=1

  PG_EXISTS=0
  docker container inspect "$PG_CONTAINER" >/dev/null 2>&1 && PG_EXISTS=1
  alloc_ports
  start_postgres
  DATABASE_URL="postgresql://vicoa:vicoa@127.0.0.1:$PG_PORT/vicoa"
  printf 'PG_PORT=%s\nBACKEND_PORT=%s\nSERVER_PORT=%s\nWEB_PORT=%s\nPROXY_PORT=%s\n' \
    "$PG_PORT" "$BACKEND_PORT" "$SERVER_PORT" "$WEB_PORT" "$PROXY_PORT" >"$STATE/ports"
  migrate

  [ -f "$STATE/keys/jwt_private.pem" ] ||
    bash "$REPO/backend/scripts/generate-jwt-keys.sh" "$STATE/keys" >/dev/null
  BROADCAST_TOKEN=$(openssl rand -hex 32)

  # The proxy first, so the tunnel has something to point at; the tunnel next,
  # because the backend allowlist and the web bundle both need its URL.
  launch proxy "$STATE" "$(command -v node)" "$SCRIPT_DIR/proxy.mjs" \
    "$PROXY_PORT" "$WEB_PORT" "$BACKEND_PORT" "$SERVER_PORT"
  for _ in $(seq 1 20); do port_open "$PROXY_PORT" && break; sleep 0.5; done
  port_open "$PROXY_PORT" || die "proxy did not start (log: $STATE/proxy.log)"
  start_tunnel
  WS_URL="wss://${PUBLIC_URL#https://}/ws"
  printf "PUBLIC_URL='%s'\nTUNNEL_PROVIDER='%s'\n" "$PUBLIC_URL" "$TUNNEL_PROVIDER" >"$STATE/public"
  printf '%s' "$ENV_FILE" >"$STATE/env_file"
  log "tunnel: $PUBLIC_URL ($TUNNEL_PROVIDER)"

  local first_seed=0 signup=true
  [ -f "$STATE/seeded" ] || first_seed=1
  [ "$ALLOW_SIGNUP" = 1 ] || [ "$first_seed" = 1 ] || signup=false
  write_backend_env "$signup"

  log "starting server, backend and web"
  start_server
  start_backend
  start_web
  wait_http server "http://127.0.0.1:$SERVER_PORT/health" 90
  wait_http backend "http://127.0.0.1:$BACKEND_PORT/health" 90
  seed_accounts
  if [ "$signup" = true ] && [ "$ALLOW_SIGNUP" = 0 ]; then
    # Accounts exist now; close sign-up so the public URL can't mint more.
    write_backend_env false
    stop backend
    start_backend
    wait_http backend "http://127.0.0.1:$BACKEND_PORT/health" 90
  fi
  log "waiting for the web dev server (first compile can take a minute)"
  wait_http web "http://127.0.0.1:$WEB_PORT/sign-in" 240

  log "checking the stack through the public URL"
  local page_code api_out api_code token ws_code
  page_code=$(public_probe /sign-in)
  api_out=$(curl -s -w '\n%{http_code}' --max-time 30 -X POST "$PUBLIC_URL/api/v1/auth/builtin/sign-in" \
    -H 'content-type: application/json' \
    -d "{\"email\":\"$OWNER_EMAIL\",\"password\":\"$OWNER_PASSWORD\"}" 2>/dev/null || true)
  api_code=${api_out##*$'\n'}
  token=""
  [ "$api_code" = 200 ] && token=$(printf '%s' "${api_out%$'\n'*}" | json_field access_token)
  ws_code=000
  [ -n "$token" ] && ws_code=$(ws_probe "$token")
  # Warm the dashboard so the reviewer's first click doesn't wait on a compile.
  curl -s -o /dev/null --max-time 180 "$PUBLIC_URL/dashboard" 2>/dev/null || true

  UP_IN_PROGRESS=0
  local status=ok message
  message="Full stack up: web, REST and realtime all on one URL. Sign in as the owner account."
  if [ "$page_code" != 200 ] || [ "$api_code" != 200 ] || [ "$ws_code" != 101 ]; then
    status=error
    message="Started, but the public check failed: page $page_code, api $api_code, websocket $ws_code (101 expected). Logs: $STATE"
  fi
  print_result "$status" "$message"
  [ "$status" = ok ]
}

print_result() { # STATUS MESSAGE
  local signup=closed
  grep -q "BUILTIN_ALLOW_SIGNUP='true'" "$STATE/backend.env" 2>/dev/null && signup=open
  printf '%s\n' \
    "* status: $1" \
    "* provider: ${TUNNEL_PROVIDER:-none}" \
    "* local_url: http://127.0.0.1:$PROXY_PORT" \
    "* port: $PROXY_PORT" \
    "* pid: $(pid_of proxy)" \
    "* message: $2" \
    "* public_url: ${PUBLIC_URL:-null}" \
    "* owner: $OWNER_EMAIL / ${OWNER_PASSWORD:-?}" \
    "* viewer: $VIEWER_EMAIL / ${VIEWER_PASSWORD:-?}" \
    "* signup: $signup" \
    "* state: $STATE" \
    "* stop: $SCRIPT_DIR/stack-preview.sh down --repo $REPO"
}

# --- other commands ----------------------------------------------------------

cmd_status() {
  load_state
  local svc line="" code status=ok
  for svc in $SERVICES; do
    if alive "$svc"; then line="$line $svc=up"; else line="$line $svc=down"; status=error; fi
  done
  if docker container inspect -f '{{.State.Running}}' "$PG_CONTAINER" 2>/dev/null | grep -q true; then
    line="$line postgres=up"
  else
    line="$line postgres=down"
    status=error
  fi
  code=000
  [ -n "$PUBLIC_URL" ] && code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 "$PUBLIC_URL/sign-in" 2>/dev/null || true)
  [ "$code" = 200 ] || status=error
  print_result "$status" "${line# } public=$code"
}

cmd_env() {
  load_state
  local pair
  while IFS= read -r pair; do
    printf 'export %s=%q\n' "${pair%%=*}" "${pair#*=}"
  done < <(preview_vars)
}

cmd_token() {
  load_state
  [ ${#ARGS[@]} = 1 ] || die "usage: stack-preview.sh token owner|viewer"
  token_for "${ARGS[0]}"
  echo
}

cmd_seed() {
  load_state
  [ ${#ARGS[@]} = 1 ] || die "usage: stack-preview.sh seed FILE"
  local file vars=() pair
  file=$(cd "$(dirname "${ARGS[0]}")" && pwd -P)/$(basename "${ARGS[0]}")
  [ -f "$file" ] || die "$file does not exist"
  alive backend || die "the preview backend is not running"
  while IFS= read -r pair; do vars+=("$pair"); done < <(preview_vars)
  vars+=("OWNER_TOKEN=$(token_for owner)" "VIEWER_TOKEN=$(token_for viewer)")
  # Same clean environment as the services: from the empty run dir, so
  # importing the backend's settings loads no checkout .env.
  case $file in
    *.py)
      (cd "$STATE/run" && env -i "HOME=$HOME" "PATH=$BASE_PATH" "LANG=${LANG:-en_US.UTF-8}" \
        "${vars[@]}" "$PY" "$file")
      ;;
    *)
      (cd "$STATE/run" && env -i "HOME=$HOME" "PATH=$PATH" "LANG=${LANG:-en_US.UTF-8}" \
        "${vars[@]}" /bin/bash "$file")
      ;;
  esac
}

cmd_run() {
  load_state
  [ ${#ARGS[@]} -ge 2 ] || die "usage: stack-preview.sh run NAME -- CMD..."
  local name=${ARGS[0]} vars=() pair
  case $name in *[!A-Za-z0-9_-]*) die "run: NAME may only use letters, digits, - and _" ;; esac
  alive "$name" "$STATE/extra" && die "$name is already running (pid $(pid_of "$name" "$STATE/extra"))"
  while IFS= read -r pair; do vars+=("$pair"); done < <(preview_vars)
  launch "$name" "$STATE/extra" env "${vars[@]}" "${ARGS[@]:1}"
  sleep 1
  alive "$name" "$STATE/extra" || { tail -n 20 "$STATE/extra/$name.log" >&2; die "$name exited immediately"; }
  log "$name: pid $(pid_of "$name" "$STATE/extra"), log $STATE/extra/$name.log"
}

# Restart services in place: same ports, same tunnel, so the reviewer's link
# keeps working. The web hot-reloads by itself; the Python processes don't.
cmd_restart() {
  load_state
  if [ ! -f "$STATE/public" ] || ! alive tunnel; then die "no running preview to restart (run: stack-preview.sh up)"; fi
  ENV_FILE=$(cat "$STATE/env_file" 2>/dev/null || true)
  WS_URL="wss://${PUBLIC_URL#https://}/ws"
  local svc
  [ ${#ARGS[@]} -gt 0 ] || ARGS=(server backend)
  for svc in "${ARGS[@]}"; do
    case $svc in
      server) stop server; start_server; wait_http server "http://127.0.0.1:$SERVER_PORT/health" 90 ;;
      backend) stop backend; start_backend; wait_http backend "http://127.0.0.1:$BACKEND_PORT/health" 90 ;;
      web) stop web; start_web; wait_http web "http://127.0.0.1:$WEB_PORT/sign-in" 240 ;;
      *) die "restart: expected backend, server or web, got $svc" ;;
    esac
    log "$svc restarted (pid $(pid_of "$svc"))"
  done
}

cmd_down() {
  [ -d "$STATE" ] || { log "nothing to stop for $REPO"; return 0; }
  stop_all
  if [ "$PURGE" = 1 ]; then
    if docker container inspect "$PG_CONTAINER" >/dev/null 2>&1; then
      docker rm -f -v "$PG_CONTAINER" >/dev/null
    fi
    case $STATE in "$STATE_ROOT"/?*) rm -rf "$STATE" ;; esac
    log "stopped; removed $PG_CONTAINER and $STATE"
  else
    rm -f "$STATE/public"
    log "stopped; database kept in container $PG_CONTAINER (down --purge removes it)"
  fi
}

case $CMD in
  up) cmd_up ;;
  status) cmd_status ;;
  env) cmd_env ;;
  token) cmd_token ;;
  seed) cmd_seed ;;
  run) cmd_run ;;
  restart) cmd_restart ;;
  down) cmd_down ;;
esac
