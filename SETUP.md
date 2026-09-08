# SIH26158 Project Setup & Hardware Profiles

This document provides setup instructions for the SIH26158 3D reconstruction and metric mesh pipeline. The codebase is designed to be hardware-agnostic, with configuration profiles ranging from entry-level edge/laptop GPUs to high-performance workstations and cloud instances.

---

## 1. Environment & Supported Configurations

### Tested Baseline Configuration (Verified)
The current verified working baseline configuration:
- **Operating System**: Windows 11 (Linux Ubuntu 22.04+ compatible)
- **Hardware Profile**: NVIDIA RTX 4050 Laptop GPU (6 GB VRAM)
- **Python**: 3.9.25
- **PyTorch**: 2.4.1+cu121
- **CUDA Toolkit**: 12.1
- **Key Packages**: Open3D 0.19.0, Ultralytics 8.3.264, HuggingFace Hub, SciPy, NumPy

### Hardware Scaling Profiles
The pipeline parameters scale according to available GPU memory:

| Profile | Target Hardware | Typical VRAM | Recommended Settings |
| :--- | :--- | :--- | :--- |
| **Development Profile** | RTX 4050 / 3060 / 4060 | 6 GB – 8 GB | `--frames 8-12`, fp16/bf16 mixed precision, TSDF voxel size 0.04m |
| **High-Performance Profile** | RTX 4090 / RTX 3090 / A5000 | 16 GB – 24 GB | `--frames 24-48+`, full dense depth, TSDF voxel size 0.015m – 0.02m |
| **Cloud / Server Profile** | A100 / H100 / L40S | 40 GB – 80 GB | Massive sequence reconstruction, high-resolution mesh extraction, batch processing |

---

## 2. Installation Steps

### Step 2.1: Python Environment Setup
Using Conda (recommended):

```bash
conda create -n sugar python=3.9.25 -y
conda activate sugar

# Install PyTorch with CUDA 12.1
pip install torch==2.4.1+cu121 torchvision==0.19.1+cu121 torchaudio==2.4.1+cu121 --index-url https://download.pytorch.org/whl/cu121

# Install core pipeline dependencies
pip install -r requirements.txt
```

---

## 3. Third-Party Repositories & Patches

Large third-party repositories are excluded from the main repository tree to avoid bloat and ensure portability. Upstream repositories are checked out at specific tested commit hashes and patched with our project adaptations.

Clone each vendor repository into `third_party/`, checkout the pinned commit, and apply the corresponding patch:

```bash
# Create third_party directory
mkdir -p third_party

# 1. VGGT (Visual Geometry Grounded Transformer)
git clone https://github.com/facebookresearch/vggt.git third_party/vggt
git -C third_party/vggt checkout a288dd0f14786c93483e45524328726ab7b1b4ce
git -C third_party/vggt apply ../../patches/vggt.patch

# 2. SuGaR (Surface-Aligned Gaussian Splatting)
git clone --recursive https://github.com/Anttwo/SuGaR.git third_party/sugar
git -C third_party/sugar checkout 7c10c4ae4a267dece512f5c7f40ed212a0a2ab44
git -C third_party/sugar apply ../../patches/SuGaR.patch

# 3. Gaussian Splatting (Original Inria Implementation)
git clone --recursive https://github.com/graphdeco-inria/gaussian-splatting third_party/gaussian_splatting
git -C third_party/gaussian_splatting checkout 54c035f7834b564019656c3e3fcc3646292f727d
git -C third_party/gaussian_splatting apply ../../patches/gaussian-splatting.patch

# 4. gsplat (Nerfstudio Rasterization Core)
git clone https://github.com/nerfstudio-project/gsplat.git third_party/gsplat
git -C third_party/gsplat checkout 507f26e118afb78ef0224ad5e0d0701f1b973853
git -C third_party/gsplat apply ../../patches/gsplat_src.patch
```

> **Note**: Custom evaluation and utility tools developed for these packages are located in `scripts/utilities/` and `scripts/testing/`.

---

## 4. Model Assets & Weights

1. **YOLOv8 Segmentation Model**:
   - `models/yolov8s-seg.pt` is tracked directly via Git LFS. Run `git lfs pull` after cloning if the binary pointer file was not automatically fetched.
2. **VGGT Foundational Checkpoint**:
   - VGGT weights are retrieved automatically on first inference via Hugging Face model hub cache (`facebook/vggt-1b`).

---

## 5. Verification & Testing

### Verify Imports and Bindings
To verify that all pipeline modules and third-party bindings resolve properly:
```bash
python scripts/testing/verify_pipeline_imports.py
```

### End-to-End Pipeline Dry Run / Smoke Test
Run the end-to-end pipeline on the provided sample drone sequence:
```bash
python run_mesh_pipeline.py --video data/sample/drone_test.MP4 --srt data/sample/drone_test.SRT --frames 8
```
