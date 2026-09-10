# API Contract

## Overview

This document defines the HTTP API contract between the frontend (React/Vite, port 5173) and the backend (Python/FastAPI, port 8000). All communication is over `http://localhost`.

---

## Coordinate System Convention

### Backend Canonical Coordinate System: LOCAL ENU

| Property | Value |
|----------|-------|
| **Backend world frame** | Local ENU (East-North-Up) when GPS-aligned |
| **X** | East |
| **Y** | North |
| **Z** | Up |
| **Units** | Metres (when `is_metric = true`) |
| **Mesh format** | PLY (binary or ASCII), with vertex colors and normals |
| **Mesh coordinate system** | ENU (Z-up) — same as backend canonical |

### Frontend Display Convention

Three.js internally uses Y-up. The frontend applies a display transform (rotation -90° around X-axis) at mesh load time. This is a **visual-only** concern that the backend never sees.

### Measurement Coordinate Flow

```
User clicks on mesh in Three.js viewport (Y-up display space)
        ↓
Frontend applies inverse display transform → ENU coordinates (Z-up)
        ↓
Measurement API receives ENU coordinates
        ↓
Backend computes measurement in ENU metres
```

> **Rule**: The backend NEVER receives Three.js display coordinates. All measurement API calls use backend canonical ENU coordinates. The frontend is responsible for the coordinate transform at the boundary.

### When Metric Alignment is NOT Available

If no SRT/GPS telemetry was provided:
- Mesh coordinates are in VGGT arbitrary units (NOT metres)
- `is_metric = false` on all responses
- `coordinate_frame = "vggt_arbitrary"`
- Measurement values MUST NOT be displayed as metres
- Frontend should disable measurement tools OR clearly label values as "relative/arbitrary units"

---

## `is_metric` Semantics

| Value | Meaning | Frontend Behaviour |
|-------|---------|-------------------|
| `true` | Geometry has been Sim3-aligned to GPS/ENU. Measurements are valid metres. | Display values with "m", "m²" units |
| `false` | Geometry is in VGGT arbitrary coordinates. Measurements have NO physical meaning. | Disable measurement tools OR label as "relative units (not calibrated)" |

> **CRITICAL**: Do NOT display "12.8 m" when `is_metric = false`. The geometry is not metric. Values in arbitrary coordinates must never be presented as metres.

---

## Endpoints

### 1. Create Job (Upload + Configuration)

```
POST /api/jobs
Content-Type: multipart/form-data
```

**Request Body** — all job configuration is set here (immutable after creation):
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `video` | file | Yes | Drone video file (MP4) |
| `srt` | file | No | SRT telemetry file |
| `mode` | string | No | `"demo"` (default) or `"quality"` |
| `frames` | integer | No | Number of frames to extract (default: 8 for demo, 16 for quality) |
| `skip_masking` | boolean | No | Skip YOLO dynamic masking (default: true for demo, false for quality) |
| `mesh_method` | string | No | `"poisson"` (default) |

**Response** (201 Created):
```json
{
  "job_id": "abc123",
  "status": "created",
  "config": {
    "mode": "demo",
    "frames": 8,
    "skip_masking": true,
    "mesh_method": "poisson",
    "has_srt": true
  },
  "created_at": "2026-09-10T10:00:00Z"
}
```

**Errors**:
| Code | Meaning |
|------|---------|
| 400 | Invalid file type or missing video |
| 500 | Server error creating job |

---

### 2. Start Processing

```
POST /api/jobs/{job_id}/start
```

**Request Body**: None — configuration was set at creation time.

**Response** (202 Accepted):
```json
{
  "job_id": "abc123",
  "status": "running",
  "message": "Processing started"
}
```

**Errors**:
| Code | Meaning |
|------|---------|
| 404 | Job not found |
| 409 | Job already running or completed |

---

### 3. Job Status (Polling)

```
GET /api/jobs/{job_id}/status
```

**Response** (200 OK):
```json
{
  "job_id": "abc123",
  "status": "running",
  "stage": "vggt_inference",
  "progress": 0.45,
  "stages": {
    "frame_extraction": {"status": "completed", "duration_sec": 12.3},
    "dynamic_masking": {"status": "skipped"},
    "vggt_inference": {"status": "running", "progress": 0.45},
    "quality_gate": {"status": "pending"},
    "metric_alignment": {"status": "pending"},
    "mesh_reconstruction": {"status": "pending"},
    "mesh_quality_gate": {"status": "pending"}
  },
  "error": null,
  "elapsed_sec": 32.5
}
```

**Status values**: `created` | `running` | `completed` | `failed`

**Stage values**: `pending` | `running` | `completed` | `failed` | `skipped`

**Polling interval**: Frontend should poll every 2 seconds.

**Errors**:
| Code | Meaning |
|------|---------|
| 404 | Job not found |

---

### 4. Job Result (Metadata)

```
GET /api/jobs/{job_id}/result
```

**Response** (200 OK):
```json
{
  "job_id": "abc123",
  "status": "completed",
  "mesh_file": "metric_mesh.ply",
  "mesh_url": "/api/jobs/abc123/mesh",
  "viewer_mesh_url": "/api/jobs/abc123/mesh?detail=viewer",
  "is_metric": true,
  "coordinate_frame": "enu",
  "unit": "meters",
  "mesh_quality": {
    "num_vertices": 125000,
    "num_triangles": 248000,
    "extent_xyz": [85.2, 42.1, 18.7],
    "has_vertex_colors": true,
    "has_vertex_normals": true,
    "appears_valid": true,
    "method_used": "poisson"
  },
  "alignment": {
    "scale": 12.345,
    "residual_mean_m": 0.82,
    "residual_max_m": 1.45,
    "matched_frames": 8,
    "total_frames": 8
  },
  "mode": "demo",
  "total_duration_sec": 145.2
}
```

When `is_metric = false` (no SRT available):
```json
{
  "is_metric": false,
  "coordinate_frame": "vggt_arbitrary",
  "unit": "arbitrary",
  "alignment": null
}
```

**Errors**:
| Code | Meaning |
|------|---------|
| 404 | Job not found |
| 409 | Job not yet completed |

---

### 5. Download Mesh (Full Resolution — for export)

```
GET /api/jobs/{job_id}/mesh
```

**Response**: Full-resolution binary PLY file
- `Content-Type: application/octet-stream`
- `Content-Disposition: attachment; filename="metric_mesh.ply"`

This is the complete reconstruction output, suitable for export and downstream processing.

---

### 5b. Download Mesh (Viewer-Optimized — for browser display)

```
GET /api/jobs/{job_id}/mesh?detail=viewer
```

**Response**: Decimated binary PLY file optimized for browser interaction.
- Vertex count capped at ~200K (configurable)
- Simplified via Open3D `simplify_quadric_decimation()` if full mesh exceeds limit
- Full-resolution mesh is always preserved in `outputs/` — this is non-destructive

If the full mesh is already under the limit, the same file is served.

---

### 6. Load Pre-existing Mesh (Demo Fallback)

```
GET /api/demo/mesh
```

**Response**: Binary PLY file of the pre-generated demo mesh (if available).

**Errors**:
| Code | Meaning |
|------|---------|
| 404 | No demo mesh available |

---

### 7. List Completed Jobs

```
GET /api/jobs
```

**Response** (200 OK):
```json
{
  "jobs": [
    {
      "job_id": "abc123",
      "status": "completed",
      "created_at": "2026-09-10T10:00:00Z",
      "mode": "demo",
      "is_metric": true,
      "mesh_url": "/api/jobs/abc123/mesh"
    }
  ]
}
```

---

## Measurement Endpoints

All measurement endpoints accept 3D points in **backend canonical ENU coordinates** (Z-up, metres when metric). The frontend is responsible for transforming from Three.js Y-up display space to ENU Z-up before calling these endpoints.

### 8. Measure Distance

```
POST /api/jobs/{job_id}/measure/distance
Content-Type: application/json
```

**Request** (coordinates in ENU):
```json
{
  "point_a": [10.5, -4.1, 3.2],
  "point_b": [15.8, -6.3, 3.0]
}
```

**Response** (200 OK):
```json
{
  "value": 6.42,
  "unit": "m",
  "is_metric": true,
  "point_a": [10.5, -4.1, 3.2],
  "point_b": [15.8, -6.3, 3.0]
}
```

When `is_metric = false`:
```json
{
  "value": 6.42,
  "unit": "arbitrary",
  "is_metric": false
}
```

**Errors**:
| Code | Meaning |
|------|---------|
| 400 | Invalid coordinates or job not metric (if strict mode) |
| 404 | Job not found |
| 409 | Job not yet completed |

---

### 9. Measure Height

```
POST /api/jobs/{job_id}/measure/height
Content-Type: application/json
```

**Request** (coordinates in ENU):
```json
{
  "top_point": [12.0, -3.0, 15.5],
  "base_point": [12.0, -3.0, 3.2]
}
```

**Response** (200 OK):
```json
{
  "value": 12.3,
  "unit": "m",
  "is_metric": true,
  "top_point": [12.0, -3.0, 15.5],
  "base_point": [12.0, -3.0, 3.2],
  "axis": "Z (Up in ENU)"
}
```

> **Implementation**: Height = absolute difference along ENU Z-axis (Up).

---

### 10. Measure Area (Planar)

```
POST /api/jobs/{job_id}/measure/area
Content-Type: application/json
```

**Request** (coordinates in ENU):
```json
{
  "vertices": [
    [10.0, -4.0, 3.0],
    [20.0, -4.0, 3.0],
    [20.0, -14.0, 3.0],
    [10.0, -14.0, 3.0]
  ]
}
```

**Response** (200 OK):
```json
{
  "value": 100.0,
  "unit": "m²",
  "is_metric": true,
  "num_vertices": 4,
  "area_type": "planar"
}
```

> **Implementation**: Polygon area via projection onto best-fit plane + shoelace formula. Minimum 3 vertices required. This computes **planar area** (not surface area over irregular terrain — that is FUTURE work).

---

## Progress Reporting

### Approach: HTTP Polling

**Why polling, not WebSocket**:
- Simpler to implement (one-day constraint)
- No additional library dependency
- Status changes infrequently (every few seconds)
- Frontend polls `GET /api/jobs/{job_id}/status` every 2 seconds

### Future (v2): WebSocket
- `ws://localhost:8000/ws/jobs/{job_id}` for real-time log streaming
- NOT part of P0 one-day demo

---

## Job Lifecycle

```
created → running → completed
                  → failed
```

- Jobs persist in memory for the session lifetime (no database)
- Jobs are NOT persisted across backend restarts
- Completed jobs keep their output files in `outputs/{job_id}/`
- A completed job's mesh can be re-loaded without re-running reconstruction

---

## Failed Jobs

```json
{
  "job_id": "abc123",
  "status": "failed",
  "stage": "mesh_reconstruction",
  "error": "Poisson reconstruction failed quality gate. BPA fallback also failed. Load demo mesh instead.",
  "elapsed_sec": 145.2
}
```

- The frontend should display the error message and the stage where failure occurred
- The user can retry by creating a new job with different parameters (fewer frames, demo mode)
- The user can load a pre-generated demo mesh instead

---

## CORS Configuration

Backend must set:
```
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: Content-Type
```

---

## Frontend/Backend Dependency Matrix

| Frontend Feature | Backend Endpoint | Dependency |
|-----------------|-----------------|------------|
| Upload video + configure | `POST /api/jobs` | File upload |
| Start processing | `POST /api/jobs/{id}/start` | Job created |
| Show progress | `GET /api/jobs/{id}/status` | Job running |
| Display mesh (browser) | `GET /api/jobs/{id}/mesh?detail=viewer` | Job completed |
| Load demo mesh | `GET /api/demo/mesh` | Pre-generated mesh file |
| Measure distance | `POST /api/jobs/{id}/measure/distance` | Job completed, ENU coords |
| Measure height | `POST /api/jobs/{id}/measure/height` | Job completed, ENU coords |
| Measure area | `POST /api/jobs/{id}/measure/area` | Job completed, ENU coords |
| List past jobs | `GET /api/jobs` | Any |
| Export full mesh | `GET /api/jobs/{id}/mesh` | Job completed (browser download) |

---

## Artifact Files on Disk

For each job, the backend stores:

```
outputs/{job_id}/
    input/              # Uploaded video + SRT
    images/             # Extracted frames
    masks/              # Dynamic masks (if generated)
    vggt_raw/           # VGGT outputs (depth, conf, extrinsic, world_points, etc.)
    metric_mesh.ply     # Full-resolution mesh (or raw_mesh.ply if no alignment)
    viewer_mesh.ply     # Decimated mesh for browser (if simplified)
    mesh_quality_report.json
    alignment_report.json
    vggt_quality_report.json
    telemetry_index.json
    filtering_log.json  # Confidence filtering details
```

The mesh endpoint serves the `.ply` file directly from this directory.
The full-resolution mesh is ALWAYS preserved — decimation for the viewer is non-destructive.
