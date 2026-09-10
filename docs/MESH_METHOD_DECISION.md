# Mesh Method Decision

## Objective

Select ONE primary and ONE fallback mesh reconstruction method for the demo prototype, based on evidence from our actual project history, existing code, and realistic one-day implementation constraints.

---

## Candidate Methods Evaluated

### Candidate A: VGGT Dense World Points → Poisson Surface Reconstruction

**Input**: `world_points.npy` (S, H, W, 3) from VGGT + `depth_conf.npy` for filtering + `images_rgb.npy` for vertex colors

**Pipeline**: Confidence filtering → outlier removal → voxel downsampling → **metric Sim3 transformation** → normal estimation → Poisson reconstruction → density-based trimming

**Evidence from project**:
- `poisson_reconstruction()` already exists in [depth_fusion.py](file:///c:/Users/anura/Desktop/SIH_3D_Pipeline/src/pipeline/depth_fusion.py#L171-L237)
- Implementation includes: confidence threshold, finite-check, outlier removal (SOR), voxel downsample, normal estimation, orient normals, Poisson with density-based trimming
- VGGT produces dense world points at 518×518 per frame — 12 frames = ~3.2M raw points
- After filtering and downsampling, expect 200K-1M points for reconstruction
- Poisson reconstruction is numerically stable and handles noise well
- Produces watertight meshes (can be trimmed via density threshold)

**Expected geometry quality**: Selected as the primary candidate based on method suitability and existing implementation, but **final geometry quality remains TO BE VALIDATED** on the actual demo dataset. Poisson is theoretically well-suited for aerial scenes with limited angular coverage and predicted depth noise. This assessment must be confirmed empirically.

**Runtime**: Estimated ~30 seconds for point cloud assembly + ~60-120 seconds for Poisson (depth=9). Total: 2-3 minutes on CPU. **These are estimates, not measured values on the target machine.**

**GPU requirement**: None for Poisson itself. VGGT inference requires GPU (done separately).

**Implementation complexity**: LOW — code already exists and is structurally correct. Requires enhancement for data-driven filtering and metric transformation of world points.

**Sensitivity to noisy depth**: MEDIUM — Poisson is inherently smoothing. Combined with confidence filtering + SOR, noise tolerance is reasonable.

**Aerial terrain behavior**: Expected GOOD — Poisson handles ground-plane geometry well. TO BE VALIDATED.

**Vegetation/structure behavior**: Expected MEDIUM — vegetation will be smoothed into blobs, which is acceptable for a demo. TO BE VALIDATED.

**Sparse viewpoint behavior**: Expected GOOD — Poisson fills gaps, unlike TSDF which requires sufficient view coverage. TO BE VALIDATED.

**Known failure modes**:
- Normal orientation failure on thin structures → causes inverted surfaces
- Overly aggressive smoothing at high Poisson depth → loss of fine detail
- Density-based trimming threshold sensitivity → too aggressive = holes; too loose = phantom geometry

**Validation plan**: Automated quality gate (see below) + MANDATORY visual inspection by a human.

---

### Candidate B: VGGT Depth Maps → TSDF Volumetric Fusion → Marching Cubes

**Input**: `depth_map.npy` (S, H, W) + `extrinsic.npy` (S, 3, 4) + `intrinsic.npy` (S, 3, 3) + `images_rgb.npy`

**Evidence from project**:
- `tsdf_fusion()` already exists in [depth_fusion.py](file:///c:/Users/anura/Desktop/SIH_3D_Pipeline/src/pipeline/depth_fusion.py#L51-L168)
- **CRITICAL**: The project history explicitly states "VGGT → TSDF: technically generated meshes, corrected tensor shape issues, resulting geometry was visually poor"
- High sensitivity to voxel size, depth accuracy, view coverage, and pose-depth consistency
- Sparse viewpoint behavior is POOR — TSDF needs multiple overlapping views

**Verdict**: **REJECTED AS FALLBACK** — Our own project history demonstrated visually poor results with this method. It is not a sensible automatic fallback for the production/demo pipeline. Retained ONLY as a historical experiment reference. Code remains in the repository but is not part of the demo reconstruction path.

---

### Candidate C: COLMAP SfM → Dense MVS → Poisson/TSDF

**Verdict**: **REJECTED** — `pycolmap` crashes on Windows, COLMAP binary not available, would consume the entire one-day budget on environment setup.

---

### Candidate D: Gaussian Splatting → Mesh Extraction

**Verdict**: **REJECTED** — 30k iteration run was "visually unsatisfactory." Does not produce a standard mesh directly. Retained as research track only.

---

### Candidate E: Ball Pivoting Algorithm (BPA)

**Input**: Same as Candidate A (filtered, metric-transformed point cloud with normals)

**Pipeline**: Same cleaned point cloud used by Poisson → Open3D `create_from_point_cloud_ball_pivoting()`

**Characteristics**:
- Simpler algorithm than Poisson
- Does NOT fill gaps — preserves only where points exist
- Preserves sharp edges better than Poisson
- Leaves holes where point density is insufficient
- More sensitive to normal estimation quality
- Produces non-watertight meshes
- Available in Open3D (already a dependency)

**Expected geometry quality**: TO BE VALIDATED. May produce a more faithful (if incomplete) representation of the actual measured surface, since it does not hallucinate geometry in unobserved regions.

**Verdict**: **SELECTED AS FALLBACK** — If Poisson produces degenerate results (overly smoothed, inverted normals, collapsed geometry), BPA on the same cleaned/metric point cloud provides a structurally different reconstruction approach using the identical input data.

---

## Decision

### PRIMARY METHOD: Candidate A — VGGT World Points → Metric Transform → Poisson Surface Reconstruction

**Exact reasons**:
1. **Poisson is theoretically MORE ROBUST than TSDF for our specific scenario** — aerial drone footage with limited angular coverage and predicted depth
2. **Code already exists** and is structurally sound in `depth_fusion.py`
3. **Gap-filling** — Poisson naturally fills small holes, which matters for aerial scenes with sparse viewpoints
4. **Noise tolerance** — Poisson's smoothing property is an advantage with VGGT's predicted (not measured) depth
5. **No voxel size tuning** — unlike TSDF, Poisson doesn't require voxel size calibration relative to scene scale
6. **Our project history explicitly documented TSDF producing "visually poor" results**

### FALLBACK METHOD: Candidate E — Ball Pivoting Algorithm (BPA)

**Exact reasons**:
1. Uses the SAME cleaned/metric-transformed point cloud as Poisson — no additional data preparation
2. Structurally different algorithm — if Poisson fails, BPA may succeed for different reasons
3. Available in Open3D — no new dependency
4. TSDF was rejected as fallback because our project already demonstrated it produces poor results

**When to use fallback**: If Poisson reconstruction produces a degenerate mesh (< 500 vertices, spatial extent < 0.1m, > 50% degenerate triangles, or geometry collapse detected)

### IF BOTH FAIL

If both Poisson and BPA fail the mesh quality gate:
1. Preserve all intermediate artifacts (filtered point cloud, raw VGGT outputs)
2. Mark the job as `failed` with a clear error
3. Allow loading a pre-generated verified demo mesh via `GET /api/demo/mesh`
4. Do NOT pretend the fallback guarantees a good result

---

## CRITICAL: Metric Transformation of World Points

> **The Sim3 metric transformation MUST be applied to the VGGT world-point coordinates BEFORE mesh reconstruction.**

The existing `metric_alignment.py` solves Sim3 mapping VGGT camera positions → ENU. The same transformation must be applied to the point cloud that enters Poisson/BPA.

### Transformation Flow

```
VGGT world_points (S, H, W, 3) — arbitrary VGGT coordinates
        │
        ▼
Sim3 solved: target = scale * R @ source + t
        │
        ▼
metric_world_points = scale * R @ vggt_world_points + t — local ENU metres
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

**What the transformation provides**:
- `scale`: converts VGGT arbitrary units → metres
- `R` (3×3): aligns VGGT axes → ENU (East, North, Up)
- `t` (3): translates origin → GPS reference point in local ENU

**What happens if metric alignment is skipped** (no SRT file):
- World points remain in VGGT arbitrary coordinates
- Mesh is saved as `raw_mesh.ply` (NOT `metric_mesh.ply`)
- `is_metric = false` on the job result
- Measurements are NOT presented as metres

Changing only camera extrinsics does NOT make the world points metric. The mesh is built from world points, so the world points themselves must carry the metric transformation.

### Coordinate System

| Frame | X | Y | Z | Units |
|-------|---|---|---|-------|
| **VGGT reconstruction** | arbitrary | arbitrary | arbitrary | arbitrary |
| **Backend canonical (ENU)** | East | North | Up | metres |
| **Frontend display (Three.js)** | right | up | forward | metres (visual only) |

---

## Critical Improvements Over Previous Implementation

The existing `poisson_reconstruction()` needs these enhancements:

### 1. Metric Transformation of Input Points
- **Current**: Operates on raw VGGT world points
- **Required**: Apply solved Sim3 to world points BEFORE reconstruction
- **Implementation**: `metric_pts = scale * (R @ pts.T).T + t`

### 2. Data-Driven Confidence Threshold
- **Current**: Fixed `conf_threshold=1.0`
- **Required**: Analyze `depth_conf` distribution, select threshold at percentile that retains 60-80% of points
- **Method**: `threshold = np.percentile(depth_conf[depth_conf > 0], 20)` (keep top 80%)

### 3. Adaptive Voxel Downsample Size
- **Current**: Fixed `voxel_downsample=0.01`
- **Required**: Compute from point cloud extent: `voxel_size = scene_extent / 500`
- **Rationale**: A 100m scene needs 0.2m voxels; a 10m scene needs 0.02m voxels

### 4. Normal Estimation Radius
- **Current**: Fixed `radius=0.05, max_nn=30`
- **Required**: Scale radius with point density: `radius = voxel_size * 5`

### 5. Poisson Depth Parameter
- **Current**: Fixed `depth=9`
- **Required**: For aerial scenes, `depth=8` may suffice and run faster. Test both.

### 6. Density Trimming
- **Current**: Trims at 5th percentile
- **Required**: May need 10th percentile for aerial scenes to remove phantom bottom/side surfaces

---

## Mesh Quality Gate

### Layer A — Automated Structural Validation

All checks are necessary conditions but **NOT sufficient for visual quality**.

| Check | Criterion | Action on Failure |
|-------|-----------|-------------------|
| NaN/Inf vertices | 0 | Abort — data corruption |
| Vertex count | > 1,000 | Try BPA fallback |
| Triangle count | > 2,000 | Try BPA fallback |
| Spatial extent (diagonal) | > 1.0m (metric) or > 0.01 (arbitrary) | Check coordinate system |
| Degenerate triangles | < 5% of total | Run mesh cleanup |
| Connected components | < 20 | Remove small components (keep largest) |
| Has vertex normals | true | Recompute normals |
| Has vertex colors | true | Warning only |
| Geometry collapse | Bounding box aspect ratio < 100:1 | Try BPA fallback |

> **Automated thresholds do NOT prove visual quality.** A mesh with 10,000 vertices and valid normals can still be completely unrecognizable.

### Layer B — Visual Acceptance (REQUIRED before demo)

A human MUST verify:
1. Open the mesh in the frontend viewer (or Open3D visualizer)
2. Confirm the mesh **resembles** the drone video's terrain/structures
3. Confirm terrain coherence (ground plane is approximately flat, not spiked)
4. Confirm building/structure coherence (if present in video)
5. Confirm no massive floating artifacts dominate the scene
6. Confirm no severe holes in the primary scene region
7. Confirm no geometry collapse (all faces coplanar, or single spike)
8. Confirm physically plausible scale (if metric alignment was applied)

> **CRITICAL: "Mesh file created" is NOT success.** The previous project repeatedly produced technically valid but visually terrible meshes. Visual acceptance is mandatory before any demo.

### Completeness Diagnostic (Basic — PLANNED)

For the demo, a basic coverage diagnostic:
- **Point density coverage**: After filtering, what fraction of the 518×518 grid per frame retained valid points?
- **Frame contribution**: How many frames contributed > 100 points to the final point cloud?
- **Spatial coverage**: Divide mesh bounding box into an 8×8 grid, count cells with > 10 vertices

Advanced completeness metrics (visible-region coverage, reference-region detection) are FUTURE work.

---

## Confidence / Filtering Strategy

### Confidence Source
- VGGT `depth_conf.npy` (S, H, W) — per-pixel confidence from the depth head

### Filtering Pipeline (ordered)

1. **Remove non-finite points**: `np.all(np.isfinite(pts), axis=1)`
2. **Confidence threshold**: Data-driven from `depth_conf` distribution
   - Compute histogram of confidence values
   - Select threshold at P20 (20th percentile) — retains top 80% of points
   - If fewer than 50K points remain, lower threshold to P10
3. **Voxel downsampling**: Adaptive based on scene extent (`voxel_size = extent / 500`)
4. **Statistical outlier removal (SOR)**: `nb_neighbors=20, std_ratio=2.0`
5. **Normal estimation**: KDTree hybrid with adaptive radius (`radius = voxel_size * 5`)
6. **Normal orientation**: `orient_normals_consistent_tangent_plane(k=15)`

> **REMOVED**: The previous plan included "remove points > 3× median distance from centroid." This is **dangerous for large aerial scenes** because valid terrain and structures can legitimately be far from the point cloud centroid. SOR (step 4) handles local outliers without this risk.

### Threshold Selection Log
Every run MUST log:
- Raw point count before filtering
- Confidence distribution (min, P10, P25, P50, P75, P90, max)
- Selected threshold and percentile
- Points retained after each filtering step
- Final point count entering Poisson

This log enables diagnosing poor mesh quality after the fact.
