import os
import cv2
import json
import re

def parse_srt_time(time_str):
    """Parses SRT time format 00:00:00,030 into seconds"""
    h, m, s_ms = time_str.split(':')
    s, ms = s_ms.split(',')
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0

def parse_srt_file(srt_path):
    """
    Parses drone SRT file and returns a list of dictionaries with telemetry data.
    Each dict contains: 'start_time', 'end_time', 'lon', 'lat', 'alt'
    """
    telemetry_data = []
    with open(srt_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    blocks = content.strip().split('\n\n')
    for block in blocks:
        lines = block.split('\n')
        if len(lines) < 3:
            continue
            
        time_line = lines[1]
        try:
            start_str, end_str = time_line.split(' --> ')
            start_time = parse_srt_time(start_str)
            end_time = parse_srt_time(end_str)
        except Exception:
            continue
            
        # Find GPS line
        gps_match = None
        for line in lines[2:]:
            match = re.search(r'GPS\(([^)]+)\)', line)
            if match:
                gps_match = match.group(1)
                break
                
        if gps_match:
            parts = gps_match.split(',')
            if len(parts) >= 3:
                try:
                    lon, lat, alt = float(parts[0]), float(parts[1]), float(parts[2])
                    telemetry_data.append({
                        'start_time': start_time,
                        'end_time': end_time,
                        'lon': lon,
                        'lat': lat,
                        'alt': alt
                    })
                except ValueError:
                    pass
    return telemetry_data

def get_telemetry_for_time(timestamp, telemetry_data):
    """Finds the closest telemetry record for a given video timestamp"""
    if not telemetry_data:
        return None
        
    # Find record where timestamp falls between start and end
    for record in telemetry_data:
        if record['start_time'] <= timestamp <= record['end_time']:
            return record
            
    # Fallback to closest start_time
    closest = min(telemetry_data, key=lambda x: abs(x['start_time'] - timestamp))
    return closest

def extract_frames(video_path, srt_path, output_dir, num_frames=8):
    """
    Extracts num_frames evenly from the video, matches with SRT,
    and saves to output_dir/images with a telemetry_index.json.
    """
    os.makedirs(output_dir, exist_ok=True)
    images_dir = os.path.join(output_dir, 'images')
    os.makedirs(images_dir, exist_ok=True)
    
    telemetry_data = parse_srt_file(srt_path) if srt_path and os.path.exists(srt_path) else None
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Failed to open video: {video_path}")
        
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    if total_frames <= 0 or fps <= 0:
        raise ValueError(f"Invalid video metadata: frames={total_frames}, fps={fps}")
        
    # Calculate evenly spaced frame indices
    step = max(1, total_frames // num_frames)
    frame_indices = [min(i * step, total_frames - 1) for i in range(num_frames)]
    
    telemetry_index = {}
    
    for i, frame_idx in enumerate(frame_indices):
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            print(f"Warning: Failed to read frame {frame_idx}")
            continue
            
        timestamp = frame_idx / fps
        filename = f"frame_{i:04d}.jpg"
        filepath = os.path.join(images_dir, filename)
        
        cv2.imwrite(filepath, frame)
        
        record = None
        if telemetry_data:
            record = get_telemetry_for_time(timestamp, telemetry_data)
            
        telemetry_index[filename] = {
            'video_timestamp': timestamp,
            'frame_index': frame_idx,
            'gps': {
                'lon': record['lon'],
                'lat': record['lat'],
                'alt': record['alt']
            } if record else None
        }
        
    cap.release()
    
    index_path = os.path.join(output_dir, 'telemetry_index.json')
    with open(index_path, 'w') as f:
        json.dump(telemetry_index, f, indent=4)
        
    return images_dir, index_path

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--video', required=True)
    parser.add_argument('--srt', required=False)
    parser.add_argument('--out', required=True)
    parser.add_argument('--frames', type=int, default=8)
    args = parser.parse_args()
    
    extract_frames(args.video, args.srt, args.out, args.frames)
    print(f"Extracted {args.frames} frames to {args.out}")
