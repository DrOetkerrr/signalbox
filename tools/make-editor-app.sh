#!/bin/bash
# Rebuild "Signalbox Editor.app" (double-click launcher for the Mac editor) and
# install the start script it relies on. Run from anywhere.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$(dirname "$HERE")"
cp "$HERE/signalbox-start.sh" "$HOME/signalbox-start.sh" && chmod +x "$HOME/signalbox-start.sh"
rm -rf "$PROJECT/Signalbox Editor.app"
osacompile -o "$PROJECT/Signalbox Editor.app" "$HERE/editor-launcher.applescript"
echo "✓ built: $PROJECT/Signalbox Editor.app  (start script: ~/signalbox-start.sh)"
