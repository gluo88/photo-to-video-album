# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Cinematic Video Album Generator v39.12** — a high-performance FFmpeg-based media orchestrator for Ubuntu that transforms photos, videos, and audio into professional cinematic videos. Pure FFmpeg pipeline (no MoviePy) delivers 5–10× faster encoding and lower memory usage than previous versions. Features smooth audio crossfading between looped music files.

**Key achievement:** Processes 232 photos into a 128-second video in 6 minutes 24 seconds on legacy hardware (Toshiba Satellite C50-A).

## Architecture

The system has three main entry points:

### 1. **Bash Wrapper** (`stitch_master.sh`)
- **Purpose:** User-facing orchestrator that handles chunking, concurrency, and stitching final output.
- **Entry point:** `./stitch_master.sh <project_name> [batch_size] [--yes] [--dry-run] [--init]`
- **Responsibilities:**
  - Parse arguments and validate project directory
  - Invoke the Python engine for each chunk (batch of assets)
  - Launch xterm dashboard for performance monitoring
  - Concatenate `part_XXXX_YYYY.mp4` chunks into `PROJECT_FINAL_MASTER.mp4`
  - Handle logging to `log_render.txt` and `log_perf.txt`

### 2. **Python Engine** (`make_video_album.py`)
- **Entry point:** Called by bash wrapper with project name, start/end indices, chunk size.
- **Core workflow:**
  1. Load `album_config.yaml` (create with defaults if missing)
  2. Discover all `.jpg`, `.png`, `.mp4`, `.mov`, `.avi` files in project directory
  3. For each asset in the chunk:
     - Load per-asset `.yaml` config (or legacy `.caption` file)
     - Process photo (Ken Burns effect + blurred background for square/portrait) or video (scale, pad, re-encode)
     - Add text overlays (album title, section title, caption, optional filename)
  4. Concatenate all segment MP4s into `part_XXXX_YYYY.mp4`
  5. Build background audio track by looping `.mp3` files, mux with video

### 3. **Configuration Files**

#### Global Config (`album_config.yaml`)
- Auto-generated with sensible defaults if missing
- Stores album metadata (title, subtitle), Ken Burns defaults, text styles, audio settings, output codec/fps
- Key sections:
  - `album:` — title/subtitle
  - `defaults.kenburns:` — zoom, pan direction, easing curve
  - `defaults.caption_style:` — font, size, color, position for per-asset captions
  - `section_style:` — font, size, color, position for album/section titles
  - `output:` — resolution (1920×1080), fps (24), codec (libx264), preset (ultrafast)
  - `audio:` — loop behavior, crossfade, optional list of MP3 files

#### Per-Asset Config (e.g., `photo.yaml` for `photo.jpg`)
- Optional; overrides global settings for one asset
- Supports: `text` (caption), `section` (title+subtitle), `kenburns` (zoom/pan/easing/duration), `style` (font/color/position overrides)
- Legacy `.caption` files still supported (plain text only)

## Key Concepts

### Ken Burns Effect
Smooth zoom + pan applied to photos. Configurable per asset or globally:
- `zoom`: final magnification (1.15 = 15% zoom)
- `pan`: direction (`center-to-top`, `top-left-to-bottom-right`, etc.)
- `easing`: acceleration curve (`linear`, `ease-in`, `ease-out`, `ease-in-out`)
- `duration`: seconds to display

### Blurred Background
Square/portrait photos (aspect ratio < 1.6) get a full-screen blurred background with the photo centered — eliminates black bars.

### Text Overlays
Three independent text layers, each with own style:
1. **Album title** — overlaid on first asset only, uses `section_style`
2. **Section title** — per-asset, overlaid on that asset, uses `section_style`
3. **Asset caption** — from `text:` field, uses `caption_style`
4. **Photo filename** (optional) — bottom-left corner, enable with `show_photo_filenames: true`

### Chunking
Large projects split into chunks (default 200 assets per chunk) to manage memory. Each chunk produces `part_XXXX_YYYY.mp4`. Bash wrapper stitches these into final master.

## Common Development Tasks

### Run a single project rendering
```bash
./stitch_master.sh myproject --yes
```

### Initialize a new project (create configs, no rendering)
```bash
./stitch_master.sh myproject --init
```

### Test with dry-run (scan assets, no rendering)
```bash
./stitch_master.sh myproject --dry-run
```

### Render with custom chunk size (larger = more memory)
```bash
./stitch_master.sh myproject 500 --yes
```

### Render Python engine directly (rarely used; bash wrapper is preferred)
```bash
python3 make_video_album.py myproject [start_idx] [end_idx] [--chunk-size N]
```

### Check logs during rendering
```bash
tail -f ~/Pictures/myproject/log_render.txt     # FFmpeg output, speed metrics
tail -f ~/Pictures/myproject/log_perf.txt       # CPU temp, encoding speed
```

## Important Implementation Details

### FFmpeg Filters
- **zoompan**: Implements Ken Burns effect on photos
- **drawtext**: Renders text overlays (requires libfreetype)
- **boxblur**: Creates blurred background for square/portrait photos
- **scale + pad**: Letterboxes all assets to 1920×1080
- **format=yuv420p**: Ensures universal playback compatibility

### Audio Pipeline
1. Discover all `.mp3` files (or use `audio.default_list` from config)
2. Cycle through them, creating a concat list until total duration ≥ video duration
3. Use `ffmpeg -f concat` to concatenate MP3s
4. Re-encode to AAC (`aac_low` profile, 192k bitrate)
5. Mux with video using `-shortest` to match video duration

### Text Handling
- Wraps long captions to 50 chars/line (configurable via `WRAP_LENGTH`)
- Uses temp files for drawtext (FFmpeg limitation — can't pass text directly)
- Supports Unicode/CJK if font is specified (e.g., Noto CJK fonts)

### Performance Tuning (for 8GB RAM systems)
- Default chunk size 200 works well for up to 500 assets
- For 1000+ assets, keep chunk size 200–500 (tested with 1388 photos in 56 min)
- Can expand swap to 16GB and use `fstrim` for SSD optimization if needed

### Version & Revision Notes
- Current version: v39.12 (Python engine) / v4.0 (bash wrapper)
- Key feature in v39.12: Audio crossfade between looped music files using FFmpeg's `acrossfade` filter
- Key fix in v39.11: Added `-r {fps}` to `process_video()` to prevent duration stretching when re-encoding
- Python script and README both have "Note to LLM" comments requesting preservation of version history and configuration details — respect these

## Key Files & Their Roles

| File | Purpose |
|------|---------|
| `stitch_master.sh` | Bash orchestrator; handles chunking, xterm dashboard, final stitching |
| `make_video_album.py` | Core Python engine; processes assets, builds segments, muxes audio with crossfade |
| `album_config.yaml` | Auto-generated; global settings for Ken Burns, text, audio, output |
| `yaml_template/` | Example configs for different use cases (Chinese fonts, H.265, etc.) |

## Known Constraints

1. **Project directory must be in `~/Pictures/<project_name>/`** — hardcoded in both scripts
2. **All assets in same directory** — no subdirectory scanning
3. **Asset order is alphabetical** — affects sequencing in final video
4. **Photos and videos are interleaved** — not grouped separately
5. **FFmpeg must have `drawtext` filter** — script warns if missing, text overlays become blank
6. **Fonts must be system-installed** — typically in `/usr/share/fonts/`
7. ~~**Audio is looped, not crossfaded with silence** — can sound abrupt if music is shorter than video~~ **[FIXED in v39.12+]** Audio now uses FFmpeg's `acrossfade` filter for smooth transitions

## Recently Implemented Features

- **Audio crossfade** (v39.12) — Uses FFmpeg's `acrossfade` filter to smoothly transition between looped music files (configurable duration via `audio.crossfade_seconds` in album_config.yaml, default 2 seconds)

## Future Enhancements (Not Yet Implemented)

Based on configuration structure, these are possible future additions but are NOT currently in the code:
- Opening/section card duration settings (config fields present, not fully wired)
- Custom background colors (config field exists, not used)

## Important Notes for Future Work

1. **Preserve version history** — The `README.md` has "Note to LLM" comments requesting that revision history and configuration details be kept when updating.
2. **Test on legacy hardware** — Performance tuning is specifically for Toshiba Satellite C50-A; changes that add memory overhead should be tested on that or similar systems.
3. **Chinese character support** — System can handle CJK if fonts are specified; Noto CJK fonts are the default fallback.
