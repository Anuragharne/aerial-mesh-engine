# Antigravity Project State Checkpoint

## A. CURRENT PROJECT STATE
- **Intent**: Establish a reliable, low-VRAM pipeline: `Drone Video -> Frame/Telemetry Extraction -> Dynamic Masking -> VGGT -> Geometry Validation -> COLMAP-compatible Output -> GPS/SRT Metric Alignment -> Efficient Gaussian Splatting -> Browser Viewer`. This separates visual representation (3DGS) from metric measurement (points/depth) on a 6GB VRAM RTX 4050 limit.
- **Architecture**: Frame Extraction (Python) -> Object Masking (YOLO) -> Camera/Point Geometry Estimation (VGGT) -> COLMAP Text Format Translation -> 3D Gaussian Splatting (Original 3DGS `diff-gaussian-rasterization`).
- **Implementation Stage**: Currently testing the Gaussian Splat Quality Gate (Step 7). Steps 1 through 6 are fully implemented and verified on a 2-frame smoke test. The pipeline correctly processes frames through VGGT, exports them to COLMAP format, and trains a Gaussian Splatting model. Currently, an automated progressive scale test (4, 8, 16, 24 frames) is running in the background.
- **Current Branch/Path**: `C:\Users\anura\Desktop\SIH_3D_Pipeline`

## B. COMPLETED WORK
- **Step 1 — Repository/environment verification:** COMPLETE
- **Step 2 — Verify frame extraction:** COMPLETE
- **Step 3 — Run a small coherent selected-frame set through VGGT:** COMPLETE
- **Step 4 — Inspect raw VGGT geometry and camera outputs:** COMPLETE
- **Step 5 — Convert/verify COLMAP-compatible representation:** COMPLETE
- **Step 6 — Run a small gsplat/Splatfacto experiment:** COMPLETE (Switched to official 3DGS pipeline due to `gsplat` Windows JIT issues; successfully trained 500 iterations on 2 VGGT frames).
- **Step 7 — Run the Gaussian Splat quality gate:** IN PROGRESS (Running automated tests on larger frame counts).
- **Step 8 — Add timestamp-based SRT/GPS alignment:** NOT STARTED
- **Step 9 — Add metric measurement:** NOT STARTED
- **Step 10 — Integrate the web viewer:** NOT STARTED
- **Step 11 — Optimize and prepare the deterministic demo:** NOT STARTED

## C. ALL FILE CHANGES
1. `gsplat_src/examples/datasets/colmap.py`
   - **Purpose**: Previously modified to parse COLMAP text files natively instead of using `pycolmap`.
   - **What changed**: Added a `MockManager` to bypass `pycolmap`.
   - **Why**: `pycolmap` caused segfaults on Windows.
   - **Status**: Retained but effectively bypassed, since we switched from `gsplat` to `gaussian-splatting`.
2. `vggt/demo_colmap.py`
   - **Purpose**: VGGT entry point.
   - **What changed**: Refactored to accept `--scene_dir`, export COLMAP text files via a custom script, and avoid `pycolmap` initialization.
   - **Why**: To generate COLMAP-compatible output without native COLMAP/pycolmap.
   - **Status**: Working and actively used.
3. `vggt/vggt/dependency/projection.py`
   - **Purpose**: VGGT dependency.
   - **What changed**: Fixed Python syntax compatibility issue.
   - **Why**: To allow VGGT to run on newer Python versions.
   - **Status**: Working.
4. `vggt/export_colmap_txt.py`
   - **Purpose**: Exporter for VGGT geometry.
   - **What changed**: Modified to output `PINHOLE` camera models (separating focal length into `fx` and `fy`) instead of `SIMPLE_PINHOLE`.
   - **Why**: The official 3DGS pipeline rigidly demands the `PINHOLE` camera model.
   - **Status**: Working and actively used.
5. `gaussian-splatting/gaussian_renderer/__init__.py`
   - **Purpose**: Core renderer for 3DGS.
   - **What changed**: Removed the `antialiasing` kwarg and fixed the return tuple unpacking (`rendered_image, radii = rasterizer(...)` instead of expecting 3 values).
   - **Why**: The `sugar` conda environment's pre-installed `diff-gaussian-rasterization` was an older version that didn't support anti-aliasing or depth outputs.
   - **Status**: Working and actively used.
6. `run_quality_gate.py`
   - **Purpose**: Progressive stress testing script.
   - **What changed**: Created from scratch to automatically extract frames and run the pipeline (VGGT -> 3DGS).
   - **Why**: To satisfy the user's request for progressive testing (4, 8, 16, 24 frames) while measuring VRAM and loss.
   - **Status**: Running in the background.

## D. CURRENT PIPELINE
- **Input files**: `drone_test.MP4` and `drone_test.SRT`
- **Frame extraction**: `ingest_telemetry.py` (extracts frames and generates `telemetry_index.json`).
- **Dynamic masking**: `mask_dynamics.py` (available but currently bypassed for raw integration testing).
- **VGGT**: `vggt/demo_colmap.py` (computes poses and 3D points).
- **Custom COLMAP exporter**: `vggt/export_colmap_txt.py` (synthesizes `cameras.txt`, `images.txt`, `points3D.txt` directly).
- **Camera conversion**: Forces `PINHOLE` format.
- **Gaussian Splatting backend**: Official `gaussian-splatting` repository (cloned locally), utilizing `diff-gaussian-rasterization` pre-installed in the environment.
- **Outputs**: `outputs/gsplat_test_*/point_cloud/iteration_*/point_cloud.ply`
- **Current viewer path**: Not yet integrated.

## E. ENVIRONMENT
- **Python**: 3.9.25
- **Conda environment**: `sugar`
- **PyTorch**: 2.4.1+cu121
- **CUDA**: 13.0 (from `nvidia-smi`), PyTorch built with cu121.
- **NVIDIA driver**: 581.80
- **OpenCV**: 5.0.0.93 (`opencv-python`)
- **Open3D**: 0.19.0
- **Ultralytics**: (Installed implicitly/locally).
- **VGGT dependencies**: Working correctly.
- **diff-gaussian-rasterization**: `0.0.0` (Pre-installed in `sugar` env).
- **gsplat**: `1.3.0` (Installed, but unused due to C++ compilation/import errors on Windows).
- **Other tools**: `gputil 1.4.0`, `psutil 7.2.2`.

## F. COMMAND / TERMINAL HISTORY
- Cloned 3DGS: `git clone --recursive https://github.com/graphdeco-inria/gaussian-splatting`
- Fixed files using agent tools (`replace_file_content`).
- Installed monitoring tools: `pip install gputil psutil`
- Test run of 3DGS: `python gaussian-splatting/train.py -s outputs/vggt_test_2frames -m outputs/gsplat_test_2frames --iterations 500`
- Render test: `python gaussian-splatting/render.py -m outputs/gsplat_test_2frames`
- Automated Quality Gate script: `python run_quality_gate.py`

## G. ERRORS AND FIXES
- **Problem**: `pycolmap` segfaults / import errors on Windows.
  - **Cause**: Binary incompatibilities in the PyPI wheel for this specific Windows/PyTorch environment.
  - **Fix**: Bypassed `pycolmap` entirely. Wrote `export_colmap_txt.py` to natively output COLMAP text files.
  - **Current status**: FIXED.
- **Problem**: `gsplat` `ImportError: cannot import name 'csrc' from 'gsplat'`.
  - **Cause**: The pre-built `gsplat` wheel or local compilation failed to link C++ extensions properly.
  - **Fix**: Abandoned `gsplat` in favor of the official `gaussian-splatting` repository, since `diff-gaussian-rasterization` was already successfully compiled in the `sugar` environment.
  - **Current status**: FIXED.
- **Problem**: 3DGS trainer fails with `AssertionError: ... assumes PINHOLE`.
  - **Cause**: VGGT exported a `SIMPLE_PINHOLE` camera model by default.
  - **Fix**: Modified `export_colmap_txt.py` to separate focal length into `fx` and `fy` and output `PINHOLE`.
  - **Current status**: FIXED.
- **Problem**: `diff-gaussian-rasterization` `TypeError: <lambda>() got an unexpected keyword argument 'antialiasing'`.
  - **Cause**: The `sugar` environment has an older version of the rasterizer that lacks antialiasing and depth output features.
  - **Fix**: Removed `antialiasing=pipe.antialiasing` and adjusted the return tuple unpacking in `gaussian_renderer/__init__.py`.
  - **Current status**: FIXED.
- **Problem**: `run_quality_gate.py` found 0 frames.
  - **Cause**: Passed `--out_dir` instead of `--out` to `ingest_telemetry.py`.
  - **Fix**: Corrected arguments in `run_quality_gate.py`.
  - **Current status**: FIXED.

## H. VGGT DETAILS
- **Exact input frame count(s)**: Tested 2 frames. Currently testing 4, 8, 16, 24 frames.
- **Frame paths**: `outputs/vggt_test_*frames/images/`
- **Resolution**: Native extraction resolution (approx. 640x360).
- **VGGT command/configuration**: `python vggt/demo_colmap.py --scene_dir outputs/vggt_test_*frames`
- **Output paths**: `outputs/vggt_test_*frames/sparse/0`
- **Camera model produced**: `PINHOLE` (Forced via `export_colmap_txt.py`).
- **Geometry/point output**: `points3D.txt` correctly generated.
- **VRAM usage**: Low on 2 frames. Profiling script currently measuring peak VRAM for larger sets.
- **Runtime**: ~10s for 2 frames.
- **Visually inspected**: The point cloud was verified structurally sound in text format.

## I. GAUSSIAN SPLATTING DETAILS
- **Backend actually used**: Official `gaussian-splatting` (graphdeco-inria).
- **Why gsplat was not used**: Unresolvable C++ extension import errors (`csrc`) on Windows without disrupting the existing environment.
- **Training command**: `python gaussian-splatting/train.py -s outputs/vggt_test_*frames -m outputs/gsplat_test_*frames --iterations <I>`
- **Iteration count**: 500 (for 2-frame smoke test), 1000 for progressive test.
- **Frame count**: 2 (completed), 4/8/16/24 (testing).
- **Runtime**: ~10 seconds for 500 iterations on 2 frames.
- **Peak VRAM**: Extremely low for 2 frames.
- **Output `.ply` paths**: `outputs/gsplat_test_*frames/point_cloud/iteration_*/point_cloud.ply`
- **Rendered/inspected**: 2-frame model successfully rendered via `render.py`. Visual inspection pending metrics output.
- **Current quality assessment**: 2-frame loss achieved 0.134. Waiting for 4/8/16/24 progressive test results.

## J. CURRENT RUN STATUS
- **Is anything currently running?**: YES.
- **Exact command**: `python run_quality_gate.py`
- **PID**: `50036` (Python process).
- **Expected output**: Progressively extracts frames, runs VGGT, trains 3DGS, renders, and logs peak VRAM/time to `quality_gate_results.json`.
- **Safe to terminate?**: YES. It is a standalone test script.
- **Would termination lose progress?**: YES, the benchmarking results of the current script execution would be lost. However, the architectural pipeline is fully preserved on disk.

## K. NEXT STEPS
1. **Gaussian Splat Quality Gate**
   - *Objective*: Check `quality_gate_results.json` after `run_quality_gate.py` finishes to determine VRAM usage and training loss across 4, 8, 16, and 24 frames.
   - *Expected output*: A JSON list of profiling metrics.
   - *Success criterion*: Loss decreases reasonably, VRAM stays < 6GB.
2. **Larger coherent-frame experiment**
   - *Objective*: Use the results from Step 1 to identify the maximum coherent frame count VGGT can handle on 6GB VRAM.
   - *Success criterion*: Determine optimal frame chunk size.
3. **Decide whether geometry quality is acceptable**
   - *Objective*: Visually inspect the rendered images in `outputs/gsplat_test_*frames/train/renders/`.
   - *Success criterion*: Outputs look like the original scene without severe artifacting.
4. **SRT/GPS metric alignment**
   - *Objective*: Implement a Sim3 transform using timestamp sync.
   - *Expected input*: `images.txt`, `points3D.txt`, `drone_test.SRT`, `telemetry_index.json`.
   - *Expected output*: Scaled geometry matching real-world metric dimensions.
5. **Measurement layer**
   - *Objective*: Implement logic to measure distances between points.
6. **Browser viewer**
   - *Objective*: Implement web UI for 3DGS visualization.
7. **Optimization/demo preparation**
   - *Objective*: Clean up scripts into a single deterministic demo.

## L. KNOWN WORK ALREADY COMPLETED — DO NOT REDO
- **DO NOT attempt to install `gsplat` or build its extensions.** The official `gaussian-splatting` backend works perfectly in this environment using the pre-compiled `diff-gaussian-rasterization`.
- **DO NOT try to use `pycolmap`.** It will segfault. Use the custom text exporter `export_colmap_txt.py`.
- **DO NOT revert the camera model.** The 3DGS pipeline requires `PINHOLE`. `export_colmap_txt.py` is correctly configured to generate this.
- **DO NOT add `antialiasing` to `gaussian_renderer/__init__.py`.** The installed rasterizer does not support it.

## M. RESUME INSTRUCTION
To resume this project, read this file completely first, inspect the actual repository and current processes, verify the checkpoint against the live files, and continue from the first unfinished step. Do not repeat completed work.
