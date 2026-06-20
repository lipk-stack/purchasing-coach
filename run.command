#!/bin/sh
# Purchasing Coach — double-click launcher for macOS.
#
# macOS Finder runs a ".command" file in Terminal when you double-click it,
# so Mac users get the same one-click start as Windows users get from run.bat.
# This thin wrapper hands off to run.sh in the same folder, so every flag and
# environment variable documented for run.sh works here too, e.g.:
#
#   double-click run.command                       # browser chat UI (default)
#   ./run.command --backend embedded               # forward any CLI flags
#   GUIDELINE=mine.docx TEMPLATE=mine.xlsx ./run.command   # your own documents

DIR=$(cd "$(dirname "$0")" && pwd)
exec "$DIR/run.sh" "$@"
