#!/usr/bin/env bash
# Start the Connect Suggests web app and open it in your browser.
#
#   ./run_webui.sh              local mock only, safe for practice
#   ./run_webui.sh --sandbox    also writes to the real Yext sandbox (needs a key in .env or ../.env)
#   ./run_webui.sh --no-browser don't open a browser
#
# Press Ctrl+C to stop.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

SANDBOX=0
OPEN_BROWSER=1
for arg in "$@"; do
  case "$arg" in
    --sandbox) SANDBOX=1 ;;
    --no-browser) OPEN_BROWSER=0 ;;
    -h|--help) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $arg (try --help)"; exit 2 ;;
  esac
done

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 isn't installed. Install Python 3.9 or newer, then try again."
  exit 1
fi
if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))'; then
  echo "This app needs Python 3.9 or newer. You have: $(python3 --version)"
  exit 1
fi
if [ -z "${CONNECT_DATA_DIR:-}" ] && [ ! -f fonecta_data/FONECTA_CONNECT_SUGGESTS_2026/mock_api/server.py ]; then
  echo "Can't find the challenge data in fonecta_data/. Set CONNECT_DATA_DIR to its folder."
  exit 1
fi

if [ "$SANDBOX" = 1 ]; then
  if [ -f .env ]; then
    export CONNECT_ENV_FILE="$PWD/.env"
  elif [ -f ../.env ]; then
    export CONNECT_ENV_FILE="$(cd .. && pwd)/.env"
  else
    echo "--sandbox needs a key in .env. Copy .env.example to .env and set YEXT_API_KEY."
    exit 1
  fi
else
  export CONNECT_ENV_FILE=/dev/null
  unset YEXT_API_KEY API_KEY
fi

# Use the first free port from 8080 up, so a second copy doesn't fail.
if [ -z "${CONNECT_PORT:-}" ]; then
  CONNECT_PORT=$(python3 - <<'PY'
import socket
for port in range(8080, 8100):
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            continue
        print(port)
        break
PY
  )
  if [ -z "$CONNECT_PORT" ]; then
    echo "No free port between 8080 and 8099. Stop another app, or set CONNECT_PORT."
    exit 1
  fi
fi
export CONNECT_PORT
URL="http://127.0.0.1:$CONNECT_PORT"

open_when_ready() {
  for _ in $(seq 1 60); do
    if python3 -c "import urllib.request; urllib.request.urlopen('$URL/', timeout=1)" 2>/dev/null; then
      if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$URL" >/dev/null 2>&1 || true
      elif command -v open >/dev/null 2>&1; then
        open "$URL" >/dev/null 2>&1 || true
      fi
      return
    fi
    sleep 0.5
  done
}

echo "Starting Connect Suggests at $URL"
echo "Press Ctrl+C to stop."
if [ "$OPEN_BROWSER" = 1 ]; then
  open_when_ready &
fi
exec python3 run.py
