"""
train_drone_gs.py — Fast, isolated Gaussian Splatting trainer for drone reconstruction.

Built on gsplat (Nerfstudio core) for NVIDIA RTX 4090.
Trains 3D Gaussians directly from COLMAP camera poses and sparse points.
Exports standard 3DGS .ply point clouds and evaluation renders.
"""

import os
import sys
import time
import math
import json
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

import cv2
import numpy as np
from scipy.spatial import KDTree
import torch
import torch.nn as nn
import torch.nn.functional as F

from gsplat import rasterization, DefaultStrategy, export_splats


def ssim(img1: torch.Tensor, img2: torch.Tensor, window_size: int = 11) -> torch.Tensor:
    """
    Compute Structural Similarity Index (SSIM) between two (H, W, 3) images in [0, 1].
    """
    # Reshape to (1, 3, H, W)
    x = img1.permute(2, 0, 1).unsqueeze(0)
    y = img2.permute(2, 0, 1).unsqueeze(0)

    channel = 3
    # Gaussian kernel
    coords = torch.arange(window_size, dtype=torch.float32, device=img1.device) - window_size // 2
    g = torch.exp(-(coords ** 2) / (2 * 1.5 ** 2))
    g = g / g.sum()
    kernel = g.unsqueeze(1) @ g.unsqueeze(0)
    kernel = kernel.expand(channel, 1, window_size, window_size).contiguous()

    mu1 = F.conv2d(x, kernel, padding=window_size // 2, groups=channel)
    mu2 = F.conv2d(y, kernel, padding=window_size // 2, groups=channel)

    mu1_sq = mu1.pow(2)
    mu2_sq = mu2.pow(2)
    mu1_mu2 = mu1 * mu2

    sigma1_sq = F.conv2d(x * x, kernel, padding=window_size // 2, groups=channel) - mu1_sq
    sigma2_sq = F.conv2d(y * y, kernel, padding=window_size // 2, groups=channel) - mu2_sq
    sigma12 = F.conv2d(x * y, kernel, padding=window_size // 2, groups=channel) - mu1_mu2

    c1 = 0.01 ** 2
    c2 = 0.03 ** 2

    ssim_map = ((2 * mu1_mu2 + c1) * (2 * sigma12 + c2)) / (
        (mu1_sq + mu2_sq + c1) * (sigma1_sq + sigma2_sq + c2)
    )
    return ssim_map.mean()


def qvec2rotmat(qvec: np.ndarray) -> np.ndarray:
    """Convert quaternion [qw, qx, qy, qz] to 3x3 rotation matrix."""
    qw, qx, qy, qz = qvec
    return np.array([
        [1 - 2 * qy ** 2 - 2 * qz ** 2, 2 * qx * qy - 2 * qz * qw, 2 * qx * qz + 2 * qy * qw],
        [2 * qx * qy + 2 * qz * qw, 1 - 2 * qx ** 2 - 2 * qz ** 2, 2 * qy * qz - 2 * qx * qw],
        [2 * qx * qz - 2 * qy * qw, 2 * qy * qz + 2 * qx * qw, 1 - 2 * qx ** 2 - 2 * qy ** 2],
    ], dtype=np.float32)


class DroneColmapDataset:
    """Loads COLMAP undistorted images, cameras, and sparse 3D point cloud."""

    def __init__(self, data_dir: str, downscale: int = 2, device: str = "cuda"):
        self.data_dir = Path(data_dir).resolve()
        self.images_dir = self.data_dir / "images"
        self.sparse_dir = self.data_dir / "sparse"
        self.downscale = downscale
        self.device = device

        if not self.images_dir.exists():
            raise FileNotFoundError(f"Images directory not found: {self.images_dir}")
        if not self.sparse_dir.exists():
            raise FileNotFoundError(f"Sparse reconstruction not found: {self.sparse_dir}")

        self._load_cameras()
        self._load_images()
        self._load_points()

    def _load_cameras(self):
        cam_file = self.sparse_dir / "cameras.txt"
        self.cameras = {}
        with open(cam_file, "r") as f:
            for line in f:
                if line.startswith("#") or not line.strip():
                    continue
                parts = line.strip().split()
                cam_id = int(parts[0])
                model = parts[1]
                w = int(parts[2])
                h = int(parts[3])
                params = [float(p) for p in parts[4:]]
                self.cameras[cam_id] = {
                    "model": model,
                    "width": w,
                    "height": h,
                    "params": params,
                }

    def _load_images(self):
        img_file = self.sparse_dir / "images.txt"
        self.frames = []
        with open(img_file, "r") as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
            for i in range(0, len(lines), 2):
                parts = lines[i].split()
                img_id = int(parts[0])
                qw, qx, qy, qz = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                tx, ty, tz = float(parts[5]), float(parts[6]), float(parts[7])
                cam_id = int(parts[8])
                img_name = parts[9]

                # Compute world-to-camera matrix (W2C)
                R = qvec2rotmat(np.array([qw, qx, qy, qz]))
                t = np.array([tx, ty, tz], dtype=np.float32)
                W2C = np.eye(4, dtype=np.float32)
                W2C[:3, :3] = R
                W2C[:3, 3] = t

                cam = self.cameras[cam_id]
                orig_w, orig_h = cam["width"], cam["height"]
                fx, fy, cx, cy = cam["params"][:4]

                target_w = orig_w // self.downscale
                target_h = orig_h // self.downscale
                scale_x = target_w / orig_w
                scale_y = target_h / orig_h

                K = np.array([
                    [fx * scale_x, 0.0, cx * scale_x],
                    [0.0, fy * scale_y, cy * scale_y],
                    [0.0, 0.0, 1.0],
                ], dtype=np.float32)

                img_path = self.images_dir / img_name
                if not img_path.exists():
                    continue

                self.frames.append({
                    "id": img_id,
                    "name": img_name,
                    "path": str(img_path),
                    "W2C": W2C,
                    "K": K,
                    "width": target_w,
                    "height": target_h,
                })

        self.frames.sort(key=lambda x: x["name"])
        print(f"[Dataset] Loaded {len(self.frames)} camera frames at {self.frames[0]['width']}x{self.frames[0]['height']} (downscale={self.downscale})")

    def _load_points(self):
        pts_file = self.sparse_dir / "points3D.txt"
        pts = []
        cols = []
        with open(pts_file, "r") as f:
            for line in f:
                if line.startswith("#") or not line.strip():
                    continue
                parts = line.strip().split()
                x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                r, g, b = int(parts[4]), int(parts[5]), int(parts[6])
                pts.append([x, y, z])
                cols.append([r / 255.0, g / 255.0, b / 255.0])

        self.init_points = np.array(pts, dtype=np.float32)
        self.init_colors = np.array(cols, dtype=np.float32)
        print(f"[Dataset] Loaded {len(self.init_points)} initial sparse 3D points")

    def preload_images_to_gpu(self) -> List[Dict[str, Any]]:
        """Preload images into GPU memory for ultra-fast training."""
        gpu_frames = []
        for f in self.frames:
            bgr = cv2.imread(f["path"])
            if self.downscale > 1:
                bgr = cv2.resize(bgr, (f["width"], f["height"]), interpolation=cv2.INTER_AREA)
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
            rgb_tensor = torch.tensor(rgb, dtype=torch.float32, device=self.device)

            W2C_tensor = torch.tensor(f["W2C"], dtype=torch.float32, device=self.device).unsqueeze(0)
            K_tensor = torch.tensor(f["K"], dtype=torch.float32, device=self.device).unsqueeze(0)

            gpu_frames.append({
                "name": f["name"],
                "image": rgb_tensor,
                "viewmat": W2C_tensor,
                "K": K_tensor,
                "width": f["width"],
                "height": f["height"],
            })
        print(f"[Dataset] Preloaded {len(gpu_frames)} frames to GPU VRAM ({self.device})")
        return gpu_frames


class DroneGaussianModel:
    """3D Gaussian Splatting parameters initialized from sparse point cloud."""

    def __init__(self, init_points: np.ndarray, init_colors: np.ndarray, device: str = "cuda"):
        self.device = device
        N = len(init_points)

        # Means (positions)
        means = torch.tensor(init_points, dtype=torch.float32, device=device)

        # Scales initialized from average distance to 3 nearest neighbors
        print(f"[Model] Computing initial scales via KDTree on {N} points...")
        tree = KDTree(init_points)
        dists, _ = tree.query(init_points, k=4)
        mean_dists = np.clip(dists[:, 1:].mean(axis=-1), 1e-4, 5.0)
        log_scales = torch.tensor(np.log(mean_dists[:, None].repeat(3, axis=-1)), dtype=torch.float32, device=device)

        # Quaternions initialized to identity [1, 0, 0, 0]
        quats = torch.zeros((N, 4), dtype=torch.float32, device=device)
        quats[:, 0] = 1.0

        # Opacities initialized to logit(0.1)
        init_opa = 0.1
        logit_opacities = torch.full((N,), math.log(init_opa / (1.0 - init_opa)), dtype=torch.float32, device=device)

        # Colors (RGB features)
        colors = torch.tensor(init_colors, dtype=torch.float32, device=device)

        # Parameter dict for gsplat strategy
        self.params = nn.ParameterDict({
            "means": nn.Parameter(means),
            "scales": nn.Parameter(log_scales),
            "quats": nn.Parameter(quats),
            "opacities": nn.Parameter(logit_opacities),
            "colors": nn.Parameter(colors),
        })

        # Calculate scene scale
        center = self.params["means"].mean(dim=0)
        self.scene_scale = (self.params["means"] - center).norm(dim=-1).quantile(0.95).item() * 1.2
        print(f"[Model] Initialized {N} Gaussians | Scene Scale: {self.scene_scale:.2f}m")

    def create_optimizers(self) -> Dict[str, torch.optim.Optimizer]:
        optimizers = {
            "means": torch.optim.Adam([self.params["means"]], lr=1.6e-4, eps=1e-15),
            "scales": torch.optim.Adam([self.params["scales"]], lr=5.0e-3, eps=1e-15),
            "quats": torch.optim.Adam([self.params["quats"]], lr=1.0e-3, eps=1e-15),
            "opacities": torch.optim.Adam([self.params["opacities"]], lr=5.0e-2, eps=1e-15),
            "colors": torch.optim.Adam([self.params["colors"]], lr=2.5e-3, eps=1e-15),
        }
        return optimizers


def train(
    dataset_dir: str,
    output_dir: str,
    iterations: int = 1500,
    downscale: int = 2,
    device: str = "cuda"
) -> Dict[str, Any]:
    """Train Gaussian Splats on the drone dataset."""
    out_path = Path(output_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)
    renders_dir = out_path / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("GAUSSIAN SPLATTING TRAINING — Aerial Drone Demo")
    print("=" * 60)
    print(f"  Device:       {torch.cuda.get_device_name(0)}")
    print(f"  Iterations:   {iterations}")
    print(f"  Downscale:    {downscale}x")
    print(f"  Output Dir:   {out_path}")

    start_time = time.time()

    # Load dataset
    dataset = DroneColmapDataset(dataset_dir, downscale=downscale, device=device)
    gpu_frames = dataset.preload_images_to_gpu()
    num_views = len(gpu_frames)

    # Initialize model
    model = DroneGaussianModel(dataset.init_points, dataset.init_colors, device=device)
    optimizers = model.create_optimizers()

    # Strategy for densification and pruning
    refine_start = 200
    refine_stop = int(iterations * 0.85)
    refine_every = 100
    reset_every = 600

    strategy = DefaultStrategy(
        prune_opa=0.008,
        grow_grad2d=0.00025,
        grow_scale3d=0.015,
        refine_start_iter=refine_start,
        refine_stop_iter=refine_stop,
        refine_every=refine_every,
        reset_every=reset_every,
        verbose=False
    )
    strategy_state = strategy.initialize_state(scene_scale=model.scene_scale)

    print(f"\n[Training] Starting {iterations} steps (Refinement: steps {refine_start} to {refine_stop} every {refine_every} steps)...")

    # Means LR exponential decay scheduler
    means_lr_init = 1.6e-4
    means_lr_final = 1.6e-6

    # Training loop
    history = []
    t0 = time.time()

    for step in range(1, iterations + 1):
        # Update means learning rate
        lr_factor = (means_lr_final / means_lr_init) ** (step / iterations)
        for param_group in optimizers["means"].param_groups:
            param_group["lr"] = means_lr_init * lr_factor

        # Sample camera view (cycle sequentially through frames)
        view_idx = (step - 1) % num_views
        frame = gpu_frames[view_idx]

        for opt in optimizers.values():
            opt.zero_grad()

        # Rasterize
        renders, alphas, info = rasterization(
            means=model.params["means"],
            quats=F.normalize(model.params["quats"], dim=-1),
            scales=torch.exp(model.params["scales"]),
            opacities=torch.sigmoid(model.params["opacities"]),
            colors=model.params["colors"],
            viewmats=frame["viewmat"],
            Ks=frame["K"],
            width=frame["width"],
            height=frame["height"],
            packed=False
        )

        rendered_img = renders.squeeze(0)  # (H, W, 3)
        gt_img = frame["image"]            # (H, W, 3)

        # Loss: 0.8 L1 + 0.2 (1 - SSIM)
        l1_loss = F.l1_loss(rendered_img, gt_img)
        ssim_val = ssim(rendered_img, gt_img)
        total_loss = 0.8 * l1_loss + 0.2 * (1.0 - ssim_val)

        # Step strategy pre-backward
        strategy.step_pre_backward(model.params, optimizers, strategy_state, step, info)

        # Backward pass
        total_loss.backward()

        # Step strategy post-backward (densify, split, prune)
        strategy.step_post_backward(model.params, optimizers, strategy_state, step, info, packed=False)

        # Optimizer step
        for opt in optimizers.values():
            opt.step()

        # Logging
        if step % 100 == 0 or step == iterations:
            elapsed = time.time() - t0
            fps_speed = 100.0 / elapsed if step > 100 else 100.0 / (elapsed + 1e-5)
            t0 = time.time()

            num_gaussians = len(model.params["means"])
            mse = F.mse_loss(rendered_img, gt_img).item()
            psnr = -10.0 * math.log10(max(mse, 1e-8))
            vram_mb = torch.cuda.max_memory_allocated() / (1024 * 1024)

            print(
                f"  Step {step:4d}/{iterations:4d} | "
                f"Loss: {total_loss.item():.4f} (L1: {l1_loss.item():.4f}, SSIM: {ssim_val.item():.4f}, PSNR: {psnr:.2f}dB) | "
                f"Gaussians: {num_gaussians:6d} | VRAM: {vram_mb:.1f}MB | Speed: {fps_speed:.1f} it/s"
            )
            history.append({
                "step": step,
                "loss": round(total_loss.item(), 5),
                "l1": round(l1_loss.item(), 5),
                "ssim": round(ssim_val.item(), 4),
                "psnr": round(psnr, 2),
                "num_gaussians": num_gaussians,
            })

    total_training_time = time.time() - start_time
    final_gaussians = len(model.params["means"])
    print(f"\n[Training Complete] Finished in {total_training_time:.1f}s | Final Gaussians: {final_gaussians}")

    # ==================== Evaluation & Rendering ====================
    print("\n[Evaluation] Rendering all 17 camera views for comparison...")
    eval_metrics = []
    with torch.no_grad():
        for i, frame in enumerate(gpu_frames):
            renders, _, _ = rasterization(
                means=model.params["means"],
                quats=F.normalize(model.params["quats"], dim=-1),
                scales=torch.exp(model.params["scales"]),
                opacities=torch.sigmoid(model.params["opacities"]),
                colors=model.params["colors"],
                viewmats=frame["viewmat"],
                Ks=frame["K"],
                width=frame["width"],
                height=frame["height"],
                packed=False
            )
            render_np = (renders.squeeze(0).clamp(0, 1).cpu().numpy() * 255).astype(np.uint8)
            gt_np = (frame["image"].clamp(0, 1).cpu().numpy() * 255).astype(np.uint8)

            # Difference image
            diff_np = np.abs(render_np.astype(np.int16) - gt_np.astype(np.int16)).clip(0, 255).astype(np.uint8)

            # Side-by-side comparison: [GT | Render | Diff]
            comparison = np.concatenate([gt_np, render_np, diff_np], axis=1)

            # Save render and comparison
            render_out = renders_dir / f"render_{i:04d}.png"
            comp_out = renders_dir / f"compare_{i:04d}.png"

            cv2.imwrite(str(render_out), cv2.cvtColor(render_np, cv2.COLOR_RGB2BGR))
            cv2.imwrite(str(comp_out), cv2.cvtColor(comparison, cv2.COLOR_RGB2BGR))

            mse = np.mean((render_np.astype(float) - gt_np.astype(float)) ** 2)
            psnr_val = 10 * np.log10(255.0 ** 2 / max(mse, 1e-6))
            eval_metrics.append({"frame": frame["name"], "psnr": round(psnr_val, 2)})

    avg_psnr = float(np.mean([m["psnr"] for m in eval_metrics]))
    print(f"  Average Evaluation PSNR: {avg_psnr:.2f} dB across {num_views} frames")
    print(f"  Renders saved to: {renders_dir}")

    # ==================== Model Export (.PLY) ====================
    ply_out = out_path / "point_cloud.ply"
    print(f"\n[Export] Saving 3D Gaussian Splatting PLY model to: {ply_out}...")

    with torch.no_grad():
        final_means = model.params["means"].detach().cpu()
        final_scales = torch.exp(model.params["scales"]).detach().cpu()
        final_quats = F.normalize(model.params["quats"], dim=-1).detach().cpu()
        final_opacities = torch.sigmoid(model.params["opacities"]).detach().cpu()

        # Convert RGB colors to SH degree 0
        final_colors = model.params["colors"].detach().cpu()
        final_sh0 = (final_colors[:, None, :] - 0.5) / 0.28209479177387814
        final_shN = torch.zeros((len(final_means), 0, 3))

        export_splats(
            means=final_means,
            scales=final_scales,
            quats=final_quats,
            opacities=final_opacities,
            sh0=final_sh0,
            shN=final_shN,
            format="ply",
            save_to=str(ply_out)
        )

    ply_size_mb = os.path.getsize(ply_out) / (1024 * 1024)
    print(f"  [OK] Exported point_cloud.ply ({ply_size_mb:.2f} MB)")

    # Save PyTorch checkpoint
    ckpt_out = out_path / "checkpoint.pt"
    torch.save({
        "step": iterations,
        "params": model.params.state_dict(),
        "scene_scale": model.scene_scale,
        "downscale": downscale,
    }, ckpt_out)
    print(f"  [OK] Saved PyTorch checkpoint: {ckpt_out}")

    # Save final report
    report = {
        "status": "SUCCESS",
        "gpu": torch.cuda.get_device_name(0),
        "iterations": iterations,
        "training_time_seconds": round(total_training_time, 2),
        "initial_points": len(dataset.init_points),
        "final_gaussians": final_gaussians,
        "average_psnr_db": round(avg_psnr, 2),
        "output_ply": str(ply_out),
        "output_ply_size_mb": round(ply_size_mb, 2),
        "output_checkpoint": str(ckpt_out),
        "renders_dir": str(renders_dir),
        "training_history": history,
        "per_frame_psnr": eval_metrics
    }

    report_out = out_path / "training_report.json"
    with open(report_out, "w") as f:
        json.dump(report, f, indent=2)
    print(f"  [OK] Saved training report: {report_out}")

    return report


def main():
    parser = argparse.ArgumentParser(description="Train 3D Gaussian Splats on Drone Video")
    parser.add_argument("--data_dir", type=str, default="gaussian_splat/data/drone_demo/undistorted",
                        help="Path to COLMAP undistorted dataset directory")
    parser.add_argument("--out_dir", type=str, default="outputs/gaussian_demo",
                        help="Output directory for trained Gaussian model and renders")
    parser.add_argument("--iterations", type=int, default=1500,
                        help="Number of training iterations (default: 1500)")
    parser.add_argument("--downscale", type=int, default=2,
                        help="Image downscale factor (default: 2 -> 1901x1069)")
    args = parser.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device != "cuda":
        print("[FAIL] CUDA is not available. An NVIDIA GPU is required.")
        sys.exit(1)

    train(
        dataset_dir=args.data_dir,
        output_dir=args.out_dir,
        iterations=args.iterations,
        downscale=args.downscale,
        device=device
    )


if __name__ == "__main__":
    main()
