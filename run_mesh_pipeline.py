"""
run_mesh_pipeline.py — Deterministic end-to-end metric mesh pipeline.

Drone Video + SRT
    → Frame Extraction (ingest_telemetry.py)
    → Dynamic Masking (mask_dynamics.py) [optional]
    → VGGT Dense Inference (vggt_inference.py)
    → VGGT Quality Gate (vggt_quality_gate.py)
    → Metric Alignment (metric_alignment.py) — BEFORE fusion
    → TSDF Depth Fusion (depth_fusion.py) — using metric-aligned poses
    → Mesh Quality Evaluation
    → Viser Viewer (mesh_viewer.py) [optional]

Usage:
    conda activate sugar
    python run_mesh_pipeline.py --video drone_test.MP4 --srt drone_test.SRT --frames 8

Existing 3DGS/SuGaR/COLMAP pipelines are SECONDARY — not invoked here.
"""

import os
import sys
import json
import shutil
import argparse
import subprocess
import time

# All scripts run in the same Python interpreter
PYTHON = sys.executable


def run_step(name, cmd, cwd=None):
    """Run a pipeline step as a subprocess."""
    print(f"\n{'=' * 60}")
    print(f"STEP: {name}")
    print(f"{'=' * 60}")
    print(f"CMD: {' '.join(cmd)}")

    start = time.time()
    result = subprocess.run(cmd, cwd=cwd or os.path.dirname(__file__))
    elapsed = time.time() - start

    if result.returncode != 0:
        print(f"[FAIL] {name} failed with exit code {result.returncode}")
        return False
    print(f"[OK] {name} completed in {elapsed:.1f}s")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Metric Mesh Pipeline — End-to-End"
    )
    parser.add_argument("--video", type=str, default="drone_test.MP4",
                        help="Input drone video")
    parser.add_argument("--srt", type=str, default="drone_test.SRT",
                        help="Input SRT telemetry file")
    parser.add_argument("--out", type=str, default="outputs/metric_mesh_demo",
                        help="Output directory")
    parser.add_argument("--frames", type=int, default=8,
                        help="Number of frames to extract")
    parser.add_argument("--fps", type=int, default=2,
                        help="Frame extraction FPS")
    parser.add_argument("--skip_masking", action="store_true",
                        help="Skip YOLO dynamic masking")
    parser.add_argument("--skip_vggt", action="store_true",
                        help="Skip VGGT inference (use existing outputs)")
    parser.add_argument("--skip_alignment", action="store_true",
                        help="Skip GPS metric alignment")
    parser.add_argument("--mesh_method", type=str, default="poisson",
                        choices=["tsdf", "poisson", "both", "bpa"])
    parser.add_argument("--conf_threshold", type=float, default=1.0,
                        help="Depth confidence threshold")
    parser.add_argument("--viewer", action="store_true",
                        help="Launch Viser viewer after mesh generation")
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.abspath(__file__))
    scene_dir = os.path.join(project_root, args.out)

    print("=" * 60)
    print("METRIC MESH PIPELINE — END-TO-END")
    print("=" * 60)
    print(f"  Video:    {args.video}")
    print(f"  SRT:      {args.srt}")
    print(f"  Output:   {scene_dir}")
    print(f"  Frames:   {args.frames}")
    print(f"  Method:   {args.mesh_method}")

    pipeline_start = time.time()

    # ========== STEP 1: Frame Extraction ==========
    images_dir = os.path.join(scene_dir, "images")
    if not os.path.exists(images_dir) or len(os.listdir(images_dir)) == 0:
        ok = run_step("Frame Extraction", [
            PYTHON, os.path.join(project_root, "src", "pipeline", "ingest_telemetry.py"),
            "--video", os.path.join(project_root, args.video),
            "--srt", os.path.join(project_root, args.srt),
            "--out", scene_dir,
            "--frames", str(args.frames)
        ])
        if not ok:
            return False

        # Keep only N frames for the prototype
        all_images = sorted([f for f in os.listdir(images_dir)
                             if f.endswith((".png", ".jpg"))])
        if len(all_images) > args.frames:
            # Keep evenly spaced frames for diversity
            step = len(all_images) / args.frames
            keep_indices = set(int(i * step) for i in range(args.frames))
            for i, img in enumerate(all_images):
                if i not in keep_indices:
                    os.remove(os.path.join(images_dir, img))
            print(f"  Kept {args.frames} evenly-spaced frames from {len(all_images)}")
    else:
        n_existing = len([f for f in os.listdir(images_dir) if f.endswith((".png", ".jpg"))])
        print(f"\n[+] Using existing {n_existing} frames in {images_dir}")

    # ========== STEP 2: Dynamic Masking (optional) ==========
    if not args.skip_masking:
        masks_dir = os.path.join(scene_dir, "masks")
        if not os.path.exists(masks_dir):
            ok = run_step("Dynamic Masking (YOLO)", [
                PYTHON, os.path.join(project_root, "src", "pipeline", "mask_dynamics.py"),
                "--scene", scene_dir,
            ])
            if not ok:
                print("[WARNING] Masking failed — continuing without masks")
        else:
            print(f"\n[+] Using existing masks in {masks_dir}")

    # ========== STEP 3: VGGT Inference ==========
    vggt_raw_dir = os.path.join(scene_dir, "vggt_raw")
    if not args.skip_vggt or not os.path.exists(vggt_raw_dir):
        ok = run_step("VGGT Dense Inference", [
            PYTHON, os.path.join(project_root, "src", "pipeline", "vggt_inference.py"),
            "--scene_dir", scene_dir,
        ])
        if not ok:
            print("[FAIL] VGGT inference failed. Cannot continue.")
            return False
    else:
        print(f"\n[+] Using existing VGGT outputs in {vggt_raw_dir}")

    # ========== STEP 4: VGGT Quality Gate ==========
    ok = run_step("VGGT Quality Gate", [
        PYTHON, os.path.join(project_root, "src", "pipeline", "vggt_quality_gate.py"),
        "--scene_dir", scene_dir,
    ])
    if not ok:
        print("[FAIL] VGGT quality gate failed. Geometry may be invalid.")
        print("       Review vggt_quality_report.json before continuing.")
        return False

    # ========== STEP 5: Metric Alignment (BEFORE fusion) ==========
    telemetry_path = os.path.join(scene_dir, "telemetry_index.json")
    if not args.skip_alignment and os.path.exists(telemetry_path):
        ok = run_step("Metric Alignment (Sim3)", [
            PYTHON, os.path.join(project_root, "src", "pipeline", "metric_alignment.py"),
            "--scene_dir", scene_dir,
            "--telemetry", telemetry_path,
        ])
        if not ok:
            print("[WARNING] Metric alignment failed — will fuse in VGGT coordinates")
    elif not os.path.exists(telemetry_path):
        print(f"\n[WARNING] No telemetry_index.json found — skipping alignment")

    # ========== STEP 6: TSDF Depth Fusion ==========
    # Check if metric extrinsics exist (alignment was done before fusion)
    metric_ext_path = os.path.join(vggt_raw_dir, "metric_extrinsic.npy")
    use_metric = os.path.exists(metric_ext_path)
    if use_metric:
        print("\n[+] Using metric-aligned camera poses for fusion (preferred path)")

    ok = run_step("Depth Fusion → Mesh", [
        PYTHON, os.path.join(project_root, "src", "pipeline", "depth_fusion.py"),
        "--scene_dir", scene_dir,
        "--method", args.mesh_method,
        "--conf_threshold", str(args.conf_threshold),
        "--output", "metric_mesh.ply" if use_metric else "raw_mesh.ply",
    ])
    if not ok:
        print("[FAIL] Mesh generation failed.")
        return False

    # ========== SUMMARY ==========
    total_time = time.time() - pipeline_start

    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)
    print(f"  Total time: {total_time:.1f}s ({total_time/60:.1f}min)")
    print(f"  Output dir: {scene_dir}")

    # List outputs
    mesh_file = "metric_mesh.ply" if use_metric else "raw_mesh.ply"
    mesh_path = os.path.join(scene_dir, mesh_file)
    if os.path.exists(mesh_path):
        size_mb = os.path.getsize(mesh_path) / (1024 * 1024)
        print(f"  Mesh: {mesh_file} ({size_mb:.1f} MB)")
    else:
        print(f"  [WARNING] Expected mesh file not found: {mesh_path}")

    for report_file in ["vggt_quality_report.json", "alignment_report.json",
                        "mesh_quality_report.json"]:
        rpath = os.path.join(scene_dir, report_file)
        if os.path.exists(rpath):
            print(f"  Report: {report_file}")

    # ========== Optional: Launch Viewer ==========
    if args.viewer and os.path.exists(mesh_path):
        print(f"\n[+] Launching Viser viewer...")
        # This will be implemented in mesh_viewer.py
        viewer_script = os.path.join(project_root, "mesh_viewer.py")
        if os.path.exists(viewer_script):
            subprocess.Popen([PYTHON, viewer_script, "--mesh", mesh_path])
            print("[OK] Viewer launched at http://localhost:8080")
        else:
            print("[!] mesh_viewer.py not yet created — skipping viewer")

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
