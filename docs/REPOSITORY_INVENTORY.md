# Repository Inventory

| File / Folder | Purpose | Owner: Our code / Third-party / Data / Generated | Currently Used? | Dependencies | Safe to Move? | Safe to Rename? | Final Location | Action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ingest_telemetry.py` | Extracts frames and telemetry from video | Our code | Yes | `cv2`, `ffmpeg` | Yes (if `run_mesh_pipeline.py` updated) | Yes | `src/pipeline/ingest_telemetry.py` | Move and update paths |
| `mask_dynamics.py` | Dynamic masking with YOLO | Our code | Yes (optional) | `yolov8s-seg.pt`, `cv2` | Yes | Yes | `src/pipeline/mask_dynamics.py` | Move and update paths |
| `vggt_inference.py` | Runs VGGT for dense depth | Our code | Yes | `vggt` module | Yes (must add `sys.path` patch) | Yes | `src/pipeline/vggt_inference.py` | Move, patch sys.path, update paths |
| `vggt_quality_gate.py` | Validates VGGT output | Our code | Yes | None | Yes | Yes | `src/pipeline/vggt_quality_gate.py` | Move and update paths |
| `metric_alignment.py` | Aligns GPS/SRT to geometry | Our code | Yes | `pyproj` | Yes | Yes | `src/pipeline/metric_alignment.py` | Move and update paths |
| `depth_fusion.py` | TSDF fusion and Poisson mesh | Our code | Yes | `open3d` | Yes | Yes | `src/pipeline/depth_fusion.py` | Move and update paths |
| `run_mesh_pipeline.py` | Primary execution script | Our code | Yes | Other scripts | Yes | No | `run_mesh_pipeline.py` (root) | Keep at root, update paths |
| `run_quality_gate.py` | Legacy/historical testing code | Our code | No | Old pipeline | Yes | No | `scripts/testing/run_quality_gate.py` | Move to testing scripts |
| `run_colmap.py` | Legacy fallback code | Our code | No | COLMAP | Yes | No | `scripts/testing/run_colmap.py` | Move to testing scripts |
| `requirements_locked.txt` | Environment definition | Our code | Yes | None | Yes | No | `requirements.txt` (root) | Rename and keep at root |
| `ANTIGRAVITY_PROJECT_STATE.md` | Historical project state | Our code | No | None | Yes | No | `docs/PROJECT_STATE.md` | Move and rename |
| `ANTIGRAVITY_STATE_CHECKPOINT.md` | Historical checkpoint | Our code | No | None | Yes | No | `docs/STATE_CHECKPOINT.md` | Move and rename |
| `drone_test.MP4` | Sample input video | Data | Yes | None | Yes | No | `data/sample/drone_test.MP4` | Move, track via LFS |
| `drone_test.SRT` | Sample input telemetry | Data | Yes | None | Yes | No | `data/sample/drone_test.SRT` | Move |
| `yolov8s-seg.pt` | YOLO weights | Third-party model | Yes | None | Yes | No | `models/yolov8s-seg.pt` | Move, track via LFS |
| `quality_gate_results.json` | Sample output artifact | Generated | No | None | Yes | No | `outputs/quality_gate_results.json` | Ignore via .gitignore |
| `models/` | Model directory | Data | Yes | None | Yes | No | `models/` | Keep, add `.gitkeep`, track `.pt` in LFS |
| `outputs/` | Generated results | Generated | No | None | Yes | No | `outputs/` | Add `.gitkeep`, ignore contents |
| `vggt/` | VGGT Submodule/Repo | Third-party | Yes | None | Yes | No | `third_party/vggt/` | Move, keep as git module or clone via setup. Preserve patches. |
| `gaussian-splatting/` | 3DGS Repo | Third-party | No (secondary) | None | Yes | No | `third_party/gaussian_splatting/` | Move, preserve patches/modifications. |
| `gsplat_src/` | gsplat Repo | Third-party | No (secondary) | None | Yes | No | `third_party/gsplat/` | Move, preserve patches/modifications. |
| `SuGaR/` | SuGaR Repo | Third-party | No (future) | None | Yes | No | `third_party/sugar/` | Move, preserve patches/modifications. |
