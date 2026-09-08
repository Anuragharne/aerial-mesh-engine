"""
mask_dynamics.py — Dynamic object masking using YOLO segmentation.

Identifies dynamic objects (persons, vehicles, bicycles, animals) and generates
binary masks to prevent dynamic object artifacts during 3D reconstruction and TSDF fusion.
"""

import os
import sys
import argparse
from pathlib import Path
import numpy as np
import cv2

# Dynamic object COCO class IDs (person, bicycle, car, motorcycle, airplane, bus, train, truck, boat, bird, cat, dog, horse, sheep, cow)
DYNAMIC_CLASS_IDS = {0, 1, 2, 3, 4, 5, 6, 7, 8, 14, 15, 16, 17, 18, 19}


def generate_masks(scene_dir: str, model_path: str = None, conf_thresh: float = 0.25):
    scene_path = Path(scene_dir).resolve()
    images_dir = scene_path / "images"
    masks_dir = scene_path / "masks"
    masks_dir.mkdir(parents=True, exist_ok=True)

    if not images_dir.exists():
        print(f"[!] Images directory not found: {images_dir}")
        return False

    image_files = sorted([f for f in images_dir.iterdir() if f.suffix.lower() in [".png", ".jpg", ".jpeg"]])
    if not image_files:
        print(f"[!] No images found in {images_dir}")
        return False

    print(f"[+] Found {len(image_files)} images for dynamic masking")

    # Resolve YOLO model path
    if model_path is None:
        project_root = Path(__file__).resolve().parent.parent.parent
        default_model = project_root / "models" / "yolov8s-seg.pt"
        if default_model.exists():
            model_path = str(default_model)
        else:
            model_path = "yolov8s-seg.pt"  # fallback to auto-download

    print(f"[+] Loading segmentation model: {model_path}")
    try:
        from ultralytics import YOLO
        model = YOLO(model_path)
    except Exception as e:
        print(f"[WARNING] Could not load YOLO model ({e}). Generating empty static masks.")
        for img_path in image_files:
            img = cv2.imread(str(img_path))
            h, w = img.shape[:2]
            mask = np.zeros((h, w), dtype=np.uint8)
            mask_out = masks_dir / f"{img_path.stem}.png"
            cv2.imwrite(str(mask_out), mask)
        return True

    for img_path in image_files:
        img = cv2.imread(str(img_path))
        h, w = img.shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)

        results = model.predict(source=str(img_path), conf=conf_thresh, verbose=False)
        if results and results[0].masks is not None:
            r = results[0]
            boxes = r.boxes
            for idx, box in enumerate(boxes):
                cls_id = int(box.cls[0].item())
                if cls_id in DYNAMIC_CLASS_IDS:
                    seg_mask = r.masks.data[idx].cpu().numpy()
                    seg_resized = cv2.resize(seg_mask, (w, h), interpolation=cv2.INTER_NEAREST)
                    mask[seg_resized > 0.5] = 255

        mask_out = masks_dir / f"{img_path.stem}.png"
        cv2.imwrite(str(mask_out), mask)
        num_dynamic_pixels = int(np.sum(mask > 0))
        pct = (num_dynamic_pixels / (h * w)) * 100
        print(f"  Processed {img_path.name} -> {pct:.2f}% dynamic area masked")

    print(f"[OK] Masks written to {masks_dir}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Generate dynamic object masks using YOLO segmentation")
    parser.add_argument("--scene", type=str, required=True, help="Path to scene output directory")
    parser.add_argument("--model", type=str, default=None, help="Path to YOLO segmentation weights")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold")
    args = parser.parse_args()

    success = generate_masks(args.scene, args.model, args.conf)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
