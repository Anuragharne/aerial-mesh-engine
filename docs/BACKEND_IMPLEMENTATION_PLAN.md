# Backend Implementation Plan

## Objective

Build a FastAPI-based local backend that takes a drone video, runs the VGGT → metric-transformed Poisson reconstruction pipeline, and serves the resulting mesh + measurement API over HTTP.

---

## Current Reusable Modules

| Module | File | Status | Action |
|--------|------|--------|--------|
| VGGT inference | [vggt_inference.py](file:///c:/Users/anura/Desktop/SIH_3D_Pipeline/src/pipeline/vggt_inference.py) | **CONFIRMED EXISTING** — complete, tested on 4090 | TO MODIFY: extract `run_vggt_dense()` as importable function; remove `main()` CLI dependency |
| Depth fusion (TSDF + Poisson) | [depth_fusion.py](file:///c:/Users/anura/Desktop/SIH_3D_Pipeline/src/pipeline/depth_fusion.py) | **CONFIRMED EXISTING** — both methods implemented | TO MODIFY: enhance Poisson with data-driven filtering, add metric point transformation, add BPA fallback |
| Metric alignment | [metric_alignment.py](file:///c:/Users/anura/Desktop/SIH_3D_Pipeline/src/pipeline/metric_alignment.py) | **CONFIRMED EXISTING** — Sim3 solver + GPS→ENU | TO MODIFY: expose `solve_sim3()` + transform functions as importable APIs; add world-point transformation |
| Quality gate | [vggt_quality_gate.py](file:///c:/Users/anura/Desktop/SIH_3D_Pipeline/src/pipeline/vggt_quality_gate.py) | **CONFIRMED EXISTING** — comprehensive validation | REUSE AS-IS |
| Mesh evaluation | [depth_fusion.py#evaluate_mesh()](file:///c:/Users/anura/Desktop/SIH_3D_Pipeline/src/pipeline/depth_fusion.py#L240-L279) | **CONFIRMED EXISTING** | TO MODIFY: add connected component check, geometry collapse detection, two-layer quality gate |
| Dynamic masking | [mask_dynamics.py](file:///c:/Users/anura/Desktop/SIH_3D_Pipeline/src/pipeline/mask_dynamics.py) | **CONFIRMED EXISTING** — YOLOv8 seg | REUSE AS-IS (optional step) |
| Frame extraction | [ingest_telemetry.py](file:///c:/Users/anura/Desktop/SIH_3D_Pipeline/src/pipeline/ingest_telemetry.py) | **EMPTY FILE (0 bytes)** | **TO CREATE** — critical missing piece |
| COLMAP text export | [export_colmap_txt.py](file:///c:/Users/anura/Desktop/SIH_3D_Pipeline/scripts/utilities/export_colmap_txt.py) | CONFIRMED EXISTING | NOT NEEDED for mesh pipeline (was for GS path) |
| Pipeline orchestrator | [run_mesh_pipeline.py](file:///c:/Users/anura/Desktop/SIH_3D_Pipeline/run_mesh_pipeline.py) | **CONFIRMED EXISTING** | Reference only — logic moves into backend service layer |
| VGGT model (third_party) | [third_party/vggt/](file:///c:/Users/anura/Desktop/SIH_3D_Pipeline/third_party/vggt/) | **CONFIRMED EXISTING** — patched, tested | REUSE AS-IS |
| YOLO weights | [models/yolov8s-seg.pt](file:///c:/Users/anura/Desktop/SIH_3D_Pipeline/models/yolov8s-seg.pt) | **CONFIRMED EXISTING** — 23MB | REUSE AS-IS |
| Sample data | [data/sample/](file:///c:/Users/anura/Desktop/SIH_3D_Pipeline/data/sample/) | **CONFIRMED EXISTING** — drone_test.MP4 (62MB) + drone_test.SRT (44KB) | REUSE AS-IS |

---

## CRITICAL: `ingest_telemetry.py` is Empty

The frame extraction + SRT parsing module is referenced throughout the pipeline but **the file is 0 bytes**. This was likely lost during the repository reorganization (Approach B).

This is the **#1 priority creation task**. It must:
1. Parse the SRT file for GPS coordinates + timestamps
2. Extract frames from MP4 at specified FPS using OpenCV/ffmpeg
3. Match frames to SRT records by timestamp
4. Output `images/` directory + `telemetry_index.json`

Evidence that this module previously worked: `telemetry_index.json` files exist in multiple output directories with the correct structure (frame names → GPS data).

If Approach B recovery does not yield a working version, write from scratch rather than forcing a broken historical file.

---

## Reconstruction Architecture

```
FastAPI (main.py)
    │
    ├── POST /api/jobs            → JobManager.create_job(config)
    ├── POST /api/jobs/{id}/start  → JobManager.start_job() → background thread
    ├── GET  /api/jobs/{id}/status → JobManager.get_status()
    ├── GET  /api/jobs/{id}/result → JobManager.get_result()
    ├── GET  /api/jobs/{id}/mesh   → serve file from outputs/
    └── POST /api/jobs/{id}/measure/* → MeasurementService.*
              │
              ▼
    PipelineOrchestrator.run(job_id, config)
        │
        ├── Step 1: FrameExtractor.extract(video, srt, num_frames)
        │       → outputs/{job_id}/images/ + telemetry_index.json
        │
        ├── Step 2: DynamicMasker.mask(scene_dir)  [optional, skipped in demo]
        │       → outputs/{job_id}/masks/
        │
        ├── Step 3: VGGTInference.run(scene_dir)
        │       → outputs/{job_id}/vggt_raw/ (depth, conf, extrinsic, intrinsic, world_points)
        │
        ├── Step 4: QualityGate.validate(scene_dir)
        │       → pass/fail + vggt_quality_report.json
        │
        ├── Step 5: MetricAlignment.align(scene_dir, telemetry)
        │       → Sim3 parameters (scale, R, t) + alignment_report.json
        │       → outputs/{job_id}/vggt_raw/metric_extrinsic.npy
        │
        ├── Step 6: MetricPointTransform.transform(world_points, sim3)
        │       → metric world points (ENU, metres) for Poisson input
        │       ⚠️ THIS IS THE CRITICAL NEW STEP — see "Metric Transformation" below
        │
        ├── Step 7: MeshReconstructor.build(metric_points, method="poisson")
        │       → outputs/{job_id}/metric_mesh.ply
        │       → if Poisson fails quality gate: automatic BPA fallback
        │
        └── Step 8: MeshQualityGate.validate(mesh)
                → pass/fail + mesh_quality_report.json
```

---

## Selected Mesh Method

**Primary**: VGGT World Points → Metric Transform → Poisson Surface Reconstruction (see MESH_METHOD_DECISION.md)

**Fallback**: Same cleaned/metric point cloud → Ball Pivoting Algorithm (BPA)

**NOT a fallback**: TSDF — rejected because our project history demonstrated visually poor results. Retained as historical experiment code only.

---

## CRITICAL: Metric Transformation of World Points

> **The Sim3 metric transformation MUST be applied to the VGGT world-point coordinates BEFORE mesh reconstruction.**

### Why This Matters

The existing `metric_alignment.py` solves Sim3 and saves `metric_extrinsic.npy`. However, changing only camera extrinsics does NOT make the world points metric. The mesh is built from `world_points.npy`, so the world points themselves must carry the metric transformation.

### Transformation Flow

```
VGGT world_points (S, H, W, 3)  — arbitrary VGGT coordinates
        │
        ▼
Sim3: target = scale * R @ source + t  (solved in metric_alignment.py)
        │
        ▼
metric_world_points = scale * (R @ pts.T).T + t  — local ENU (metres)
        │
        ▼
Confidence filtering + outlier removal + normals
        │
        ▼
Poisson / BPA reconstruction
        │
        ▼
metric_mesh.ply — vertices in ENU metres
```

### What Each Sim3 Component Provides
- **scale**: converts VGGT arbitrary depth units → metres
- **R** (3×3 rotation): aligns VGGT coordinate axes → ENU (East=X, North=Y, Up=Z)
- **t** (3 translation): shifts origin → local GPS reference point in ENU

### If Metric Alignment is Skipped (no SRT)
- World points remain in VGGT arbitrary coordinates
- Mesh is saved as `raw_mesh.ply` (NOT `metric_mesh.ply`)
- Job result reports `is_metric = false`, `coordinate_frame = "vggt_arbitrary"`, `unit = "arbitrary"`
- Measurements must NOT be presented as metres by the frontend

### Artifacts Receiving the Transform
| Artifact | Transformed? | Notes |
|----------|-------------|-------|
| `world_points.npy` | YES — transformed before mesh reconstruction | Core requirement |
| `metric_extrinsic.npy` | Already exists | Camera poses for reference |
| `metric_mesh.ply` | Inherits from transformed points | Output mesh in ENU metres |
| `depth_map.npy` | NOT transformed | Raw per-frame depth values retained |
| `depth_conf.npy` | NOT transformed | Confidence is unitless |

---

## Confidence Filtering

**Strategy** (per MESH_METHOD_DECISION.md):
1. Remove non-finite points
2. Analyze `depth_conf` distribution, select threshold at P20 (retaining top 80%)
3. Adaptive fallback to P10 if point count is too low
4. Voxel downsample (adaptive based on scene extent)
5. Statistical outlier removal (SOR) — nb_neighbors=20, std_ratio=2.0
6. Normal estimation + orientation
7. Log full distribution + selected threshold + per-step point counts

**REMOVED**: Centroid-distance cutoff (dangerous for large aerial scenes where valid geometry can be far from the centroid).

---

## Measurement Engine

**Approach**: Pure metric geometry, no AI model needed.

**Canonical system**: All measurements operate on ENU coordinates (X=East, Y=North, Z=Up, metres).

| Measurement | Method | Computed on |
|------------|--------|-------------|
| **Distance** | Euclidean 3D: `sqrt(sum((a-b)^2))` | ENU coordinates |
| **Height** | Vertical difference: `abs(top.Z - base.Z)` | ENU Z-axis (Up) |
| **Area** | Planar polygon: project onto best-fit plane, shoelace formula | ENU coordinates |

**Area type distinction**:
- **Demo**: Planar area (projection onto best-fit plane)
- **Future**: Irregular surface area (summing triangle areas on mesh surface)

**Why no AI for measurement**: The user clicks points on a metric mesh. The 3D coordinates are already metric. Euclidean geometry suffices. An AI model (e.g., for automatic building footprint detection) would be a FUTURE enhancement, not a demo requirement.

---

## Dynamic Masking

**Status**: CONFIRMED EXISTING — [mask_dynamics.py](file:///c:/Users/anura/Desktop/SIH_3D_Pipeline/src/pipeline/mask_dynamics.py)

**Demo**: SKIP by default (set `skip_masking=True`)
**Quality mode**: ENABLED (integrate masks into depth filtering before Poisson)

---

## FastAPI Application Structure

```
backend/
    app/
        main.py              # FastAPI app, CORS, startup
        api/
            routes.py         # All HTTP endpoints
        services/
            job_manager.py    # Job lifecycle, background thread execution
            pipeline.py       # PipelineOrchestrator
            measurement.py    # Distance, height, area calculations
        schemas/
            models.py         # Pydantic request/response models
```

**Key design decisions**:
- Jobs run in `threading.Thread` (not multiprocessing — simpler, shares GPU context)
- Job state stored in a `dict` (no database — local demo only)
- Output files stored in `outputs/{job_id}/`
- CORS configured for `http://localhost:5173`

---

## Job Manager

**State machine**: `created → running → completed | failed`

**Background execution**: Pipeline runs in a daemon thread. Status is updated atomically via a shared dict with a threading lock.

**Progress reporting**: Each pipeline step updates `job.stage` and `job.progress` (0.0-1.0). The status endpoint reads the current state.

**Error handling**: If any step fails, the job status becomes `"failed"` with the error message and the stage where it failed.

---

## Demo Mode vs Quality Mode

| Parameter | Demo Mode | Quality Mode |
|-----------|-----------|--------------|
| Frames | 8 | 16-24 |
| Skip masking | Yes | No |
| Skip alignment | No (if SRT available) | No |
| Mesh method | Poisson (depth=8) | Poisson (depth=9) |
| Confidence percentile | P20 | P15 |
| Expected runtime | 3-5 minutes (ESTIMATE) | 8-15 minutes (ESTIMATE) |

**Pre-generated demo fallback**: If a pre-generated `metric_mesh.ply` exists in `outputs/demo/`, the frontend can load it directly via `GET /api/demo/mesh` without running the pipeline.

---

## Local Packaging

### Minimal Backend Requirements (PINNED)

```
# Core API
fastapi==0.141.1
uvicorn==0.52.4
python-multipart==0.0.32

# ML/Reconstruction
torch==2.3.1+cu121
torchvision==0.18.1+cu121
numpy==1.26.4
scipy==1.15.3
open3d==0.19.0

# GPS
pyproj==3.5.0

# Image processing
opencv-python==4.9.0.80
pillow==11.3.0

# VGGT dependencies (via third_party/vggt)
einops==0.8.2
safetensors==0.8.0
huggingface_hub==1.29.0

# Dynamic masking (optional)
ultralytics==8.3.264

# Utilities
tqdm==4.70.0
```

> **NOTE**: These are pinned to the versions verified in the existing `sugar` conda environment. Do NOT use `>=` ranges — the project has already experienced dependency breakage from version mismatches.

### Python Version
- Python 3.9.25 (tested in `sugar` conda environment)

### PyTorch/CUDA
- PyTorch 2.3.1+cu121 (verified working)
- torchvision 0.18.1+cu121
- CUDA toolkit 12.1
- NVIDIA driver ≥ 581.80
- VGGT requires ~5GB VRAM for 8-12 frame batch

### VGGT Model Acquisition
- Automatic download from HuggingFace on first run (~5GB)
- Cached at `~/.cache/huggingface/hub/models--facebook--VGGT-1B`
- No manual download needed (requires one-time internet)

### Local Startup

**Development**:
```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Demo / Judging** (without --reload to avoid process restarts during GPU jobs):
```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

> `--reload` is for development only. The demo/judging launch MUST NOT use `--reload`, as it causes unnecessary process restarts that can interfere with long-running GPU inference jobs.

---

## Validation Plan

### Automated Tests
1. **Import test**: `python scripts/testing/verify_pipeline_imports.py`
2. **API smoke test**: `curl http://localhost:8000/docs` (FastAPI auto-docs)
3. **Pipeline smoke test**: Upload demo video, start job, poll until complete
4. **Measurement validation**: Known-distance points → verify output

### Manual Verification
1. Upload `drone_test.MP4` + `drone_test.SRT`
2. Start pipeline in demo mode
3. Confirm each stage completes
4. **VISUALLY INSPECT THE MESH** in the frontend viewer or MeshLab
5. Verify mesh resembles the actual scene (terrain, structures)
6. Test all three measurement endpoints
7. Verify is_metric flag is correct

---

## Failure Handling

| Failure | Backend Behaviour | Frontend Display |
|---------|-----------------|-----------------|
| Video upload fails | 400 error | "Invalid video file" |
| VGGT OOM | Job failed, stage = vggt_inference | "GPU memory error — try fewer frames" |
| Quality gate fails | Job failed, stage = quality_gate | "Geometry validation failed" |
| Poisson fails quality gate | Automatic BPA fallback attempted | Show fallback message |
| BPA also fails quality gate | Job failed, stage = mesh_reconstruction | "Mesh reconstruction failed — load demo mesh" |
| No SRT file | Skip alignment, `is_metric=false` | Disable metric measurements OR label as arbitrary |
| Alignment residual > 10m | Warn but continue | "Metric accuracy may be limited" |

---

## Implementation Order

### MOST IMPORTANT EXECUTION PRIORITY

> The first meaningful milestone is NOT "FastAPI starts." It is: **"The pipeline produces a recognizable mesh from the demo dataset."**

### Recommended Sequence

1. **Recover or write `ingest_telemetry.py`** — frame extraction + SRT — **2 hours**
2. **Run VGGT on extracted frames** — validate end-to-end data path — **included in test time**
3. **Implement metric world-point transformation** — apply Sim3 to world_points — **1 hour**
4. **Implement corrected Poisson reconstruction** — data-driven filtering — **1 hour**
5. **Implement BPA fallback** — `create_from_point_cloud_ball_pivoting()` — **30 min**
6. **Implement mesh quality gate (two layers)** — automated + log — **45 min**
7. **VISUAL INSPECTION** — run on demo video, inspect result — **30 min**
8. **Implement measurement service** — distance, height, area in ENU — **45 min**
9. **FastAPI app + routes** — all endpoints from API_CONTRACT.md — **1.5 hours**
10. **Job manager** — background thread + state — **1 hour**
11. **End-to-end backend test** — upload → process → mesh → measure — **1 hour**

**Estimated total: ~10 hours** (tight for one day — see simplification below)

### P0 Simplification (if time is tight)

- Wrap existing `run_mesh_pipeline.py` as a subprocess call instead of rewriting as importable services — saves ~2 hours
- Skip viewer mesh decimation — serve full PLY directly
- Skip area measurement — implement distance + height only

### P1 — Strongly useful

- Viewer mesh decimation endpoint
- Demo mode pre-generation script
- Better error messages
- Enhanced mesh quality gate with completeness diagnostic

### P2 — Future/Research

- Streaming reconstruction interface (`StreamingReconstructionService`)
- WebSocket progress streaming
- Database-backed job persistence
- Surface area measurement (irregular terrain)
- Automatic AI-based feature detection for measurement

---

## OUT OF SCOPE

- Cloud deployment
- User authentication
- Job persistence across restarts
- Multi-user support
- Automatic hyperparameter tuning
- Online/streaming reconstruction
- Gaussian Splatting integration
- Point cloud viewer (mesh only)
- Texture mapping
- TSDF as primary or fallback (historical experiment only)

---

## Future Streaming Architecture (RESEARCH / VERSION 2)

```python
class ReconstructionService(ABC):
    @abstractmethod
    async def reconstruct(self, scene_dir: str, config: dict) -> str:
        """Returns path to output mesh."""
        pass

class BatchReconstructionService(ReconstructionService):  # NOW
    async def reconstruct(self, scene_dir, config):
        # Run VGGT → metric transform → Poisson as batch
        pass

class StreamingReconstructionService(ReconstructionService):  # FUTURE/v2
    async def reconstruct(self, scene_dir, config):
        # Incremental frame processing
        # Progressive mesh updates
        pass
```

This is labelled RESEARCH / VERSION 2. The current system is NOT streaming. Do NOT add WebSocket work to the P0 path. HTTP polling is sufficient for the first demo.
