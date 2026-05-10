#!/bin/bash
cd "$(dirname "$0")"
echo "Starting Signalbox editor at http://localhost:5001"
open "http://localhost:5001"
python3 editor/app.py
