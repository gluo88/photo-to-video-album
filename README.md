LLM：Please keep all valid information when updating!!! (please keep this line.)

================================================================================
Cinematic Batch & Stitch Engine (v40.0) - Documentation
================================================================================

DESCRIPTION:
A high‑performance, FFmpeg‑based media orchestrator for Ubuntu that transforms 
photos, videos, and audio into a professional cinematic video.  
All assets are processed with a pure FFmpeg pipeline (no MoviePy), resulting in 
**5–10× faster encoding** and much lower memory usage. 

Optimized for legacy hardware like a Toshiba Satellite C50-A running Ubuntu,
the latest version delivers a 20–30× speed increase over v34/v35, processing 232
photos into a 128-second (2:08) video with a 57.6-second chunk processing time 
and a total render and stitch time of 6 minutes 24 seconds.  

**Key Improvements over v34:**
- Pure FFmpeg engine (zoompan, drawtext, boxblur) – dramatically faster
- YAML configuration (album_config.yaml) – all settings in one place
- Per‑asset YAML files (.yaml) replace simple .caption files
- Title overlays on the first asset (no separate black title cards)
- Separate styles for section titles (large, gold) and asset captions (smaller, white)
- Blurred background for square/portrait photos (centered, no black bars)
- Optional photo filename overlay (bottom‑left corner, configurable)
- Fixed video frame rate conversion – no duration stretching
- **Audio crossfade between looped music files** – smooth transitions using FFmpeg acrossfade filter (v39.12+)
- **Global audio muxing** – audio is now generated as one continuous track for the entire stitched master, eliminating loop resets at chunk boundaries (v40.0+)
- Full logging: log_render.txt (render output) and log_perf.txt (performance)
- Xterm dashboard showing CPU temperature and encoding speed
- Automatic template generation for configuration files
- Full Unicode/Chinese character support (using Noto CJK fonts)


**Visual Assets:**
   • Photos (.jpg, .png) – Ken Burns effect (zoom + pan) applied via FFmpeg zoompan filter.
   • Video clips (.mp4, .mov, .avi) – seamlessly integrated (audio removed, replaced by background music). Videos are re‑encoded to match the output frame rate (default 24 fps) to preserve original duration.

**Audio Assets:**
   • Multiple background music files (.mp3) – automatically looped to match video duration.
   • Audio crossfades smoothly between files using FFmpeg's acrossfade filter (v39.12+).
   • Crossfade duration configurable via `audio.crossfade_seconds` in album_config.yaml (default: 2 seconds).
   • Audio is now muxed into the final stitched master (not per-chunk) so music loops and crossfades are seamless across the entire album (v40.0+).
   • The render log prints a timestamped audio timeline showing which track starts at which point (MM:SS.ss).
   • Audio is re‑encoded to AAC for universal compatibility.

**Text Captions (YAML based):**
   • For any photo or video, create a .yaml file with the same base name.
   • The .yaml file can contain:
        - `text:` – the caption to overlay
        - `section:` – title/subtitle that will appear on this asset (see below)
        - `kenburns:` – override zoom, pan, easing, duration for that photo
        - `style:` – override font, size, color, position, background (applies to caption)
   • Legacy .caption files are still supported (treated as plain text).

**Title Cards (no separate black screens):**
   • Album title and subtitle (from album_config.yaml) are overlaid on the **first asset** only.
   • Section titles (defined in a per‑asset .yaml under `section:`) are overlaid on that specific asset.
   • Multiple text sources are combined into separate overlays: section title (top) and caption (bottom) with independent styles.

**Key Features:**
   • **Ken Burns Effect**: Zoom + pan with configurable direction and easing (linear, ease‑in, ease‑out, ease‑in‑out).
   • **Separate Text Styles**: Section titles (default 56px, gold, top) and asset captions (default 40px, white, bottom) can be customised independently in album_config.yaml.
   • **Blurred Background**: For square/portrait photos (aspect ratio < 1.6), a full‑screen blurred version is used as background, with the photo centred – eliminates black bars.
   • **Photo Filename Overlay** (optional): Enable `show_photo_filenames: true` in `album_config.yaml` to display each photo's filename at bottom‑left corner (small white text on semi‑transparent black background). Videos are not overlaid.
   • **Smart Timeline Construction**: Assets sorted alphabetically; photos and videos interleaved.
   • **1080p Cinematic Output**: All assets scaled to 1920×1080, letterboxed, with forced yuv420p pixel format for universal playback.
   • **Fast Encoding**: Preset `ultrafast` by default, configurable in album_config.yaml.
   • **Streaming Optimized**: moov atom moved to beginning (`+faststart`).
   • **Chunked Processing**: Default 200 assets per chunk (adjustable via command line or script default). Tested with 1500 assets in one chunk.

**Example Asset Structure (modern):**
~/Pictures/myProject/
├── album_config.yaml
├── vacation_photo1.jpg
├── vacation_photo1.yaml          # contains caption, section, kenburns, style
├── vacation_photo2.png
├── vacation_video.mp4
├── vacation_video.yaml           # optional text or section
├── background_music_1.mp3
├── background_music_2.mp3
└── background_music_3.mp3

**Processing Flow (v40.0):**
1. Scan project directory for all .jpg, .png, .mp4, .mov, .avi.
2. Load album_config.yaml (create default with comments if missing). The default config includes `section_style` and `caption_style` with Chinese‑capable font path.
3. For each asset:
   a. If no .yaml exists for the first asset, create a commented template.
   b. Build separate text strings: section text (album + section titles) and asset caption.
   c. Process photo:
        - If aspect ratio < 1.6: create blurred full‑screen background, then overlay scaled photo (centered), apply Ken Burns to the photo.
        - Else: scale, pad, apply zoompan (Ken Burns).
   d. Process video: scale, pad, remove original audio, force output frame rate (`-r`), encode to H.264.
   e. Overlay section text (using `section_style`) and caption text (using `caption_style`), and optionally photo filename (bottom‑left, small gray/white).
4. Concatenate all segments into a part_*.mp4 file (silent – no audio track).
5. The bash wrapper (stitch_master.sh) repeats steps 1–4 for each chunk, then stitches all silent parts into the final master.
6. After stitching, build one continuous background audio track for the full video duration (looping MP3 files with smooth crossfades, v40.0+), mux into the final master, add faststart flag.

1. INPUTS:
   -- Visual Assets: Photos (.jpg, .png) and videos (.mp4, .mov, .avi).
   -- Audio Assets: One or more .mp3 files (looped automatically).
   -- Configuration: album_config.yaml (global) and per‑asset .yaml files.

2. DIRECTORY STRUCTURE & ASSET NAMING:
   All assets must reside in the same project folder under ~/Pictures/.
   Example: ~/Pictures/neighbourhoodWinterScenes/

   * **album_config.yaml** – created automatically if missing; contains all global settings with inline comments explaining every option (Ken Burns, captions, audio, output, `section_style`, `show_photo_filenames`). The default template now includes a clean, non‑duplicated configuration.
   * **Per‑asset .yaml** – for any photo or video, create a file with the same base name but .yaml extension.
        Example: For "PXL_20251110_190845826.jpg", create "PXL_20251110_190845826.yaml"
        The engine reads `text:`, `section:`, `kenburns:`, `style:`.
   * **Legacy .caption files** – still supported (plain text only, no overrides).

   * **Music Files** – all .mp3 files are detected and looped. You can specify a subset in album_config.yaml under `audio.default_list`.

3. OUTPUTS:
   -- Final Master Video: Saved in the project's /output/ folder as ${PROJECT}_FINAL_MASTER.mp4.
   -- log_render.txt: Contains all console output (timestamps, FFmpeg messages, etc.).
   -- log_perf.txt: Contains periodic CPU temperature and encoding speed (from xterm dashboard).

4. EXECUTION / CLI USAGE:
   The pipeline is triggered via the Bash wrapper. Do not run the Python script directly.

   Syntax:
        ./stitch_master.sh <project_name> [batch_size] [--yes] [--dry-run] [--init]

   Examples:
        ./stitch_master.sh neighbourhoodWinterScenes
        ./stitch_master.sh neighbourhoodWinterScenes 200 --yes
        ./stitch_master.sh new_project --init   # generate config files only

   Options:
        batch_size        Number of assets per chunk (default 200). Larger chunks (e.g., 1500) work well for up to ~1500 assets; for very large projects, reduce to 100–200.
        --yes             Skip pre‑flight confirmation prompt.
        --dry-run         Only scan assets, do not render.
        --init            Create album_config.yaml and a per‑asset template for the first asset, then exit (no rendering).

5. PERFORMANCE & TUNE‑UP (8GB RAM systems):
   The pure FFmpeg engine is very memory‑efficient. However, for large projects (hundreds of assets), the following steps are recommended:

   A. Expand Swap Memory to 16GB (if not already done):
        sudo swapoff -a
        sudo dd if=/dev/zero of=/swapfile bs=1G count=16
        sudo chmod 600 /swapfile
        sudo mkswap /swapfile
        sudo swapon /swapfile
        free -h

   B. SSD Clean & Speed Boost:
        sudo fstrim -av

   C. Tune chunk size: The default is 200, which works well for up to 500 assets. For extremely large projects (1000+ photos), keep chunk size at 200–500; for smaller projects, you can increase to 1500 (tested with 1388 photos in 56 minutes).

6. CUSTOMIZATION
  A. album_config.yaml:
   The configuration file is heavily commented. Key settings:
   - `output.preset`: "ultrafast" (fastest), "veryfast", "medium", "slow", "veryslow"
   - `defaults.kenburns.pan`: direction of zoom (center-to-top, top-left-to-bottom-right, etc.)
   - `defaults.kenburns.easing`: acceleration curve
   - `defaults.caption_style`: font, size, color, background, position (for per‑asset captions)
   - `section_style`: font, size, color, position (for album and section titles)
   - `defaults.show_photo_filenames`: `true` or `false` – overlay photo filenames (bottom‑left, small gray/white)
   - `audio.default_list`: restrict which MP3 files are used
   - `audio.crossfade_seconds`: duration of crossfade between looped audio files (default: 2 seconds, v39.12+)
   It is entirely optional; if missing, the engine creates a clean one with detailed comments and reasonable defaults, including Chinese‑capable font paths (Noto CJK) if available.

   For Chinese (or other non‑Latin) characters, ensure the font in `caption_style` and `section_style` points to a font that supports those characters, e.g.:
        font: "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"

  B. Per‑asset .yaml file (e.g., vacation_photo1.yaml)
   This file overrides global settings for a specific photo or video.
   It is entirely optional; if missing, the engine uses album defaults.

   Supported fields (all optional):

   ┌─────────────────┬──────────────────────────────────────────────────┐
   │ Field           │ Description                                      │
   ├─────────────────┼──────────────────────────────────────────────────┤
   │ text            │ Caption to overlay on this asset.                │
   │                 │ Example: `text: "Beautiful sunset"`              │
   ├─────────────────┼──────────────────────────────────────────────────┤
   │ section         │ Inserts a section title overlaid on this asset   │
   │                 │ (not a separate card). Sub‑fields:               │
   │                 │   title   – required, main heading               │
   │                 │   subtitle – optional, smaller secondary text    │
   │                 │ Example:                                         │
   │                 │   section:                                       │
   │                 │     title: "Golden Hour"                         │
   │                 │     subtitle: "Beach walk"                       │
   ├─────────────────┼──────────────────────────────────────────────────┤
   │ kenburns        │ Overrides Ken Burns motion for this photo only   │
   │                 │ (ignored for videos). Sub‑fields:                │
   │                 │   zoom     – final zoom factor (1.15 = 15%)      │
   │                 │   pan      – direction (e.g., "center-to-top")   │
   │                 │   easing   – acceleration curve                  │
   │                 │   duration – seconds to show this photo          │
   │                 │ Example:                                         │
   │                 │   kenburns:                                      │
   │                 │     zoom: 1.3                                    │
   │                 │     pan: "top-left-to-bottom-right"              │
   │                 │     easing: "ease-out"                           │
   │                 │     duration: 6                                  │
   ├─────────────────┼──────────────────────────────────────────────────┤
   │ style           │ Overrides caption appearance for this asset only.│
   │                 │ Sub‑fields (same as in album_config.yaml):       │
   │                 │   font, font_size, font_color, bg_color, position│
   │                 │ Example:                                         │
   │                 │   style:                                         │
   │                 │     font_size: 56                                │
   │                 │     font_color: "#FFD700"                        │
   │                 │     position: "top"                              │
   └─────────────────┴──────────────────────────────────────────────────┘

   **Combining texts**: Album title (first asset only), section title, and `text:` are displayed as separate overlays, each using its own style (section style for album/section titles, caption style for asset text). They appear at their respective positions (e.g., title at top, caption at bottom). If `show_photo_filenames` is enabled, the filename appears at bottom‑left, independent of other texts.

   **Example full per‑asset .yaml**:
   ```yaml
   text: "Walking along the shore"
   section:
     title: "Evening Stroll"
     subtitle: "Sunset reflections"
   kenburns:
     zoom: 1.25
     pan: "center-to-top"
     easing: "ease-in-out"
   style:
     font_size: 52
     font_color: "#FFE4B5"
     position: "bottom"

