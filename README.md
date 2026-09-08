# SIH26158 Aerial Mesh Engine

This repository contains the source code for the SIH26158 3D Pipeline. It is designed to take raw drone video and telemetry (SRT) and produce a metric 3D mesh and interactive measurement viewer.

## Project Objective
The goal is to provide rapid, hardware-agnostic, drone-based 3D reconstruction and measurement capabilities.

## Architecture

Our primary, stable pipeline focuses on direct depth and metric point fusion:

1. **Frame Extraction**: Extract frames from drone MP4.
2. **VGGT Inference**: Extract dense depth maps, confidence, and camera poses.
3. **Metric Alignment**: Map VGGT trajectory to GPS/telemetry to obtain metric scale and orientation *before* fusion.
4. **TSDF Fusion**: Filter and fuse metric depth into a volumetric representation.
5. **Meshing**: Extract a colored metric mesh using Open3D TSDF integration and Poisson surface reconstruction.
6. **Viewer**: Interactive web-based visualization and measurement using Viser.

### Secondary Pipeline (Research)
- **Gaussian Splatting (3DGS)**: Used for high-fidelity novel view synthesis.
- **SuGaR / gsplat**: Future enhancements for faster splat-to-mesh conversion.

## Hardware Profiles
The repository is designed to be configurable across hardware profiles:
- **Development**: RTX 4050 6GB (Prototype: ~12 frames)
- **High-Performance**: RTX 4090 24GB (Higher frame counts, denser TSDF)
- **Cloud**: Configurable NVIDIA GPU

*Note: The current demo configuration defaults to 12 frames for rapid prototyping on edge devices, but this is not a universal maximum.*

## Documentation
- `SETUP.md`: Instructions for environment creation and third-party dependencies.
- `docs/ARCHITECTURE.md`: Detailed architecture.
- `docs/EXPERIMENTS.md`: Historical experiments and outputs.
- `docs/REPOSITORY_INVENTORY.md`: File and directory breakdown.

## Execution
To run the primary pipeline:
```bash
python run_mesh_pipeline.py --video data/sample/drone_test.MP4 --srt data/sample/drone_test.SRT --frames 12
```
