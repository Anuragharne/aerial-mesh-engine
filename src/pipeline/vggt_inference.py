"""
VGGT Dense Inference — saves raw depth maps, confidence, camera poses, and point maps.

This script runs VGGT on a set of input images and saves all dense intermediate
outputs as .npz files for downstream TSDF fusion and metric mesh generation.

Outputs saved to <scene_dir>/vggt_raw/:
  - depth_map.npy          (S, H, W)     per-pixel depth
  - depth_conf.npy         (S, H, W)     per-pixel confidence
  - extrinsic.npy          (S, 3, 4)     camera extrinsic (camera-from-world, OpenCV)
  - intrinsic.npy          (S, 3, 3)     camera intrinsic
  - world_points.npy       (S, H, W, 3)  dense 3D world points
  - images_rgb.npy         (S, H, W, 3)  RGB images at inference resolution
  - metadata.npz           resolution, image paths, original_coords

VGGT Convention Notes (verified from source code):
  - extrinsic is camera-from-world (OpenCV convention)
  - intrinsic is standard [fx, 0, cx; 0, fy, cy; 0, 0, 1]
  - depth is along the z-axis in camera coordinates
  - inference resolution is 518x518 (fixed)
  - images are loaded at 1024x1024, but depth is at 518x518
"""

import os
import sys
import glob
import random
import argparse

import numpy as np
import torch
import torch.nn.functional as F

# Configure CUDA
torch.backends.cudnn.enabled = True
torch.backends.cudnn.benchmark = True
torch.backends.cudnn.deterministic = False

# VGGT path added dynamically below

import sys
import os
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(project_root, "third_party", "vggt"))

from vggt.models.vggt import VGGT
from vggt.utils.load_fn import load_and_preprocess_images
from vggt.utils.pose_enc import pose_encoding_to_extri_intri
from vggt.utils.geometry import unproject_depth_map_to_point_map


def run_vggt_dense(model, images, dtype):
    """
    Run VGGT and return ALL dense outputs.

    Args:
        model: VGGT model
        images: (S, 3, H, W) tensor
        dtype: torch dtype for mixed precision

    Returns:
        extrinsic: (S, 3, 4) numpy — camera-from-world (OpenCV)
        intrinsic: (S, 3, 3) numpy
        depth_map: (S, H, W) numpy — per-pixel depth at inference resolution
        depth_conf: (S, H, W) numpy — per-pixel confidence
    """
    assert len(images.shape) == 4
    assert images.shape[1] == 3

    with torch.no_grad():
        with torch.cuda.amp.autocast(dtype=dtype):
            predictions = model(images)
            
        extrinsic, intrinsic = pose_encoding_to_extri_intri(predictions["pose_enc"], images.shape[-2:])
        depth_map = predictions["depth"]
        depth_conf = predictions["depth_conf"]

    extrinsic = extrinsic.squeeze(0).cpu().numpy()
    intrinsic = intrinsic.squeeze(0).cpu().numpy()
    depth_map = depth_map.squeeze(0).squeeze(-1).cpu().numpy()
    depth_conf = depth_conf.squeeze(0).cpu().numpy()

    return extrinsic, intrinsic, depth_map, depth_conf


def save_vggt_outputs(scene_dir, extrinsic, intrinsic, depth_map, depth_conf,
                      world_points, images_rgb, image_paths, original_coords,
                      vggt_resolution):
    """Save all dense VGGT outputs to disk."""
    out_dir = os.path.join(scene_dir, "vggt_raw")
    os.makedirs(out_dir, exist_ok=True)

    np.save(os.path.join(out_dir, "depth_map.npy"), depth_map)
    np.save(os.path.join(out_dir, "depth_conf.npy"), depth_conf)
    np.save(os.path.join(out_dir, "extrinsic.npy"), extrinsic)
    np.save(os.path.join(out_dir, "intrinsic.npy"), intrinsic)
    np.save(os.path.join(out_dir, "world_points.npy"), world_points)
    np.save(os.path.join(out_dir, "images_rgb.npy"), images_rgb)

    np.savez(
        os.path.join(out_dir, "metadata.npz"),
        image_paths=np.array(image_paths),
        original_coords=original_coords,
        vggt_resolution=np.array(vggt_resolution),
    )

    print(f"[OK] Saved VGGT dense outputs to: {out_dir}")
    print(f"    depth_map:    {depth_map.shape} dtype={depth_map.dtype}")
    print(f"    depth_conf:   {depth_conf.shape}")
    print(f"    extrinsic:    {extrinsic.shape}")
    print(f"    intrinsic:    {intrinsic.shape}")
    print(f"    world_points: {world_points.shape}")
    print(f"    images_rgb:   {images_rgb.shape}")

    return out_dir


def main():
    parser = argparse.ArgumentParser(description="VGGT Dense Inference")
    parser.add_argument("--scene_dir", type=str, required=True,
                        help="Directory containing images/ subfolder")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--conf_thres", type=float, default=5.0,
                        help="Confidence threshold for sparse export (not used for dense)")
    args = parser.parse_args()

    # Seed
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    random.seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(args.seed)
        torch.cuda.manual_seed_all(args.seed)

    # Device
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16
    print(f"[+] Device: {device} | dtype: {dtype}")

    if device == "cpu":
        print("[WARNING] Running on CPU — this will be very slow for VGGT.")

    # Load model
    print("[+] Loading VGGT model...")
    model = VGGT()
    _URL = "https://huggingface.co/facebook/VGGT-1B/resolve/main/model.pt"
    model.load_state_dict(torch.hub.load_state_dict_from_url(_URL))
    model.eval()
    model = model.to(device)
    print("[OK] Model loaded")

    # Load images
    image_dir = os.path.join(args.scene_dir, "images")
    image_path_list = sorted(glob.glob(os.path.join(image_dir, "*")))
    if not image_path_list:
        raise ValueError(f"No images found in {image_dir}")

    base_image_paths = [os.path.basename(p) for p in image_path_list]

    vggt_resolution = 518
    # For a 6GB VRAM target, we MUST load images at the inference resolution to save memory.
    img_load_resolution = 518

    print(f"[+] Loading {len(image_path_list)} images...")
    images = load_and_preprocess_images(image_path_list, mode="crop")
    images = images.to(device)
    
    # original_coords is not returned by mode="crop", create dummy for metadata
    original_coords_np = np.zeros((len(images), 5))
    print(f"[OK] Loaded {len(images)} images, shape: {images.shape}")

    # Run VGGT
    print("[+] Running VGGT inference...")
    import time
    t0 = time.time()
    extrinsic, intrinsic, depth_map, depth_conf = run_vggt_dense(
        model, images, dtype
    )
    t1 = time.time()
    print(f"[OK] Inference completed in {t1 - t0:.2f}s")

    # Unproject to world points (dense)
    print("[+] Unprojecting depth to world coordinates...")
    world_points = unproject_depth_map_to_point_map(depth_map, extrinsic, intrinsic)

    # Extract RGB at inference resolution for vertex coloring
    images_rgb = (images.cpu().numpy() * 255).astype(np.uint8)
    images_rgb = images_rgb.transpose(0, 2, 3, 1)  # (S, H, W, 3)

    # Save
    save_vggt_outputs(
        args.scene_dir, extrinsic, intrinsic, depth_map, depth_conf,
        world_points, images_rgb, base_image_paths, original_coords_np,
        vggt_resolution
    )

    # Print convention summary for downstream consumers
    print("\n=== VGGT Convention Summary ===")
    print(f"  extrinsic shape: {extrinsic.shape} — camera-from-world (OpenCV)")
    print(f"  intrinsic shape: {intrinsic.shape} — [fx,0,cx; 0,fy,cy; 0,0,1]")
    print(f"  depth_map shape: {depth_map.shape} — z-depth in camera coords")
    print(f"  depth range: [{depth_map.min():.4f}, {depth_map.max():.4f}]")
    print(f"  depth_conf range: [{depth_conf.min():.4f}, {depth_conf.max():.4f}]")
    print(f"  world_points shape: {world_points.shape}")
    print(f"  world_points range X: [{world_points[...,0].min():.4f}, {world_points[...,0].max():.4f}]")
    print(f"  world_points range Y: [{world_points[...,1].min():.4f}, {world_points[...,1].max():.4f}]")
    print(f"  world_points range Z: [{world_points[...,2].min():.4f}, {world_points[...,2].max():.4f}]")

    # Quick NaN/Inf check
    nan_depth = np.isnan(depth_map).sum()
    inf_depth = np.isinf(depth_map).sum()
    nan_pts = np.isnan(world_points).sum()
    inf_pts = np.isinf(world_points).sum()
    print(f"\n  NaN in depth: {nan_depth}, Inf in depth: {inf_depth}")
    print(f"  NaN in world_points: {nan_pts}, Inf in world_points: {inf_pts}")

    if nan_depth > 0 or inf_depth > 0 or nan_pts > 0 or inf_pts > 0:
        print("[WARNING] Detected NaN/Inf values in VGGT output!")
    else:
        print("[OK] No NaN/Inf detected — VGGT output looks clean")

    # Free GPU memory aggressively
    del model
    del images
    import gc
    gc.collect()
    torch.cuda.empty_cache()

    print("\n[OK] VGGT inference complete.")


if __name__ == "__main__":
    main()
