LLM：Please keep all valid information when updating!!! (please keep this line.)

================================================================================
Cinematic Video Album Generator (v41.6) - Documentation
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
- Title overlays on assets (no separate black title cards)
- Separate styles for section titles (large, gold) and asset captions (smaller, white)
- Blurred background for square/portrait photos (centered, no black bars)
- Optional photo filename overlay (bottom‑left corner, configurable)
- **Geolocation overlay** – automatically fetches location from photo EXIF GPS (with caching)
- **Global timeline tracking** (`geo_timeline.yaml`) – stores GPS, location, start time, duration
- **Geo engine merged into main pipeline** – no separate `photo_geo.py`; location queries happen inline during chunk processing with Nominatim rate‑limit compliance (1s between requests)
- **Audio stitching after video concatenation** – prevents loop resets across chunks, supports crossfade
- Fixed video frame rate conversion – no duration stretching
- Full logging: log_render.txt (render output) and log_perf.txt (performance)
- Xterm dashboard showing CPU temperature and encoding speed
- Automatic template generation for configuration files
- Full Unicode/Chinese character support (using Noto CJK fonts)

**Visual Assets:**
   • Photos (.jpg, .png) – Ken Burns effect (zoom + pan) applied via FFmpeg zoompan filter.
   • Video clips (.mp4, .mov, .avi) – seamlessly integrated (audio removed, replaced by background music). Videos are re‑encoded to match the output frame rate (default 24 fps) to preserve original duration.

**Audio Assets:**
   • Multiple background music files (.mp3) – automatically looped and crossfaded to match video duration.
   • Audio is re‑encoded to AAC with smooth crossfade (default 2 seconds) between tracks.
   • Audio is added **after** final video stitching (no reset between chunks).

**Text Overlays (YAML based):**
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
   • Multiple text sources are combined into separate overlays: section title (top), caption (bottom), and location (bottom‑left) with independent styles.

**Text Overlay Layers (bottom‑left):**
   • **Filename** (optional, configurable via `show_photo_filenames`) – small white text at bottom‑left.
   • **Location** – displayed above the filename (if shown) or at bottom‑left otherwise, font size = 40, semi‑transparent background. Auto‑fetched from GPS EXIF via Nominatim, cached in `geo_timeline.yaml`.

**Geolocation Overlay:**
   • For photos with GPS EXIF data, the engine automatically fetches a human‑readable location (town, city, landmark) using Nominatim (OpenStreetMap).
   • The location is cached in `geo_timeline.yaml` to avoid repeated API calls.
   • You can manually override the location by editing `geo_timeline.yaml` and setting `location_correction`.
   • The location text appears at bottom‑left (font size = 40, semi‑transparent background) above the filename (if enabled).
   • **Captions do not contain landmark information** – landmark is a separate overlay layer.
   • **No per‑photo YAML for location storage** – location data lives exclusively in `geo_timeline.yaml`.

**Key Features:**
   • **Ken Burns Effect**: Zoom + pan with configurable direction and easing (linear, ease‑in, ease‑out, ease‑in‑out).
   • **Separate Text Styles**: Section titles (default 56px, gold, top) and asset captions (default 40px, white, bottom) can be customised independently in album_config.yaml.
   • **Blurred Background**: For square/portrait photos (aspect ratio < 1.6), a full‑screen blurred version is used as background, with the photo centred – eliminates black bars.
   • **Photo Filename Overlay** (optional): Enable `show_photo_filenames: true` in `album_config.yaml` to display each photo's filename at bottom‑left corner (small white text on semi‑transparent black background). Videos are not overlaid.
   • **Location Overlay** (automatic): Font size = 40, shown above filename at bottom‑left. Override location text via `location_correction` in `geo_timeline.yaml`.
   • **Smart Timeline Construction**: Assets sorted alphabetically; photos and videos interleaved.
   • **Global Timeline File**: `geo_timeline.yaml` stores for each asset: start time, duration, GPS coordinates, cached location, and manual location correction.
   • **1080p Cinematic Output**: All assets scaled to 1920×1080, letterboxed, with forced yuv420p pixel format and standard color space (bt709) for universal playback.
   • **Fast Encoding**: Preset `ultrafast` by default, configurable in album_config.yaml.
   • **Streaming Optimized**: moov atom moved to beginning (`+faststart`).
   • **Chunked Processing**: Default 200 assets per chunk (adjustable via command line or script default). Tested with 1500 assets in one chunk.
   • **Audio Crossfade**: Smooth transition between background music tracks (default 2 seconds).

**Example Asset Structure (v41.6):**
~/Pictures/myProject/
├── album_config.yaml
├── geo_timeline.yaml                # automatically generated/updated; stores GPS, location, start_time, duration, location_correction
├── vacation_photo1.jpg
├── vacation_photo1.yaml             # contains caption, section, kenburns, style (no location data)
├── vacation_photo2.png
├── vacation_video.mp4
├── vacation_video.yaml              # optional text or section
├── background_music_1.mp3
├── background_music_2.mp3
└── background_music_3.mp3

**Processing Flow (v41.6):**
1. Scan project directory for all .jpg, .png, .mp4, .mov, .avi.
2. Load album_config.yaml (create default if missing).
3. Build/update geo_timeline.yaml (timeline pre‑pass):
   - Register new assets with default entries (no GPS, no location).
   - Calculate start times and durations for all assets.
   - Extract GPS from photos' EXIF (silently – no Nominatim call yet).
   - Write updated timeline to disk.
4. For each chunk (default 200 assets):
   a. Look up each asset in geo_timeline.yaml:
      - If `location_correction` exists → use as‑is.
      - Else if `location` is cached → use cached value.
      - Else if GPS is available → query Nominatim (with smart 1.1s delay for rate compliance), cache result, save timeline incrementally.
   b. Process each asset (photo/video) with Ken Burns, scaling, padding, and appropriate background (blur for square/portrait).
   c. Overlay texts: section title (top), caption (bottom), location (bottom‑left, above filename), filename (bottom‑left, optional).
   d. Output a silent video segment.
5. Concatenate all silent video segments into a single silent master video.
6. Build a continuous audio track from MP3 files (looping, crossfade) matching the total video duration.
7. Mux audio into the master video (faststart, AAC).
8. The bash wrapper (stitch_master.sh) handles chunking, final stitch, and audio muxing automatically.

1. INPUTS:
   -- Visual Assets: Photos (.jpg, .png) and videos (.mp4, .mov, .avi).
   -- Audio Assets: One or more .mp3 files (looped automatically, crossfaded).
   -- Configuration: album_config.yaml (global), per‑asset .yaml files, and geo_timeline.yaml (auto‑managed).

2. DIRECTORY STRUCTURE & ASSET NAMING:
   All assets must reside in the same project folder under ~/Pictures/.
   Example: ~/Pictures/neighbourhoodWinterScenes/

   * **album_config.yaml** – created automatically if missing; contains all global settings with inline comments explaining every option (Ken Burns, captions, audio, output, `section_style`, `show_photo_filenames`). The default template is clean (no duplication).
   * **geo_timeline.yaml** – automatically generated and updated. Stores start time, duration, GPS coordinates, cached location, and manual location correction. You can edit `location_correction` to override displayed location text. For each asset:
        - `gps`: [lat, lon] or `null`
        - `location`: cached Nominatim result (e.g. "München, Bayern")
        - `location_correction`: manual override (empty string = no override)
        - `start_time`: cumulative start time in seconds
        - `duration`: asset duration in seconds
   * **Per‑asset .yaml** – for any photo or video, create a file with the same base name but .yaml extension.
        Example: For "PXL_20251110_190845826.jpg", create "PXL_20251110_190845826.yaml"
        The engine reads `text:`, `section:`, `kenburns:`, `style:`.
        **Location/landmark info is NOT stored here** – it lives in `geo_timeline.yaml`.
   * **Legacy .caption files** – still supported (plain text only, no overrides).

   * **Music Files** – all .mp3 files are detected and looped. You can specify a subset in album_config.yaml under `audio.default_list`.

3. OUTPUTS:
   -- Final Master Video: Saved in the project's /output/ folder as ${PROJECT}_FINAL_MASTER.mp4.
   -- geo_timeline.yaml: Updated in‑place with cached locations.
   -- log_render.txt: Contains all console output (timestamps, FFmpeg messages, etc.).
   -- log_perf.txt: Contains periodic CPU temperature and encoding speed (from xterm dashboard).

4. EXECUTION / CLI USAGE:
   The pipeline is triggered via the Bash wrapper. Do not run the Python script directly.

   Syntax:
        ./stitch_master.sh <project_name> [batch_size] [--dry-run] [--init]

   Examples:
        ./stitch_master.sh neighbourhoodWinterScenes
        ./stitch_master.sh neighbourhoodWinterScenes 200
        ./stitch_master.sh new_project --init   # generate config files only

   Options:
        batch_size        Number of assets per chunk (default 200). Larger chunks (e.g., 1500) work well for up to ~1500 assets; for very large projects, reduce to 100–200.
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

6. PERFORMANCE CHARACTERISTICS (v41.6, 1459 genuine assets):
   The following benchmarks demonstrate typical performance on the Toshiba C50-A:

   | Scenario | Chunk Size | Total Render | Notes |
   |---|---|---|---|
   | geo_timeline.yaml not yet generated | 200 | ~1h 30m | Nominatim queries (~10 min) incurred inline |
   | geo_timeline.yaml exists (all cached) | 200 | ~1h 02m | All locations pre‑cached, no Nominatim delay |
   | geo_timeline.yaml exists (all cached) | 1500 | ~1h 02m | Larger chunks have negligible impact |

   The ~10 minute penalty on first run is entirely explained by the Nominatim free‑tier rate limit (1 request/second). This is a one‑time cost – subsequent runs reuse cached values.

7. CUSTOMIZATION
  A. album_config.yaml:
   The configuration file is heavily commented. Key settings:
   - `output.preset`: "ultrafast" (fastest), "veryfast", "medium", "slow", "veryslow"
   - `defaults.kenburns.pan`: direction of zoom (center-to-top, top-left-to-bottom-right, etc.)
   - `defaults.kenburns.easing`: acceleration curve
   - `defaults.caption_style`: font, size, color, background, position (for per‑asset captions)
   - `section_style`: font, size, color, position (for album and section titles)
   - `defaults.show_photo_filenames`: `true` or `false` – overlay photo filenames (bottom‑left, small gray/white)
   - `audio.default_list`: restrict which MP3 files are used
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

   **Combining texts**: Album title (first asset only), section title, and `text:` are displayed as separate overlays, each using its own style (section style for album/section titles, caption style for asset text). They appear at their respective positions (e.g., title at top, caption at bottom). If `show_photo_filenames` is enabled, the filename appears at bottom‑left, independent of other texts. Location text appears above the filename (bottom‑left, font size = 40).

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
```
