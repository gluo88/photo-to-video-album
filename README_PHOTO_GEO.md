# 🌍 Photo Geo-Extractor

**photo_geo.py** — a standalone pre-processing tool that reads GPS coordinates from your photos (Google Pixel, iPhone, any camera with GPS) and reverse-geocodes them to city/landmark names.

By default it writes a clean **summary file** (`geo_summary.txt`) without touching your project files. Pass `--inject-yaml` to also write location data into the `.yaml` caption files used by `make_video_album.py`.

---

## ⚙️ Installation

Activate your virtual environment and install the dependencies:

```bash
source ~/code/python/venv/bin/activate
pip install Pillow reverse_geocoder geopy
```

**Note:** On first use of `--offline` mode, `reverse_geocoder` downloads a ~15MB city dataset. This happens once automatically.

---

## 🚀 Usage

Run via the bash wrapper **before** `stitch_master.sh`:

```bash
./run_photo_geo.sh <project_name> [options]
```

### Modes

| Mode | Flag | Internet? | Detail | Rate limit |
|------|------|-----------|--------|------------|
| **Nominatim (default)** | *(none)* | Required | Landmark + city | ~1 req/sec (auto-retry) |
| **Google Maps** | `--google-key "KEY"` | Required | Street address + POI | Per API plan |
| **Offline** | `--offline` | Not needed | City / province only | None |

### Output options

| Flag | Behaviour |
|------|-----------|
| *(none)* | Write `geo_summary.txt` only — safe, no file modifications |
| `--inject-yaml` | Also create/update per-asset `.yaml` files with location captions |

### Examples

```bash
# Default: geo_summary.txt only, Nominatim (free OSM)
./run_photo_geo.sh park_pottery

# Include yaml injection for video album rendering
./run_photo_geo.sh park_pottery --inject-yaml

# Google Maps (most detailed addresses and POIs)
./run_photo_geo.sh park_pottery --inject-yaml --google-key "AIzaSyYourKeyHere"

# Offline mode (no internet, city-level only)
./run_photo_geo.sh park_pottery --offline
```

---

## 📁 What gets generated

### `geo_summary.txt` — always written

A clean master list in your project folder:

```
# Photographic GPS Summary
# Project: park_pottery
==================================================
PXL_20251020_062416293.MP.jpg | 36.070503, 103.828225 | Lanzhou, Gansu
PXL_20251020_062609118.MP.jpg | 36.071200, 103.829100 | Lanzhou, Gansu
```

Each line: `filename | lat, lon | location_name` — easy to parse by scripts or read by humans. The `via` mode is also printed per-photo in the terminal so you can see whether a result came from Nominatim, Google, cache, or a fallback.

### `.yaml` caption files — only with `--inject-yaml`

The script finds (or creates) each photo's `.yaml` file and writes the location into the `text:` field. Existing custom captions are preserved and appended below the location.

**Before:**
```yaml
text: "Kids looking at pottery"
```

**After:**
```yaml
text: "Lanzhou, Gansu -- Kids looking at pottery"
```

The `\n` separates location (top) from your note (bottom) in the video overlay.

---

## 🔄 Workflow

```
1. Drop photos into    ~/Pictures/park_pottery/
2. Run geo tags  →     ./run_photo_geo.sh park_pottery --inject-yaml     ← writes yaml captions
3. (Optional) tweak     park_pottery/*.yaml captions
4. Render video  →     ./stitch_master.sh park_pottery
```

Step 2 auto-writes location into the `.yaml` files. Step 4 picks them up automatically — location is overlaid on each photo in the final video.

If you run without `--inject-yaml`, step 2 only writes `geo_summary.txt` for your reference — no files are modified.

---

## 🧠 Proximity Caching (Haversine)

When processing a batch of photos from the same location, the script detects co-located shots using **Haversine distance** — photos taken within 15 meters of a previously geocoded coordinate reuse the cached location name without making another API call.

This matters because a single photo session often produces 10–50 frames from the same spot (tripod pans, bracketing, multiple subjects). Without caching, every one of those frames would hit Nominatim or Google Maps — wasting API quota and adding ~1 second per photo.

**Example:** 40 photos all standing within 15m of each other → only 1 API call instead of 40.

This applies to all modes — Nominatim, Google Maps, and offline — and is transparent in the output (you'll see a line like `via Cache (within 2.3m of Nominatim)` in the terminal log).

---

## 📝 Notes

- **No GPS data?** The script skips the photo with a `[ ]` marker and prints a clean count of how many had GPS vs total.
- **Custom captions are safe** — when `--inject-yaml` is on, the script only *prepends* the location if the `.yaml` already has a `text:` field.
- **Already geocoded?** If the location string is already present in the `text:` field, the script skips that photo.
- **Nominatim rate limits** — Nominatim allows ~1 request/second. The script enforces a mandatory 1-second delay between requests and auto-retries on timeout with back-off (up to 3 attempts). Google Maps and offline modes have no such delay.
- **Mode indicator per photo** — The live output shows exactly which mode resolved each coordinate (e.g., `Nominatim`, `Cache`, `Offline`, `Raw GPS`), so you can audit at a glance.
- **Fallback chain** — In default mode, if Nominatim fails it falls back to offline reverse-geocoder, and if that also fails, falls back to raw coordinates. Offline-only and Google Maps modes skip this chain.
