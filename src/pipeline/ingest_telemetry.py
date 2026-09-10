"""
ingest_telemetry.py — Drone video frame extraction and DJI SRT telemetry synchronization.

Extracts video frames at specified FPS or count, parses DJI subtitle telemetry (SRT),
and generates a synchronized telemetry_index.json mapping each frame to its
interpolated GPS and flight state parameters for downstream metric alignment.

Usage:
    python src/pipeline/ingest_telemetry.py --video data/sample/drone_test.MP4 --srt data/sample/drone_test.SRT --out outputs/smoke_ingest --fps 2
"""

import os
import sys
import re
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional
import cv2
import numpy as np


def parse_timecode(tc_str: str) -> float:
    """
    Convert SRT timecode string (HH:MM:SS,mmm or HH:MM:SS.mmm) to seconds.
    """
    tc_clean = tc_str.strip().replace(",", ".")
    parts = tc_clean.split(":")
    if len(parts) == 3:
        h = float(parts[0])
        m = float(parts[1])
        s = float(parts[2])
        return h * 3600.0 + m * 60.0 + s
    elif len(parts) == 2:
        m = float(parts[0])
        s = float(parts[1])
        return m * 60.0 + s
    return float(parts[0])


def parse_dji_srt(srt_path: str) -> List[Dict[str, Any]]:
    """
    Parse DJI drone SRT subtitle file into a sorted list of telemetry records.

    Supports:
    1. Standard DJI format:
       HOME(lon, lat) YYYY.MM.DD HH:MM:SS
       GPS(lon, lat, alt) BAROMETER:value
       ISO:value Shutter:value EV:value Fnum:value
    2. Bracketed DJI format:
       [latitude: ...] [longitude: ...] [altitude: ...]
    """
    if not os.path.exists(srt_path):
        print(f"[WARNING] SRT file not found: {srt_path}")
        return []

    encodings = ["utf-8-sig", "utf-8", "latin-1"]
    content = None
    for enc in encodings:
        try:
            with open(srt_path, "r", encoding=enc) as f:
                content = f.read()
            break
        except Exception:
            continue

    if content is None:
        print(f"[ERROR] Could not read SRT file with supported encodings: {srt_path}")
        return []

    # Regex patterns for DJI SRT formats
    # Standard format: HOME(lon, lat), GPS(lon, lat, alt)
    home_pat = re.compile(r"HOME\s*\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)")
    gps_pat = re.compile(r"GPS\s*\(\s*([-\d.]+)\s*,\s*([-\d.]+)(?:\s*,\s*([-\d.]+))?\s*\)")
    baro_pat = re.compile(r"BAROMETER\s*:\s*([-\d.]+)", re.IGNORECASE)
    dt_pat = re.compile(r"(\d{4}[./-]\d{2}[./-]\d{2}\s+\d{2}:\d{2}:\d{2})")
    iso_pat = re.compile(r"ISO\s*:\s*(\d+)", re.IGNORECASE)
    shutter_pat = re.compile(r"Shutter\s*:\s*([^\s,]+)", re.IGNORECASE)
    ev_pat = re.compile(r"EV\s*:\s*([^\s,]+)", re.IGNORECASE)
    fnum_pat = re.compile(r"Fnum\s*:\s*([^\s,]+)", re.IGNORECASE)

    # Bracketed format fallbacks
    b_lat_pat = re.compile(r"\[(?:lat|latitude)\s*:\s*([-\d.]+)\]", re.IGNORECASE)
    b_lon_pat = re.compile(r"\[(?:lon|longitude)\s*:\s*([-\d.]+)\]", re.IGNORECASE)
    b_alt_pat = re.compile(r"\[(?:alt|altitude|rel_alt)\s*:\s*([-\d.]+)\]", re.IGNORECASE)
    b_baro_pat = re.compile(r"\[barometer\s*:\s*([-\d.]+)\]", re.IGNORECASE)
    b_iso_pat = re.compile(r"\[iso\s*:\s*(\d+)\]", re.IGNORECASE)
    b_shutter_pat = re.compile(r"\[shutter\s*:\s*([^\]]+)\]", re.IGNORECASE)
    b_fnum_pat = re.compile(r"\[fnum\s*:\s*([^\]]+)\]", re.IGNORECASE)
    b_ev_pat = re.compile(r"\[ev\s*:\s*([^\]]+)\]", re.IGNORECASE)

    records: List[Dict[str, Any]] = []
    # Split blocks separated by blank lines
    blocks = re.split(r"\r?\n\s*\r?\n", content.strip())

    for b in blocks:
        lines = [l.strip() for l in b.strip().splitlines() if l.strip()]
        if len(lines) < 2:
            continue

        # Look for timecode line (contains '-->')
        tc_line = None
        for l in lines[:3]:
            if "-->" in l:
                tc_line = l
                break
        if not tc_line:
            continue

        try:
            start_tc, end_tc = tc_line.split("-->")
            start_sec = parse_timecode(start_tc)
            end_sec = parse_timecode(end_tc)
            mid_sec = (start_sec + end_sec) / 2.0
        except Exception:
            continue

        block_text = " ".join(lines)

        # GPS coordinates
        lat = None
        lon = None
        alt = 0.0

        gps_match = gps_pat.search(block_text)
        if gps_match:
            # In DJI standard SRT: GPS(lon, lat, alt)
            lon = float(gps_match.group(1))
            lat = float(gps_match.group(2))
            if gps_match.group(3) is not None:
                alt = float(gps_match.group(3))
        else:
            lat_m = b_lat_pat.search(block_text)
            lon_m = b_lon_pat.search(block_text)
            alt_m = b_alt_pat.search(block_text)
            if lat_m and lon_m:
                lat = float(lat_m.group(1))
                lon = float(lon_m.group(1))
            if alt_m:
                alt = float(alt_m.group(1))

        if lat is None or lon is None:
            continue

        # Home coordinates
        home_lat = None
        home_lon = None
        home_match = home_pat.search(block_text)
        if home_match:
            home_lon = float(home_match.group(1))
            home_lat = float(home_match.group(2))

        # Barometer
        baro = None
        baro_match = baro_pat.search(block_text) or b_baro_pat.search(block_text)
        if baro_match:
            try:
                baro = float(baro_match.group(1))
            except ValueError:
                pass

        # Datetime
        dt_str = None
        dt_match = dt_pat.search(block_text)
        if dt_match:
            dt_str = dt_match.group(1)

        # Camera settings
        iso_val = None
        iso_m = iso_pat.search(block_text) or b_iso_pat.search(block_text)
        if iso_m:
            try:
                iso_val = int(iso_m.group(1))
            except ValueError:
                pass

        shutter_val = None
        shutter_m = shutter_pat.search(block_text) or b_shutter_pat.search(block_text)
        if shutter_m:
            shutter_val = shutter_m.group(1).strip()

        ev_val = None
        ev_m = ev_pat.search(block_text) or b_ev_pat.search(block_text)
        if ev_m:
            ev_val = ev_m.group(1).strip()

        fnum_val = None
        fnum_m = fnum_pat.search(block_text) or b_fnum_pat.search(block_text)
        if fnum_m:
            fnum_val = fnum_m.group(1).strip()

        records.append({
            "start_sec": start_sec,
            "end_sec": end_sec,
            "mid_sec": mid_sec,
            "lat": lat,
            "lon": lon,
            "altitude": alt,
            "barometer": baro,
            "home_lat": home_lat,
            "home_lon": home_lon,
            "datetime": dt_str,
            "camera": {
                "iso": iso_val,
                "shutter": shutter_val,
                "ev": ev_val,
                "fnum": fnum_val,
            }
        })

    # Sort records chronologically by mid_sec
    records.sort(key=lambda r: r["mid_sec"])
    return records


def interpolate_telemetry(srt_records: List[Dict[str, Any]], target_time_sec: float) -> Optional[Dict[str, Any]]:
    """
    Interpolate or match telemetry from parsed SRT records for a given target timestamp in seconds.

    Returns a telemetry dictionary containing:
      - 'gps': dict with 'lat', 'lon', 'altitude', 'barometer', 'timestamp_sec'
      - 'home': dict with 'lat', 'lon'
      - 'datetime': str
      - 'camera': dict
    """
    if not srt_records:
        return None

    # Range clamping if target_time is outside available SRT records
    if target_time_sec <= srt_records[0]["mid_sec"]:
        r = srt_records[0]
        return {
            "gps": {
                "lat": round(r["lat"], 7),
                "lon": round(r["lon"], 7),
                "altitude": round(r["altitude"], 3),
                "barometer": round(r["barometer"], 2) if r.get("barometer") is not None else None,
                "timestamp_sec": round(target_time_sec, 4),
            },
            "lat": round(r["lat"], 7),
            "lon": round(r["lon"], 7),
            "altitude": round(r["altitude"], 3),
            "barometer": round(r["barometer"], 2) if r.get("barometer") is not None else None,
            "home": {"lat": r.get("home_lat"), "lon": r.get("home_lon")},
            "datetime": r.get("datetime"),
            "camera": r.get("camera", {}),
            "source_srt_sec": round(r["mid_sec"], 4)
        }

    if target_time_sec >= srt_records[-1]["mid_sec"]:
        r = srt_records[-1]
        return {
            "gps": {
                "lat": round(r["lat"], 7),
                "lon": round(r["lon"], 7),
                "altitude": round(r["altitude"], 3),
                "barometer": round(r["barometer"], 2) if r.get("barometer") is not None else None,
                "timestamp_sec": round(target_time_sec, 4),
            },
            "lat": round(r["lat"], 7),
            "lon": round(r["lon"], 7),
            "altitude": round(r["altitude"], 3),
            "barometer": round(r["barometer"], 2) if r.get("barometer") is not None else None,
            "home": {"lat": r.get("home_lat"), "lon": r.get("home_lon")},
            "datetime": r.get("datetime"),
            "camera": r.get("camera", {}),
            "source_srt_sec": round(r["mid_sec"], 4)
        }

    # Binary search to find bounding records [idx1, idx2]
    low = 0
    high = len(srt_records) - 1
    while low <= high:
        mid = (low + high) // 2
        if srt_records[mid]["mid_sec"] <= target_time_sec:
            low = mid + 1
        else:
            high = mid - 1

    idx1 = max(0, min(len(srt_records) - 1, high))
    idx2 = max(0, min(len(srt_records) - 1, idx1 + 1))
    r1 = srt_records[idx1]
    r2 = srt_records[idx2]

    t1 = r1["mid_sec"]
    t2 = r2["mid_sec"]
    dt = t2 - t1
    alpha = (target_time_sec - t1) / dt if dt > 1e-6 else 0.0
    alpha = max(0.0, min(1.0, alpha))

    # Continuous parameters linearly interpolated
    lat = r1["lat"] + alpha * (r2["lat"] - r1["lat"])
    lon = r1["lon"] + alpha * (r2["lon"] - r1["lon"])
    alt = r1["altitude"] + alpha * (r2["altitude"] - r1["altitude"])

    baro1 = r1.get("barometer")
    baro2 = r2.get("barometer")
    if baro1 is not None and baro2 is not None:
        baro = baro1 + alpha * (baro2 - baro1)
    else:
        baro = baro1 if baro1 is not None else baro2

    # Discrete metadata from nearest neighbor
    nearest_r = r1 if alpha < 0.5 else r2

    return {
        "gps": {
            "lat": round(lat, 7),
            "lon": round(lon, 7),
            "altitude": round(alt, 3),
            "barometer": round(baro, 2) if baro is not None else None,
            "timestamp_sec": round(target_time_sec, 4),
        },
        "lat": round(lat, 7),
        "lon": round(lon, 7),
        "altitude": round(alt, 3),
        "barometer": round(baro, 2) if baro is not None else None,
        "home": {"lat": nearest_r.get("home_lat"), "lon": nearest_r.get("home_lon")},
        "datetime": nearest_r.get("datetime"),
        "camera": nearest_r.get("camera", {}),
        "source_srt_sec": round(nearest_r["mid_sec"], 4)
    }


def extract_frames(
    video_path: str,
    output_images_dir: str,
    target_fps: float = 2.0,
    ext: str = "png",
    max_frames: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Extract frames from a video at target_fps (or evenly sampled up to max_frames) and save them into output_images_dir.

    Returns:
        List of dictionaries with frame metadata:
        [{'frame_idx': int, 'video_frame_idx': int, 'timestamp_sec': float, 'image_name': str, 'image_path': str}]
    """
    os.makedirs(output_images_dir, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise IOError(f"Failed to open video file: {video_path}")

    video_fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    if video_fps <= 0 or np.isnan(video_fps):
        video_fps = 30.0
    duration_sec = total_frames / video_fps if total_frames > 0 else 0.0

    print(f"  Video: {video_path}")
    print(f"  Resolution: {width}x{height} | Total Frames: {total_frames} | Video FPS: {video_fps:.3f} | Duration: {duration_sec:.2f}s")

    if max_frames and total_frames > 0:
        step = max(1.0, float(total_frames) / float(max_frames))
        target_indices = [int(round(i * step)) for i in range(max_frames)]
        target_indices = [min(idx, total_frames - 1) for idx in target_indices]
        print(f"  Target Frame Count: {len(target_indices)} frames (evenly sampled across video)")
    else:
        print(f"  Target Extraction FPS: {target_fps} (Step: every {video_fps / target_fps:.2f} video frames)")
        step = video_fps / target_fps
        target_indices = []
        idx = 0
        while True:
            target_idx = int(round(idx * step))
            if total_frames > 0 and target_idx >= total_frames:
                break
            target_indices.append(target_idx)
            idx += 1

    target_set = set(target_indices)
    extracted_frames: List[Dict[str, Any]] = []

    current_frame_idx = 0
    saved_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if current_frame_idx in target_set:
            filename = f"frame_{saved_count:04d}.{ext}"
            filepath = os.path.join(output_images_dir, filename)
            cv2.imwrite(filepath, frame)

            timestamp_sec = current_frame_idx / video_fps
            extracted_frames.append({
                "frame_idx": saved_count,
                "video_frame_idx": current_frame_idx,
                "timestamp_sec": timestamp_sec,
                "image_name": filename,
                "image_path": f"images/{filename}"
            })
            saved_count += 1
            if max_frames and saved_count >= max_frames:
                break

        current_frame_idx += 1

    cap.release()
    print(f"  Extracted {saved_count} frames into: {output_images_dir}")
    return extracted_frames


def ingest(
    video_path: str,
    srt_path: Optional[str],
    out_dir: str,
    fps: float = 2.0,
    ext: str = "png",
    max_frames: Optional[int] = None
) -> Dict[str, Any]:
    """
    Main ingestion pipeline:
    1. Extracts frames into <out_dir>/images/
    2. Parses SRT telemetry (if available)
    3. Generates synchronized <out_dir>/telemetry_index.json
    """
    out_path = Path(out_dir).resolve()
    images_dir = out_path / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("INGEST TELEMETRY — Drone Frame Extraction & SRT Sync")
    print("=" * 60)

    # 1. Extract frames
    frames_meta = extract_frames(
        video_path=video_path,
        output_images_dir=str(images_dir),
        target_fps=fps,
        ext=ext,
        max_frames=max_frames
    )

    # 2. Parse SRT telemetry if provided
    srt_records = []
    if srt_path and os.path.exists(srt_path):
        print(f"\n[+] Parsing DJI SRT telemetry from: {srt_path}")
        srt_records = parse_dji_srt(srt_path)
        print(f"  Parsed {len(srt_records)} valid SRT records")
    elif srt_path:
        print(f"\n[WARNING] Specified SRT file does not exist: {srt_path}")
    else:
        print("\n[NOTE] No SRT file specified. Telemetry index will contain timestamps only.")

    # 3. Synchronize frames with telemetry
    telemetry_index: Dict[str, Any] = {}
    for fm in frames_meta:
        img_name = fm["image_name"]
        frame_ts = fm["timestamp_sec"]

        entry: Dict[str, Any] = {
            "frame_idx": fm["frame_idx"],
            "video_frame_idx": fm["video_frame_idx"],
            "image_name": img_name,
            "image_path": fm["image_path"],
            "timestamp_sec": round(frame_ts, 4),
        }

        if srt_records:
            sync_data = interpolate_telemetry(srt_records, frame_ts)
            if sync_data:
                entry.update(sync_data)
        else:
            entry["gps"] = None

        telemetry_index[img_name] = entry

    # 4. Write telemetry_index.json
    index_path = out_path / "telemetry_index.json"
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(telemetry_index, f, indent=2)

    print(f"\n[OK] Ingestion complete:")
    print(f"  Frames saved:   {len(frames_meta)} frames -> {images_dir}")
    print(f"  Telemetry index: {index_path} ({len(telemetry_index)} entries)")

    return telemetry_index


def main():
    parser = argparse.ArgumentParser(
        description="Ingest drone video and DJI SRT telemetry for 3D reconstruction."
    )
    parser.add_argument("--video", type=str, required=True,
                        help="Path to input video file (MP4)")
    parser.add_argument("--srt", type=str, default=None,
                        help="Path to input DJI SRT telemetry file")
    parser.add_argument("--out", type=str, default=None,
                        help="Output scene directory")
    parser.add_argument("--out_dir", type=str, default=None,
                        help="Alias for --out")
    parser.add_argument("--fps", type=float, default=2.0,
                        help="Target frame extraction FPS (default: 2.0)")
    parser.add_argument("--ext", type=str, default="png", choices=["png", "jpg", "jpeg"],
                        help="Extracted frame image format (default: png)")
    parser.add_argument("--max_frames", "--frames", dest="max_frames", type=int, default=None,
                        help="Optional cap on maximum number of frames to extract (aliases: --max_frames, --frames)")

    args = parser.parse_args()

    # Support either --out or --out_dir
    out_dir = args.out or args.out_dir
    if not out_dir:
        out_dir = "outputs/smoke_ingest"

    if not os.path.exists(args.video):
        print(f"[FAIL] Input video does not exist: {args.video}")
        sys.exit(1)

    try:
        telemetry_index = ingest(
            video_path=args.video,
            srt_path=args.srt,
            out_dir=out_dir,
            fps=args.fps,
            ext=args.ext,
            max_frames=args.max_frames
        )
        if not telemetry_index:
            print("[FAIL] No frames extracted.")
            sys.exit(1)
        sys.exit(0)
    except Exception as e:
        print(f"[FAIL] Error during ingestion: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
