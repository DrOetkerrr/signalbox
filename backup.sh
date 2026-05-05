#!/bin/bash
SRC="/Users/willem-jan/Desktop/CODE PROJECTS/Signalbox"
DEST="$SRC/_backups"
STAMP=$(date +"%Y%m%d_%H%M")
zip -rq "$DEST/signalbox_$STAMP.zip" "$SRC" --exclude "$SRC/_backups/*"
# Keep only the 20 most recent backups
ls -t "$DEST"/signalbox_*.zip | tail -n +21 | xargs rm -f 2>/dev/null
