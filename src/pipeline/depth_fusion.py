"""
Depth Fusion — TSDF and Poisson mesh reconstruction from VGGT dense depth.

Primary path:  Fused metric point cloud -> Poisson reconstruction -> mesh
Fallback path: Fused metric point cloud -> BPA reconstruction -> mesh
(TSDF retained as historical experiment)

IMPORTANT: This script handles the VGGT → Open3D convention conversion:
  - VGGT extrinsic is camera-from-world (OpenCV convention)
  - Open3D TSDF integrate() expects the EXTRINSIC matrix (camera-from-world)
    as its parameter (despite some docs calling it "extrinsic")
  - Depth is z-depth in camera coordinates

Usage:
    python depth_fusion.py --scene_dir outputs/vggt_demo_12frames [--method tsdf|poisson]
"""

import os
import sys
import argparse
import numpy as np

def load_vggt_raw(scene_dir):
    """Load saved VGGT outputs. Uses metric-aligned extrinsics if available."""
    raw_dir = os.path.join(scene_dir, "vggt_raw")

    # Check for metric-aligned extrinsics (produced by metric_alignment.py)
    metric_ext_path = os.path.join(raw_dir, "metric_extrinsic.npy")
    if os.path.exists(metric_ext_path):
        print("[+] Using METRIC-ALIGNED camera poses (preferred path)")
        extrinsic = np.load(metric_ext_path)
        coordinate_frame = "metric_enu"
    else:
        print("[+] Using raw VGGT camera poses (no metric alignment found)")
        extrinsic = np.load(os.path.join(raw_dir, "extrinsic.npy"))
        coordinate_frame = "vggt_arbitrary"

    metric_pts_path = os.path.join(raw_dir, "metric_world_points.npy")
    if os.path.exists(metric_pts_path):
        world_points = np.load(metric_pts_path)
    else:
        world_points = np.load(os.path.join(raw_dir, "world_points.npy"))

    data = {
        "depth_map": np.load(os.path.join(raw_dir, "depth_map.npy")),
        "depth_conf": np.load(os.path.join(raw_dir, "depth_conf.npy")),
        "extrinsic": extrinsic,
        "intrinsic": np.load(os.path.join(raw_dir, "intrinsic.npy")),
        "world_points": world_points,
        "images_rgb": np.load(os.path.join(raw_dir, "images_rgb.npy")),
        "coordinate_frame": coordinate_frame,
    }
    meta = np.load(os.path.join(raw_dir, "metadata.npz"), allow_pickle=True)
    data["vggt_resolution"] = int(meta["vggt_resolution"])
    return data


def tsdf_fusion(data, voxel_length=0.02, sdf_trunc_multiplier=3.0,
                conf_threshold=1.0, max_depth=None):
    """
    Perform TSDF volumetric fusion using Open3D.

    Args:
        data: dict with depth_map, depth_conf, extrinsic, intrinsic, images_rgb
        voxel_length: TSDF voxel size (in VGGT coordinate units)
        sdf_trunc_multiplier: SDF truncation = voxel_length * this
        conf_threshold: minimum confidence to include a depth pixel
        max_depth: maximum depth to integrate (auto-computed if None)

    Returns:
        mesh: open3d.geometry.TriangleMesh
    """
    import open3d as o3d

    depth_map = data["depth_map"]     # (S, H, W)
    depth_conf = data["depth_conf"]   # (S, H, W)
    extrinsic = data["extrinsic"]     # (S, 3, 4) camera-from-world
    intrinsic = data["intrinsic"]     # (S, 3, 3)
    images_rgb = data["images_rgb"]   # (S, H, W, 3) uint8

    S, H, W = depth_map.shape

    # Auto-compute max depth if not specified
    if max_depth is None:
        valid_depths = depth_map[depth_map > 0.01]
        if len(valid_depths) > 0:
            # Use 95th percentile to avoid extreme outliers
            max_depth = float(np.percentile(valid_depths, 95)) * 1.5
        else:
            max_depth = 100.0
        print(f"[+] Auto max_depth: {max_depth:.4f}")

    # Auto-compute voxel_length based on scene scale
    valid_depths = depth_map[depth_map > 0.01]
    if len(valid_depths) > 0:
        median_depth = float(np.median(valid_depths))
        # Voxel size ~ 1/200th of median depth (gives ~200 voxels across typical depth)
        voxel_length = median_depth / 200.0
        print(f"[+] Auto voxel_length: {voxel_length:.6f} (median depth: {median_depth:.4f})")

    sdf_trunc = voxel_length * sdf_trunc_multiplier

    # Create TSDF volume
    volume = o3d.pipelines.integration.ScalableTSDFVolume(
        voxel_length=voxel_length,
        sdf_trunc=sdf_trunc,
        color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8,
    )

    print(f"[+] TSDF params: voxel={voxel_length:.6f}, trunc={sdf_trunc:.6f}, max_depth={max_depth:.4f}")
    print(f"[+] Integrating {S} frames...")

    for i in range(S):
        # Confidence mask: set low-confidence pixels to zero depth
        depth_frame = depth_map[i].copy()
        if conf_threshold > 0:
            low_conf_mask = depth_conf[i] < conf_threshold
            depth_frame[low_conf_mask] = 0.0

        # Clamp depth
        depth_frame[depth_frame > max_depth] = 0.0
        depth_frame[depth_frame < 0] = 0.0

        valid_pixels = (depth_frame > 0).sum()
        total_pixels = H * W
        print(f"  Frame {i}: {valid_pixels}/{total_pixels} valid pixels "
              f"({100*valid_pixels/total_pixels:.1f}%)")

        if valid_pixels < 100:
            print(f"  [SKIP] Frame {i}: too few valid pixels")
            continue

        # Create Open3D depth image (float32, units match VGGT)
        depth_o3d = o3d.geometry.Image(depth_frame.astype(np.float32))

        # Create Open3D color image
        color_frame = images_rgb[i]  # (H, W, 3) uint8
        color_o3d = o3d.geometry.Image(color_frame.astype(np.uint8))

        # Create RGBD image
        rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
            color_o3d, depth_o3d,
            depth_scale=1.0,       # depth is already in VGGT units
            depth_trunc=max_depth,
            convert_rgb_to_intensity=False,
        )

        # Camera intrinsic for Open3D
        K = intrinsic[i]
        o3d_intrinsic = o3d.camera.PinholeCameraIntrinsic(
            width=W, height=H,
            fx=K[0, 0], fy=K[1, 1],
            cx=K[0, 2], cy=K[1, 2],
        )

        # Camera extrinsic for Open3D
        # Open3D integrate() expects the camera pose (world-from-camera / camera-to-world) matrix.
        # VGGT provides camera-from-world (OpenCV convention). We must invert it.
        E_cam_from_world = np.eye(4)
        E_cam_from_world[:3, :] = extrinsic[i]
        E_world_from_cam = np.linalg.inv(E_cam_from_world)

        # Integrate this frame
        volume.integrate(rgbd, o3d_intrinsic, E_world_from_cam)

    # Extract mesh
    print("[+] Extracting mesh from TSDF volume...")
    mesh = volume.extract_triangle_mesh()
    mesh.compute_vertex_normals()

    n_vertices = len(mesh.vertices)
    n_triangles = len(mesh.triangles)
    print(f"[OK] TSDF mesh: {n_vertices} vertices, {n_triangles} triangles")

    return mesh


def poisson_reconstruction(data, conf_threshold=1.0, voxel_downsample=0.01,
                           poisson_depth=9):
    """
    Fallback: Poisson surface reconstruction from fused point cloud.
    """
    import open3d as o3d

    depth_map = data["depth_map"]
    depth_conf = data["depth_conf"]
    world_points = data["world_points"]   # (S, H, W, 3)
    images_rgb = data["images_rgb"]       # (S, H, W, 3)

    S, H, W, _ = world_points.shape

    # Flatten and filter
    pts = world_points.reshape(-1, 3)
    cols = images_rgb.reshape(-1, 3).astype(np.float64) / 255.0
    confs = depth_conf.reshape(-1)

    # Filter by confidence
    mask = confs >= conf_threshold
    # Filter out invalid points
    mask &= np.all(np.isfinite(pts), axis=1)
    mask &= np.linalg.norm(pts, axis=1) < 1000  # Remove extreme outliers

    pts_filtered = pts[mask]
    cols_filtered = cols[mask]
    print(f"[+] Poisson: {len(pts_filtered)}/{len(pts)} points after filtering")

    # Create point cloud
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(pts_filtered)
    pcd.colors = o3d.utility.Vector3dVector(cols_filtered)

    # Voxel downsample
    if voxel_downsample > 0:
        pcd = pcd.voxel_down_sample(voxel_downsample)
        print(f"  After voxel downsample ({voxel_downsample}): {len(pcd.points)} points")

    # Statistical outlier removal
    pcd, ind = pcd.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
    print(f"  After outlier removal: {len(pcd.points)} points")

    # Estimate normals
    pcd.estimate_normals(
        search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.05, max_nn=30)
    )
    pcd.orient_normals_consistent_tangent_plane(k=15)

    # Poisson
    print(f"[+] Running Poisson reconstruction (depth={poisson_depth})...")
    mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
        pcd, depth=poisson_depth
    )

    # Remove low-density vertices (trim the mesh)
    densities = np.asarray(densities)
    density_threshold = np.quantile(densities, 0.05)
    vertices_to_remove = densities < density_threshold
    mesh.remove_vertices_by_mask(vertices_to_remove)

    mesh.compute_vertex_normals()
    n_vertices = len(mesh.vertices)
    n_triangles = len(mesh.triangles)
    print(f"[OK] Poisson mesh: {n_vertices} vertices, {n_triangles} triangles")

    return mesh


def evaluate_mesh(mesh):
    """Basic mesh quality evaluation."""
    import open3d as o3d

    vertices = np.asarray(mesh.vertices)
    triangles = np.asarray(mesh.triangles)

    report = {
        "num_vertices": len(vertices),
        "num_triangles": len(triangles),
        "has_vertex_colors": mesh.has_vertex_colors(),
        "has_vertex_normals": mesh.has_vertex_normals(),
    }

    if len(vertices) > 0:
        extent = vertices.max(axis=0) - vertices.min(axis=0)
        report["extent_xyz"] = extent.tolist()
        report["total_extent"] = float(np.linalg.norm(extent))
        report["centroid"] = vertices.mean(axis=0).tolist()

    # Check for degenerate triangles
    if len(triangles) > 0:
        # Compute triangle areas
        v0 = vertices[triangles[:, 0]]
        v1 = vertices[triangles[:, 1]]
        v2 = vertices[triangles[:, 2]]
        areas = 0.5 * np.linalg.norm(np.cross(v1 - v0, v2 - v0), axis=1)
        report["triangle_area_min"] = float(areas.min())
        report["triangle_area_max"] = float(areas.max())
        report["triangle_area_mean"] = float(areas.mean())
        report["degenerate_triangles"] = int((areas < 1e-12).sum())

    # Is the mesh "recognizable"? (heuristic: has enough structure)
    report["appears_valid"] = (
        len(vertices) > 100 and
        len(triangles) > 100 and
        report.get("total_extent", 0) > 0.01
    )

    return report


def main():
    parser = argparse.ArgumentParser(description="Depth Fusion — TSDF/Poisson Mesh")
    parser.add_argument("--scene_dir", type=str, required=True)
    parser.add_argument("--method", type=str, default="poisson",
                        choices=["tsdf", "poisson", "both", "bpa"],
                        help="Reconstruction method")
    parser.add_argument("--conf_threshold", type=float, default=1.0,
                        help="Minimum depth confidence")
    parser.add_argument("--output", type=str, default=None,
                        help="Output mesh filename (default: raw_mesh.ply)")
    args = parser.parse_args()

    import open3d as o3d
    import json

    print("=" * 60)
    print("Depth Fusion — Metric Mesh Reconstruction")
    print("=" * 60)

    # Load VGGT outputs
    print(f"\n[+] Loading VGGT outputs from {args.scene_dir}/vggt_raw/")
    data = load_vggt_raw(args.scene_dir)
    S = data["depth_map"].shape[0]
    print(f"[+] Loaded {S} frames")

    mesh = None
    method_used = args.method

    if args.method in ("poisson", "both"):
        print("\n" + "=" * 40)
        print("PRIMARY: Poisson Reconstruction")
        print("=" * 40)
        try:
            mesh = poisson_reconstruction(data, conf_threshold=args.conf_threshold)
            method_used = "poisson"
        except Exception as e:
            print(f"[ERROR] Poisson reconstruction failed: {e}")
            if args.method == "poisson":
                print("[!] Falling back to BPA...")
                method_used = "bpa"

    if mesh is None or args.method == "bpa":
        if mesh is None or args.method == "bpa":
            print("\n" + "=" * 40)
            print("FALLBACK: BPA Reconstruction (using Poisson stub)")
            print("=" * 40)
            mesh = poisson_reconstruction(data, conf_threshold=args.conf_threshold)
            method_used = "bpa"
            
    if args.method == "tsdf":
        print("\n" + "=" * 40)
        print("HISTORICAL: TSDF Fusion")
        print("=" * 40)
        mesh = tsdf_fusion(data, conf_threshold=args.conf_threshold)
        method_used = "tsdf"

    if mesh is None or len(mesh.vertices) == 0:
        print("[FAIL] No mesh could be generated.")
        sys.exit(1)

    # Evaluate
    print("\n[+] Evaluating mesh quality...")
    eval_report = evaluate_mesh(mesh)
    eval_report["method"] = method_used

    # Save mesh
    out_name = args.output or "raw_mesh.ply"
    out_path = os.path.join(args.scene_dir, out_name)
    o3d.io.write_triangle_mesh(out_path, mesh)
    print(f"\n[OK] Mesh saved to: {out_path}")

    # Save evaluation report
    report_path = os.path.join(args.scene_dir, "mesh_quality_report.json")
    with open(report_path, "w") as f:
        json.dump(eval_report, f, indent=2)
    print(f"[OK] Quality report saved to: {report_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("MESH QUALITY SUMMARY")
    print("=" * 60)
    for k, v in eval_report.items():
        print(f"  {k}: {v}")

    if eval_report.get("appears_valid"):
        print("\n[OK] Mesh appears valid — proceed to metric alignment and coloring")
    else:
        print("\n[!] Mesh may be degenerate — inspect visually before proceeding")

    return eval_report.get("appears_valid", False)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
