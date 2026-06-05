#!/bin/bash
# Cinematic Batch & Stitch Engine
# Revisions
# v3.3 – Fixed xterm logger recursion
# v3.4 – New log naming: log_perf.txt and log_render.txt
# v3.5 – with version and audio logging
# v3.6 – with cumulative rendering time
# v4.0 - merged. Combines run_video.sh and stitch_master.sh into one script.
#
# Usage: ./stitch_master.sh <project_name> [batch_size] [--yes] [--dry-run] [--init]
# Example:
#        ./stitch_master.sh  z_SanXingDuiMuseumX 200 --yes --dry-run
#
#  To LLM：Please keep all valid comments and other information when updating!!! (please keep this line.)

# current version:
VERSION="4.0"
VERSION_DATE="2026-06-02"

# ====================================================================
# 1. Special case: internal logger (called by xterm)
# ====================================================================
if [ "$1" == "--logger-internal" ]; then
    proj_dir="$2"
    r_log="$proj_dir/log_render.txt"
    p_log="$proj_dir/log_perf.txt"
    while true; do
        TIMESTAMP=$(date '+%H:%M:%S')
        if command -v sensors &>/dev/null; then
            TEMP=$(sensors 2>/dev/null | grep -m1 "Package id 0" | awk '{print $4}')
            [ -z "$TEMP" ] && TEMP=$(sensors 2>/dev/null | grep -m1 "Core 0" | awk '{print $3}')
            [ -z "$TEMP" ] && TEMP="N/A"
        else
            TEMP="N/A"
        fi
        SPEED=$(tail -n 100 "$r_log" 2>/dev/null | grep -o "[0-9.]*it/s" | tail -n 1)
        [ -z "$SPEED" ] && SPEED="initialising..."
        echo "$TIMESTAMP | CPU: $TEMP | Speed: $SPEED"
        echo "$TIMESTAMP | $TEMP | $SPEED" >> "$p_log"
        sleep 10
    done
    exit 0
fi

# ====================================================================
# 2. Argument parsing
# ====================================================================
PROJECT=""
BATCH_SIZE=200          # default (matches Python default)
YES_FLAG=""
DRY_RUN=""
INIT_FLAG=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --chunk-size)   # legacy alias for batch_size
            BATCH_SIZE="$2"
            shift 2
            ;;
        --yes)
            YES_FLAG="--yes"
            shift
            ;;
        --dry-run)
            DRY_RUN="--dry-run"
            shift
            ;;
        --init)
            INIT_FLAG="--init"
            shift
            ;;
        -*)
            echo "Unknown option: $1"
            exit 1
            ;;
        *)
            if [ -z "$PROJECT" ]; then
                PROJECT="$1"
            else
                BATCH_SIZE="$1"
            fi
            shift
            ;;
    esac
done

if [ -z "$PROJECT" ]; then
    echo "Usage: ./stitch_master.sh <project_name> [batch_size] [--yes] [--dry-run] [--init]"
    echo "Example: ./stitch_master.sh park_pottery 200 --yes --dry-run"
    echo "Example: ./stitch_master.sh park_pottery --yes"
    echo "Example: ./stitch_master.sh park_pottery --init"
    echo "Example: ./stitch_master.sh z_Europe --yes"
    exit 1
fi

# ====================================================================
# 3. Paths and project directory
# ====================================================================
PICTURES_DIR="/home/gluo/Pictures/$PROJECT"
OUTPUT_DIR="$PICTURES_DIR/output"
FINAL_OUT="$PICTURES_DIR/${PROJECT}_FINAL_MASTER.mp4"
PERF_LOG="$PICTURES_DIR/log_perf.txt"
RENDER_LOG="$PICTURES_DIR/log_render.txt"
PY_SCRIPT="make_video_album.py"
VENV_PATH="/home/gluo/code/python/venv/bin/activate"

# ====================================================================
# 4. Pre-flight checks and cleanup
# ====================================================================
echo "----------------------------------------------------"
echo "🦞 PRE-FLIGHT: Hardening workspace for $PROJECT..."

# Move existing master to output/old
if [ -f "$FINAL_OUT" ]; then
    mkdir -p "$OUTPUT_DIR"
    mv "$FINAL_OUT" "$OUTPUT_DIR/old_master_$(date +%Y%m%d_%H%M).mp4"
    echo "   - Previous master relocated to /output/"
fi

# Backup and recreate output directory
if [ -d "$OUTPUT_DIR" ]; then
    rm -rf "${OUTPUT_DIR}.bak"
    mv "$OUTPUT_DIR" "${OUTPUT_DIR}.bak"
fi
mkdir -p "$OUTPUT_DIR"

# Clear old logs
rm -f "$RENDER_LOG" "$PERF_LOG"
touch "$RENDER_LOG" "$PERF_LOG"

# ====================================================================
# 5. Launch xterm dashboard (unless --dry-run or --init)
# ====================================================================
if [ -z "$DRY_RUN" ] && [ -z "$INIT_FLAG" ]; then
    if command -v xterm &>/dev/null; then
        xterm -T "RENDER MONITOR: $PROJECT" -geometry 60x10 -e bash "$0" --logger-internal "$PICTURES_DIR" &
        LOGGER_PID=$!
        echo "🦞 Dashboard started in new xterm window."
        echo "   📊 Logging performance to: $PERF_LOG"
        echo "   📝 Rendering log: $RENDER_LOG"
    else
        echo "⚠️ xterm not installed. Install with: sudo apt install xterm"
        # Fallback: run logger in background (no GUI)
        (
            while true; do
                TIMESTAMP=$(date '+%H:%M:%S')
                if command -v sensors &>/dev/null; then
                    TEMP=$(sensors 2>/dev/null | grep -m1 "Package id 0" | awk '{print $4}')
                    [ -z "$TEMP" ] && TEMP=$(sensors 2>/dev/null | grep -m1 "Core 0" | awk '{print $3}')
                    [ -z "$TEMP" ] && TEMP="N/A"
                else
                    TEMP="N/A"
                fi
                SPEED=$(tail -n 100 "$RENDER_LOG" 2>/dev/null | grep -o "[0-9.]*it/s" | tail -n 1)
                [ -z "$SPEED" ] && SPEED="initialising..."
                echo "$TIMESTAMP | CPU: $TEMP | Speed: $SPEED"
                echo "$TIMESTAMP | $TEMP | $SPEED" >> "$PERF_LOG"
                sleep 10
            done
        ) &
        LOGGER_PID=$!
    fi
fi

# ====================================================================
# 6. Asset discovery
# ====================================================================
TOTAL_ASSETS=$(find "$PICTURES_DIR" -maxdepth 1 -type f \( -iname "*.jpg" -o -iname "*.png" -o -iname "*.mp4" \) ! -name "*_MASTER.mp4" ! -name "part_*.mp4" | wc -l)
echo "🦞 Found $TOTAL_ASSETS genuine assets." | tee -a "$RENDER_LOG"

# ====================================================================
# 7. Handle --init: generate configs and exit
# ====================================================================
if [ -n "$INIT_FLAG" ]; then
    echo "🦞 --init mode: generating configuration files only." | tee -a "$RENDER_LOG"
    # Call Python script with --init (it will create album_config.yaml and per‑asset template)
    source "$VENV_PATH"
    python3 "$PY_SCRIPT" "$PROJECT" 0 999999 --init 2>&1 | tee -a "$RENDER_LOG"
    deactivate
    # Kill logger if running
    kill $LOGGER_PID 2>/dev/null
    echo "Initialisation complete." | tee -a "$RENDER_LOG"
    exit 0
fi

# ====================================================================
# 8. Pre-flight confirmation (unless --yes)
# ====================================================================
if [ -z "$YES_FLAG" ]; then
    MP3_COUNT=$(find "$PICTURES_DIR" -maxdepth 1 -iname "*.mp3" | wc -l)
    echo "Project: $PROJECT" | tee -a "$RENDER_LOG"
    echo "Assets: $TOTAL_ASSETS (photos+videos)" | tee -a "$RENDER_LOG"
    echo "Music files: $MP3_COUNT" | tee -a "$RENDER_LOG"
    read -p "Continue? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        kill $LOGGER_PID 2>/dev/null
        exit 0
    fi
fi

if [ -n "$DRY_RUN" ]; then
    echo "Dry run – exiting." | tee -a "$RENDER_LOG"
    kill $LOGGER_PID 2>/dev/null
    exit 0
fi

# ====================================================================
# 9. Rendering loop (chunks)
# ====================================================================
start_time=$(date +%s)

for (( i=0; i<$TOTAL_ASSETS; i+=$BATCH_SIZE )); do
    START_IDX=$i
    END_IDX=$((i + BATCH_SIZE))
    echo ">>> Rendering batch $START_IDX to $END_IDX" | tee -a "$RENDER_LOG"
    # Activate venv and call Python script for this chunk
    source "$VENV_PATH"
    python3 "$PY_SCRIPT" "$PROJECT" "$START_IDX" "$END_IDX" --chunk-size "$BATCH_SIZE" 2>&1 | tee -a "$RENDER_LOG"
    deactivate
    # Move any generated part_*.mp4 to output folder
    if ls "$PICTURES_DIR"/part_*.mp4 1> /dev/null 2>&1; then
        mv "$PICTURES_DIR"/part_*.mp4 "$OUTPUT_DIR/"
    fi
done

# ====================================================================
# 10. Final stitch
# ====================================================================
echo "🦞 Stitching final master video..." | tee -a "$RENDER_LOG"
cd "$OUTPUT_DIR" || exit
rm -f "inputs.txt"
for f in $(ls -v part_*.mp4 2>/dev/null); do
    echo "file '$f'" >> "inputs.txt"
done

if [ -s "inputs.txt" ]; then
    ffmpeg -f concat -safe 0 -i inputs.txt -c copy "$FINAL_OUT" >> "$RENDER_LOG" 2>&1
    echo "✅ SUCCESS: $PROJECT Final Master Created!" | tee -a "$RENDER_LOG"
else
    echo "❌ ERROR: No parts found to stitch." | tee -a "$RENDER_LOG"
fi

# Kill the logger
kill $LOGGER_PID 2>/dev/null

# ====================================================================
# 11. Print total execution time (stitching only)
# ====================================================================
end_time=$(date +%s)
elapsed=$((end_time - start_time))
hours=$((elapsed / 3600))
minutes=$(((elapsed % 3600) / 60))
seconds=$((elapsed % 60))

# Get actual video duration from final master
if [ -f "$FINAL_OUT" ]; then
    VIDEO_DUR=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$FINAL_OUT")
    if [ -n "$VIDEO_DUR" ]; then
        dur_sec=$(printf "%.0f" "$VIDEO_DUR")
        dur_h=$((dur_sec / 3600))
        dur_m=$(((dur_sec % 3600) / 60))
        dur_s=$((dur_sec % 60))
        echo "Video duration: ${dur_h}h ${dur_m}m ${dur_s}s" | tee -a "$RENDER_LOG"
    fi
else
    echo "Final master not found." | tee -a "$RENDER_LOG"
fi

# Sum total rendering time from Python logs
if command -v bc &>/dev/null; then
    TOTAL_RENDER_SEC=0
    while IFS= read -r line; do
        if [[ $line =~ Total\ processing\ time:\ ([0-9.]+)\ seconds ]]; then
            TOTAL_RENDER_SEC=$(echo "$TOTAL_RENDER_SEC + ${BASH_REMATCH[1]}" | bc)
        fi
    done < "$RENDER_LOG"
    if (( $(echo "$TOTAL_RENDER_SEC > 0" | bc -l) )); then
        render_hours=$(echo "$TOTAL_RENDER_SEC / 3600" | bc)
        render_minutes=$(echo "($TOTAL_RENDER_SEC % 3600) / 60" | bc)
        render_seconds=$(echo "$TOTAL_RENDER_SEC % 60" | bc)
        echo "Total rendering time: ${render_hours}h ${render_minutes}m ${render_seconds}s" | tee -a "$RENDER_LOG"
    fi
else
    echo "Install bc to see cumulative rendering time: sudo apt install bc" | tee -a "$RENDER_LOG"
fi

echo "$TOTAL_ASSETS genuine assets." | tee -a "$RENDER_LOG"
echo "$FINAL_OUT -  codec name, and duration obtained by ffprobe:" 
ffprobe -v error -show_entries stream=codec_name:format=duration,size -of default=noprint_wrappers=1 "$FINAL_OUT"| awk -F= '
/codec_name/ {codecs = codecs (codecs ? ", " : "") $2}
/duration/ {dur = $2}
/size/ {sz = $2 / 1024 / 1024}
END {printf "codec_name=%s; duration=%s, file_size=%.2fMB\n", codecs, dur, sz}'

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   Cinematic Batch & Stitch Engine $VERSION  ($VERSION_DATE)          ║"
echo "╚══════════════════════════════════════════════════════════════╝"
