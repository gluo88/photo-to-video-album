#!/usr/bin/env python3
"""
REVISIONS:
v1.16 – Track Nominatim-to-offline fallback count. Rephrased 429 display
         as "rate-limited (429)" instead of "x429".
v1.15 – Track retry/429/timeout counts during geocoding and report them
         in the phase timing summary.
v1.14 – Replaced fixed 1s Nominatim delay with smart_delay() that only
         sleeps the remaining time to reach 1.1s since last request.
         Also applies adaptive delay on retries after timeouts/429s.
v1.13 – Added stale process detection: when starting, kills any existing
         photo_geo.py processes (same script + same project_dir) that have
         been running for >30s, to avoid hitting Nominatim rate limits from
         abandoned parallel runs.
v1.12 – Added per-phase elapsed time logging for Nominatim geocoding
         and translation phases. Prints phase timings inline and a final
         breakdown summary at the end.
v1.11 – geo_translations.yaml output is now grouped by city/area and
         normalised (e.g., "Vienna, Austria", "Praha, Czechia").
         Added infer_city_group() / _normalise_city_group() helpers.
v1.10 – Renamed translations.yaml to geo_translations.yaml for consistency
         with geo_summary.yaml naming pattern.
v1.9  – Removed --inject-yaml option (per-asset YAML injection is no longer needed).
v1.8  – Added --translate flag: auto-translates unique location names to English
         via GoogleTranslator (deep-translator). Writes translations.yaml with
         deduped (location, location_english) pairs. Added --overwrite to force
         retranslation of already-populated location_english fields.
v1.7  – Added location_raw_data field to geo_summary.yaml with raw server response
         (Nominatim: osm_type/id, display_name, address dict; Google: place_id,
         formatted_address, address_components; Offline: reverse_geocoder result).
         All geocoding functions now return (location_str, raw_data_dict) tuples.
v1.6  – Output changed from geo_summary.txt to geo_summary.yaml with structured
         fields (photo_name, gps, location, original_language, location_english).
         Added --cache-radius argument (default 0) for proximity-based GPS caching.
         Nominatim now prioritizes landmark-level results over city-level defaults.
         Fixed sleep(1) placement to fire before Nominatim API call (rate limiting).
         Offline results are now cached too (saves redundant reverse_geocoder lookups).
v1.5  – Fixed --offline mode which silently fell through to Nominatim.
         Restored offline fallback when Nominatim fails.
         Cache now respects --offline and doesn't store Nominatim results when offline-only.
v1.4  – Added Haversine distance calculation and caching to reuse locations within 15 meters.
v1.3  – Add 1-second delay to Nominatim to prevent rate limiting. 
         Add retry loop for Google Maps. 
         Explicitly print active mode per photo and log failures/retries.
v1.2  – Add --inject-yaml flag (default: summary-only).
         Nominatim retry loop on timeout/rate-limit.
v1.1  – Initial version: GPS extraction, offline/online geocoding, yaml injection.

To LLM：Please add the comment for new revision, and keeping all previous revision
notes, when updating!!! (please keep this line.)

photo_geo.py - Extract EXIF GPS data and geocode into geo_summary.yaml and/or
per-asset YAML caption files for the Cinematic Video Album Engine.
"""

import os
import sys
import glob
import argparse
import time
import math
import signal
import subprocess
from PIL import Image, ExifTags
import yaml

VERSION = "1.16"
VERSION_DATE = "2026-06-14"

# Optional dependencies based on online/offline mode
try:
    import reverse_geocoder as rg
except ImportError:
    rg = None

try:
    from geopy.geocoders import Nominatim, GoogleV3
    from geopy.exc import GeocoderTimedOut, GeocoderServiceError
except ImportError:
    Nominatim = None
    GoogleV3 = None

try:
    from deep_translator import GoogleTranslator
except ImportError:
    GoogleTranslator = None

def get_exif_data(image_path):
    """Extracts standard EXIF data from an image."""
    try:
        with Image.open(image_path) as img:
            exif_raw = img._getexif()
            if not exif_raw:
                return None
            
            exif_data = {}
            for tag_id, value in exif_raw.items():
                tag = ExifTags.TAGS.get(tag_id, tag_id)
                # Recursively convert GPSInfo sub-dict keys from int to string names
                if tag == 'GPSInfo' and isinstance(value, dict):
                    gps_named = {}
                    for gps_key, gps_val in value.items():
                        gps_name = ExifTags.GPSTAGS.get(gps_key, gps_key)
                        gps_named[gps_name] = gps_val
                    exif_data[tag] = gps_named
                else:
                    exif_data[tag] = value
            return exif_data
    except Exception as e:
        print(f"  [!] Error reading EXIF from {os.path.basename(image_path)}: {e}")
        return None

def get_decimal_coordinates(info):
    """Converts EXIF GPS info to decimal latitude and longitude."""
    for key in ['GPSLatitude', 'GPSLongitude', 'GPSLatitudeRef', 'GPSLongitudeRef']:
        if key not in info:
            return None

    def convert_to_degrees(value):
        # Handle different PIL versions (some return tuples, some IFDRational)
        d, m, s = value
        d = float(d)
        m = float(m)
        s = float(s)
        return d + (m / 60.0) + (s / 3600.0)

    try:
        lat = convert_to_degrees(info['GPSLatitude'])
        lon = convert_to_degrees(info['GPSLongitude'])
        
        if info['GPSLatitudeRef'] != 'N':
            lat = -lat
        if info['GPSLongitudeRef'] != 'E':
            lon = -lon
            
        return lat, lon
    except Exception:
        return None

def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculates distance in meters between two GPS points."""
    R = 6371000  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(delta_lambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c

def get_location_offline(lat, lon):
    """Uses local reverse_geocoder (City/Province level).
    Returns (formatted_location, raw_data_dict).
    """
    if not rg:
        return ("Offline geocoding unavailable (install reverse_geocoder)", {})

    results = rg.search((lat, lon))
    if results:
        res = results[0]
        city = res.get('name', '')
        state = res.get('admin1', '')
        location = f"{city}, {state}".strip(", ")
        return (location, dict(res))
    return (None, {})

def get_location_nominatim(lat, lon):
    """Uses Nominatim API (Detailed Landmark/Address level).
    Retries on timeout/429 with a back-off, and enforces a mandatory
    1-second delay to comply with OSM usage policies.
    Returns the most specific landmark name available, falling back
    to the geographic hierarchy only when no landmark is found.
    Returns (formatted_location, raw_data_dict).
    """
    if not Nominatim:
        return ("Online geocoding unavailable (install geopy)", {})

    geolocator = Nominatim(user_agent="photo_video_album_generator")
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Adaptive delay to comply with OSM 1 req/sec policy
            smart_delay()
            loc_raw = geolocator.reverse(f"{lat}, {lon}", timeout=5)

            if loc_raw:
                raw_data = {
                    "address": loc_raw.raw.get("address", {}),
                    "display_name": loc_raw.raw.get("display_name", ""),
                }
                address = loc_raw.raw.get('address', {})

                # Priority: named place (amenity, shop, historic, etc.)
                named_place = (
                    address.get('amenity') or
                    address.get('shop') or
                    address.get('historic') or
                    address.get('tourism') or
                    address.get('leisure') or
                    address.get('attraction') or
                    address.get('museum') or
                    address.get('theatre') or
                    address.get('gallery') or
                    address.get('house_name') or
                    address.get('building')
                )

                # Only keep named_place if it looks like a real name
                # (skip bare house numbers like "34" from building tags)
                has_named_place = bool(named_place and not named_place.isdigit())

                # Build compact geographic hierarchy (town/city/region level)
                raw_parts = []
                for key in ['village', 'town', 'district', 'county', 'city', 'region', 'state']:
                    val = address.get(key)
                    if val and val not in raw_parts:
                        raw_parts.append(val)

                # Dedupe when city == district, promote region
                city_val = address.get('city')
                district_val = address.get('district')
                region_val = address.get('region')
                if city_val and district_val and city_val == district_val and region_val and region_val in raw_parts:
                    raw_parts = [region_val if p == city_val else p for p in raw_parts]
                    seen = set()
                    raw_parts = [p for p in raw_parts if not (p in seen or seen.add(p))]

                hierarchy = ', '.join(raw_parts) if raw_parts else ''

                # Combine: named_place first, then compact hierarchy
                if has_named_place:
                    if hierarchy:
                        return (f"{named_place} - {hierarchy}", raw_data)
                    return (named_place, raw_data)

                # No named place: hierarchy with road/suburb for richer context
                raw_parts = []
                for key in ['road', 'suburb', 'village', 'town', 'district', 'county', 'city', 'region', 'state']:
                    val = address.get(key)
                    if val and val not in raw_parts:
                        raw_parts.append(val)

                # Dedupe when city == district, promote region
                city_val = address.get('city')
                district_val = address.get('district')
                region_val = address.get('region')
                if city_val and district_val and city_val == district_val and region_val and region_val in raw_parts:
                    raw_parts = [region_val if p == city_val else p for p in raw_parts]
                    seen = set()
                    raw_parts = [p for p in raw_parts if not (p in seen or seen.add(p))]

                if raw_parts:
                    return (', '.join(raw_parts), raw_data)

                # Final fallback: first address part
                return (loc_raw.address.split(',')[0], raw_data)
        except GeocoderTimedOut as e:
            global _nominatim_timeouts
            _nominatim_timeouts += 1
            print(f"      [!] Nominatim timeout (attempt {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                smart_delay()  # back-off in case of rate limiting
                continue
        except Exception as e:
            msg = str(e)
            if "429" in msg:
                global _nominatim_429_errors
                _nominatim_429_errors += 1
            else:
                global _nominatim_other_errors
                _nominatim_other_errors += 1
            print(f"      [!] Nominatim error (attempt {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                smart_delay()  # back-off in case of rate limiting
                continue
        break
    return (None, {})

def get_location_google(lat, lon, api_key):
    """Uses Google Maps Geocoding API for highly detailed landmark data.
    Returns (formatted_location, raw_data_dict).
    """
    if not GoogleV3:
        return ("Google geocoding unavailable (install geopy)", {})

    geolocator = GoogleV3(api_key=api_key)
    max_retries = 3
    for attempt in range(max_retries):
        try:
            location = geolocator.reverse(f"{lat}, {lon}", timeout=5)
            if location:
                raw_result = location[0].raw
                raw_data = raw_result.get("address_components", [])
                address_components = raw_result.get('address_components', [])

                # Find Points of Interest, Parks, and Locality (City)
                poi = next((comp['long_name'] for comp in address_components if 'point_of_interest' in comp['types'] or 'park' in comp['types'] or 'establishment' in comp['types']), None)
                city = next((comp['long_name'] for comp in address_components if 'locality' in comp['types']), None)

                parts = []
                if poi: parts.append(poi)
                if city: parts.append(city)

                if parts:
                    return (" - ".join(parts), raw_data)
                return (location[0].address.split(',')[0], raw_data)
        except (GeocoderTimedOut, GeocoderServiceError) as e:
            print(f"      [!] Google Maps API error (attempt {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
        except Exception as e:
            print(f"      [!] Unexpected Google API error: {e}")
            break
        break
    return (None, {})

def translate_location_batch(locations):
    """Translates a set of unique location strings to English via GoogleTranslate.
    Returns dict: {original_location: english_translation}
    """
    if not GoogleTranslator:
        print("  [!] deep-translator not installed. Install with: pip install deep-translator")
        return {}

    to_translate = set(loc for loc in locations if loc and loc not in ("[Unknown location]", ""))
    if not to_translate:
        return {}

    translator = GoogleTranslator(source='auto', target='en')
    translations = {}
    total = len(to_translate)
    done = 0

    print(f"\n🌐 Translating {total} unique location(s) to English...")
    for idx, loc in enumerate(sorted(to_translate), 1):
        try:
            result = translator.translate(loc)
            translations[loc] = result
            done += 1
            print(f"  [{idx}/{total}] {loc[:60]} → {result[:60]}")
            if idx < total:
                time.sleep(0.5)  # rate limit for free Google Translate
        except Exception as e:
            print(f"  [!] Translation failed for '{loc[:40]}': {e}")
            translations[loc] = ""

    print(f"✅ Translated {done}/{total} locations.")
    return translations


def infer_city_group(location_str):
    """Derives a city/area group key from a location string.

    Patterns handled:
      - "Landmark - City, Region"       → "City, Region"
      - "Street, District, City, Region" → "City, Region"
      - "Landmark - City"               → "City"
      - "Street, City"                  → "City"
      - "Landmark" (no hierarchy)       → "Other"
    Returns a clean title-case group name.
    """
    if not location_str or location_str in ("[Unknown location]", ""):
        return "Other"

    # Pattern 1: "Landmark - City, Region" or "Landmark - City"
    if " - " in location_str:
        after_dash = location_str.split(" - ", 1)[1].strip()
        if after_dash:
            return _normalise_city_group(after_dash)

    # Pattern 2: Comma-separated hierarchy
    # Try to extract city-like parts from the tail end
    parts = [p.strip() for p in location_str.split(",")]
    if len(parts) >= 3:
        # Take the last 2 parts (usually city/region/province)
        tail = ", ".join(parts[-2:])
        # Normalise known aliases
        tail = _normalise_city_group(tail)
        return tail
    elif len(parts) == 2:
        # Could be "Street, City"
        group = parts[-1].strip()
        return _normalise_city_group(group)

    return "Other"


def _normalise_city_group(group):
    """Normalise inferred city-group names for cleaner output."""
    CITY_ALIASES = {
        # Czechia — strip district prefix, use country name
        "obvod Praha 1, Praha": "Praha, Czechia",
        "Praha": "Praha, Czechia",
        # Germany — unify variations under country where useful
        # (keep "München, Bayern" as-is, that's fine)
        # Austria — use standard English names
        "Katastralgemeinde Schönbrunn, Wien": "Vienna, Austria",
        "Wien": "Vienna, Austria",
        # Hungary
        "Buda, Budapest": "Budapest, Hungary",
        "Budapest": "Budapest, Hungary",
    }
    return CITY_ALIASES.get(group, group)


# Globals: Nominatim rate-limiting and retry tracking
_last_nominatim_time = 0.0
_nominatim_timeouts = 0
_nominatim_429_errors = 0
_nominatim_other_errors = 0
_nominatim_cache_hits = 0
_nominatim_offline_fallbacks = 0


def smart_delay():
    """Adaptive delay: only sleeps the remaining time to reach 1.1s
    since the last Nominatim request. Avoids unnecessary waiting
    when the API response itself took significant time."""
    global _last_nominatim_time
    elapsed = time.time() - _last_nominatim_time
    if elapsed < 1.1:
        wait = 1.1 - elapsed
        print(f"      ⏳ Nominatim rate-limit: sleeping {wait:.1f}s (last call {elapsed:.1f}s ago)")
        time.sleep(wait)
    _last_nominatim_time = time.time()


def print_version():
    print(f"🌍 Photo Geo-Extractor v{VERSION} ({VERSION_DATE})")
    print()


def kill_stale_processes(project_dir):
    """Kill any other photo_geo.py processes running on the same project_dir
    that have been alive >30s (stale/abandoned). Avoids Nominatim rate-limit
    collisions from parallel runs."""
    pid = os.getpid()
    script = os.path.abspath(__file__)
    try:
        result = subprocess.run(
            ["pgrep", "-f", f"photo_geo.py.*{project_dir}"],
            capture_output=True, text=True, timeout=5
        )
        pids = [int(p.strip()) for p in result.stdout.split() if p.strip()]
        for other_pid in pids:
            if other_pid == pid:
                continue
            try:
                with open(f"/proc/{other_pid}/stat") as f:
                    fields = f.read().split()
                    # field 22 is starttime (jiffies since boot)
                    start_jiffies = int(fields[21])
                with open("/proc/self/stat") as f:
                    now_jiffies = int(f.read().split()[21])
                clk_tck = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
                age_s = (now_jiffies - start_jiffies) / clk_tck
                if age_s > 30:
                    os.kill(other_pid, signal.SIGTERM)
                    print(f"  [🧹] Killed stale photo_geo.py PID {other_pid} (running {age_s:.0f}s)")
            except (ProcessLookupError, PermissionError, FileNotFoundError, ValueError):
                pass
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass  # pgrep not available or timed out — skip


def main():
    print_version()
    parser = argparse.ArgumentParser(description="Extract GPS and geocode photos.")
    parser.add_argument("project_dir", help="Path to the project directory containing photos")
    parser.add_argument("--google-key", help="Use Google Maps API for geocoding with this key")
    parser.add_argument("--offline", action="store_true", help="Skip online geocoding; use local reverse_geocoder only")
    parser.add_argument("--cache-radius", type=float, default=0, metavar="METERS",
                        help="GPS proximity cache radius in meters (default: 0 = exact coords only)")
    parser.add_argument("--landmark-only", action="store_true",
                        help="Output only the landmark name (omit geographic hierarchy)")
    parser.add_argument("--translate", action="store_true",
                        help="Auto-translate unique location names to English via GoogleTranslator")
    parser.add_argument("--overwrite", action="store_true",
                        help="Overwrite location_english even if already populated (only with --translate)")
    args = parser.parse_args()

    project_dir = args.project_dir
    if not os.path.isdir(project_dir):
        print(f"❌ Project directory {project_dir} not found")
        sys.exit(1)

    # Determine display mode
    mode_text = "NOMINATIM (OSM, default, needs internet)"
    if args.google_key:
        mode_text = "GOOGLE MAPS API"
    elif args.offline:
        mode_text = "OFFLINE (reverse_geocoder, local only)"
    mode_text += ""

    print(f"🌍 Scanning for GPS data in: {project_dir}")
    print(f"📡 Mode: {mode_text}")
    print(f"📏 Cache radius: {args.cache_radius}m")
    if args.landmark_only:
        print(f"📍 Landmark-only mode: city/region hierarchy suppressed")

    # Kill stale processes running on the same project
    kill_stale_processes(project_dir)

    photos = glob.glob(os.path.join(project_dir, "*.[jJ][pP][gG]"))
    photos.extend(glob.glob(os.path.join(project_dir, "*.[jJ][pP][eE][gG]")))
    photos.sort()

    summary_file = os.path.join(project_dir, "geo_summary.yaml")
    summary = {
        "project": os.path.basename(project_dir),
        "photos": []
    }

    processed_count = 0
    geo_count = 0

    # Phase timing tracking
    phase_timings = {}
    t_phase_start = time.time()

    # Cache for coordinates: {(lat, lon): ("Location Name", "Used Mode", raw_data_dict)}
    location_cache = {}
    CACHE_RADIUS_METERS = args.cache_radius

    for photo_path in photos:
        filename = os.path.basename(photo_path)
        exif = get_exif_data(photo_path)
        
        if not exif or 'GPSInfo' not in exif:
            print(f"  [ ] {filename}: No GPS data")
            continue
            
        coords = get_decimal_coordinates(exif['GPSInfo'])
        if not coords:
            print(f"  [ ] {filename}: Invalid GPS format")
            continue
            
        lat, lon = coords
        geo_count += 1
        
        # Geocode in priority order
        location_name = None
        used_mode = ""
        
        # Check cache first
        for (cached_lat, cached_lon), (cached_name, cached_mode, cached_raw) in location_cache.items():
            dist = haversine_distance(lat, lon, cached_lat, cached_lon)
            if dist <= CACHE_RADIUS_METERS:
                location_name = cached_name
                location_raw_data = cached_raw
                # Strip previous cache tags so we don't end up with nested cache strings
                base_mode = cached_mode.split(" (")[0] if "Cache" not in cached_mode else cached_mode
                used_mode = f"Cache (within {dist:.1f}m of {base_mode})"
                break

        if not location_name:
            location_raw_data = {}
            if args.offline:
                # Offline-only: skip Nominatim entirely
                used_mode = "Offline"
                location_name, location_raw_data = get_location_offline(lat, lon)
            elif args.google_key:
                # Google Maps API
                used_mode = "Google Maps"
                location_name, location_raw_data = get_location_google(
                    lat, lon, args.google_key
                )
            else:
                # Default: try Nominatim, fall back to offline
                used_mode = "Nominatim"
                location_name, location_raw_data = get_location_nominatim(lat, lon)
                if not location_name:
                    global _nominatim_offline_fallbacks
                    _nominatim_offline_fallbacks += 1
                    print(f"      [!] Nominatim failed, falling back to offline geocoding")
                    location_name, location_raw_data = get_location_offline(lat, lon)
                    used_mode = "Nominatim->Offline"

            if not location_name:
                location_name = f"{lat:.4f}, {lon:.4f}"
                location_raw_data = {}
                used_mode = "Raw GPS"

            # Save to cache (all modes: offline results get cached too)
            if used_mode != "Raw GPS":
                location_cache[(lat, lon)] = (location_name, used_mode, location_raw_data)
            elif "Cache" in used_mode:
                global _nominatim_cache_hits
                _nominatim_cache_hits += 1

        # If --landmark-only, strip geographic hierarchy from the location name.
        # Keep only the most specific non-numeric part.
        if args.landmark_only:
            # Extract the landmark part: everything before the first separator
            for sep in [' - ', ', ']:
                if sep in location_name:
                    first_part = location_name.split(sep)[0].strip()
                    if first_part and not first_part.isdigit():
                        location_name = first_part
                        break
            else:
                # No separator: if it's just a number, mark unknown
                if location_name.strip().isdigit():
                    location_name = "[Unknown location]"

        # Append structured entry to summary
        summary["photos"].append({
            "photo_name": filename,
            "gps": f"{lat:.6f}, {lon:.6f}",
            "location": location_name,
            "original_language": "",
            "location_english": "",
            "location_raw_data": location_raw_data if location_raw_data else {}
        })

        print(f"  [+] {filename}: {location_name} (via {used_mode})")

        processed_count += 1

    # --- Phase timing: geocoding done ---
    geo_elapsed = time.time() - t_phase_start
    # Build retry summary line
    retry_parts = []
    retry_parts.append(f"{_nominatim_timeouts} timeouts")
    retry_parts.append(f"{_nominatim_429_errors} rate-limited (429)")
    retry_parts.append(f"{_nominatim_other_errors} other errors")
    retry_parts.append(f"{_nominatim_cache_hits} cache hits")
    retry_parts.append(f"{_nominatim_offline_fallbacks} offline fallbacks")
    retry_summary = f" ({', '.join(retry_parts)})"
    print(f"\n⏱️  Geocoding phase: {geo_elapsed:.1f}s ({int(geo_elapsed//60)}m {int(geo_elapsed%60)}s){retry_summary}")
    phase_timings["geocoding"] = geo_elapsed

    # --- Translation pass ---
    t_trans_start = time.time()
    if args.translate:
        # Determine which locations need translation
        if args.overwrite:
            locations_to_translate = set(
                p["location"] for p in summary["photos"]
                if p["location"] and p["location"] not in ("[Unknown location]", "")
            )
        else:
            # Only translate locations whose location_english is still empty
            locations_to_translate = set(
                p["location"] for p in summary["photos"]
                if p["location"]
                and p["location"] not in ("[Unknown location]", "")
                and not p["location_english"]
            )
            skipped = len(set(p["location"] for p in summary["photos"])) - len(locations_to_translate)
            if skipped > 0:
                print(f"\n⏭️  Skipping {skipped} location(s) with existing English translations")
                print(f"   (use --overwrite to force retranslation)")

        translations = translate_location_batch(locations_to_translate)

        # Fill location_english into summary
        filled = 0
        for photo in summary["photos"]:
            loc = photo["location"]
            if loc in translations and translations[loc]:
                if args.overwrite or not photo["location_english"]:
                    photo["location_english"] = translations[loc]
                    filled += 1

        # Write geo_translations.yaml grouped by city/area
        translations_file = os.path.join(project_dir, "geo_translations.yaml")
        unique_pairs = {
            loc: eng for loc, eng in translations.items() if eng
        }
        if unique_pairs:
            # Group by inferred city
            grouped = {}
            for loc, eng in unique_pairs.items():
                group = infer_city_group(loc)
                grouped.setdefault(group, {})[loc] = eng

            # Sort: groups alphabetically, entries within each group alphabetically
            grouped_sorted = dict(sorted(
                ((g, dict(sorted(entries.items())))
                 for g, entries in grouped.items()),
                key=lambda x: x[0]
            ))

            # Write with city-group comments for readability
            with open(translations_file, 'w', encoding='utf-8') as f:
                f.write("# geo_translations.yaml - Grouped by city/area\n")
                f.write(f"# Generated: {VERSION_DATE}\n\n")
                yaml.dump(grouped_sorted, f, default_flow_style=False,
                          allow_unicode=True, sort_keys=False, indent=2)
            pair_count = sum(len(v) for v in grouped_sorted.values())
            group_count = len(grouped_sorted)
            print(f"📄 Geo-translations saved to: {translations_file} ({pair_count} pairs across {group_count} groups)")
            print(f"📍 Filled location_english for {filled} photo(s)")

    # Phase timing: translation done (if ran)
    if args.translate:
        trans_elapsed = time.time() - t_trans_start
        print(f"⏱️  Translation phase: {trans_elapsed:.1f}s ({int(trans_elapsed//60)}m {int(trans_elapsed%60)}s)")
        phase_timings["translation"] = trans_elapsed
    else:
        phase_timings["translation"] = 0.0

    # Save summary as YAML
    t_save_start = time.time()
    with open(summary_file, 'w', encoding='utf-8') as f:
        yaml.dump(summary, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    save_elapsed = time.time() - t_save_start
    phase_timings["save"] = save_elapsed

    # Final timing summary
    total_elapsed = time.time() - t_phase_start
    print("\n" + "="*50)
    print(f"✅ Found GPS data in {geo_count}/{len(photos)} photos.")
    print(f"📄 Summary saved to: {summary_file} ({len(summary['photos'])} photos)")
    print(f"\n⏱️  Phase timing breakdown:")
    for phase, secs in phase_timings.items():
        if secs > 0:
            print(f"     {phase:15s} {secs:8.1f}s  ({int(secs//60)}m {int(secs%60)}s)")
    print(f"     {'total':15s} {total_elapsed:8.1f}s  ({int(total_elapsed//60)}m {int(total_elapsed%60)}s)")
    print("==================================================")

if __name__ == "__main__":
    main()
