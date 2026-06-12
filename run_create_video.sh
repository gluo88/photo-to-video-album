#!/bin/bash
# Cinematic Batch & Stitch Engine
# Revisions
# v3.3 – Fixed xterm logger recursion
# v3.4 – New log naming: log_perf.txt and log_render.txt
# v3.5 – with version and audio logging
# v3.6 – with cumulative rendering time
# v4.0 - merged. Combines run_video.sh and run_create_video.sh into one script.
# v4.1 - Separated audio stitching to prevent loop resets across chunks.
# v4.2 - Removed --yes flag / confirmation prompt. Defaults to auto-continue.
# v4.3 - Added --clear-config and --migrate flags (delegates to make_video_album.py v42.0)
# v4.4 - Renamed stitch_master.sh → run_create_video.sh (2026-06-10)
# v4.5 - Added --location-only flag, updated help text for non-rendering modes
#
# Usage: ./run_create_video.sh <project_name> [batch_size] [--dry-run] [--init] [--migrate] [--clear-config] [--location-only]
# Example:
#        ./run_create_video.sh  z_SanXingDuiMuseumX 200 --dry-run
#
#  To LLM：Please keep all valid comments and other information when updating!!! (please keep this line.)

# current version:
VERSION="4.6"
VERSION_DATE="2026-06-11"
# v4.6  2026-06-11  Detailed TIMING REPORT at end of run.
#                   Concat and audio steps wrapped in bash timers.
#                   Python emits Location resolution time + Chunk rendering time.

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
DRY_RUN=""
INIT_FLAG=""
MIGRATE_FLAG=""
CLEAR_CONFIG_FLAG=""
LOCATION_ONLY_FLAG=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --chunk-size)   # legacy alias for batch_size
            BATCH_SIZE="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN="--dry-run"
            shift
            ;;
        --init)
            INIT_FLAG="--init"
            shift
            ;;
        --migrate)
            MIGRATE_FLAG="--migrate"
            shift
            ;;
        --clear-config)
            CLEAR_CONFIG_FLAG="--clear-config"
            shift
            ;;
        --location-only)
            LOCATION_ONLY_FLAG="--location-only"
            shift
            ;;
        --help|-h)
            echo "Usage: ./run_create_video.sh <project_name> [batch_size] [options]"
            echo ""
            echo "Options:"
            echo "  --dry-run        Asset discovery only, no rendering"
            echo "  --init           Generate config files (album_config.yaml + geo_timeline.yaml)"
            echo "  --migrate        Migrate legacy per-asset .yaml files into geo_timeline.yaml (no rendering)"
            echo "  --clear-config   Clean geo_timeline.yaml (remove stale, clear locations, remove legacy)"
            echo "  --location-only  Query server to fill all empty location fields, then exit (no rendering)"
            echo "  --chunk-size N   Assets per chunk (default: 200)"
            echo ""
            echo "Examples:"
            echo "  ./run_create_video.sh park_pottery --init"
            echo "  ./run_create_video.sh park_pottery --migrate"
            echo "  ./run_create_video.sh park_pottery --clear-config"
            echo "  ./run_create_video.sh park_pottery --location-only"
            echo "  ./run_create_video.sh z_Europe 200"
            exit 0
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
    echo "Usage: ./run_create_video.sh <project_name> [batch_size] [options]"
    echo ""
    echo "Options:"
    echo "  --dry-run        Asset discovery only, no rendering"
    echo "  --init           Generate config files (album_config.yaml + geo_timeline.yaml)"
    echo "  --migrate        Migrate legacy per-asset .yaml files into geo_timeline.yaml (no rendering)"
    echo "  --clear-config   Clean geo_timeline.yaml (remove stale, clear locations, remove legacy)"
    echo "  --location-only  Query server to fill all empty location fields, then exit (no rendering)"
    echo "  --chunk-size N   Assets per chunk (default: 200)"
    echo ""
    echo "Examples:"
    echo "  ./run_create_video.sh park_pottery --init"
    echo "  ./run_create_video.sh park_pottery --migrate"
    echo "  ./run_create_video.sh park_pottery --clear-config"
    echo "  ./run_create_video.sh park_pottery --location-only"
    echo "  ./run_create_video.sh z_Europe 200"
    exit 1
fi

# ====================================================================
# 3. Paths and project directory
# ====================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
PICTURES_DIR="/home/gluo/Pictures/$PROJECT"
OUTPUT_DIR="$PICTURES_DIR/output"
FINAL_OUT="$PICTURES_DIR/${PROJECT}_FINAL_MASTER.mp4"
PERF_LOG="$PICTURES_DIR/log_perf.txt"
RENDER_LOG="$PICTURES_DIR/log_render.txt"
PY_SCRIPT="$SCRIPT_DIR/make_video_album.py"
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
# 5. Launch xterm dashboard (unless --dry-run, --init, --migrate, or --clear-config)
# ====================================================================
if [ -z "$DRY_RUN" ] && [ -z "$INIT_FLAG" ] && [ -z "$MIGRATE_FLAG" ] && [ -z "$CLEAR_CONFIG_FLAG" ] && [ -z "$LOCATION_ONLY_FLAG" ]; then
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
    # Call Python script with --init (creates album_config.yaml + geo_timeline.yaml)
    source "$VENV_PATH"
    python3 "$PY_SCRIPT" "$PROJECT" 0 999999 --init 2>&1 | tee -a "$RENDER_LOG"
    deactivate
    # Kill logger if running
    kill $LOGGER_PID 2>/dev/null
    echo "Initialisation complete." | tee -a "$RENDER_LOG"
    exit 0
fi

# ====================================================================
# 7b. Handle --migrate: migrate per-asset yamls to geo_timeline.yaml
# ====================================================================
if [ -n "$MIGRATE_FLAG" ]; then
    echo "🦞 --migrate mode: migrating legacy per-asset configs to geo_timeline.yaml." | tee -a "$RENDER_LOG"
    source "$VENV_PATH"
    python3 "$PY_SCRIPT" "$PROJECT" --migrate 2>&1 | tee -a "$RENDER_LOG"
    deactivate
    kill $LOGGER_PID 2>/dev/null
    echo "Migration complete. Run --clear-config to remove legacy .yaml files." | tee -a "$RENDER_LOG"
    exit 0
fi

# ====================================================================
# 7c. Handle --clear-config: clean geo_timeline.yaml
# ====================================================================
if [ -n "$CLEAR_CONFIG_FLAG" ]; then
    echo "🦞 --clear-config mode: cleaning geo_timeline.yaml." | tee -a "$RENDER_LOG"
    source "$VENV_PATH"
    python3 "$PY_SCRIPT" "$PROJECT" --clear-config 2>&1 | tee -a "$RENDER_LOG"
    deactivate
    kill $LOGGER_PID 2>/dev/null
    echo "Configuration cleaned." | tee -a "$RENDER_LOG"
    exit 0
fi

# ====================================================================
# 7d. Handle --location-only: resolve location fields only
# ====================================================================
if [ -n "$LOCATION_ONLY_FLAG" ]; then
    echo "🦞 --location-only mode: resolving location fields from GPS data." | tee -a "$RENDER_LOG"
    source "$VENV_PATH"
    python3 "$PY_SCRIPT" "$PROJECT" --location-only 2>&1 | tee -a "$RENDER_LOG"
    deactivate
    kill $LOGGER_PID 2>/dev/null
    echo "Location resolution complete." | tee -a "$RENDER_LOG"
    exit 0
fi

# ====================================================================
# 8. Project summary (informational only, auto-continue)
# ====================================================================
MP3_COUNT=$(find "$PICTURES_DIR" -maxdepth 1 -iname "*.mp3" | wc -l)
echo "Project: $PROJECT" | tee -a "$RENDER_LOG"
echo "Assets: $TOTAL_ASSETS (photos+videos)" | tee -a "$RENDER_LOG"
echo "Music files: $MP3_COUNT" | tee -a "$RENDER_LOG"

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
# 10. Final stitch and Global Audio Mux
# ====================================================================
echo "🦞 Stitching final master video..." | tee -a "$RENDER_LOG"
cd "$OUTPUT_DIR" || exit
rm -f "inputs.txt"
for f in $(ls -v part_*.mp4 2>/dev/null); do
    echo "file '$f'" >> "inputs.txt"
done

if [ -s "inputs.txt" ]; then
    # Stitch video parts together (silent)
    concat_start=$(date +%s)
    ffmpeg -f concat -safe 0 -i inputs.txt -c copy "$FINAL_OUT" >> "$RENDER_LOG" 2>&1
    concat_end=$(date +%s)
    CONCAT_SEC=$((concat_end - concat_start))
    echo "✅ SUCCESS: Video parts stitched (Silent)." | tee -a "$RENDER_LOG"
    
    # Run the Python script in audio-only mode on the final stitched master
    audio_start=$(date +%s)
    echo "🦞 Generating continuous audio track and muxing into final master..." | tee -a "$RENDER_LOG"
    source "$VENV_PATH"
    python3 "$PY_SCRIPT" "$PROJECT" --add-audio "$FINAL_OUT" 2>&1 | tee -a "$RENDER_LOG"
    deactivate
    audio_end=$(date +%s)
    AUDIO_SEC=$((audio_end - audio_start))
    
    echo "✅ SUCCESS: $PROJECT Final Master Created with Audio!" | tee -a "$RENDER_LOG"
else
    echo "❌ ERROR: No parts found to stitch." | tee -a "$RENDER_LOG"
fi

# Kill the logger
kill $LOGGER_PID 2>/dev/null

# ====================================================================
# 11. Timing report (detailed breakdown)
# ====================================================================

# Aggregate location resolution time from Python logs
LOCATION_SEC=0
RENDER_SEC=0
if command -v bc &>/dev/null; then
    while IFS= read -r line; do
        if [[ $line =~ Location\ resolution\ time:\ ([0-9.]+)\ seconds ]]; then
            LOCATION_SEC=$(echo "$LOCATION_SEC + ${BASH_REMATCH[1]}" | bc)
        fi
        if [[ $line =~ Chunk\ rendering\ time:\ ([0-9.]+)\ seconds ]]; then
            RENDER_SEC=$(echo "$RENDER_SEC + ${BASH_REMATCH[1]}" | bc)
        fi
    done < "$RENDER_LOG"
fi

# Wall-clock total since first python call
total_wall_end=$(date +%s)
TOTAL_WALL=$((total_wall_end - start_time))

# Format helper (prints Xh Ym Zs)
fmt_time() {
    local s=$1
    local h=$((s / 3600))
    local m=$(((s % 3600) / 60))
    local sec=$((s % 60))
    if [ "$h" -gt 0 ]; then echo "${h}h ${m}m ${sec}s"
    elif [ "$m" -gt 0 ]; then echo "${m}m ${sec}s"
    else echo "${sec}s"
    fi
}

SUM_ALL=$(( $(echo "$LOCATION_SEC + $RENDER_SEC + ${CONCAT_SEC:-0} + ${AUDIO_SEC:-0}" | bc 2>/dev/null | cut -d. -f1) ))

# Print timing report (plain rows, easy to copy-paste)
echo "" | tee -a "$RENDER_LOG"
echo "📊 TIMING REPORT" | tee -a "$RENDER_LOG"
echo "Location fetching  : $(fmt_time "$(echo "$LOCATION_SEC/1" | bc 2>/dev/null || echo 0)") ($(printf "%.0f" "$LOCATION_SEC")s)" | tee -a "$RENDER_LOG"
echo "Rendering          : $(fmt_time "$(echo "$RENDER_SEC/1" | bc 2>/dev/null || echo 0)") ($(printf "%.0f" "$RENDER_SEC")s)" | tee -a "$RENDER_LOG"
echo "Concatenation      : $(fmt_time "${CONCAT_SEC:-0}") (${CONCAT_SEC:-0}s)" | tee -a "$RENDER_LOG"
echo "Audio mixing       : $(fmt_time "${AUDIO_SEC:-0}") (${AUDIO_SEC:-0}s)" | tee -a "$RENDER_LOG"
echo "Sum of components  : $(fmt_time "$SUM_ALL") ($SUM_ALL s)" | tee -a "$RENDER_LOG"
echo "Wall-clock total   : $(fmt_time "$TOTAL_WALL") ($TOTAL_WALL s)" | tee -a "$RENDER_LOG"
echo "Gap (overhead)     : $(fmt_time "$((TOTAL_WALL - SUM_ALL))") ($((TOTAL_WALL - SUM_ALL)) s) — Logger, ffprobe, file I/O, script glue" | tee -a "$RENDER_LOG"

# Video metadata
echo "" | tee -a "$RENDER_LOG"
echo "$TOTAL_ASSETS genuine assets." | tee -a "$RENDER_LOG"
if [ -f "$FINAL_OUT" ]; then
    VIDEO_DUR=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$FINAL_OUT")
    if [ -n "$VIDEO_DUR" ]; then
        echo "Video duration: $(fmt_time "$(printf "%.0f" "$VIDEO_DUR")")" | tee -a "$RENDER_LOG"
    fi
fi
echo "$FINAL_OUT - codec name, and duration obtained by ffprobe:" 
ffprobe -v error -show_entries stream=codec_name:format=duration,size -of default=noprint_wrappers=1 "$FINAL_OUT"| awk -F= '
/codec_name/ {codecs = codecs (codecs ? ", " : "") $2}
/duration/ {dur = $2}
/size/ {sz = $2 / 1024 / 1024}
END {printf "codec_name=%s; duration=%s, file_size=%.2fMB\n", codecs, dur, sz}'

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   Cinematic Batch & Stitch Engine $VERSION  ($VERSION_DATE)          ║"
echo "╚══════════════════════════════════════════════════════════════╝"
