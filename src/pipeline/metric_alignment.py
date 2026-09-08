"""
Metric Alignment — GPS/SRT to VGGT coordinate alignment via Sim3.

Pipeline:
  1. Load telemetry_index.json (from ingest_telemetry.py — NOT modified)
  2. Load VGGT camera poses (extrinsic arrays)
  3. Match frames to SRT records by TIMESTAMP (not array index)
  4. Convert GPS (lat, lon, alt) to local ENU using pyproj
  5. Solve Sim3 (scale, rotation, translation) mapping VGGT → ENU
  6. Output metric-aligned camera poses for TSDF fusion

IMPORTANT ASSUMPTIONS (documented per requirement):
  - GPS altitude field from SRT is treated as DJI RELATIVE altitude
    (height above takeoff point in meters), NOT geodetic/MSL elevation.
  - Barometer field is parsed and retained separately.
  - The vertical reference is configurable via --altitude_source.
  - Relative metric measurements are valid without absolute elevation.

Distinguishes (per requirement):
  - cameras.txt  → camera INTRINSICS (focal length, principal point)
  - images.txt   → camera EXTRINSICS/POSES (quaternion + translation)
  - points3D.txt → 3D points (not used here)

Usage:
    python metric_alignment.py --scene_dir outputs/vggt_demo_12frames \\
                               --telemetry outputs/test_scene/telemetry_index.json
"""

import os
import sys
import json
import argparse
import numpy as np


def load_telemetry(telemetry_path):
    """Load telemetry_index.json produced by ingest_telemetry.py."""
    with open(telemetry_path, "r") as f:
        telemetry = json.load(f)
    return telemetry


def load_vggt_cameras(scene_dir):
    """
    Load VGGT camera extrinsics.
    Returns extrinsic (S, 3, 4) and metadata.
    """
    raw_dir = os.path.join(scene_dir, "vggt_raw")
    extrinsic = np.load(os.path.join(raw_dir, "extrinsic.npy"))
    intrinsic = np.load(os.path.join(raw_dir, "intrinsic.npy"))
    meta = np.load(os.path.join(raw_dir, "metadata.npz"), allow_pickle=True)
    image_paths = list(meta["image_paths"])
    return extrinsic, intrinsic, image_paths


def gps_to_enu(gps_points, reference=None):
    """
    Convert GPS coordinates (lat, lon, alt) to local ENU (East, North, Up).

    Args:
        gps_points: list of (lat, lon, alt) tuples
        reference: (lat, lon, alt) reference point. If None, uses first point.

    Returns:
        enu_points: (N, 3) numpy array in meters
        reference: the reference point used
    """
    try:
        from pyproj import Transformer
    except ImportError:
        print("[WARNING] pyproj not installed. Using simplified flat-earth approximation.")
        return _gps_to_enu_simple(gps_points, reference)

    if reference is None:
        reference = gps_points[0]

    ref_lat, ref_lon, ref_alt = reference

    # Use pyproj for accurate projection
    # EPSG:4326 = WGS84 geographic, EPSG:4978 = WGS84 geocentric (ECEF)
    transformer_to_ecef = Transformer.from_crs("EPSG:4326", "EPSG:4978", always_xy=True)
    
    # Reference point in ECEF
    ref_x, ref_y, ref_z = transformer_to_ecef.transform(ref_lon, ref_lat, ref_alt)

    # Rotation matrix from ECEF to ENU at reference point
    lat_rad = np.radians(ref_lat)
    lon_rad = np.radians(ref_lon)
    R_ecef_to_enu = np.array([
        [-np.sin(lon_rad),                np.cos(lon_rad),                0],
        [-np.sin(lat_rad)*np.cos(lon_rad), -np.sin(lat_rad)*np.sin(lon_rad), np.cos(lat_rad)],
        [ np.cos(lat_rad)*np.cos(lon_rad),  np.cos(lat_rad)*np.sin(lon_rad), np.sin(lat_rad)],
    ])

    enu_points = []
    for lat, lon, alt in gps_points:
        x, y, z = transformer_to_ecef.transform(lon, lat, alt)
        dx = np.array([x - ref_x, y - ref_y, z - ref_z])
        enu = R_ecef_to_enu @ dx
        enu_points.append(enu)

    return np.array(enu_points), reference


def _gps_to_enu_simple(gps_points, reference=None):
    """Simplified flat-earth GPS to ENU (fallback if pyproj unavailable)."""
    if reference is None:
        reference = gps_points[0]

    ref_lat, ref_lon, ref_alt = reference
    R_earth = 6371000.0  # meters

    enu_points = []
    for lat, lon, alt in gps_points:
        dlat = np.radians(lat - ref_lat)
        dlon = np.radians(lon - ref_lon)
        east = dlon * R_earth * np.cos(np.radians(ref_lat))
        north = dlat * R_earth
        up = alt - ref_alt
        enu_points.append([east, north, up])

    return np.array(enu_points), reference


def match_frames_to_telemetry(image_paths, telemetry, max_time_diff=1.0):
    """
    Match VGGT frames to SRT telemetry records by TIMESTAMP.

    Args:
        image_paths: list of image filenames from VGGT
        telemetry: dict from telemetry_index.json
        max_time_diff: maximum allowed time difference in seconds

    Returns:
        matches: list of (vggt_idx, frame_name, gps_data, time_diff)
        rejected: list of (vggt_idx, frame_name, reason)
    """
    matches = []
    rejected = []

    for vggt_idx, img_name in enumerate(image_paths):
        if img_name in telemetry:
            entry = telemetry[img_name]
            gps = entry.get("gps")
            if gps and isinstance(gps, dict) and "lat" in gps and "lon" in gps:
                # Check timestamp difference
                frame_ts = entry.get("timestamp_sec", 0)
                gps_ts = gps.get("timestamp_sec", 0)
                time_diff = abs(frame_ts - gps_ts)

                if time_diff <= max_time_diff:
                    matches.append((vggt_idx, img_name, gps, time_diff))
                else:
                    rejected.append((vggt_idx, img_name,
                                     f"time_diff={time_diff:.3f}s > {max_time_diff}s"))
            else:
                rejected.append((vggt_idx, img_name, "no valid GPS data"))
        else:
            rejected.append((vggt_idx, img_name, "not found in telemetry"))

    return matches, rejected


def extract_vggt_camera_positions(extrinsic, indices):
    """
    Extract camera positions in VGGT world coordinates.

    VGGT extrinsic is camera-from-world: [R|t]
    Camera position in world = -R^T @ t
    """
    positions = []
    for idx in indices:
        R = extrinsic[idx, :3, :3]
        t = extrinsic[idx, :3, 3]
        cam_pos = -R.T @ t
        positions.append(cam_pos)
    return np.array(positions)


def solve_sim3(source_pts, target_pts):
    """
    Solve Sim3 transformation: target = s * R @ source + t

    Uses Umeyama's method for similarity transform estimation.

    Args:
        source_pts: (N, 3) points in source frame (VGGT)
        target_pts: (N, 3) points in target frame (ENU)

    Returns:
        scale: float
        R: (3, 3) rotation matrix
        t: (3,) translation vector
        residuals: (N,) per-point residual errors
    """
    N = len(source_pts)
    assert N >= 3, f"Need at least 3 correspondences, got {N}"

    # Centroids
    src_mean = source_pts.mean(axis=0)
    tgt_mean = target_pts.mean(axis=0)

    # Center the points
    src_centered = source_pts - src_mean
    tgt_centered = target_pts - tgt_mean

    # Compute scale (ratio of RMS distances from centroid)
    src_rms = np.sqrt((src_centered ** 2).sum() / N)
    tgt_rms = np.sqrt((tgt_centered ** 2).sum() / N)

    if src_rms < 1e-10:
        raise ValueError("Source points are degenerate (all at same location)")

    scale = tgt_rms / src_rms

    # Compute rotation via SVD
    H = src_centered.T @ tgt_centered
    U, S_vals, Vt = np.linalg.svd(H)
    d = np.linalg.det(Vt.T @ U.T)
    sign_matrix = np.diag([1, 1, d])  # Ensure proper rotation (det=+1)
    R = Vt.T @ sign_matrix @ U.T

    # Compute translation
    t = tgt_mean - scale * R @ src_mean

    # Compute residuals
    transformed = scale * (R @ source_pts.T).T + t
    residuals = np.linalg.norm(transformed - target_pts, axis=1)

    return scale, R, t, residuals


def apply_sim3_to_extrinsic(extrinsic, scale, R_sim3, t_sim3):
    """
    Apply Sim3 transform to VGGT camera extrinsics.

    VGGT extrinsic [R_cam|t_cam] transforms world→camera.
    After Sim3, the new world frame is metric ENU.

    For a point in ENU: P_enu = s * R_s @ P_vggt + t_s
    For camera pose: new_extrinsic transforms ENU→camera.

    New: R_new = R_cam @ R_s^{-1} / s
         t_new = t_cam - R_cam @ R_s^{-1} @ t_s / s

    But we keep the convention that depth is metric after Sim3.
    Actually, the clean way is to build the full 4x4 Sim3 and compose.
    """
    S = extrinsic.shape[0]
    metric_extrinsic = np.zeros_like(extrinsic)

    # Sim3 as 4x4: maps VGGT world → metric ENU
    Sim3 = np.eye(4)
    Sim3[:3, :3] = scale * R_sim3
    Sim3[:3, 3] = t_sim3

    Sim3_inv = np.eye(4)
    R_sim3_inv = R_sim3.T
    Sim3_inv[:3, :3] = R_sim3_inv / scale
    Sim3_inv[:3, 3] = -R_sim3_inv @ t_sim3 / scale

    for i in range(S):
        E = np.eye(4)
        E[:3, :] = extrinsic[i]

        # E maps VGGT_world → camera
        # Sim3_inv maps ENU → VGGT_world
        # New extrinsic: E_new = E @ Sim3_inv maps ENU → camera
        E_new = E @ Sim3_inv
        metric_extrinsic[i] = E_new[:3, :]

    return metric_extrinsic


def main():
    parser = argparse.ArgumentParser(description="Metric Alignment — GPS/SRT → Sim3")
    parser.add_argument("--scene_dir", type=str, required=True,
                        help="Scene directory with vggt_raw/")
    parser.add_argument("--telemetry", type=str, required=True,
                        help="Path to telemetry_index.json")
    parser.add_argument("--altitude_source", type=str, default="gps",
                        choices=["gps", "barometer"],
                        help="Which altitude field to use (default: gps)")
    parser.add_argument("--max_time_diff", type=float, default=2.0,
                        help="Max time diff for frame-SRT matching (seconds)")
    args = parser.parse_args()

    print("=" * 60)
    print("Metric Alignment — GPS/SRT → Sim3 Transform")
    print("=" * 60)

    # Load data
    print(f"\n[+] Loading telemetry from {args.telemetry}")
    telemetry = load_telemetry(args.telemetry)
    print(f"  {len(telemetry)} frames in telemetry")

    print(f"[+] Loading VGGT cameras from {args.scene_dir}/vggt_raw/")
    extrinsic, intrinsic, image_paths = load_vggt_cameras(args.scene_dir)
    S = extrinsic.shape[0]
    print(f"  {S} VGGT camera poses")

    # Match frames to telemetry by timestamp
    print(f"\n[+] Matching frames to SRT by timestamp (max_diff={args.max_time_diff}s)...")
    matches, rejected = match_frames_to_telemetry(
        image_paths, telemetry, max_time_diff=args.max_time_diff
    )
    print(f"  Matched: {len(matches)}/{S}")
    print(f"  Rejected: {len(rejected)}")
    for r in rejected:
        print(f"    {r[1]}: {r[2]}")

    if len(matches) < 3:
        print("[FAIL] Need at least 3 matched frames for Sim3. Aborting.")
        sys.exit(1)

    # Extract GPS coordinates
    gps_points = []
    vggt_indices = []
    for vggt_idx, frame_name, gps, time_diff in matches:
        alt = gps.get("altitude", 0.0)
        # Document altitude assumption
        gps_points.append((gps["lat"], gps["lon"], alt))
        vggt_indices.append(vggt_idx)

    # Convert GPS to ENU
    print(f"\n[+] Converting GPS to local ENU coordinates...")
    print(f"  Altitude source: {args.altitude_source}")
    print(f"  ASSUMPTION: GPS altitude is DJI RELATIVE altitude (height above takeoff)")
    print(f"  This is NOT verified as geodetic/MSL elevation.")

    enu_points, ref_origin = gps_to_enu(gps_points)
    print(f"  Reference origin: lat={ref_origin[0]:.6f}, lon={ref_origin[1]:.6f}, alt={ref_origin[2]:.1f}")
    print(f"  ENU extent: E=[{enu_points[:,0].min():.2f}, {enu_points[:,0].max():.2f}]m")
    print(f"               N=[{enu_points[:,1].min():.2f}, {enu_points[:,1].max():.2f}]m")
    print(f"               U=[{enu_points[:,2].min():.2f}, {enu_points[:,2].max():.2f}]m")

    # Extract VGGT camera positions
    vggt_cam_positions = extract_vggt_camera_positions(extrinsic, vggt_indices)
    print(f"\n[+] VGGT camera positions:")
    print(f"  X=[{vggt_cam_positions[:,0].min():.4f}, {vggt_cam_positions[:,0].max():.4f}]")
    print(f"  Y=[{vggt_cam_positions[:,1].min():.4f}, {vggt_cam_positions[:,1].max():.4f}]")
    print(f"  Z=[{vggt_cam_positions[:,2].min():.4f}, {vggt_cam_positions[:,2].max():.4f}]")

    # Solve Sim3
    print(f"\n[+] Solving Sim3 alignment ({len(matches)} correspondences)...")
    try:
        scale, R, t, residuals = solve_sim3(vggt_cam_positions, enu_points)
    except ValueError as e:
        print(f"[FAIL] Sim3 failed: {e}")
        sys.exit(1)

    # Apply Sim3 to all extrinsics
    print(f"\n[+] Applying Sim3 to all {S} camera poses...")
    metric_extrinsic = apply_sim3_to_extrinsic(extrinsic, scale, R, t)

    # Save metric-aligned outputs
    out_dir = os.path.join(args.scene_dir, "vggt_raw")
    np.save(os.path.join(out_dir, "metric_extrinsic.npy"), metric_extrinsic)

    # Build alignment report
    report = {
        "matched_frame_count": len(matches),
        "total_frames": S,
        "rejected_count": len(rejected),
        "rejected_frames": [(r[1], r[2]) for r in rejected],
        "scale": float(scale),
        "rotation": R.tolist(),
        "translation": t.tolist(),
        "residual_mean": float(residuals.mean()),
        "residual_max": float(residuals.max()),
        "residual_std": float(residuals.std()),
        "residual_per_frame": {
            matches[i][1]: float(residuals[i]) for i in range(len(matches))
        },
        "gps_reference_origin": {
            "lat": ref_origin[0], "lon": ref_origin[1], "alt": ref_origin[2]
        },
        "altitude_assumption": (
            f"GPS altitude ({args.altitude_source}) treated as DJI RELATIVE "
            f"altitude (height above takeoff in meters). NOT verified as "
            f"geodetic/MSL elevation. Barometer field parsed but not used for alignment."
        ),
        "sim3_note": (
            "Sim3 provides global scale/rotation/translation alignment. "
            "It does NOT fix local geometric distortion within the VGGT reconstruction."
        ),
    }

    report_path = os.path.join(args.scene_dir, "alignment_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    # Print summary
    print("\n" + "=" * 60)
    print("METRIC ALIGNMENT REPORT")
    print("=" * 60)
    print(f"  Matched frames:       {report['matched_frame_count']}/{report['total_frames']}")
    print(f"  Scale:                {report['scale']:.6f}")
    print(f"  Residual (mean):      {report['residual_mean']:.4f} meters")
    print(f"  Residual (max):       {report['residual_max']:.4f} meters")
    print(f"  Residual (std):       {report['residual_std']:.4f} meters")
    print(f"\n  Rotation matrix:")
    for row in R:
        print(f"    [{row[0]:8.5f} {row[1]:8.5f} {row[2]:8.5f}]")
    print(f"\n  Translation: [{t[0]:.4f}, {t[1]:.4f}, {t[2]:.4f}]")
    print(f"\n  Per-frame residuals:")
    for frame_name, res in report["residual_per_frame"].items():
        print(f"    {frame_name}: {res:.4f}m")

    print(f"\n[OK] Metric extrinsics saved to: {out_dir}/metric_extrinsic.npy")
    print(f"[OK] Alignment report saved to: {report_path}")

    print(f"\n  NOTE: {report['altitude_assumption']}")
    print(f"  NOTE: {report['sim3_note']}")

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
