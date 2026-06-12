LLM：Please keep all valid information when updating!!! (please keep this line.)

================================================================================
Cinematic Video Album Generator (v42.2) - Documentation
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

**Key Improvements over v41.6 (v42.0+):**
- **Unified per-asset configuration** — all per-asset settings (text, section, style, kenburns)
  now live in `geo_timeline.yaml` alongside GPS/location/timeline data. No more scattered
  per-asset .yaml files.
- **--clear-config** — removes stale entries for deleted photos, clears cached location fields
  (preserving manual `location_correction`), and deletes legacy per-asset .yaml/.caption files.
- **--migrate** — one-shot migration of legacy per-asset .yaml content into `geo_timeline.yaml`.
- **--location-only** — resolves all empty location fields from GPS via Nominatim, then exits.
  No rendering. Useful for pre‑warming the location cache.
- **GPS‑based location reuse** — when resolving a location, the engine checks if another
  asset within a configurable distance already has a cached location (Haversine formula).
  Cuts Nominatim API calls by up to 60%.
- **Configurable reuse distance** — `geo.location_reuse_distance` in `album_config.yaml`
  (default 15.0 meters). Tune for accuracy vs. API call trade‑off.
- **Nominatim delay logging** — when the 1.1s rate‑limit delay actually fires, it's now
  logged: `⏳ Nominatim rate-limit: sleeping X.Xs`.
- **Default font: NotoSansCJK** — supports English + Chinese (CJK: JP, KR, SC, TC)
  out of the box. Falls back to DejaVu Sans if Noto is unavailable.
- **Script renamed** — `stitch_master.sh` → `run_create_video.sh` (v4.5).

**Visual Assets:**
   • Photos (.jpg, .png) – Ken Burns effect (zoom + pan) applied via FFmpeg zoompan filter.
   • Video clips (.mp4, .mov, .avi) – seamlessly integrated (audio removed, replaced by background music). Videos are re‑encoded to match the output frame rate (default 24 fps) to preserve original duration.

**Audio Assets:**
   • Multiple background music files (.mp3) – automatically looped and crossfaded to match video duration.
   • Audio is re‑encoded to AAC with smooth crossfade (default 2 seconds) between tracks.
   • Audio is added **after** final video stitching (no reset between chunks).

**Text Overlays (now via geo_timeline.yaml):**
   • All per-asset configuration lives in `geo_timeline.yaml` — no more separate per-photo .yaml files.
   • For any photo or video, add these optional fields to its entry in geo_timeline.yaml:
        - `text:` – the caption to overlay
        - `section:` – title/subtitle that will appear on this asset
            - `title:` – section title (required)
            - `subtitle:` – section subtitle (optional)
        - `kenburns:` – override zoom, pan, easing, duration for that photo
        - `style:` – override font size, font color, position for caption
   • See `--init` output for a self‑documenting template header in `geo_timeline.yaml`.

**Title Cards (no separate black screens):**
   • Album title and subtitle (from album_config.yaml) are overlaid on the **first asset** only.
   • Section titles (defined in `geo_timeline.yaml` under `section:`) are overlaid on that specific asset.
   • Multiple text sources are combined into separate overlays: section title (top), caption (bottom), and location (bottom‑left) with independent styles.

**Text Overlay Layers (bottom‑left):**
   • **Filename** (optional, configurable via `show_photo_filenames`) – small white text at bottom‑left.
   • **Location** – displayed above the filename (if shown) or at bottom‑left otherwise, font size = 40, semi‑transparent background. Auto‑fetched from GPS EXIF via Nominatim, cached in `geo_timeline.yaml`.

**Geolocation Overlay:**
   • For photos with GPS EXIF data, the engine automatically fetches a human‑readable location (town, city, landmark) using Nominatim (OpenStreetMap).
   • The location is cached in `geo_timeline.yaml` to avoid repeated API calls.
   • **Nearby reuse**: Before calling Nominatim, the engine checks if another asset within `geo.location_reuse_distance` meters (default 15.0m) already has a cached location — and reuses it if found. This cuts API calls significantly.
   • You can manually override the location by editing `geo_timeline.yaml` and setting `location_correction`.
   • The location text appears at bottom‑left (font size = 40, semi‑transparent background) above the filename (if enabled).
   • **Captions do not contain landmark information** – landmark is a separate overlay layer.
   • **All location data lives exclusively in `geo_timeline.yaml`** — no per‑photo YAML for location.

**Key Features:**
   • **Ken Burns Effect**: Zoom + pan with configurable direction and easing (linear, ease‑in, ease‑out, ease‑in‑out).
   • **Per‑asset Ken Burns overrides**: Set zoom, pan, easing, or duration per photo in `geo_timeline.yaml`.
   • **Separate Text Styles**: Section titles (default 56px, gold, top) and asset captions (default 40px, white, bottom) can be customised independently in album_config.yaml.
   • **Blurred Background**: For square/portrait photos (aspect ratio < 1.6), a full‑screen blurred version is used as background, with the photo centred – eliminates black bars.
   • **Photo Filename Overlay** (optional): Enable `show_photo_filenames: true` in `album_config.yaml` to display each photo's filename at bottom‑left corner (small white text on semi‑transparent black background). Videos are not overlaid.
   • **Location Overlay** (automatic): Font size = 40, shown above filename at bottom‑left. Override location text via `location_correction` in `geo_timeline.yaml`.
   • **Smart Timeline Construction**: Assets sorted alphabetically; photos and videos interleaved.
   • **Unified Timeline File**: `geo_timeline.yaml` stores everything per‑asset: GPS, location, location_correction, start_time, duration, text, section, style, kenburns. System fields (start_time, duration, GPS) are auto‑synced; user fields (text, section, style, kenburns, location_correction) are preserved across runs.
   • **1080p Cinematic Output**: All assets scaled to 1920×1080, letterboxed, with forced yuv420p pixel format and standard color space (bt709) for universal playback.
   • **Fast Encoding**: Preset `ultrafast` by default, configurable in album_config.yaml.
   • **Streaming Optimized**: moov atom moved to beginning (`+faststart`).
   • **Chunked Processing**: Default 200 assets per chunk (adjustable via command line or script default). Tested with 1500 assets in one chunk.
   • **Audio Crossfade**: Smooth transition between background music tracks (default 2 seconds).

**Example Asset Structure (v42.3):**
~/Pictures/myProject/
├── album_config.yaml                # global settings (created by --init)
├── geo_timeline.yaml                # unified per-asset timeline + config (auto‑synced)
├── vacation_photo1.jpg
├── vacation_photo2.png
├── vacation_video.mp4
├── background_music_1.mp3
├── background_music_2.mp3
└── background_music_3.mp3

Note: Per‑asset .yaml files (e.g., vacation_photo1.yaml) are no longer needed.
All per‑asset settings live in geo_timeline.yaml. Legacy .yaml files can be
migrated with --migrate and cleaned up with --clear-config.

**Processing Flow (v42.2):**
1. Scan project directory for all .jpg, .png, .mp4, .mov, .avi.
2. Load album_config.yaml (create default if missing).
3. Build/update geo_timeline.yaml (timeline pre‑pass):
   - Register new assets with full schema (GPS, location, text, section, style, kenburns).
   - Calculate start times and durations for all assets.
   - Extract GPS from photos' EXIF (silently – no Nominatim call yet).
   - Write updated timeline to disk.
4. For each chunk (default 200 assets):
   a. Look up each asset in geo_timeline.yaml:
      - If `location_correction` exists → use as‑is.
      - Else if `location` is cached → use cached value.
      - Else if GPS is available → check nearby cached locations (within `location_reuse_distance` meters first, then query Nominatim (with smart 1.1s delay for rate compliance), cache result, save timeline incrementally.
   b. Process each asset (photo/video) with Ken Burns, scaling, padding, and appropriate background (blur for square/portrait). Per‑asset kenburns overrides read from geo_timeline.yaml.
   c. Overlay texts: section title (top), caption (bottom), location (bottom‑left, above filename), filename (bottom‑left, optional). All text content and style overrides read from geo_timeline.yaml.
   d. Output a silent video segment.
5. Concatenate all silent video segments into a single silent master video.
6. Build a continuous audio track from MP3 files (looping, crossfade) matching the total video duration.
7. Mux audio into the master video (faststart, AAC).
8. The bash wrapper (run_create_video.sh) handles chunking, final stitch, and audio muxing automatically.

1. INPUTS:
   -- Visual Assets: Photos (.jpg, .png) and videos (.mp4, .mov, .avi).
   -- Audio Assets: One or more .mp3 files (looped automatically, crossfaded).
   -- Configuration: album_config.yaml (global) and geo_timeline.yaml (per‑asset, auto‑managed).

2. DIRECTORY STRUCTURE & ASSET NAMING:
   All assets must reside in the same project folder under ~/Pictures/.
   Example: ~/Pictures/neighbourhoodWinterScenes/

   * **album_config.yaml** – created automatically if missing (or via --init); contains all global settings with inline comments explaining every option (Ken Burns, captions, audio, output, `section_style`, `show_photo_filenames`, `geo.location_reuse_distance`). The default template is clean (no duplication).
   * **geo_timeline.yaml** – automatically generated and updated. This is the **unified** per‑asset file. Each asset entry contains:
        *System fields (auto‑synced, do not edit):*
        - `gps`: [lat, lon] or `null`
        - `location`: cached Nominatim result (e.g. "München, Bayern")
        - `start_time`: cumulative start time in seconds
        - `duration`: asset duration in seconds
        *User‑editable fields (optional, preserved across runs):*
        - `location_correction`: manual override (empty string = no override)
        - `text`: caption text displayed over the asset
        - `section`: {title, subtitle} for chapter overlays
        - `style`: {font_size, font_color, position} override for caption
        - `kenburns`: {zoom, pan, easing, duration} override for Ken Burns motion
     See `geo_timeline.yaml` header comment (generated by --init) for full documentation.

   * **Music Files** – all .mp3 files are detected and looped. You can specify a subset in album_config.yaml under `audio.default_list`.

3. OUTPUTS:
   -- Final Master Video: Saved in the project's /output/ folder as ${PROJECT}_FINAL_MASTER.mp4.
   -- geo_timeline.yaml: Updated in‑place with cached locations and timeline data.
   -- log_render.txt: Contains all console output (timestamps, FFmpeg messages, etc.).
   -- log_perf.txt: Contains periodic CPU temperature and encoding speed (from xterm dashboard).

4. EXECUTION / CLI USAGE:
   The pipeline is triggered via the Bash wrapper. Do not run the Python script directly.

   Syntax:
        ./run_create_video.sh <project_name> [batch_size] [options]

   Examples:
        ./run_create_video.sh neighbourhoodWinterScenes
        ./run_create_video.sh neighbourhoodWinterScenes 200
        ./run_create_video.sh new_project --init            # generate config files only
        ./run_create_video.sh old_project --migrate         # migrate legacy per-asset .yaml → geo_timeline.yaml
        ./run_create_video.sh old_project --clear-config    # clean stale entries + remove legacy files
        ./run_create_video.sh myProject --location-only     # resolve all location fields, no rendering

   Options:
        batch_size        Number of assets per chunk (default 200). Larger chunks (e.g., 1500) work well for up to ~1500 assets; for very large projects, reduce to 100–200.
        --dry-run         Only scan assets, do not render.
        --init            Generate album_config.yaml + geo_timeline.yaml with documented template, then exit (no rendering).
        --migrate         One‑shot: copy legacy per‑asset .yaml content into geo_timeline.yaml (no rendering).
        --clear-config    Remove stale geo_timeline entries for deleted photos, clear all location fields (preserves location_correction), delete legacy per‑asset .yaml/.caption files (no rendering).
        --location-only   Resolve all empty location fields from GPS via Nominatim (with nearby‑cache heuristic), then exit (no rendering).
        --chunk-size N    Number of assets per chunk (default: 200).

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

6. PERFORMANCE CHARACTERISTICS (v42.3):
   The following benchmarks demonstrate typical performance on the Toshiba C50-A:

   | Scenario | Time | Notes |
   |---|---|---|
   | Auto pre-resolve (3,625 unique GPS coords) | ~2h 52m | Nominatim rate‑limited at 1 req/s. **One‑time cost** — cached on disk. |
   | Chunk rendering (3,625 assets → 4h 30m video) | ~2h 48m | Pure FFmpeg, no geocoding overhead during render. |
   | Concat + Audio mux (4h 30m master) | ~28m | Audio crossfade generation scales linearly with video length. |
   | **Wall clock total** (3,625 assets) | **~3h 20m** | Gap ~2m (script overhead, ffprobe, I/O). |
   | Pre-resolve (1,450 assets, all cached) | ~0 | No API calls. |
   | Chunk rendering (1,450 assets) | ~1h 10m | Same as v42.2 — FFmpeg throughput unchanged. |
   | --location-only (standalone, 1,450 assets) | ~10m | Nominatim calls still rate‑limited; Haversine reuse helps. |

   **Key insight:** With the auto pre-resolve (v42.3), location fetching is no longer interleaved
   with rendering. On large projects this avoids paying the Nominatim wait penalty multiple times
   across chunks. The timing report's Gap row isolates overhead: on a 3,625-asset run it was ~2m,
   confirming <1% of wall time is spent on script glue, ffprobe, and file I/O.

   **Location caching efficiency:** With `location_reuse_distance: 15.0m`, Haversine reuse can
   cut Nominatim API calls by up to 60% (e.g., 10 calls vs ~24 for 25 co‑located assets).

7. CUSTOMIZATION
  A. album_config.yaml:
   The configuration file is heavily commented. Key settings:
   - `output.preset`: "ultrafast" (fastest), "veryfast", "medium", "slow", "veryslow"
   - `defaults.kenburns.pan`: direction of zoom (center-to-top, top-left-to-bottom-right, etc.)
   - `defaults.kenburns.easing`: acceleration curve
   - `defaults.caption_style`: font, size, color, background, position (for per‑asset captions)
   - `section_style`: font, size, color, position (for album and section titles)
   - `defaults.show_photo_filenames`: `true` or `false` – overlay photo filenames (bottom‑left, small gray/white)
   - `geo.location_reuse_distance`: distance in meters for reusing nearby cached locations (default 15.0)
   - `audio.default_list`: restrict which MP3 files are used
   It is entirely optional; if missing, the engine creates a clean one with detailed comments and reasonable defaults, including the NotoSansCJK font for English + Chinese.

   **Default font:** `/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc` supports both English and Chinese (CJK) characters. Falls back to DejaVu Sans if unavailable. To use a different font, change `font` in `caption_style` and `section_style`.

  B. Per‑asset settings in geo_timeline.yaml:
   All per‑asset configuration lives under each filename's entry in `geo_timeline.yaml`.
   System fields (gps, location, start_time, duration) are auto‑synced — do not edit.
   User fields (all optional):

   ┌─────────────────────┬──────────────────────────────────────────────────┐
   │ Field               │ Description                                      │
   ├─────────────────────┼──────────────────────────────────────────────────┤
   │ text                │ Caption to overlay on this asset.                │
   │                     │ Example: `text: "Beautiful sunset"`              │
   ├─────────────────────┼──────────────────────────────────────────────────┤
   │ section             │ Section title overlaid on this asset             │
   │                     │ (not a separate card). Sub‑fields:               │
   │                     │   title   – required, main heading               │
   │                     │   subtitle – optional, smaller secondary text    │
   │                     │ Example:                                         │
   │                     │   section:                                       │
   │                     │     title: "Golden Hour"                         │
   │                     │     subtitle: "Beach walk"                       │
   ├─────────────────────┼──────────────────────────────────────────────────┤
   │ kenburns            │ Overrides Ken Burns motion for this photo only   │
   │                     │ (ignored for videos). Sub‑fields:                │
   │                     │   zoom     – final zoom factor (1.15 = 15%)      │
   │                     │   pan      – direction (e.g., "center-to-top")   │
   │                     │   easing   – acceleration curve                  │
   │                     │   duration – seconds to show this photo          │
   │                     │ Example:                                         │
   │                     │   kenburns:                                      │
   │                     │     zoom: 1.3                                    │
   │                     │     pan: "top-left-to-bottom-right"              │
   │                     │     easing: "ease-out"                           │
   │                     │     duration: 6                                  │
   ├─────────────────────┼──────────────────────────────────────────────────┤
   │ style               │ Overrides caption appearance for this asset.     │
   │                     │ Sub‑fields: font_size, font_color, position      │
   │                     │ Example:                                         │
   │                     │   style:                                         │
   │                     │     font_size: 56                                │
   │                     │     font_color: "#FFD700"                        │
   │                     │     position: "top"                              │
   ├─────────────────────┼──────────────────────────────────────────────────┤
   │ location_correction │ Manual location override.                        │
   │                     │ Preserved by --clear-config; takes priority over  │
   │                     │ auto‑fetched location.                           │
   │                     │ Example: `location_correction: "Munich Airport"`  │
   └─────────────────────┴──────────────────────────────────────────────────┘

   **Example per‑asset entry in geo_timeline.yaml**:
   ```yaml
   PXL_20251110_190845826.jpg:
     gps: [48.148, 11.574]
     location: "München, Bayern"
     location_correction: "Marienplatz"
     start_time: 0.0
     duration: 4.0
     text: "Walking along the shore"
     section:
       title: "Evening Stroll"
       subtitle: "Sunset reflections"
     kenburns:
       zoom: 1.25
       pan: "center-to-top"
       easing: "ease-in-out"
       duration: 6
     style:
       font_size: 52
       font_color: "#FFE4B5"
       position: "bottom"
   ```

   **Combining texts**: Album title (first asset only), section title, and `text:` are displayed as separate overlays, each using its own style (section style for album/section titles, caption style for asset text). They appear at their respective positions (e.g., title at top, caption at bottom). If `show_photo_filenames` is enabled, the filename appears at bottom‑left, independent of other texts. Location text appears above the filename (bottom‑left, font size = 40).

8. MIGRATION FROM v41.x (legacy per-asset .yaml files):
   If you have an existing project with per‑asset .yaml files (e.g., vacation_photo1.yaml):

   1. `./run_create_video.sh myProject --migrate`  — copies text/section/style/kenburns into geo_timeline.yaml
   2. `./run_create_video.sh myProject --clear-config`  — deletes the legacy .yaml/.caption files
   3. `./run_create_video.sh myProject --init`  — adds the documented header + template fields to geo_timeline.yaml

   After migration, all per‑asset configuration is edited directly in geo_timeline.yaml.
