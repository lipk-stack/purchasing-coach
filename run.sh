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

# Clear stale Python bytecode so an edited source tree is always recompiled and
# nothing cached from a previous run is reused.
find "$DIR" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

# Pre-flight: make sure the chosen documents exist, so a renamed or
# wrong-folder file is caught here with a clear message instead of failing
# deep inside the app. (Drop your files into samples/ keeping the same names,
# or point GUIDELINE/TEMPLATE at them.)
if [ ! -f "$GUIDELINE" ]; then
  echo " [ERROR] Guideline file not found:" >&2
  echo "         $GUIDELINE" >&2
  echo "         Put your guideline in samples/ as" >&2
  echo "         XXEON_IT_Procurement_Guideline.docx (.docx/.pdf/.md/.txt)," >&2
  echo "         or run:  GUIDELINE=/path/to/your-guideline.docx ./run.sh" >&2
  exit 1
fi
if [ ! -f "$TEMPLATE" ]; then
  echo " [WARN] Template not found: $TEMPLATE" >&2
  echo "        Falling back to the built-in checklist layout." >&2
  TEMPLATE=""
fi

# Default to the browser UI when no flags were given.
if [ "$#" -eq 0 ]; then
  set -- --web
fi

echo " Python:    $PY"
echo " Guideline: $GUIDELINE"
echo " Template:  ${TEMPLATE:-<built-in layout>}"
echo ""

# Build the argument list, passing --template only when one was found.
if [ -n "$TEMPLATE" ]; then
  set -- --guideline "$GUIDELINE" --template "$TEMPLATE" "$@"
else
  set -- --guideline "$GUIDELINE" "$@"
fi

# Prefer the prebuilt portable .pyz; fall back to running from source.
APP="$DIR/dist/purchasing-coach.pyz"
if [ -f "$APP" ]; then
  exec "$PY" "$APP" "$@"
else
  exec "$PY" -m coach "$@"
fi
