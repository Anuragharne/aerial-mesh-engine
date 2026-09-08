# ANTIGRAVITY STATE CHECKPOINT

**Date/Time:** 2026-09-06T16:10:01+05:30
**Goal:** Make the project fully resumable by documenting the current state of the implementation, dependencies, and known issues.

## 1. File Modifications

| File Path | Status | Reason / Explanation |
| :--- | :--- | :--- |
| `vggt/demo_colmap.py` | Modified | Replaced the buggy `pycolmap` integration with a custom `write_colmap_txt` exporter to avoid API breaks and segfaults. Commented out `lightglue` imports since we are not running bundle adjustment (BA). |
| `vggt/vggt/dependency/projection.py` | Modified | Replaced Python 3.10 syntax (`np.ndarray \| None`) with `Optional[np.ndarray]` to fix a `TypeError` in Python 3.9. |
| `vggt/export_colmap_txt.py` | Created | A standalone exporter that manually formats the raw VGGT tensors into COLMAP `cameras.txt`, `images.txt`, and `points3D.txt` files, entirely bypassing the `pycolmap` library. |
| `vggt/vggt/dependency/np_to_pycolmap.py` | Modified & Reverted | Briefly modified to fix an `id` vs `image_id` API change in `pycolmap`, but reverted after deciding to downgrade/remove `pycolmap` due to further crashes. |

## 2. Plan Progress

**Completed Steps:**
- **Step 1:** Pre-process Raw Telemetry & Geometry.
- **Step 2:** Validate Output Formats.
- **Step 3 (Partial):** Run VGGT Geometry Estimation (We successfully ran inference on a 2-frame batch and exported the COLMAP `.txt` format).

**Currently In Progress:**
- **Step 4:** VGGT Quality Gate / Inspecting Raw Geometry (Need to verify the exported `.txt` files actually contain valid geometry).

## 3. Running Processes
**None.** All terminal processes, python processes, and inference jobs have completed successfully. The final successful task was `task-348` (VGGT inference on 2 frames) which exited with code `0`.

## 4. Executed Commands
* `pip install pycolmap`, `huggingface_hub`, `einops`, `safetensors`
* `pip install pycolmap==0.6.1` (attempted downgrade)
* `mkdir outputs\vggt_test_2frames\images -Force; (Get-ChildItem outputs\vggt_test\images\*.png | Select-Object -First 2) | Copy-Item -Destination outputs\vggt_test_2frames\images\`
* `$env:PYTHONUNBUFFERED="1"; C:\Users\anura\miniconda3\envs\sugar\python.exe vggt/demo_colmap.py --scene_dir outputs/vggt_test_2frames`

## 5. Errors, Warnings, and Issues Encountered
* **Dependency Errors:** Missing `pycolmap`, `huggingface_hub`, `einops`, `safetensors`, and `lightglue`. (Resolved by installing dependencies and skipping `lightglue` as we don't need BA).
* **Python Compatibility:** `TypeError` on `\| None` syntax. (Resolved by using `typing.Optional`).
* **PyCOLMAP API Instability:** `AttributeError: 'pycolmap._core.Image' object attribute 'cam_from_world' is read-only`. (Resolved by bypassing PyCOLMAP entirely and writing text files directly).
* **PyCOLMAP Segfaults:** `KiUserExceptionDispatcher` / `_seh_filter_exe` segfaults when running `pycolmap==0.6.1` with `numpy 2.0.2`. (Resolved by bypassing PyCOLMAP).
* **VRAM / Memory Thrashing (OOM):** The RTX 4050 6GB struggled to run the 8-frame batch jointly. It took over 18 minutes (likely due to paging to system RAM). **Resolution:** Testing was scaled back to a 2-frame batch, which completed in ~20 seconds.

## 6. Environment State
* **OS:** Windows
* **GPU:** NVIDIA RTX 4050 6GB (Driver: 581.80, CUDA: 13.0)
* **Conda Environment:** `sugar`
* **Python:** 3.9.x
* **PyTorch:** 2.3.1 (with `torchvision 0.18.1`)
* **Numpy:** 2.0.2

## 7. VGGT Input/Output Paths
* **Inputs:** `outputs/vggt_test_2frames/images/*.png`
* **Outputs:** `outputs/vggt_test_2frames/sparse/`
* **Output Format:** COLMAP-compatible text format (`cameras.txt`, `images.txt`, `points3D.txt`). (Not `.bin`!).

## 8. Gaussian Splatting (gsplat) Status
* **Installed:** No.
* **Compatibility Verified:** No.
* **Training Executed:** No.

## 9. Current Outputs and Logs
* The 5GB VGGT-1B model is fully downloaded and cached at `~/.cache/huggingface/hub/models--facebook--VGGT-1B`.
* Output sparse geometry resides at `C:\Users\anura\Desktop\SIH_3D_Pipeline\outputs\vggt_test_2frames\sparse`.

## 10. Summary: What works, what's broken, what's missing
* **Working:** Extraction, Masking, VGGT model loading, VGGT inference on small batches (2 frames), custom COLMAP `.txt` exporting.
* **Broken / Deprecated:** Direct `pycolmap` package usage for reconstruction saving on this Windows environment. The legacy `run_colmap.py` script.
* **Incomplete:** `gsplat` installation, Gaussian Splatting execution, Metric Alignment (GPS/Telemetry matching), and the Web Viewer integration.

---
**Status:** Pipeline execution paused per user instruction. Ready to resume at Step 4.
