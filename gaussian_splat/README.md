# Isolated Gaussian Splatting Experiment

This directory contains the isolated 3D Gaussian Splatting pipeline evaluated on the NVIDIA GeForce RTX 4090.
It is decoupled from the primary metric mesh pipeline and uses the dedicated `gsplat310` Conda environment.

## Environment Setup

- Conda environment: `gsplat310` (Python 3.10)
- PyTorch: `2.4.1+cu121`
- CUDA core: `gsplat 1.5.2+pt24cu121` (official prebuilt Windows CUDA rasterizer)
- Structure-from-Motion: COLMAP 3.9.1 with CUDA acceleration

To activate:
```powershell
conda activate gsplat310
```

## Workflow

### 1. COLMAP SfM Reconstruction (Automatic)
Runs CUDA-accelerated feature extraction, sequential matching, and bundle adjustment on drone frames:
```powershell
& "gaussian_splat\colmap\COLMAP-3.9.1-windows-cuda\colmap.bat" automatic_reconstructor --workspace_path gaussian_splat\data\drone_demo --image_path gaussian_splat\data\drone_demo\images --data_type video --single_camera 1 --sparse 1 --dense 0 --use_gpu 1
```

### 2. Image Undistortion
Undistorts images to clean PINHOLE models:
```powershell
& "gaussian_splat\colmap\COLMAP-3.9.1-windows-cuda\colmap.bat" image_undistorter --image_path gaussian_splat\data\drone_demo\images --input_path gaussian_splat\data\drone_demo\sparse\0 --output_path gaussian_splat\data\drone_demo\undistorted --output_type COLMAP
```

### 3. Gaussian Splatting Training
Trains 3D Gaussians using `gsplat` with densification and adaptive pruning on the RTX 4090:
```powershell
python gaussian_splat\train_drone_gs.py --data_dir gaussian_splat\data\drone_demo\undistorted --out_dir outputs\gaussian_demo --iterations 1500 --downscale 2
```

### 4. Interactive 3D Visualization
Launches the interactive WebGL Viser viewer:
```powershell
python gaussian_splat\view_gaussian.py --ply outputs\gaussian_demo\point_cloud.ply --port 8080
```
Open `http://localhost:8080` in your web browser.

## Outputs

- `outputs/gaussian_demo/point_cloud.ply`: Standard 3DGS PLY point cloud model.
- `outputs/gaussian_demo/checkpoint.pt`: PyTorch weights and scene configuration.
- `outputs/gaussian_demo/renders/`: Per-view high-resolution renders and ground-truth comparisons.
- `outputs/gaussian_demo/training_report.json`: Metrics (PSNR, training time, Gaussian count).
