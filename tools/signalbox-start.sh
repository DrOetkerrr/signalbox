#!/bin/bash
# Signalbox editor on the Mac — started by launchd (com.signalbox.editor, KeepAlive)
# and by the editor's own ↻ Restart button. Serves http://localhost:5001
PROJECT="/Users/willem-jan/Desktop/Hobby Projects/Signalbox"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
export SIGNALBOX_AUTOPLAY=0          # dev server: never auto-run scenes on the Mac
export PYTHONUNBUFFERED=1
cd "$PROJECT" || { echo "project folder not found: $PROJECT"; sleep 30; exit 1; }
exec /usr/bin/python3 editor/app.py
