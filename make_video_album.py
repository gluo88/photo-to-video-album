#!/usr/bin/env python3
"""
REVISIONS:
v34     Kern Burns (by ffmpeg and moviepy), captions, blurred background
v36     use ffmpeg only: zoompan + drawtext + boxblur
        having major performance enhancement. 8-20 time faster.
        Processed 1480 photos (200 per chunk) in about one hour
v39.11  Fixed video frame rate, Added -r {fps} to process_video to prevent duration stretching
v39.12  Audio crossfade implementation - uses FFmpeg acrossfade filter for smooth transitions
        between looped music files. Configurable via audio.crossfade_seconds in album_config.yaml
        Also consolidated versioned filenames: make_video_album_v39_11.py -> make_video_album.py

FEATURES: Ken Burns (by ffmpeg only), title/subtitle/captions, Chinese fonts,
        photo filename overlay option (2.5× slower when enabled),
        audio crossfade between looped music files,
        two types of yaml files for configuration

Note to LLM (please do not remove this note):
     1. please update this revision history by adding new content and keeping all existing contents.
"""


"""
Cinematic Video Album Generator v39.12 – Audio Crossfade Implementation
- Added FFmpeg acrossfade filter for smooth audio transitions between looped music files
- Configurable crossfade duration via audio.crossfade_seconds in album_config.yaml (default: 2 seconds)
- Consolidated file naming: make_video_album.py (was make_video_album_v39_11.py)
- Fade-in at start, fade-out at end of final audio track
- Gracefully handles short audio files by skipping crossfade and using concat instead
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
from pathlib import Path

import yaml

VERSION = "39.12"
VERSION_DATE = "2026-06-06"
ENGINE = "Pure FFmpeg (zoompan + drawtext + boxblur)"
DEFAULT_CHUNK_SIZE = 200
WRAP_LENGTH = 50
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
    print(f"║   Caption wrap: {WRAP_LENGTH} chars/line                      ║")
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
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        log(f"FFmpeg error: {e.stderr}")
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
        "section_card_duration": 4,
        "opening_card_duration": 5,
        "title_card_background": "black",
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
        font_path = resolve_portable_font() or "None"
        config_comment = f"""# ====================================================================
# album_config.yaml - Master configuration for your video album
# Generated by Cinematic Hybrid Media Generator v{VERSION}
# ====================================================================
# Edit values below to customize your album.

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
    ext = os.path.splitext(asset_path)[1].lower()
    is_video = ext in ['.mp4', '.mov', '.avi']
    template = f"""# ====================================================================
# Per-asset configuration for: {os.path.basename(asset_path)}
# Generated by Cinematic Hybrid Media Generator v{VERSION}
# ====================================================================
# This file overrides settings from album_config.yaml for this specific asset.
#
# text: Caption to display over the asset (remove line if no caption)
"""
    if is_video:
        template += f"""#
# For videos, only 'text', 'section', and 'style' are supported (no Ken Burns).
"""
    else:
        template += f"""#
# kenburns: Override the album's Ken Burns settings for this photo only.
#   zoom: Final zoom factor (e.g., 1.3)
#   pan: Pan direction (see album_config.yaml for options)
#   easing: "linear", "ease-in", "ease-out", "ease-in-out"
#   duration: Override global photo_duration for this photo (seconds)
#
# style: Override caption appearance (font, size, color, position, etc.)
#
# section: If present, the title will be overlaid on this asset.
#   title: Section title (required)
#   subtitle: Section subtitle (optional)
#
# ====================================================================
# Example with custom values:
#
text: "Replace with your caption"
#
# kenburns:
#   zoom: 1.25
#   pan: "top-left-to-bottom-right"
#   easing: "ease-out"
#   duration: 6
#
# style:
#   font_size: 56
#   font_color: "#FFD700"
#   position: "top"
#
# section:
#   title: "My Section Title"
#   subtitle: "Optional subtitle"
#
# ====================================================================
"""
    with open(yaml_path, 'w') as f:
        f.write(template)
    log(f"   Created template asset config: {os.path.basename(yaml_path)}")
    return True

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
    if "zoom_intensity" in kb_default:
        zoom = 1.0 + kb_default["zoom_intensity"]
    pan = kb_default.get("pan", "center-to-top")
    easing = kb_default.get("easing", "linear")
    
    if asset_config and "kenburns" in asset_config:
        kb = asset_config["kenburns"]
        if "zoom" in kb:
            zoom = kb["zoom"]
        elif "zoom_intensity" in kb:
            zoom = 1.0 + kb["zoom_intensity"]
        if "pan" in kb:
            pan = kb["pan"]
        if "easing" in kb:
            easing = kb["easing"]
        if "duration" in kb:
            duration = kb["duration"]
    
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
        log(f"   Photo {os.path.basename(asset_path)}: {w}x{h} (aspect {aspect_ratio:.2f}) -> blur={use_blur_background}")
    else:
        use_blur_background = False
    
    output_path = os.path.join(temp_dir, f"asset_{idx:04d}.mp4")
    
    if use_blur_background:
        cmd = [
            "ffmpeg", "-i", asset_path, "-filter_complex",
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=1,setpts=PTS-STARTPTS[base];"
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},boxblur=30:1,setpts=PTS-STARTPTS[blur];"
            f"[blur][base]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2,{zoompan_filter},format=yuv420p,fps={fps}",
            "-c:v", album_cfg["output"]["codec"], "-preset", album_cfg["output"]["preset"],
            "-b:v", album_cfg["output"]["bitrate"], "-t", str(duration), "-y", output_path
        ]
    else:
        cmd = [
            "ffmpeg", "-i", asset_path,
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=1,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,{zoompan_filter}",
            "-pix_fmt", "yuv420p",
            "-c:v", album_cfg["output"]["codec"], "-preset", album_cfg["output"]["preset"],
            "-b:v", album_cfg["output"]["bitrate"], "-t", str(duration), "-y", output_path
        ]
    run_ffmpeg(cmd, f"photo {os.path.basename(asset_path)}")
    return output_path

def process_video(asset_path, album_cfg, temp_dir, idx):
    width, height = album_cfg["output"]["resolution"]
    fps = album_cfg["output"]["fps"]          # ← get target frame rate
    output_path = os.path.join(temp_dir, f"asset_{idx:04d}.mp4")
    cmd = [
        "ffmpeg", "-i", asset_path,
        "-vf", f"scale={width}:{height}:force_original_aspect_ratio=1,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
        "-r", str(fps),                       # ← force output frame rate
        "-pix_fmt", "yuv420p",
        "-an",
        "-c:v", album_cfg["output"]["codec"], "-preset", album_cfg["output"]["preset"],
        "-b:v", album_cfg["output"]["bitrate"], "-y", output_path
    ]
    run_ffmpeg(cmd, f"video {os.path.basename(asset_path)}")
    return output_path

def add_text_overlays(video_path, section_text, caption_text, resolution,
                      section_style, caption_style, output_path,
                      photo_filename=None, show_photo_filename=False):
    if not check_drawtext_available():
        log("   WARNING: 'drawtext' missing, skipping text overlays")
        shutil.copy2(video_path, output_path)
        return output_path

    filters = []
    temp_files = []

    def add_drawtext(text, style, is_photo_filename=False):
        if not text:
            return
        if is_photo_filename:
            font = caption_style.get("font")
            if not font:
                font = resolve_portable_font()
            if not font:
                log("   WARNING: No font for filename overlay")
                return
            fontsize = 18
            fontcolor = "white"
            box = 1
            boxcolor = "black@0.5"
            boxborderw = 4
            x = 10
            y = f"h-30"
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as tf:
                tf.write(text)
                text_file = tf.name
                temp_files.append(text_file)
            filter_str = (f"drawtext=textfile='{text_file}':fontfile='{font}':"
                          f"fontsize={fontsize}:fontcolor={fontcolor}:x={x}:y={y}:"
                          f"box={box}:boxcolor={boxcolor}:boxborderw={boxborderw}")
            filters.append(filter_str)
            return

        font = style.get("font")
        fontsize = style.get("font_size", 40)
        color = style.get("font_color", "white")
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
                      f"fontsize={fontsize}:fontcolor={color}:x={x}:y={y}")
        filters.append(filter_str)

    if section_text:
        add_drawtext(section_text, section_style, is_photo_filename=False)
    if caption_text:
        add_drawtext(caption_text, caption_style, is_photo_filename=False)
    if show_photo_filename and photo_filename:
        add_drawtext(photo_filename, {}, is_photo_filename=True)

    if not filters:
        shutil.copy2(video_path, output_path)
        return output_path

    vf = ",".join(filters)
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", vf,
        "-c:a", "copy", "-y", output_path
    ]
    run_ffmpeg(cmd, "text overlays")
    for tf in temp_files:
        os.unlink(tf)
    return output_path

def build_audio_track_ffmpeg(music_files, total_duration, output_path, crossfade=2):
    if not music_files:
        return None
    total_dur = 0
    loop_files = []
    file_durations = []
    for f in itertools.cycle(music_files):
        if total_dur >= total_duration:
            break
        loop_files.append(f)
        dur = get_media_duration(f)
        file_durations.append(dur)
        total_dur += dur

    log(f"   Building audio track with {len(loop_files)} files, crossfade: {crossfade}s")

    if len(loop_files) == 1:
        cmd = [
            "ffmpeg", "-i", loop_files[0],
            "-af", f"afade=t=in:st=0:d={crossfade},afade=t=out:st={max(0, total_duration - crossfade)}:d={crossfade}",
            "-t", str(total_duration),
            "-acodec", "aac",
            "-profile:a", "aac_low",
            "-b:a", "192k",
            "-y", output_path
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
                log(f"      File {i} ({os.path.basename(loop_files[i-1])}) shorter than crossfade duration, skipping crossfade")
                filter_parts.append(f"[{current_output}][{i}]concat=v=0:a=1[a{i}]")
                current_output = f"a{i}"

    filter_parts.append(f"[{current_output}]afade=t=out:st={max(0, total_duration - crossfade)}:d={crossfade}[final]")

    filter_complex = ";".join(filter_parts)

    cmd = ["ffmpeg"]
    for audio_file in loop_files:
        cmd.extend(["-i", audio_file])

    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[final]",
        "-t", str(total_duration),
        "-acodec", "aac",
        "-profile:a", "aac_low",
        "-b:a", "192k",
        "-y", output_path
    ])

    run_ffmpeg(cmd, "building audio track with crossfade")
    return output_path

def main():
    init_mode = "--init" in sys.argv
    if init_mode:
        sys.argv.remove("--init")

    print_version()
    
    if len(sys.argv) < 2:
        print("Usage: make_video_album_v39_11.py <project_name> [start] [end] [--chunk-size N] [--init]")
        sys.exit(1)

    start_time = time.time()
    project_name = sys.argv[1]
    start_idx = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    end_idx = int(sys.argv[3]) if len(sys.argv) > 3 else 999999
    chunk_size = DEFAULT_CHUNK_SIZE
    if "--chunk-size" in sys.argv:
        pos = sys.argv.index("--chunk-size")
        chunk_size = int(sys.argv[pos+1])

    project_dir = os.path.join("/home/gluo/Pictures", project_name)
    if not os.path.isdir(project_dir):
        print(f"❌ Project directory {project_dir} not found")
        sys.exit(1)

    drawtext_ok = check_drawtext_available()
    if not drawtext_ok:
        log("⚠️ WARNING: ffmpeg lacks 'drawtext' filter. Captions and title cards will be blank.")
        log("   Install ffmpeg with libfreetype (e.g., 'sudo apt install ffmpeg')")

    log("Loading album config...")
    album_cfg = load_album_config(project_dir, init_mode=init_mode)

    log("Discovering assets...")
    raw_files = []
    for ext in ['*.jpg', '*.jpeg', '*.png', '*.mp4', '*.mov', '*.avi']:
        raw_files.extend(glob.glob(os.path.join(project_dir, ext)))
        raw_files.extend(glob.glob(os.path.join(project_dir, ext.upper())))
    assets = sorted([
        f for f in set(raw_files)
        if not os.path.basename(f).startswith("part_")
        and "_MASTER" not in os.path.basename(f).upper()
    ])[start_idx:end_idx]
    log(f"Found {len(assets)} assets")
    
    if init_mode:
        log("--init mode: generating configuration files only.")
        if assets:
            create_default_asset_config(assets[0], project_dir)
            log(f"Created per‑asset template for {os.path.basename(assets[0])}")
        else:
            log("No assets found. Only album_config.yaml was created.")
        log("Initialisation complete. Exiting.")
        sys.exit(0)
    
    if assets:
        first_asset = assets[0]
        create_default_asset_config(first_asset, project_dir)

    temp_dir = f"/tmp/{project_name}"
    os.makedirs(temp_dir, exist_ok=True)

    segment_files = []
    album_title = album_cfg["album"].get("title", "")
    album_subtitle = album_cfg["album"].get("subtitle", "")
    album_text = None
    if album_title or album_subtitle:
        album_text = album_title + ("\n" + album_subtitle if album_subtitle else "")
        log(f"Album title will be overlaid on the first asset: '{album_text}'")
    
    default_section_style = album_cfg.get("section_style", DEFAULT_SECTION_STYLE.copy())
    default_caption_style = album_cfg["defaults"]["caption_style"].copy()
    if not default_section_style.get("font"):
        default_section_style["font"] = resolve_portable_font()
    if not default_caption_style.get("font"):
        default_caption_style["font"] = resolve_portable_font()
    
    if default_section_style.get("font") != default_caption_style.get("font"):
        if default_caption_style.get("font") and "NotoSansCJK" in str(default_caption_style["font"]):
            default_section_style["font"] = default_caption_style["font"]
            log("   Applied Chinese‑capable font to section titles")
    
    if isinstance(default_caption_style.get("bg_color"), list):
        default_caption_style["bg_color"] = tuple(default_caption_style["bg_color"])
    
    show_photo_filenames = album_cfg["defaults"].get("show_photo_filenames", False)
    if show_photo_filenames:
        log("   Photo filename overlay enabled (bottom-left corner)")
    
    for idx, asset_path in enumerate(assets):
        log(f"Processing {os.path.basename(asset_path)}")
        asset_config = load_asset_config(asset_path)
        ext = os.path.splitext(asset_path)[1].lower()
        
        section_text = None
        caption_text = None
        photo_filename = None
        
        if idx == 0 and album_text:
            section_text = album_text
            album_text = None
            log(f"   Album title added to section text")
        
        if asset_config and "section" in asset_config:
            sect = asset_config["section"]
            title = sect.get("title", "")
            subtitle = sect.get("subtitle", "")
            if title:
                sect_str = title + ("\n" + subtitle if subtitle else "")
                if section_text:
                    section_text = section_text + "\n\n" + sect_str
                else:
                    section_text = sect_str
                log(f"   Section text: '{sect_str}'")
        
        if asset_config and "text" in asset_config and asset_config["text"]:
            caption_text = asset_config["text"]
            log(f"   Caption text: '{caption_text[:40]}...'")
        
        if show_photo_filenames and ext in ['.jpg', '.jpeg', '.png']:
            photo_filename = os.path.basename(asset_path)
            log(f"   Photo filename overlay: {photo_filename}")
        
        sec_style = default_section_style.copy()
        cap_style = default_caption_style.copy()
        if asset_config and "style" in asset_config:
            cap_style.update(asset_config["style"])
        
        if ext in ['.jpg', '.jpeg', '.png']:
            seg_path = process_photo(asset_path, asset_config, album_cfg, temp_dir, idx)
        else:
            seg_path = process_video(asset_path, album_cfg, temp_dir, idx)
        
        if section_text or caption_text or photo_filename:
            wrapped_section = wrap_text(section_text, width=WRAP_LENGTH) if section_text else None
            wrapped_caption = wrap_text(caption_text, width=WRAP_LENGTH) if caption_text else None
            capped_path = seg_path.replace(".mp4", "_capped.mp4")
            seg_path = add_text_overlays(seg_path, wrapped_section, wrapped_caption,
                                         album_cfg["output"]["resolution"],
                                         sec_style, cap_style, capped_path,
                                         photo_filename=photo_filename,
                                         show_photo_filename=bool(photo_filename))
        segment_files.append(seg_path)
    
    if not segment_files:
        log("❌ No segments produced")
        sys.exit(1)
    
    log(f"Concatenating {len(segment_files)} segments...")
    concat_list = os.path.join(temp_dir, "concat.txt")
    with open(concat_list, "w") as f:
        for seg in segment_files:
            f.write(f"file '{seg}'\n")
    part_output = os.path.join(project_dir, f"part_{start_idx:04d}_{end_idx:04d}.mp4")
    cmd_concat = [
        "ffmpeg", "-f", "concat", "-safe", "0", "-i", concat_list,
        "-c", "copy", "-movflags", "+faststart", "-y", part_output
    ]
    run_ffmpeg(cmd_concat, "concatenating segments")
    
    music_files = sorted(glob.glob(os.path.join(project_dir, "*.mp3")))
    if album_cfg["audio"]["default_list"]:
        music_files = album_cfg["audio"]["default_list"]
    if music_files:
        log("Adding background music...")
        log(f"   Audio files ({len(music_files)} total):")
        for mf in music_files:
            log(f"      - {os.path.basename(mf)}")
        total_dur = get_media_duration(part_output)
        log(f"   Video duration: {total_dur:.1f} seconds")
        audio_path = os.path.join(temp_dir, "full_audio.m4a")
        build_audio_track_ffmpeg(
            music_files, total_dur, audio_path,
            crossfade=album_cfg["audio"].get("crossfade_seconds", 2)
        )
        final_video = part_output.replace(".mp4", "_temp.mp4")
        cmd_mux = [
            "ffmpeg", "-i", part_output, "-i", audio_path,
            "-c:v", "copy", "-c:a", album_cfg["output"]["audio_codec"],
            "-movflags", "+faststart", "-shortest", "-y", final_video
        ]
        run_ffmpeg(cmd_mux, "muxing audio")
        os.replace(final_video, part_output)
    
    shutil.rmtree(temp_dir, ignore_errors=True)
    elapsed = time.time() - start_time
    log(f"✅ Done: {part_output}")
    log(f"⏱️ Total processing time: {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)")

if __name__ == "__main__":
    main()
