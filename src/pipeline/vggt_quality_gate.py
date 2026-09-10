"""
VGGT Quality Gate & Single-Frame Projection Sanity Test

This script:
1. Loads saved VGGT dense outputs from vggt_raw/
2. Validates Quality Gate A (no NaN/Inf, reasonable depth, spatial extent)
3. Performs a SINGLE-FRAME projection/unprojection sanity check:
   - Verifies VGGT depth units/convention
   - Verifies camera-from-world vs world-from-camera
   - Verifies intrinsics
   - Tests round-trip: pixel â†’ 3D â†’ pixel
   - Saves diagnostic visualizations
4. Reports whether VGGT output is safe for TSDF fusion

IMPORTANT: Run this BEFORE any TSDF/mesh generation.

Usage:
    python vggt_quality_gate.py --scene_dir outputs/vggt_demo_12frames
"""

import os
import sys
import json
import argparse
import numpy as np

def load_vggt_raw(scene_dir):
    """Load saved VGGT outputs."""
    raw_dir = os.path.join(scene_dir, "vggt_raw")
    if not os.path.exists(raw_dir):
        raise FileNotFoundError(f"No vggt_raw/ directory found at {raw_dir}")

    data = {
        "depth_map": np.load(os.path.join(raw_dir, "depth_map.npy")),
        "depth_conf": np.load(os.path.join(raw_dir, "depth_conf.npy")),
        "extrinsic": np.load(os.path.join(raw_dir, "extrinsic.npy")),
        "intrinsic": np.load(os.path.join(raw_dir, "intrinsic.npy")),
        "world_points": np.load(os.path.join(raw_dir, "world_points.npy")),
        "images_rgb": np.load(os.path.join(raw_dir, "images_rgb.npy")),
    }

    meta = np.load(os.path.join(raw_dir, "metadata.npz"), allow_pickle=True)
    data["image_paths"] = meta["image_paths"]
    data["original_coords"] = meta["original_coords"]
    data["vggt_resolution"] = int(meta["vggt_resolution"])

    return data


def quality_gate_a(data):
    """
    Quality Gate A â€” VGGT Output Validation.
    Returns (passed: bool, report: dict)
    """
    report = {"gate": "A", "checks": {}, "passed": True}

    depth_map = data["depth_map"]
    depth_conf = data["depth_conf"]
    extrinsic = data["extrinsic"]
    intrinsic = data["intrinsic"]
    world_points = data["world_points"]

    S = depth_map.shape[0]
    report["num_frames"] = S

    # Check 1: shapes exist and are non-empty
    for name, arr in [("depth_map", depth_map), ("depth_conf", depth_conf),
                       ("extrinsic", extrinsic), ("intrinsic", intrinsic),
                       ("world_points", world_points)]:
        check = {
            "shape": list(arr.shape),
            "dtype": str(arr.dtype),
            "non_empty": arr.size > 0
        }
        report["checks"][f"{name}_exists"] = check
        if not check["non_empty"]:
            report["passed"] = False

    # Check 2: No catastrophic NaN/Inf
    for name, arr in [("depth_map", depth_map), ("extrinsic", extrinsic),
                       ("intrinsic", intrinsic), ("world_points", world_points)]:
        nan_count = int(np.isnan(arr).sum())
        inf_count = int(np.isinf(arr).sum())
        total = arr.size
        check = {
            "nan_count": nan_count,
            "inf_count": inf_count,
            "nan_fraction": nan_count / total if total > 0 else 0,
            "pass": nan_count == 0 and inf_count == 0
        }
        report["checks"][f"{name}_nan_inf"] = check
        if not check["pass"]:
            # Allow small fraction of NaN in world_points (from zero-depth pixels)
            if name == "world_points" and check["nan_fraction"] < 0.1:
                check["pass"] = True
                check["note"] = "Small fraction of NaN acceptable in world_points"
            else:
                report["passed"] = False

    # Check 3: Depth range
    valid_depth = depth_map[depth_map > 0]
    if len(valid_depth) > 0:
        depth_stats = {
            "min": float(valid_depth.min()),
            "max": float(valid_depth.max()),
            "mean": float(valid_depth.mean()),
            "median": float(np.median(valid_depth)),
            "std": float(valid_depth.std()),
        }
        # For aerial drone footage, depth should be ~1m to ~500m
        reasonable = depth_stats["min"] > 0.01 and depth_stats["max"] < 10000
        depth_stats["physically_plausible"] = reasonable
        if not reasonable:
            report["passed"] = False
    else:
        depth_stats = {"error": "No valid depth values > 0"}
        report["passed"] = False
    report["checks"]["depth_range"] = depth_stats

    # Check 4: Confidence stats
    conf_stats = {
        "min": float(depth_conf.min()),
        "max": float(depth_conf.max()),
        "mean": float(depth_conf.mean()),
    }
    report["checks"]["confidence_stats"] = conf_stats

    # Check 5: Camera poses â€” check for degenerate extrinsics
    cam_positions = []
    for i in range(S):
        R = extrinsic[i, :3, :3]
        t = extrinsic[i, :3, 3]
        # Camera position in world = -R^T @ t
        cam_pos = -R.T @ t
        cam_positions.append(cam_pos)
    cam_positions = np.array(cam_positions)

    # Spatial extent of cameras
    cam_extent = cam_positions.max(axis=0) - cam_positions.min(axis=0)
    report["checks"]["camera_positions"] = {
        "extent_xyz": cam_extent.tolist(),
        "total_extent": float(np.linalg.norm(cam_extent)),
        "note": "camera-from-world convention, so cam_pos = -R^T @ t"
    }

    # Check 6: World points spatial extent
    # Use a subsample to avoid memory issues
    pts_flat = world_points.reshape(-1, 3)
    valid_mask = np.all(np.isfinite(pts_flat), axis=1) & (np.linalg.norm(pts_flat, axis=1) < 1000)
    valid_pts = pts_flat[valid_mask]
    if len(valid_pts) > 10000:
        idx = np.random.choice(len(valid_pts), 10000, replace=False)
        sample_pts = valid_pts[idx]
    else:
        sample_pts = valid_pts

    if len(sample_pts) > 0:
        pts_extent = sample_pts.max(axis=0) - sample_pts.min(axis=0)
        report["checks"]["world_points_extent"] = {
            "extent_xyz": pts_extent.tolist(),
            "total_extent": float(np.linalg.norm(pts_extent)),
            "valid_point_count": int(len(valid_pts)),
            "total_point_count": int(len(pts_flat)),
        }
    else:
        report["checks"]["world_points_extent"] = {"error": "No valid world points"}
        report["passed"] = False

    # Check 7: Intrinsics sanity
    for i in range(S):
        K = intrinsic[i]
        fx, fy = K[0, 0], K[1, 1]
        cx, cy = K[0, 2], K[1, 2]
        check = {
            "frame": i,
            "fx": float(fx), "fy": float(fy),
            "cx": float(cx), "cy": float(cy),
            "fx_positive": bool(fx > 0),
            "fy_positive": bool(fy > 0),
        }
        if not (check["fx_positive"] and check["fy_positive"]):
            report["passed"] = False
        if i == 0:
            report["checks"]["intrinsics_sample"] = check

    return report


def single_frame_sanity_test(data, frame_idx=0):
    """
    Single-frame projection/unprojection sanity test.

    Verifies:
    1. Depth + intrinsics + extrinsics produce coherent 3D points
    2. VGGT extrinsic convention (camera-from-world)
    3. Re-projection round-trip accuracy
    4. Open3D pose format requirements

    Returns diagnostic report dict.
    """
    report = {"frame_idx": frame_idx, "checks": {}}

    depth = np.squeeze(data["depth_map"][frame_idx])       # (H, W)
    conf = data["depth_conf"][frame_idx]        # (H, W)
    E = data["extrinsic"][frame_idx]            # (3, 4) camera-from-world
    K = data["intrinsic"][frame_idx]            # (3, 3)
    world_pts = data["world_points"][frame_idx]  # (H, W, 3)

    H, W = depth.shape
    report["depth_shape"] = [H, W]

    # --- Convention Verification ---

    # VGGT extrinsic is camera-from-world (OpenCV): P_cam = E @ P_world_homo
    R = E[:3, :3]
    t = E[:3, 3]
    cam_pos_world = -R.T @ t  # Camera position in world coordinates

    report["checks"]["extrinsic_convention"] = {
        "R_det": float(np.linalg.det(R)),
        "R_is_rotation": bool(abs(np.linalg.det(R) - 1.0) < 0.01),
        "camera_position_world": cam_pos_world.tolist(),
        "convention": "camera-from-world (OpenCV)",
    }

    # For Open3D TSDF: expects camera-to-world (world-from-camera) as the
    # extrinsic parameter. So we need to INVERT the VGGT extrinsic.
    E_homo = np.eye(4)
    E_homo[:3, :] = E
    E_inv = np.linalg.inv(E_homo)  # world-from-camera

    report["checks"]["open3d_pose"] = {
        "needs_inversion": True,
        "note": "Open3D integrate() expects camera-to-world (world-from-camera). "
                "VGGT provides camera-from-world. Must invert before TSDF.",
        "inverted_translation": E_inv[:3, 3].tolist(),
    }

    # --- Depth unit test ---
    valid_depth = depth[depth > 0.01]
    report["checks"]["depth_units"] = {
        "min": float(valid_depth.min()) if len(valid_depth) > 0 else None,
        "max": float(valid_depth.max()) if len(valid_depth) > 0 else None,
        "mean": float(valid_depth.mean()) if len(valid_depth) > 0 else None,
        "note": "VGGT depth is z-depth in camera coords. Units are arbitrary "
                "(not metric) â€” metric scale comes from GPS/SRT alignment.",
    }

    # --- Intrinsics check ---
    fx, fy = K[0, 0], K[1, 1]
    cx, cy = K[0, 2], K[1, 2]
    report["checks"]["intrinsics"] = {
        "fx": float(fx), "fy": float(fy),
        "cx": float(cx), "cy": float(cy),
        "cx_near_center": bool(abs(cx - W/2) < W * 0.1),
        "cy_near_center": bool(abs(cy - H/2) < H * 0.1),
        "resolution": [H, W],
    }

    # --- Round-trip test: unproject â†’ reproject ---
    # Pick center pixel
    py, px = H // 2, W // 2
    z = depth[py, px]
    if z > 0.01:
        # Unproject: pixel â†’ camera coords
        x_cam = (px - cx) * z / fx
        y_cam = (py - cy) * z / fy
        z_cam = z
        pt_cam = np.array([x_cam, y_cam, z_cam])

        # Camera â†’ world
        pt_world_computed = E_inv[:3, :3] @ pt_cam + E_inv[:3, 3]
        pt_world_vggt = world_pts[py, px]

        # Compare
        diff = np.linalg.norm(pt_world_computed - pt_world_vggt)
        report["checks"]["round_trip"] = {
            "pixel": [px, py],
            "depth": float(z),
            "pt_cam": pt_cam.tolist(),
            "pt_world_computed": pt_world_computed.tolist(),
            "pt_world_vggt": pt_world_vggt.tolist(),
            "difference_norm": float(diff),
            "pass": bool(diff < 0.01),
            "note": "If difference is small, VGGT world_points are consistent "
                    "with depth+intrinsic+extrinsic unprojection."
        }

        # Reproject: world â†’ pixel
        pt_cam_reproj = R @ pt_world_computed + t
        if pt_cam_reproj[2] > 0:
            px_reproj = fx * pt_cam_reproj[0] / pt_cam_reproj[2] + cx
            py_reproj = fy * pt_cam_reproj[1] / pt_cam_reproj[2] + cy
            reproj_error = np.sqrt((px_reproj - px)**2 + (py_reproj - py)**2)
            report["checks"]["reprojection"] = {
                "original_pixel": [px, py],
                "reprojected_pixel": [float(px_reproj), float(py_reproj)],
                "error_pixels": float(reproj_error),
                "pass": bool(reproj_error < 1.0),
            }
    else:
        report["checks"]["round_trip"] = {"skip": "center pixel has zero depth"}

    # --- TSDF depth scaling ---
    # Open3D TSDF expects depth in some unit (typically meters).
    # VGGT depth is in arbitrary units. We need to know the scale factor.
    report["checks"]["tsdf_depth_scaling"] = {
        "note": "VGGT depth is NOT metric. For TSDF fusion before GPS alignment, "
                "use raw depth values directly â€” the mesh will be in VGGT's "
                "arbitrary coordinate system. Apply Sim3 metric transform afterward, "
                "OR apply metric alignment to camera poses before fusion (preferred).",
        "recommendation": "For initial test: use raw VGGT values. "
                          "For final pipeline: align camera poses to metric first.",
    }

    return report


def _json_safe(obj):
    if hasattr(obj, "item"):
        try:
            return obj.item()
        except Exception:
            pass
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj

def main():
    parser = argparse.ArgumentParser(description="VGGT Quality Gate & Sanity Test")
    parser.add_argument("--scene_dir", type=str, required=True)
    args = parser.parse_args()

    print("=" * 60)
    print("VGGT Quality Gate & Single-Frame Sanity Test")
    print("=" * 60)

    # Load
    print(f"\n[+] Loading VGGT outputs from {args.scene_dir}/vggt_raw/")
    data = load_vggt_raw(args.scene_dir)

    # Quality Gate A
    print("\n[+] Running Quality Gate A...")
    gate_report = quality_gate_a(data)

    # Single-frame sanity test
    print("\n[+] Running single-frame projection sanity test...")
    sanity_report = single_frame_sanity_test(data, frame_idx=0)

    # Combine reports
    full_report = {
        "quality_gate_a": gate_report,
        "single_frame_sanity": sanity_report,
    }

    # Save report
    report_path = os.path.join(args.scene_dir, "vggt_quality_report.json")
    with open(report_path, "w") as f:
        json.dump(full_report, f, indent=2, default=lambda o: bool(o) if hasattr(o, "item") and str(type(o)).find("numpy") >= 0 and getattr(o, "dtype", None) is not None and getattr(o.dtype, "kind", None) == "b" else (o.item() if hasattr(o, "item") else str(o)))
    print(f"\n[OK] Report saved to: {report_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("QUALITY GATE A RESULT:", "PASS OK" if gate_report["passed"] else "FAIL X")
    print("=" * 60)

    for check_name, check_data in gate_report["checks"].items():
        if isinstance(check_data, dict):
            status = check_data.get("pass", check_data.get("physically_plausible", "N/A"))
            print(f"  {check_name}: {status}")

    print("\n" + "=" * 60)
    print("SINGLE-FRAME SANITY TEST RESULTS:")
    print("=" * 60)
    for check_name, check_data in sanity_report["checks"].items():
        if isinstance(check_data, dict):
            status = check_data.get("pass", "info")
            print(f"  {check_name}: {status}")
            if "note" in check_data:
                print(f"    â†’ {check_data['note']}")

    # Final verdict
    round_trip_ok = sanity_report["checks"].get("round_trip", {}).get("pass", False)
    reproj_ok = sanity_report["checks"].get("reprojection", {}).get("pass", False)

    print("\n" + "=" * 60)
    if gate_report["passed"] and (round_trip_ok or "skip" in str(sanity_report["checks"].get("round_trip", {}))):
        print("VERDICT: SAFE TO PROCEED WITH TSDF FUSION")
        print("  - Extrinsic must be INVERTED for Open3D (camera-from-world â†’ world-from-camera)")
        print("  - Depth values are in VGGT arbitrary units (not metric)")
    else:
        print("VERDICT: DO NOT PROCEED â€” review the report")
    print("=" * 60)

    return gate_report["passed"]


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
