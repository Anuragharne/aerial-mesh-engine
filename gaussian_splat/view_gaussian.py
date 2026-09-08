"""
view_gaussian.py — Interactive 3D web viewer for drone Gaussian Splats using Viser.

Usage:
    python gaussian_splat/view_gaussian.py --ply outputs/gaussian_demo/point_cloud.ply --port 8080
"""

import os
import sys
import time
import argparse
from pathlib import Path
import numpy as np
from plyfile import PlyData
import viser


def main():
    parser = argparse.ArgumentParser(description="View trained 3D Gaussian Splats in interactive web viewer")
    parser.add_argument("--ply", type=str, default="outputs/gaussian_demo/point_cloud.ply",
                        help="Path to 3DGS .ply point cloud")
    parser.add_argument("--port", type=int, default=8080,
                        help="Server port (default: 8080)")
    parser.add_argument("--max_points", type=int, default=300000,
                        help="Max points to display in interactive viewer")
    args = parser.parse_args()

    ply_path = Path(args.ply).resolve()
    if not ply_path.exists():
        print(f"[FAIL] PLY file not found: {ply_path}")
        sys.exit(1)

    print("=" * 60)
    print("GAUSSIAN SPLAT 3D VIEWER (Viser)")
    print("=" * 60)
    print(f"  Loading model: {ply_path} ({ply_path.stat().st_size / (1024*1024):.2f} MB)...")

    plydata = PlyData.read(str(ply_path))
    vertex = plydata["vertex"]

    x = np.array(vertex["x"])
    y = np.array(vertex["y"])
    z = np.array(vertex["z"])
    points = np.stack([x, y, z], axis=-1)

    # Load colors
    if "f_dc_0" in vertex:
        # SH degree 0 to RGB
        c0 = np.array(vertex["f_dc_0"])
        c1 = np.array(vertex["f_dc_1"])
        c2 = np.array(vertex["f_dc_2"])
        rgb = np.stack([c0, c1, c2], axis=-1) * 0.28209479177387814 + 0.5
        colors = np.clip(rgb, 0.0, 1.0)
    elif "red" in vertex:
        r = np.array(vertex["red"]) / 255.0
        g = np.array(vertex["green"]) / 255.0
        b = np.array(vertex["blue"]) / 255.0
        colors = np.stack([r, g, b], axis=-1)
    else:
        colors = np.ones_like(points) * 0.7

    # Load opacity if present
    if "opacity" in vertex:
        opacities = 1.0 / (1.0 + np.exp(-np.array(vertex["opacity"])))
        mask = opacities > 0.05
        points = points[mask]
        colors = colors[mask]

    num_points = len(points)
    print(f"  Loaded {num_points} active Gaussians.")

    if num_points > args.max_points:
        indices = np.random.choice(num_points, args.max_points, replace=False)
        points = points[indices]
        colors = colors[indices]
        print(f"  Subsampled to {args.max_points} points for smooth 60fps web rendering.")

    print(f"\n[+] Starting Viser Web Server on http://localhost:{args.port}...")
    server = viser.ViserServer(host="0.0.0.0", port=args.port)

    server.scene.add_point_cloud(
        name="/gaussian_splats",
        points=points,
        colors=colors,
        point_size=0.03,
        point_shape="circle"
    )

    # Coordinate grid
    server.scene.add_grid(name="/grid", width=40.0, height=40.0, cell_size=1.0)

    print(f"\n[OK] Viewer is READY!")
    print(f"  --> Open in browser: http://localhost:{args.port}")
    print("  Press Ctrl+C to close viewer.")

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nViewer closed.")


if __name__ == "__main__":
    main()
