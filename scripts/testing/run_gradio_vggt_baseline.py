import os
import sys
import time
import torch
import torch.nn.functional as F
import glob
import numpy as np

torch.backends.cudnn.enabled = True
torch.backends.cudnn.benchmark = True
torch.backends.cudnn.deterministic = False

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(project_root, "third_party", "vggt"))

from vggt.models.vggt import VGGT
from vggt.utils.load_fn import load_and_preprocess_images
from vggt.utils.pose_enc import pose_encoding_to_extri_intri

if __name__ == "__main__":
    scene_dir = os.path.join(project_root, "outputs", "baseline_test")
    image_dir = os.path.join(scene_dir, "images")
        
    print("\nRunning OFFICIAL FacebookResearch demo_gradio inference on 8 frames...")
    
    dtype = torch.bfloat16 if torch.cuda.get_device_capability()[0] >= 8 else torch.float16
    device = "cuda" if torch.cuda.is_available() else "cpu"

    model = VGGT()
    _URL = "https://huggingface.co/facebook/VGGT-1B/resolve/main/model.pt"
    
    t0 = time.time()
    model.load_state_dict(torch.hub.load_state_dict_from_url(_URL))
    model.eval()
    model = model.to(device)
    t1 = time.time()
    print(f"Model loaded in {t1 - t0:.1f}s")

    image_path_list = sorted(glob.glob(os.path.join(image_dir, "*")))

    t0 = time.time()
    images = load_and_preprocess_images(image_path_list, mode="crop")
    images = images.to(device)
    t1 = time.time()
    print(f"Loaded {len(images)} images in {t1 - t0:.1f}s, shape: {images.shape}")

    t0 = time.time()
    with torch.no_grad():
        with torch.cuda.amp.autocast(dtype=dtype):
            predictions = model(images)
            
    # Convert pose encoding to extrinsic and intrinsic matrices
    extrinsic, intrinsic = pose_encoding_to_extri_intri(predictions["pose_enc"], images.shape[-2:])
    t1 = time.time()
    
    print(f"Inference completed in {t1 - t0:.1f}s")
    print(f"extrinsic: {extrinsic.shape}, depth_map: {predictions['depth'].shape}")
