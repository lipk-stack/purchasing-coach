#!/usr/bin/env sh
# Purchasing Coach — easy startup for Linux / macOS.
#
#   ./run.sh                       # browser chat UI with the bundled samples
#   ./run.sh --backend embedded    # any extra flags are forwarded to the app
#   ./run.sh --backend ollama      # use a specific backend (see README)
#   GUIDELINE=mine.docx TEMPLATE=mine.xlsx ./run.sh   # use your own documents
#
# With no arguments it launches the local web UI. Pass any CLI flags to
# override; they are forwarded verbatim and argparse takes the last value, so
# `./run.sh --guideline other.docx` overrides the default below.

set -eu
DIR=$(cd "$(dirname "$0")" && pwd)
cd "$DIR"

echo ""
echo " ================================================"
echo "  Purchasing Coach - Starting..."
echo " ================================================"
echo ""

# Find a Python 3.10+ interpreter.
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo " [ERROR] Python 3.10+ not found. Install it from" >&2
  echo "         https://www.python.org/downloads/" >&2
  exit 1
fi

GUIDELINE="${GUIDELINE:-$DIR/samples/XXEON_IT_Procurement_Guideline.docx}"
TEMPLATE="${TEMPLATE:-$DIR/samples/TENDER_TEMPLATE.xlsx}"

# Default to the browser UI when no flags were given.
if [ "$#" -eq 0 ]; then
  set -- --web
fi

echo " Python:    $PY"
echo " Guideline: $GUIDELINE"
echo ""

# Prefer the prebuilt portable .pyz; fall back to running from source.
APP="$DIR/dist/purchasing-coach.pyz"
if [ -f "$APP" ]; then
  exec "$PY" "$APP" --guideline "$GUIDELINE" --template "$TEMPLATE" "$@"
else
  exec "$PY" -m coach --guideline "$GUIDELINE" --template "$TEMPLATE" "$@"
fi
