#!/usr/bin/env python3
"""
REVISIONS:
v36     use ffmpeg only: zoompan + drawtext + boxblur
v39.11  Fixed video frame rate, Added -r {fps} to process_video to prevent duration stretching
v39.12  Audio crossfade implementation - uses FFmpeg acrossfade filter for smooth transitions
v40.0   Separated Audio Muxing from Chunking. Audio now generated as one continuous loop.
v40.1   Fixed performance bug in text overlays missing ultrafast preset parameters.
        Total rendering time: 2h53m for 1460 genuine assets is reduced to 1h4m for 200 or 1500 per chunk
v41.0   Merged photo_geo.py into engine. Added Smart Delay API handling,
        persistent geo_timeline.yaml generation (with location_correction), 
        and an exclusive location text overlay.
v41.5   Reverted FFmpeg filter chains for process_video and process_photo exactly back to V40.1 standard
        to eliminate green screen artifacts.
v41.6   Fixed HDR video green screen by explicitly declaring SDR color space output 
        (-color_range 1 -colorspace bt709 -color_primaries bt709 -color_trc bt709) based on user testing.

FEATURES: Ken Burns (by ffmpeg only), captions, Chinese fonts,
        photo filename overlay, exclusive location overlay,
        audio crossfade between looped music files,
        global geo_timeline.yaml tracking.
"""

import os
import sys
import glob
import json
import itertools
import shutil
import subprocess
import tempfile
import time
import textwrap
import math
from pathlib import Path

import yaml
from PIL import Image, ExifTags

try:
    from geopy.geocoders import Nominatim
    from geopy.exc import GeocoderTimedOut
except ImportError:
    Nominatim = None

VERSION = "41.6"
VERSION_DATE = "2026-06-09"
ENGINE = "Pure FFmpeg (zoompan + drawtext + boxblur)"
DEFAULT_CHUNK_SIZE = 200
WRAP_LENGTH = 50

last_nominatim_time = 0.0

DEFAULT_SECTION_STYLE = {
    "font_size": 56,
    "font_color": "#FFD700",
    "position": "top",
    "font": None
}
DEFAULT_CAPTION_STYLE = {
    "font_size": 40,
    "font_color": "white",
    "position": "bottom",
    "font": None
}

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def print_version():
    print(f"╔══════════════════════════════════════════════════════════════╗")
    print(f"║   Cinematic Video Album Generator v{VERSION} ({ENGINE})   ║")
    print(f"║   Date: {VERSION_DATE}                                          ║")
    print(f"║   Logs: log_render.txt (render log)                           ║")
    print(f"║         log_perf.txt (performance)                            ║")
    print(f"║   Chunk size: {DEFAULT_CHUNK_SIZE} assets                     ║")
    print(f"╚══════════════════════════════════════════════════════════════╝")
    log(f"Starting render engine v{VERSION}")

def wrap_text(text, width=WRAP_LENGTH):
    if not text:
        return ""
    paragraphs = text.split('\n')
    wrapped = []
    for para in paragraphs:
        if para.strip():
            wrapped.append(textwrap.fill(para, width=width, break_long_words=False))
        else:
            wrapped.append('')
    return '\n'.join(wrapped)

def run_ffmpeg(cmd, description="ffmpeg"):
    log(f"   Running {description}...")
    log(f"   [DEBUG CMD] {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        log(f"   [!] FFmpeg error: {e.stderr}")
        raise

def get_media_duration(filepath):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", filepath
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())

def resolve_portable_font():
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]:
        if os.path.exists(p):
            return p
    return None

def check_drawtext_available():
    result = subprocess.run(["ffmpeg", "-filters"], capture_output=True, text=True)
    return "drawtext" in result.stdout

# ====================================================================
# GEO & TIMELINE FUNCTIONS
# ====================================================================

def smart_delay():
    global last_nominatim_time
    elapsed = time.time() - last_nominatim_time
    if elapsed < 1.1:
        time.sleep(1.1 - elapsed)
    last_nominatim_time = time.time()

def get_exif_data(image_path):
    try:
        with Image.open(image_path) as img:
            exif_raw = img._getexif()
            if not exif_raw: return None
            exif_data = {}
            for tag_id, value in exif_raw.items():
                tag = ExifTags.TAGS.get(tag_id, tag_id)
                if tag == 'GPSInfo' and isinstance(value, dict):
                    gps_named = {}
                    for gps_key, gps_val in value.items():
                        gps_name = ExifTags.GPSTAGS.get(gps_key, gps_key)
                        gps_named[gps_name] = gps_val
                    exif_data[tag] = gps_named
                else:
                    exif_data[tag] = value
            return exif_data
    except Exception:
        return None

def get_decimal_coordinates(info):
    for key in ['GPSLatitude', 'GPSLongitude', 'GPSLatitudeRef', 'GPSLongitudeRef']:
        if key not in info: return None
    def convert_to_degrees(value):
        d, m, s = value
        return float(d) + (float(m) / 60.0) + (float(s) / 3600.0)
    try:
        lat = convert_to_degrees(info['GPSLatitude'])
        lon = convert_to_degrees(info['GPSLongitude'])
        if info['GPSLatitudeRef'] != 'N': lat = -lat
        if info['GPSLongitudeRef'] != 'E': lon = -lon
        return lat, lon
    except Exception:
        return None

def get_location_nominatim(lat, lon):
    if not Nominatim:
        log("   [!] Nominatim not available. Install geopy.")
        return None
    geolocator = Nominatim(user_agent="photo_video_album_generator")
    for attempt in range(3):
        try:
            smart_delay()
            location = geolocator.reverse(f"{lat}, {lon}", timeout=5)
            if location:
                address = location.raw.get('address', {})
                landmark = address.get('amenity') or address.get('historic') or address.get('tourism') or address.get('leisure')
                
                raw_parts = []
                for key in ['village', 'town', 'district', 'county', 'city', 'region', 'state']:
                    val = address.get(key)
                    if val and val not in raw_parts:
                        raw_parts.append(val)
                
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
                return location.address.split(',')[0]
        except Exception as e:
            log(f"   [!] Nominatim retry {attempt+1}: {e}")
            time.sleep(2)
    return None

def load_album_config(project_dir, init_mode=False):
    config_path = os.path.join(project_dir, "album_config.yaml")
    defaults = {
        "album": {"title": "", "subtitle": ""},
        "defaults": {
            "photo_duration": 4,
            "kenburns": {"zoom": 1.15, "pan": "center-to-top", "easing": "linear"},
            "caption_style": {
                "font": resolve_portable_font(),
                "font_size": 40,
                "font_color": "white",
                "bg_color": [0, 0, 0, 150],
                "position": "bottom"
            },
            "show_photo_filenames": False
        },
        "section_style": {
            "font": resolve_portable_font(),
            "font_size": 56,
            "font_color": "#FFD700",
            "position": "top"
        },
        "audio": {"default_list": [], "loop": True, "crossfade_seconds": 2},
        "output": {
            "resolution": [1920, 1080],
            "fps": 24,
            "codec": "libx264",
            "bitrate": "5000k",
            "audio_codec": "aac",
            "preset": "ultrafast"
        }
    }
    
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            user_config = yaml.safe_load(f)
            for section, values in user_config.items():
                if isinstance(values, dict) and section in defaults:
                    defaults[section].update(values)
                else:
                    defaults[section] = values
        log(f"Loaded {config_path}")
        if "defaults" in user_config and "kenburns" in user_config["defaults"]:
            kb = user_config["defaults"]["kenburns"]
            if "zoom_intensity" in kb and "zoom" not in kb:
                zoom_intensity = kb["zoom_intensity"]
                defaults["defaults"]["kenburns"]["zoom"] = 1.0 + zoom_intensity
    else:
        config_comment = f"""# ====================================================================
# album_config.yaml - Master configuration for your video album
# Generated by Cinematic Hybrid Media Generator v{VERSION}
# ====================================================================
"""
        with open(config_path, 'w') as f:
            f.write(config_comment)
            yaml.dump(defaults, f, default_flow_style=False, allow_unicode=True)
        log(f"Created default {config_path}")
    
    defaults["output"]["resolution"] = tuple(defaults["output"]["resolution"])
    if isinstance(defaults["defaults"]["caption_style"]["bg_color"], list):
        defaults["defaults"]["caption_style"]["bg_color"] = tuple(defaults["defaults"]["caption_style"]["bg_color"])
    if "show_photo_filenames" not in defaults["defaults"]:
        defaults["defaults"]["show_photo_filenames"] = False
    return defaults

def load_asset_config(asset_path):
    yaml_path = os.path.splitext(asset_path)[0] + ".yaml"
    if os.path.exists(yaml_path):
        with open(yaml_path, 'r') as f:
            return yaml.safe_load(f)
    cap_path = os.path.splitext(asset_path)[0] + ".caption"
    if os.path.exists(cap_path):
        with open(cap_path, 'r', encoding='utf-8') as f:
            text = f.read().strip()
            return {"text": text} if text else None
    return None

def create_default_asset_config(asset_path, project_dir):
    yaml_path = os.path.splitext(asset_path)[0] + ".yaml"
    if os.path.exists(yaml_path):
        return False
    template = f"""# Per-asset configuration for: {os.path.basename(asset_path)}
# text: Caption to display over the asset (remove line if no caption)
# section: Title/Subtitle overlay for chapters
text: "Replace with your caption"
"""
    with open(yaml_path, 'w') as f:
        f.write(template)
    log(f"   Created template asset config: {os.path.basename(yaml_path)}")
    return True

def get_asset_duration(asset_path, album_cfg, asset_config):
    ext = os.path.splitext(asset_path)[1].lower()
    if ext in ['.mp4', '.mov', '.avi']:
        return get_media_duration(asset_path)
    duration = album_cfg["defaults"]["photo_duration"]
    if asset_config and "kenburns" in asset_config and "duration" in asset_config["kenburns"]:
        duration = asset_config["kenburns"]["duration"]
    return float(duration)

def get_zoompan_filter(duration_sec, fps, zoom, pan_direction, easing="linear"):
    total_frames = int(duration_sec * fps)
    if easing == "linear":
        z_expr = f"1+({zoom}-1)*on/{total_frames}"
    elif easing == "ease-in":
        z_expr = f"1+({zoom}-1)*pow(on/{total_frames},2)"
    elif easing == "ease-out":
        z_expr = f"1+({zoom}-1)*pow(on/{total_frames},0.5)"
    else:
        t = "on/{total_frames}"
        z_expr = f"1+({zoom}-1)*((1-cos(PI*{t}))/2)"
    
    pan_map = {
        "center-to-top": (0.5, 0.5, 0.5, 0.0),
        "center-to-bottom": (0.5, 0.5, 0.5, 1.0),
        "center-to-left": (0.5, 0.5, 0.0, 0.5),
        "center-to-right": (0.5, 0.5, 1.0, 0.5),
        "top-left-to-bottom-right": (0.0, 0.0, 1.0, 1.0),
        "top-right-to-bottom-left": (1.0, 0.0, 0.0, 1.0),
        "none": (0.5, 0.5, 0.5, 0.5),
    }
    sx, sy, ex, ey = pan_map.get(pan_direction, pan_map["center-to-top"])
    x_expr = f"(iw-iw/{zoom})*({sx} + ({ex}-{sx})*on/{total_frames})"
    y_expr = f"(ih-ih/{zoom})*({sy} + ({ey}-{sy})*on/{total_frames})"
    return f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d={total_frames}:s=1920x1080:fps={fps}"

def process_photo(asset_path, asset_config, album_cfg, temp_dir, idx):
    duration = album_cfg["defaults"]["photo_duration"]
    if asset_config and "kenburns" in asset_config and "duration" in asset_config["kenburns"]:
        duration = asset_config["kenburns"]["duration"]
    
    kb_default = album_cfg["defaults"]["kenburns"]
    zoom = kb_default.get("zoom", 1.15)
    pan = kb_default.get("pan", "center-to-top")
    easing = kb_default.get("easing", "linear")
    
    fps = album_cfg["output"]["fps"]
    width, height = album_cfg["output"]["resolution"]
    zoompan_filter = get_zoompan_filter(duration, fps, zoom, pan, easing)
    
    probe_cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height", "-of", "json", asset_path]
    result = subprocess.run(probe_cmd, capture_output=True, text=True)
    data = json.loads(result.stdout)
    if data["streams"]:
        w = data["streams"][0]["width"]
        h = data["streams"][0]["height"]
        aspect_ratio = w / h
        use_blur_background = aspect_ratio < 1.6
    else:
        use_blur_background = False
    
    output_path = os.path.join(temp_dir, f"asset_{idx:04d}.mp4")
    
    if use_blur_background:
        cmd = [
            "ffmpeg", "-i", asset_path, "-filter_complex",
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=1,setpts=PTS-STARTPTS[base];"
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},boxblur=30:1,setpts=PTS-STARTPTS[blur];"
            f"[blur][base]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2,{zoompan_filter},format=yuv420p,fps={fps}",
            "-color_range", "1", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-c:v", album_cfg["output"]["codec"], "-preset", album_cfg["output"]["preset"],
            "-b:v", album_cfg["output"]["bitrate"], "-t", str(duration), "-y", output_path
        ]
    else:
        cmd = [
            "ffmpeg", "-i", asset_path,
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=1,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,{zoompan_filter}",
            "-pix_fmt", "yuv420p",
            "-color_range", "1", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-c:v", album_cfg["output"]["codec"], "-preset", album_cfg["output"]["preset"],
            "-b:v", album_cfg["output"]["bitrate"], "-t", str(duration), "-y", output_path
        ]
    run_ffmpeg(cmd, f"photo {os.path.basename(asset_path)}")
    return output_path

def process_video(asset_path, album_cfg, temp_dir, idx):
    width, height = album_cfg["output"]["resolution"]
    fps = album_cfg["output"]["fps"]
    output_path = os.path.join(temp_dir, f"asset_{idx:04d}.mp4")
    
    # Applying user's successful BT.709 color space conversions
    cmd = [
        "ffmpeg", "-i", asset_path,
        "-vf", f"scale={width}:{height}:force_original_aspect_ratio=1,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
        "-r", str(fps),
        "-pix_fmt", "yuv420p",
        "-color_range", "1", 
        "-colorspace", "bt709", 
        "-color_primaries", "bt709", 
        "-color_trc", "bt709",
        "-an",
        "-c:v", album_cfg["output"]["codec"], "-preset", album_cfg["output"]["preset"],
        "-b:v", album_cfg["output"]["bitrate"], "-y", output_path
    ]
    run_ffmpeg(cmd, f"video {os.path.basename(asset_path)}")
    return output_path

def add_text_overlays(video_path, section_text, caption_text, resolution,
                      section_style, caption_style, output_path,
                      photo_filename=None, show_photo_filename=False, 
                      location_text=None, album_cfg=None):
    if not check_drawtext_available():
        shutil.copy2(video_path, output_path)
        return output_path

    filters = []
    temp_files = []

    def add_drawtext(text, style, text_type="caption"):
        if not text:
            return
            
        font = style.get("font") or resolve_portable_font()
        if not font: return

        if text_type == "filename":
            fontsize = 18
            fontcolor = "white"
            box = 1; boxcolor = "black@0.5"; boxborderw = 4
            x = 10; y = "h-30"
        elif text_type == "location":
            fontsize = 40
            fontcolor = "white"
            box = 1; boxcolor = "black@0.5"; boxborderw = 4
            x = 10
            # Position above filename if present
            y = "h-text_h-40" if show_photo_filename else "h-text_h-10"
        else: # Regular Captions/Sections
            fontsize = style.get("font_size", 40)
            fontcolor = style.get("font_color", "white")
            box = 0; boxcolor = "black@0.0"; boxborderw = 0
            position = style.get("position", "bottom")
            if position == "bottom":
                y = f"h-text_h-{int(resolution[1]*0.05)}"
            elif position == "top":
                y = str(int(resolution[1]*0.05))
            else:
                y = "(h-text_h)/2"
            x = "(w-text_w)/2"
            
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as tf:
            tf.write(text)
            text_file = tf.name
            temp_files.append(text_file)
            
        filter_str = (f"drawtext=textfile='{text_file}':fontfile='{font}':"
                      f"fontsize={fontsize}:fontcolor={fontcolor}:x={x}:y={y}:"
                      f"box={box}:boxcolor={boxcolor}:boxborderw={boxborderw}")
        filters.append(filter_str)

    if section_text: add_drawtext(section_text, section_style, "section")
    if caption_text: add_drawtext(caption_text, caption_style, "caption")
    if location_text: add_drawtext(location_text, {}, "location")
    if show_photo_filename and photo_filename: add_drawtext(photo_filename, {}, "filename")

    if not filters:
        shutil.copy2(video_path, output_path)
        return output_path

    vf = ",".join(filters)
    preset = album_cfg["output"]["preset"] if album_cfg else "ultrafast"
    codec = album_cfg["output"]["codec"] if album_cfg else "libx264"
    bitrate = album_cfg["output"]["bitrate"] if album_cfg else "5000k"

    cmd = [
        "ffmpeg", "-i", video_path, "-vf", vf,
        "-c:v", codec, "-preset", preset, "-b:v", bitrate,
        "-color_range", "1", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
        "-c:a", "copy", "-y", output_path
    ]
    run_ffmpeg(cmd, "text overlays")
    for tf in temp_files: os.unlink(tf)
    return output_path

def build_audio_track_ffmpeg(music_files, total_duration, output_path, crossfade=2):
    if not music_files: return None
    loop_files = []
    file_durations = []
    current_timeline_dur = 0.0

    log("   === Audio Timeline ===")
    for f in itertools.cycle(music_files):
        if current_timeline_dur >= total_duration: break
        dur = get_media_duration(f)
        loop_files.append(f)
        file_durations.append(dur)
        mins = int(current_timeline_dur // 60)
        secs = current_timeline_dur % 60
        log(f"      ▶ Starts at {mins:02d}:{secs:05.2f} | {os.path.basename(f)}")
        current_timeline_dur += (dur - crossfade) if dur >= crossfade else dur

    if len(loop_files) == 1:
        cmd = [
            "ffmpeg", "-i", loop_files[0], "-vn",
            "-af", f"afade=t=in:st=0:d={crossfade},afade=t=out:st={max(0, total_duration - crossfade)}:d={crossfade}",
            "-t", str(total_duration), "-acodec", "aac", "-profile:a", "aac_low", "-b:a", "192k", "-y", output_path
        ]
        run_ffmpeg(cmd, "processing single audio file with fading")
        return output_path

    filter_parts = []
    current_output = None
    for i in range(len(loop_files)):
        if i == 0:
            filter_parts.append(f"[{i}]afade=t=in:st=0:d={crossfade}[a{i}]")
            current_output = f"a{i}"
        else:
            prev_dur = file_durations[i-1]
            if prev_dur >= crossfade:
                filter_parts.append(f"[{current_output}][{i}]acrossfade=d={crossfade}[a{i}]")
                current_output = f"a{i}"
            else:
                filter_parts.append(f"[{current_output}][{i}]concat=v=0:a=1[a{i}]")
                current_output = f"a{i}"

    filter_parts.append(f"[{current_output}]afade=t=out:st={max(0, total_duration - crossfade)}:d={crossfade}[final]")
    filter_complex = ";".join(filter_parts)

    cmd = ["ffmpeg"]
    for audio_file in loop_files: cmd.extend(["-i", audio_file])
    cmd.extend([
        "-filter_complex", filter_complex, "-map", "[final]", "-t", str(total_duration),
        "-acodec", "aac", "-profile:a", "aac_low", "-b:a", "192k", "-y", output_path
    ])
    run_ffmpeg(cmd, "building audio track with crossfade")
    return output_path

def main():
    init_mode = "--init" in sys.argv
    if init_mode: sys.argv.remove("--init")

    add_audio_mode = "--add-audio" in sys.argv
    audio_target_video = None
    if add_audio_mode:
        pos = sys.argv.index("--add-audio")
        audio_target_video = sys.argv[pos+1]
        sys.argv.pop(pos)
        sys.argv.pop(pos)

    print_version()
    if len(sys.argv) < 2:
        print("Usage: make_video_album.py <project_name> [start] [end] [--chunk-size N] [--init] [--add-audio <video>]")
        sys.exit(1)

    project_name = sys.argv[1]
    project_dir = os.path.join("/home/gluo/Pictures", project_name)
    if not os.path.isdir(project_dir):
        print(f"❌ Project directory {project_dir} not found")
        sys.exit(1)

    album_cfg = load_album_config(project_dir, init_mode=init_mode)

    # ----------------------------------------------------------------
    # AUDIO MUXING MODE
    # ----------------------------------------------------------------
    if add_audio_mode:
        log("--- GLOBAL AUDIO MUXING ---")
        music_files = sorted(glob.glob(os.path.join(project_dir, "*.mp3")))
        if not music_files:
            log("No music files found. Skipping audio.")
            sys.exit(0)
            
        temp_dir = f"/tmp/{project_name}_audio"
        os.makedirs(temp_dir, exist_ok=True)
        total_dur = get_media_duration(audio_target_video)
        
        audio_path = os.path.join(temp_dir, "full_audio.m4a")
        build_audio_track_ffmpeg(music_files, total_dur, audio_path, crossfade=album_cfg["audio"].get("crossfade_seconds", 2))
        
        final_video = audio_target_video.replace(".mp4", "_temp_audio.mp4")
        cmd_mux = [
            "ffmpeg", "-i", audio_target_video, "-i", audio_path,
            "-c:v", "copy", "-c:a", album_cfg["output"]["audio_codec"],
            "-movflags", "+faststart", "-shortest", "-y", final_video
        ]
        run_ffmpeg(cmd_mux, "muxing audio to master video")
        
        os.replace(final_video, audio_target_video)
        shutil.rmtree(temp_dir, ignore_errors=True)
        log(f"✅ Audio successfully added to {os.path.basename(audio_target_video)}")
        sys.exit(0)

    # ----------------------------------------------------------------
    # ASSET DISCOVERY & TIMELINE PRE-PASS
    # ----------------------------------------------------------------
    start_time = time.time()
    start_idx = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    end_idx = int(sys.argv[3]) if len(sys.argv) > 3 else 999999

    raw_files = []
    for ext in ['*.jpg', '*.jpeg', '*.png', '*.mp4', '*.mov', '*.avi']:
        raw_files.extend(glob.glob(os.path.join(project_dir, ext)))
        raw_files.extend(glob.glob(os.path.join(project_dir, ext.upper())))
        
    all_assets = sorted([
        f for f in set(raw_files)
        if not os.path.basename(f).startswith("part_")
        and "_MASTER" not in os.path.basename(f).upper()
    ])
    log(f"Found {len(all_assets)} total assets.")

    # Timeline Sync
    timeline_path = os.path.join(project_dir, "geo_timeline.yaml")
    geo_timeline = {}
    if os.path.exists(timeline_path):
        with open(timeline_path, 'r', encoding='utf-8') as f:
            geo_timeline = yaml.safe_load(f) or {}

    log("Syncing global timeline (geo_timeline.yaml)...")
    current_time_tracker = 0.0
    timeline_updated = False
    
    for asset_path in all_assets:
        filename = os.path.basename(asset_path)
        ext = os.path.splitext(asset_path)[1].lower()
        
        if filename not in geo_timeline:
            geo_timeline[filename] = {"gps": None, "location": "", "location_correction": "", "start_time": 0.0, "duration": 0.0}
            timeline_updated = True
            
        t_data = geo_timeline[filename]

        # Calculate exact start_time dynamically
        if t_data.get("start_time") != current_time_tracker:
            t_data["start_time"] = current_time_tracker
            timeline_updated = True

        # Grab duration (cache video duration to save ffprobe time)
        if ext in ['.mp4', '.mov', '.avi']:
            if t_data.get("duration", 0.0) == 0.0:
                t_data["duration"] = get_media_duration(asset_path)
                timeline_updated = True
        else:
            new_dur = get_asset_duration(asset_path, album_cfg, load_asset_config(asset_path))
            if t_data.get("duration") != new_dur:
                t_data["duration"] = new_dur
                timeline_updated = True
        
        # Extract GPS silently (no Nominatim calls yet)
        if t_data.get("gps") is None and ext in ['.jpg', '.jpeg', '.png']:
            exif = get_exif_data(asset_path)
            if exif and 'GPSInfo' in exif:
                coords = get_decimal_coordinates(exif['GPSInfo'])
                if coords:
                    t_data["gps"] = list(coords)
                    timeline_updated = True

        current_time_tracker += t_data["duration"]

    if timeline_updated:
        with open(timeline_path, 'w', encoding='utf-8') as f:
            yaml.dump(geo_timeline, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    if init_mode:
        log("Initialisation complete. Exiting.")
        sys.exit(0)

    # ----------------------------------------------------------------
    # CHUNK PROCESSING
    # ----------------------------------------------------------------
    chunk_assets = all_assets[start_idx:end_idx]
    temp_dir = f"/tmp/{project_name}"
    os.makedirs(temp_dir, exist_ok=True)
    
    segment_files = []
    default_section_style = album_cfg.get("section_style", DEFAULT_SECTION_STYLE.copy())
    default_caption_style = album_cfg["defaults"]["caption_style"].copy()
    show_photo_filenames = album_cfg["defaults"].get("show_photo_filenames", False)

    for idx, asset_path in enumerate(chunk_assets):
        filename = os.path.basename(asset_path)
        log(f"Processing {filename}")
        
        # Geolocation Resolution via Timeline
        t_data = geo_timeline.get(filename, {})
        location_text = None
        
        if t_data.get("location_correction"):
            location_text = t_data["location_correction"]
            log(f"   Location (Override): {location_text}")
        elif t_data.get("location"):
            location_text = t_data["location"]
            log(f"   Location (Cached): {location_text}")
        elif t_data.get("gps"):
            lat, lon = t_data["gps"]
            loc = get_location_nominatim(lat, lon)
            if loc:
                t_data["location"] = loc
                location_text = loc
                log(f"   Location (Fetched): {location_text}")
                # Save dynamically so we don't lose data if it crashes
                with open(timeline_path, 'w', encoding='utf-8') as f:
                    yaml.dump(geo_timeline, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            else:
                log(f"   Location (Fetch Failed): GPS {lat:.4f}, {lon:.4f}")

        asset_config = load_asset_config(asset_path)
        ext = os.path.splitext(asset_path)[1].lower()
        
        section_text = None
        caption_text = asset_config.get("text") if asset_config else None
        photo_filename = filename if (show_photo_filenames and ext in ['.jpg', '.jpeg', '.png']) else None

        if asset_config and "section" in asset_config:
            title = asset_config["section"].get("title", "")
            subtitle = asset_config["section"].get("subtitle", "")
            if title: section_text = title + ("\n" + subtitle if subtitle else "")

        sec_style = default_section_style.copy()
        cap_style = default_caption_style.copy()
        
        if ext in ['.jpg', '.jpeg', '.png']:
            seg_path = process_photo(asset_path, asset_config, album_cfg, temp_dir, idx)
        else:
            seg_path = process_video(asset_path, album_cfg, temp_dir, idx)
        
        if section_text or caption_text or photo_filename or location_text:
            wrapped_section = wrap_text(section_text, width=WRAP_LENGTH) if section_text else None
            wrapped_caption = wrap_text(caption_text, width=WRAP_LENGTH) if caption_text else None
            capped_path = seg_path.replace(".mp4", "_capped.mp4")
            
            seg_path = add_text_overlays(
                seg_path, wrapped_section, wrapped_caption,
                album_cfg["output"]["resolution"], sec_style, cap_style, capped_path,
                photo_filename=photo_filename, show_photo_filename=show_photo_filenames,
                location_text=location_text, album_cfg=album_cfg
            )
        segment_files.append(seg_path)
    
    if not segment_files:
        log("❌ No segments produced")
        sys.exit(1)
    
    log(f"Concatenating {len(segment_files)} segments...")
    concat_list = os.path.join(temp_dir, "concat.txt")
    with open(concat_list, "w") as f:
        for seg in segment_files: f.write(f"file '{seg}'\n")
    
    part_output = os.path.join(project_dir, f"part_{start_idx:04d}_{end_idx:04d}.mp4")
    cmd_concat = [
        "ffmpeg", "-f", "concat", "-safe", "0", "-i", concat_list,
        "-c", "copy", "-movflags", "+faststart", "-y", part_output
    ]
    run_ffmpeg(cmd_concat, "concatenating segments")
    
    shutil.rmtree(temp_dir, ignore_errors=True)
    elapsed = time.time() - start_time
    log(f"✅ Done: {part_output} (Silent Video Chunk)")
    log(f"⏱️ Total processing time: {elapsed:.1f} seconds")

if __name__ == "__main__":
    main()
