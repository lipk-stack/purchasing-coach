#!/usr/bin/env sh
# Purchasing Coach — Portable Launcher (Linux / macOS).
#
# This ships inside the standalone deployment zip next to the application
# (purchasing-coach*.pyz) and the samples/ folder. Nothing needs to be
# installed except Python 3.10+.
#
#   ./run.sh                         # browser chat UI with the bundled samples
#   ./run.sh --backend keyword       # forward any CLI flags (see README)
#   GUIDELINE=mine.docx TEMPLATE=mine.xlsx ./run.sh   # use your own documents
#
# macOS users can double-click run.command instead (it calls this script).

set -eu
DIR=$(cd "$(dirname "$0")" && pwd)
cd "$DIR"

echo ""
echo " ================================================"
echo "  Purchasing Coach - Portable Edition"
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

# Find the bundled .pyz (prefer the embedded build if both are present).
PYZ=""
for f in "$DIR/purchasing-coach-embedded.pyz" "$DIR/purchasing-coach.pyz"; do
  if [ -f "$f" ]; then PYZ="$f"; break; fi
done
if [ -z "$PYZ" ]; then
  echo " [ERROR] purchasing-coach*.pyz not found next to this script." >&2
  exit 1
fi

GUIDELINE="${GUIDELINE:-$DIR/samples/XXEON_IT_Procurement_Guideline.docx}"
TEMPLATE="${TEMPLATE:-$DIR/samples/TENDER_TEMPLATE.xlsx}"

# Pre-flight: make sure the chosen documents exist, so a renamed or
# wrong-folder file is caught here with a clear message rather than failing
# deep inside the app. Drop your own files into samples/ keeping the same
# names, or point GUIDELINE/TEMPLATE at them.
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

echo " Python:    $PY"
echo " App:       $PYZ"
echo " Guideline: $GUIDELINE"
echo " Template:  ${TEMPLATE:-<built-in layout>}"
echo ""

# Default to the browser UI when no flags were given; otherwise forward them.
if [ "$#" -eq 0 ]; then
  set -- --web
fi
if [ -n "$TEMPLATE" ]; then
  set -- --guideline "$GUIDELINE" --template "$TEMPLATE" "$@"
else
  set -- --guideline "$GUIDELINE" "$@"
fi
exec "$PY" "$PYZ" "$@"
