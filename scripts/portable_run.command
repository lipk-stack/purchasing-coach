#!/bin/sh
# Purchasing Coach — macOS double-click launcher (Portable Edition).
#
# macOS Finder runs a ".command" file in Terminal when double-clicked, so Mac
# users get a one-click start just like Windows users get from run.bat. It
# hands off to run.sh beside it, so every documented flag works here too.

DIR=$(cd "$(dirname "$0")" && pwd)
exec "$DIR/run.sh" "$@"
