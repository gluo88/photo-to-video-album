#!/bin/bash
#
# REVISIONS:
# v1.5 – Updated version date to match Python script v1.5.
# v1.4 – Fixed Python output buffering (added -u flag) so prints appear instantly when logging to file.
# v1.3 – Added execution time tracking and output logging to log_geo.txt
# v1.2 – Removed --online flag; all remaining args forwarded to Python. Added --inject-yaml to usage; 
#         Now supports --offline and --google-key transparently.
# v1.1 – Initial version
#
#
#  To LLM：Please add the comment for new revision, and keeping all previous revision notes, when updating!!! (please keep this line.)
#
# run_photo_geo.sh - Bash wrapper for GPS extraction and YAML injection
# Part of the Cinematic Batch & Stitch Engine

VERSION="1.5"
VERSION_DATE="2026-06-07"

if [ -z "$1" ]; then
    echo "Usage: ./run_photo_geo.sh <project_name> [options]"
    echo ""
    echo "  Default mode:  Nominatim (OSM, online, no key needed), writes geo_summary.txt only"
    echo "  --offline:     Use local reverse_geocoder only (no internet)"
    echo "  --google-key:  Use Google Maps API (most detailed)"
    echo "  --inject-yaml: Also write location into per-asset .yaml files (default: summary only)"
    echo ""
    echo "Examples:"
    echo "  ./run_photo_geo.sh park_pottery"
    echo "  ./run_photo_geo.sh park_pottery --offline"
    echo "  ./run_photo_geo.sh park_pottery --google-key \"AIza...\""
    echo "  ./run_photo_geo.sh park_pottery --inject-yaml --offline"
    exit 1
fi

PROJECT="$1"
shift

PICTURES_DIR="/home/gluo/Pictures/$PROJECT"
PY_SCRIPT="photo_geo.py"
VENV_PATH="/home/gluo/code/python/venv/bin/activate"
LOG_FILE="$PICTURES_DIR/log_geo.txt"

if [ ! -d "$PICTURES_DIR" ]; then
    echo "❌ ERROR: Project directory $PICTURES_DIR not found."
    exit 1
fi

# Clear old log and start fresh
> "$LOG_FILE"

echo "----------------------------------------------------" | tee -a "$LOG_FILE"
echo "🌍 Starting Geo-Extraction for $PROJECT  (v$VERSION)" | tee -a "$LOG_FILE"
echo "📝 Logging output to: $LOG_FILE" | tee -a "$LOG_FILE"
echo "----------------------------------------------------" | tee -a "$LOG_FILE"

# Track Start Time
START_TIME=$(date +%s)

# Activate Python virtual environment
if [ -f "$VENV_PATH" ]; then
    source "$VENV_PATH"
else
    echo "⚠️ Warning: Python virtual environment not found at $VENV_PATH" | tee -a "$LOG_FILE"
fi

# Run the Python script (unbuffered), forwarding any extra flags, and pipe to tee for the log file
python3 -u "$PY_SCRIPT" "$PICTURES_DIR" "$@" 2>&1 | tee -a "$LOG_FILE"

# Deactivate environment
if declare -f deactivate > /dev/null; then
    deactivate
fi

# Track End Time and Calculate Duration
END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))
MINUTES=$((ELAPSED / 60))
SECONDS=$((ELAPSED % 60))

echo "----------------------------------------------------" | tee -a "$LOG_FILE"
echo "⏱️ Total geo-processing time: ${MINUTES}m ${SECONDS}s" | tee -a "$LOG_FILE"
echo "----------------------------------------------------" | tee -a "$LOG_FILE"
