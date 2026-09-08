# SIH26158 Project Setup

This document outlines how to set up the SIH26158 3D reconstruction pipeline. The repository is hardware-agnostic but configurations can be tuned for different profiles (e.g., RTX 4050 6GB, RTX 4090 24GB, or Cloud GPU).

## 1. Environment Requirements

Our verified working `sugar` environment uses:
- **Python**: 3.9.25
- **PyTorch**: 2.4.1+cu121
- **CUDA**: 12.1

### Windows / Linux Setup (Conda)
```bash
conda create -n sugar python=3.9.25
conda activate sugar

# Install PyTorch
pip install torch==2.4.1+cu121 torchvision==0.19.1+cu121 torchaudio==2.4.1+cu121 --index-url https://download.pytorch.org/whl/cu121

# Install requirements
pip install -r requirements.txt
```

## 2. Third-Party Repositories
Large third-party repositories are excluded from this Git repository to save space. We preserve local modifications via patch files.

Clone the following repositories into the `third_party/` directory:

```bash
mkdir third_party
cd third_party

# VGGT
git clone https://github.com/facebookresearch/vggt.git
cd vggt
git apply ../../patches/vggt.patch
cd ..

# Gaussian Splatting
git clone https://github.com/graphdeco-inria/gaussian-splatting
cd gaussian-splatting
git apply ../../patches/gaussian-splatting.patch
cd ..

# gsplat
git clone https://github.com/nerfstudio-project/gsplat.git
cd gsplat
git apply ../../patches/gsplat_src.patch
cd ..

# SuGaR
git clone https://github.com/Anttwo/SuGaR.git sugar
cd sugar
git apply ../../patches/SuGaR.patch
cd ../..
```
*Note: Any untracked custom scripts we added to these repositories can be found in `scripts/utilities/`.*

## 3. Models
- `yolov8s-seg.pt` (tracked via Git LFS in `models/`).
- VGGT checkpoints are automatically downloaded from HuggingFace/PyTorch Hub on first run.

## 4. Verification

Run the basic pipeline test (smoke test):
```bash
python run_mesh_pipeline.py --video data/sample/drone_test.MP4 --srt data/sample/drone_test.SRT --frames 12
```
