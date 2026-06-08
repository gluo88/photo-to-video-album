#!/usr/bin/env python3
"""
REVISIONS:
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

photo_geo.py - Extract EXIF GPS data and geocode into geo_summary.txt and/or
per-asset YAML caption files for the Cinematic Video Album Engine.
"""

import os
import sys
import glob
import argparse
import time
import math
from PIL import Image, ExifTags
import yaml

VERSION = "1.5"
VERSION_DATE = "2026-06-07"

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
    """Uses local reverse_geocoder (City/Province level)."""
    if not rg:
        return "Offline geocoding unavailable (install reverse_geocoder)"
    
    results = rg.search((lat, lon))
    if results:
        res = results[0]
        city = res.get('name', '')
        state = res.get('admin1', '')
        # E.g., "Lanzhou, Gansu"
        return f"{city}, {state}".strip(", ")
    return None

def get_location_nominatim(lat, lon):
    """Uses Nominatim API (Detailed Landmark/Address level).
    Retries on timeout/429 with a back-off, and enforces a mandatory 
    1-second delay to comply with OSM usage policies.
    """
    if not Nominatim:
        return "Online geocoding unavailable (install geopy)"

    geolocator = Nominatim(user_agent="photo_video_album_generator")
    max_retries = 3
    for attempt in range(max_retries):
        try:
            location = geolocator.reverse(f"{lat}, {lon}", timeout=5)
            time.sleep(1) # MANDATORY 1-second delay to prevent IP ban
            
            if location:
                address = location.raw.get('address', {})
                # Try to grab the most specific landmark/city info
                landmark = address.get('amenity') or address.get('historic') or address.get('tourism') or address.get('leisure')
                
                # Build location from most specific to least
                district = address.get('district') or address.get('county') or address.get('suburb')
                city = address.get('city')
                region = address.get('region')
                town = address.get('town') or address.get('village')
                
                # Prefer the broader city over district as the city name
                actual_city = city
                if city and district and (district == city):
                    actual_city = region or city
                
                # Assemble: meaningful location hierarchy, deduped
                raw_parts = []
                for key in ['village', 'town', 'district', 'county', 'city', 'region', 'state']:
                    val = address.get(key)
                    if val and val not in raw_parts:
                        raw_parts.append(val)
                
                # If 'city' == 'district', promote 'region' as the real city
                city_val = address.get('city')
                district_val = address.get('district')
                region_val = address.get('region')
                if city_val and district_val and city_val == district_val and region_val and region_val in raw_parts:
                    raw_parts = [region_val if p == city_val else p for p in raw_parts]
                    seen = set()
                    raw_parts = [p for p in raw_parts if not (p in seen or seen.add(p))]
                
                location_name = ', '.join(raw_parts) if raw_parts else ''
                
                parts = []
                if landmark: parts.append(landmark)
                if location_name: parts.append(location_name)
                
                if parts:
                    return " - ".join(parts)
                return location.address.split(',')[0] # Fallback to first address part
        except GeocoderTimedOut as e:
            print(f"      [!] Nominatim timeout (attempt {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2) # Backoff before retry
                continue
        except Exception as e:
            print(f"      [!] Nominatim error (attempt {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
        break  # success or exhausted retries
    return None

def get_location_google(lat, lon, api_key):
    """Uses Google Maps Geocoding API for highly detailed landmark data."""
    if not GoogleV3:
        return "Google geocoding unavailable (install geopy)"
        
    geolocator = GoogleV3(api_key=api_key)
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Get the exact location
            location = geolocator.reverse(f"{lat}, {lon}", timeout=5)
            if location:
                # We look at the first (most specific) result
                address_components = location[0].raw.get('address_components', [])
                
                # Find Points of Interest, Parks, and Locality (City)
                poi = next((comp['long_name'] for comp in address_components if 'point_of_interest' in comp['types'] or 'park' in comp['types'] or 'establishment' in comp['types']), None)
                city = next((comp['long_name'] for comp in address_components if 'locality' in comp['types']), None)
                
                parts = []
                if poi: parts.append(poi)
                if city: parts.append(city)
                
                if parts:
                    return " - ".join(parts)
                return location[0].address.split(',')[0]
        except (GeocoderTimedOut, GeocoderServiceError) as e:
            print(f"      [!] Google Maps API error (attempt {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
        except Exception as e:
            print(f"      [!] Unexpected Google API error: {e}")
            break
        break
    return None

def update_yaml_caption(asset_path, location_text):
    """Updates or creates the .yaml file with the new location text."""
    yaml_path = os.path.splitext(asset_path)[0] + ".yaml"
    data = {}
    
    if os.path.exists(yaml_path):
        with open(yaml_path, 'r') as f:
            try:
                data = yaml.safe_load(f) or {}
            except yaml.YAMLError:
                pass
                
    # Check if text already exists so we don't overwrite user's custom notes
    existing_text = data.get('text', '')
    
    # If the location is already in the text, skip
    if location_text in existing_text:
        return False
        
    if existing_text and existing_text != "Replace with your caption":
        data['text'] = f"{location_text}\n{existing_text}"
    else:
        data['text'] = location_text
        
    with open(yaml_path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        
    return True

def print_version():
    print(f"🌍 Photo Geo-Extractor v{VERSION} ({VERSION_DATE})")
    print()

def main():
    print_version()
    parser = argparse.ArgumentParser(description="Extract GPS and geocode photos.")
    parser.add_argument("project_dir", help="Path to the project directory containing photos")
    parser.add_argument("--google-key", help="Use Google Maps API for geocoding with this key")
    parser.add_argument("--offline", action="store_true", help="Skip online geocoding; use local reverse_geocoder only")
    parser.add_argument("--inject-yaml", action="store_true", help="Also inject geolocation into per-asset .yaml caption files")
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
    mode_text += " [summary only]" if not args.inject_yaml else " [summary + yaml injection]"

    print(f"🌍 Scanning for GPS data in: {project_dir}")
    print(f"📡 Mode: {mode_text}")

    photos = glob.glob(os.path.join(project_dir, "*.[jJ][pP][gG]"))
    photos.extend(glob.glob(os.path.join(project_dir, "*.[jJ][pP][eE][gG]")))
    photos.sort()

    summary_file = os.path.join(project_dir, "geo_summary.txt")
    summary_lines = ["# Photographic GPS Summary", f"# Project: {os.path.basename(project_dir)}", "="*50]

    processed_count = 0
    geo_count = 0
    
    # Cache for coordinates: {(lat, lon): ("Location Name", "Used Mode")}
    location_cache = {}
    CACHE_RADIUS_METERS = 15.0

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
        for (cached_lat, cached_lon), (cached_name, cached_mode) in location_cache.items():
            dist = haversine_distance(lat, lon, cached_lat, cached_lon)
            if dist <= CACHE_RADIUS_METERS:
                location_name = cached_name
                # Strip previous cache tags so we don't end up with nested cache strings
                base_mode = cached_mode.split(" (")[0] if "Cache" not in cached_mode else cached_mode
                used_mode = f"Cache (within {dist:.1f}m of {base_mode})"
                break
        
        if not location_name:
            if args.offline:
                # Offline-only: skip Nominatim entirely
                used_mode = "Offline"
                location_name = get_location_offline(lat, lon)
            elif args.google_key:
                # Google Maps API
                used_mode = "Google Maps"
                location_name = get_location_google(lat, lon, args.google_key)
            else:
                # Default: try Nominatim, fall back to offline
                used_mode = "Nominatim"
                location_name = get_location_nominatim(lat, lon)
                if not location_name:
                    print(f"      [!] Nominatim failed, falling back to offline geocoding")
                    location_name = get_location_offline(lat, lon)
                    used_mode = "Nominatim->Offline"

            if not location_name:
                location_name = f"{lat:.4f}, {lon:.4f}"
                used_mode = "Raw GPS"

            # Save to cache if we successfully resolved a real location (but
            # don't cache Nominatim results when user asked for offline-only)
            if used_mode != "Raw GPS" and not args.offline:
                location_cache[(lat, lon)] = (location_name, used_mode)

        # Write to summary
        summary_lines.append(f"{filename} | {lat:.6f}, {lon:.6f} | {location_name}")
        
        # Inject into YAML (only if --inject-yaml)
        if args.inject_yaml:
            updated = update_yaml_caption(photo_path, location_name)
            status = "[Updated YAML]" if updated else "[YAML untouched]"
        else:
            status = "[summary only]"
            
        print(f"  [+] {filename}: {location_name} (via {used_mode}) {status}")
        
        processed_count += 1

    # Save summary
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write("\n".join(summary_lines) + "\n")

    print("\n" + "="*50)
    print(f"✅ Found GPS data in {geo_count}/{len(photos)} photos.")
    print(f"📄 Summary saved to: {summary_file}")
    print("==================================================")

if __name__ == "__main__":
    main()
