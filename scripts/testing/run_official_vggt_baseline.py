import os
import sys
import time
import torch
import torch.nn.functional as F
import glob
import numpy as np

# Configure CUDA settings matching official demo_colmap.py
torch.backends.cudnn.enabled = True
torch.backends.cudnn.benchmark = True
torch.backends.cudnn.deterministic = False

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(project_root, "third_party", "vggt"))

from vggt.models.vggt import VGGT
from vggt.utils.load_fn import load_and_preprocess_images_square
from vggt.utils.pose_enc import pose_encoding_to_extri_intri
from vggt.utils.geometry import unproject_depth_map_to_point_map

def run_VGGT(model, images, dtype, resolution=518):
    # This is exactly copied from third_party/vggt/demo_colmap.py
    # images: [B, 3, H, W]

    assert len(images.shape) == 4
    assert images.shape[1] == 3

    # hard-coded to use 518 for VGGT
    images = F.interpolate(images, size=(resolution, resolution), mode="bilinear", align_corners=False)

    with torch.no_grad():
        with torch.cuda.amp.autocast(dtype=dtype):
            images = images[None]  # add batch dimension
            aggregated_tokens_list, ps_idx = model.aggregator(images)

        # Predict Cameras
        pose_enc = model.camera_head(aggregated_tokens_list)[-1]
        # Extrinsic and intrinsic matrices, following OpenCV convention (camera from world)
        extrinsic, intrinsic = pose_encoding_to_extri_intri(pose_enc, images.shape[-2:])
        # Predict Depth Maps
        depth_map, depth_conf = model.depth_head(aggregated_tokens_list, images, ps_idx)

    extrinsic = extrinsic.squeeze(0).cpu().numpy()
    intrinsic = intrinsic.squeeze(0).cpu().numpy()
    depth_map = depth_map.squeeze(0).cpu().numpy()
    depth_conf = depth_conf.squeeze(0).cpu().numpy()
    return extrinsic, intrinsic, depth_map, depth_conf

if __name__ == "__main__":
    scene_dir = os.path.join(project_root, "outputs", "baseline_test")
    image_dir = os.path.join(scene_dir, "images")
    
    # Generate images if not exist
    if not os.path.exists(image_dir) or len(glob.glob(os.path.join(image_dir, "*"))) == 0:
        import subprocess
        print("Extracting 8 frames for the baseline test...")
        subprocess.run([
            sys.executable, "src/pipeline/ingest_telemetry.py",
            "--video", "data/sample/drone_test.MP4",
            "--out", scene_dir,
            "--frames", "8"
        ], cwd=project_root, check=True)
        
    print("\nRunning OFFICIAL FacebookResearch VGGT inference on 8 frames...")
    
    dtype = torch.bfloat16 if torch.cuda.get_device_capability()[0] >= 8 else torch.float16
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")
    print(f"Using dtype: {dtype}")

    # Run VGGT for camera and depth estimation
    model = VGGT()
    _URL = "https://huggingface.co/facebook/VGGT-1B/resolve/main/model.pt"
    
    print("Loading model...")
    t0 = time.time()
    model.load_state_dict(torch.hub.load_state_dict_from_url(_URL))
    model.eval()
    model = model.to(device)
    t1 = time.time()
    print(f"Model loaded in {t1 - t0:.1f}s")

    # Get image paths and preprocess them
    image_path_list = glob.glob(os.path.join(image_dir, "*"))
    vggt_fixed_resolution = 518
    img_load_resolution = 1024

    print("Loading images...")
    t0 = time.time()
    images, original_coords = load_and_preprocess_images_square(image_path_list, img_load_resolution)
    images = images.to(device)
    t1 = time.time()
    print(f"Loaded {len(images)} images in {t1 - t0:.1f}s, shape: {images.shape}")

    print("Running inference...")
    t0 = time.time()
    extrinsic, intrinsic, depth_map, depth_conf = run_VGGT(model, images, dtype, vggt_fixed_resolution)
    t1 = time.time()
    
    print(f"Inference completed in {t1 - t0:.1f}s")
    print(f"extrinsic: {extrinsic.shape}, depth_map: {depth_map.shape}")
