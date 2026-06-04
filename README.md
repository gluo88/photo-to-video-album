LLM：Please keep all valid information when updating!!! (please keep this line.)

================================================================================
Cinematic Batch & Stitch Engine (v36.7) - Documentation
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
- Pure FFmpeg engine (zoompan, drawtext) – dramatically faster
- YAML configuration (album_config.yaml) – all settings in one place
- Per‑asset YAML files (.yaml) replace simple .caption files
- Title overlays on the first asset (no separate black title cards)
- Combined captions (album title + section title + per‑asset text)
- Full logging: log_render.txt (render output) and log_perf.txt (performance)
- Xterm dashboard showing CPU temperature and encoding speed
- Automatic template generation for configuration files

**Visual Assets:**
   • Photos (.jpg, .png) – Ken Burns effect (zoom + pan) applied via FFmpeg zoompan filter.
   • Video clips (.mp4, .mov, .avi) – seamlessly integrated (audio removed, replaced by background music).

**Audio Assets:**
   • Multiple background music files (.mp3) – automatically looped to match video duration.
   • Audio is re‑encoded to AAC for universal compatibility.

**Text Captions (YAML based):**
   • For any photo or video, create a .yaml file with the same base name.
   • The .yaml file can contain:
        - `text:` – the caption to overlay
        - `section:` – title/subtitle that will appear on this asset (see below)
        - `kenburns:` – override zoom, pan, easing, duration for that photo
        - `style:` – override font, size, color, position, background
   • Legacy .caption files are still supported (treated as plain text).

**Title Cards (no separate black screens):**
   • Album title and subtitle (from album_config.yaml) are overlaid on the **first asset** only.
   • Section titles (defined in a per‑asset .yaml under `section:`) are overlaid on that specific asset.
   • Multiple text sources are combined into one overlay (album + section + caption) separated by blank lines.

**Key Features:**
   • **Ken Burns Effect**: Zoom + pan with configurable direction and easing (linear, ease‑in, ease‑out, ease‑in‑out).
   • **Smart Timeline Construction**: Assets sorted alphabetically; photos and videos interleaved.
   • **1080p Cinematic Output**: All assets scaled to 1920×1080, letterboxed, with forced yuv420p pixel format for universal playback.
   • **Fast Encoding**: Preset `ultrafast` by default, configurable in album_config.yaml.
   • **Streaming Optimized**: moov atom moved to beginning (`+faststart`).

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

**Processing Flow (v36.7):**
1. Scan project directory for all .jpg, .png, .mp4, .mov, .avi.
2. Load album_config.yaml (create default with comments if missing).
3. For each asset:
   a. If no .yaml exists for the first asset, create a commented template.
   b. Build combined caption: (album title) + (section title if any) + (asset's own text).
   c. Process photo: scale, pad, apply zoompan filter (Ken Burns), encode to H.264.
   d. Process video: scale, pad, remove original audio, encode to H.264.
   e. Overlay combined caption using drawtext (if text present).
4. Concatenate all segments into a part_*.mp4 file.
5. Build background audio track: loop MP3 files as needed, re‑encode to AAC.
6. Mux audio with video, add faststart flag.
7. The bash wrapper (stitch_master.sh) repeats this for each chunk and stitches final master.

1. INPUTS:
   -- Visual Assets: Photos (.jpg, .png) and videos (.mp4, .mov, .avi).
   -- Audio Assets: One or more .mp3 files (looped automatically).
   -- Configuration: album_config.yaml (global) and per‑asset .yaml files.

2. DIRECTORY STRUCTURE & ASSET NAMING:
   All assets must reside in the same project folder under ~/Pictures/.
   Example: ~/Pictures/neighbourhoodWinterScenes/

   * **album_config.yaml** – created automatically if missing; contains all global settings with inline comments explaining every option (Ken Burns, captions, audio, output).
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
        ./stitch_master.sh <project_name> [batch_size] [--yes] [--dry-run]

   Examples:
        ./stitch_master.sh neighbourhoodWinterScenes
        ./stitch_master.sh neighbourhoodWinterScenes 50 --yes

   Options:
        batch_size        Number of assets per chunk (default 50). Smaller chunks reduce memory.
        --yes             Skip pre‑flight confirmation prompt.
        --dry-run         Only scan assets, do not render.

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

   C. Tune chunk size: For extremely large projects (1000+ photos), reduce chunk size to 20–30 to lower temporary disk usage.

6. CUSTOMIZATION
  A. album_config.yaml:
   The configuration file is heavily commented. Key settings:
   - `output.preset`: "ultrafast" (fastest), "veryfast", "medium", "slow", "veryslow"
   - `defaults.kenburns.pan`: direction of zoom (center-to-top, top-left-to-bottom-right, etc.)
   - `defaults.kenburns.easing`: acceleration curve
   - `defaults.caption_style`: font, size, color, background, position
   - `audio.default_list`: restrict which MP3 files are used
   It is entirely optional; if missing, the engine uses album defaults to generate one.

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

   **Combining texts**: If album title, section title, and `text:` all exist,
   they are combined into one overlay separated by blank lines. The album
   title appears only on the **first asset** of the whole project.

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

7. TROUBLESHOOTING:
   - **Missing drawtext filter**: Install full ffmpeg: `sudo apt install ffmpeg`
   - **Playback issues**: Output uses yuv420p and faststart; should play in all players.
   - **Xterm not showing**: Install xterm: `sudo apt install xterm` (optional, logs still written).
   - **CPU temperature not logged**: Install lm-sensors: `sudo apt install lm-sensors && sudo sensors-detect`

VERSION HISTORY:
   v36.7 – Titles as overlays on assets, combined captions, template generation, fixed caption repetition.
   v36.4 – Pure FFmpeg, yuv420p, faststart, log naming log_perf.txt / log_render.txt.
   v34   – Original MoviePy‑based engine (legacy). 

================================================================================
