# Frontend Implementation Plan

## Objective

Build a single-page React application that uploads drone video, displays reconstruction progress, renders the resulting 3D mesh interactively, and provides metric measurement tools (distance, height, area).

---

## Scope

| Feature | In Scope | Status |
|---------|----------|--------|
| Video upload | Yes | TO CREATE |
| Demo mesh loading | Yes | TO CREATE |
| Pipeline progress display | Yes | TO CREATE |
| 3D mesh viewer (PLY) | Yes | TO CREATE |
| Orbit/pan/zoom/reset | Yes | TO CREATE |
| Distance measurement | Yes | TO CREATE |
| Height measurement | Yes | TO CREATE |
| Area measurement (planar) | Yes | TO CREATE |
| Mesh export (download full PLY) | Yes | TO CREATE |
| Error display | Yes | TO CREATE |
| `is_metric` aware UI | Yes | TO CREATE |
| Authentication | No | OUT OF SCOPE |
| Multiple pages/routing | No | OUT OF SCOPE |
| Settings panel | No | OUT OF SCOPE |
| Dashboard | No | OUT OF SCOPE |
| Mobile-optimized layout | No | OUT OF SCOPE |

---

## UX Design

### Visual Identity
- **Engineering tool aesthetic** — clean, dark theme, minimal decoration
- Colors: Dark gray background (#1a1a2e), accent blue (#0ea5e9), success green (#22c55e), warning amber (#f59e0b)
- Typography: Inter (via Google Fonts) — clean, technical
- No gradients, no glassmorphism — this is a serious analysis tool, not a landing page

### Page Structure

```
┌──────────────────────────────────────────────────────────┐
│  HEADER — "SIH26158 Aerial Mesh Engine" | Status badge   │
├──────────────┬───────────────────────────────────────────┤
│              │                                           │
│  CONTROL     │         3D VIEWPORT                       │
│  PANEL       │         (Three.js)                        │
│  (280px)     │                                           │
│              │                                           │
│  ┌────────┐  │                                           │
│  │Upload  │  │                                           │
│  │or Demo │  │                                           │
│  └────────┘  │                                           │
│              │                                           │
│  ┌────────┐  │                                           │
│  │Start   │  │                                           │
│  │Process │  │                                           │
│  └────────┘  │                                           │
│              │                                           │
│  ┌────────┐  │                                           │
│  │Progress│  │                                           │
│  │Stages  │  │                                           │
│  └────────┘  │                                           │
│              │                                           │
│  ┌────────┐  │                                           │
│  │Measure │  │         ┌──────────────────┐              │
│  │Tools   │  │         │ Measurement      │              │
│  └────────┘  │         │ Result Overlay   │              │
│              │         └──────────────────┘              │
│  ┌────────┐  │                                           │
│  │Export  │  │                                           │
│  └────────┘  │                                           │
│              │                                           │
├──────────────┴───────────────────────────────────────────┤
│  STATUS BAR — coord system | metric flag | vertex count  │
└──────────────────────────────────────────────────────────┘
```

### Interaction Flow

1. **Initial state**: Viewport shows placeholder ("Upload a video or load demo")
2. **Upload**: User selects MP4 + optional SRT, or clicks "Load Demo"
3. **Processing**: Progress bar with stage names + completion checkmarks
4. **Viewing**: Mesh appears in viewport. Orbit/pan/zoom enabled.
5. **Measuring**: User selects measurement mode → clicks points on mesh → result displayed
6. **Export**: Download PLY button

---

## Technology Choices

| Technology | Purpose | Justification |
|-----------|---------|---------------|
| **React** | UI framework | Standard, well-known, component model |
| **Vite** | Build tool | Fast HMR, simple config |
| **Three.js** | 3D rendering | Industry standard WebGL library |
| **@react-three/fiber** | React↔Three.js bridge | Declarative Three.js in React |
| **@react-three/drei** | Three.js helpers | OrbitControls, loaders, etc. |
| **three/examples/jsm/loaders/PLYLoader** | PLY file loading | Built into Three.js |
| **Vanilla CSS** | Styling | Simple, no build dependency |

> **No additional 3D libraries needed.** Three.js + PLYLoader handles everything.
> **Viser is NOT the final viewer.** The production viewer is React + Three.js.

---

## Components

### `App.jsx` — Root layout
- Manages global state: currentJob, meshData, measurementMode, isMetric
- Renders Header, ControlPanel, Viewport, StatusBar

### `Header.jsx` — Top bar
- Project title
- Connection status indicator (backend reachable?)

### `ControlPanel.jsx` — Left sidebar
- Contains all sub-panels in order
- Scrollable if viewport is short

### `UploadPanel.jsx` — File upload section
- File input for MP4 + SRT
- "Load Demo Mesh" button
- Mode selector (Demo / Quality)

### `ProcessingPanel.jsx` — Pipeline progress
- Shows only when a job is running
- Stage list with status icons (pending/running/done/failed)
- Overall progress bar
- Elapsed time
- Cancel button (optional P1)

### `MeasurementPanel.jsx` — Measurement tools
- Shows only when mesh is loaded AND `is_metric = true`
- Three buttons: Distance | Height | Area
- Active mode indicator
- Current measurement result display with proper units ("m", "m²")
- Clear/reset button
- **When `is_metric = false`**: Measurement tools are DISABLED or clearly labelled as "relative units (not calibrated)" — NEVER show "m" or "m²"

### `ExportPanel.jsx` — Export controls
- Download PLY button (full resolution via `/api/jobs/{id}/mesh`)
- Mesh info summary (vertices, triangles, metric flag)

### `Viewport.jsx` — 3D viewer (dominant element)
- Three.js canvas via @react-three/fiber
- Loads PLY mesh as BufferGeometry (viewer-optimized version via `?detail=viewer`)
- OrbitControls (free orbit, pan, zoom)
- Reset camera button
- Mesh rendered with vertex colors + MeshStandardMaterial
- Ambient + directional lighting
- Grid helper (optional, toggleable)

### `MeasurementOverlay.jsx` — In-viewport measurement display
- Renders measurement points as small spheres
- Renders lines between measurement points
- Displays measurement value as HTML overlay positioned near the midpoint
- Polygon visualization for area measurement

### `StatusBar.jsx` — Bottom information bar
- Coordinate system ("ENU (metric)" / "VGGT (arbitrary)")
- Metric flag (green badge if metric, amber warning if not)
- Vertex/triangle count
- Mouse world position (on hover — P1)

---

## Coordinate System Handling

### Backend Canonical System: ENU (Z-up)
The backend serves mesh vertices in ENU coordinates: X=East, Y=North, Z=Up, units=metres.

### Three.js Display System: Y-up
Three.js internally uses Y-up. A display transform is applied at mesh load time.

### Display Transform (Applied at Load Time)

```
ENU (backend)        Three.js (display)
  X (East)     →      X (right)
  Y (North)    →      Z (forward/into screen, negated)
  Z (Up)       →      Y (up)
```

**Implementation**: Rotate mesh geometry -90° around X-axis at load time:
```javascript
geometry.rotateX(-Math.PI / 2);
```

This is a one-time operation applied to the BufferGeometry.

### Measurement Coordinate Transform (CRITICAL)

When the user clicks on the mesh in Three.js:
1. Raycaster returns a point in **Three.js display space** (Y-up)
2. Frontend applies the **inverse display transform** to get **ENU coordinates** (Z-up)
3. **ENU coordinates** are sent to the backend measurement API
4. Backend computes measurement in ENU and returns the result

```javascript
// Inverse display transform: Three.js Y-up → ENU Z-up
function displayToENU(threePoint) {
  return {
    x: threePoint.x,    // East
    y: -threePoint.z,   // North
    z: threePoint.y     // Up
  };
}
```

> **RULE**: The backend NEVER receives Three.js display coordinates. All API calls use ENU coordinates. The frontend is responsible for the transform at the boundary.

---

## `is_metric` Handling

### Frontend Rules

| `is_metric` | Measurement Tools | Unit Labels | UI Indicator |
|-------------|------------------|-------------|--------------|
| `true` | **ENABLED** | "m", "m²" | Green badge: "Metric (ENU)" |
| `false` | **DISABLED** or labelled "relative" | "arb" or no units | Amber warning: "Not calibrated — no GPS data" |

> **CRITICAL**: Do NOT display "12.8 m" when `is_metric = false`. The geometry is in VGGT arbitrary coordinates and has NO physical meaning in metres.

---

## Viewer Architecture

### PLY Loading
1. Fetch PLY from `GET /api/jobs/{job_id}/mesh?detail=viewer` (viewer-optimized) or `GET /api/demo/mesh`
2. Parse with `PLYLoader` from Three.js
3. Create `BufferGeometry` with position, color, normal attributes
4. Apply display transform: `geometry.rotateX(-Math.PI / 2)` (ENU Z-up → Three.js Y-up)
5. Attach to `Mesh` with `MeshStandardMaterial({ vertexColors: true })`

### Camera Controls
- `OrbitControls` from drei — provides orbit, pan, zoom
- No camera restrictions (free movement)
- Reset button: camera returns to initial position that frames the entire mesh

### Initial Camera Position
- Compute mesh bounding box (after display transform)
- Position camera at 1.5× bounding sphere radius, looking at center
- Up vector: Y-up (Three.js convention)

### Mesh Size Handling
- The backend provides a viewer-optimized mesh via `?detail=viewer` (≤200K vertices)
- The full-resolution mesh is available separately for export via `/api/jobs/{id}/mesh`
- If the backend doesn't support decimation yet (P0 simplification), the frontend loads the full mesh directly

---

## Measurement Interaction

### Distance Mode
1. User clicks "Distance" button → mode activates
2. User clicks first point on mesh → raycaster hits mesh, stores 3D point (display coords)
3. User clicks second point → stores second point
4. Frontend applies inverse display transform → ENU coordinates
5. Frontend can compute distance client-side: `Math.sqrt(sum of squared differences)`
6. **Optionally**: send ENU points to `POST /api/jobs/{id}/measure/distance` for server-authoritative result
7. Display: "6.42 m" if is_metric, "6.42 (relative)" if not

### Height Mode
1. User clicks "Height" button → mode activates
2. User clicks top point on mesh → stores point
3. User clicks base point on mesh → stores point
4. Frontend applies inverse display transform → ENU coordinates
5. Height = `abs(top.Z_enu - base.Z_enu)` (vertical difference along ENU Up axis)
6. Shows vertical line + height value

### Area Mode (Planar)
1. User clicks "Area" button → mode activates
2. User clicks vertices to form polygon (minimum 3)
3. Double-click or "Finish" button closes polygon
4. Frontend applies inverse display transform → ENU coordinates
5. Send ENU vertices to `POST /api/jobs/{id}/measure/area`
6. Shows polygon outline + area value
7. Area type: **planar** (projection onto best-fit plane). Future: irregular surface area.

### Raycasting
- Use Three.js `Raycaster` on mouse click
- Intersect with loaded mesh (in display space)
- Extract intersection point in Three.js world coordinates
- Apply inverse display transform before sending to backend

### Client-side vs Server-side Measurement
- **Distance and Height**: Computed client-side (simple Euclidean/vertical math on ENU coords)
- **Area**: Computed server-side (3D polygon projection)
- **`is_metric` flag**: Always comes from backend result metadata — frontend never guesses

---

## Loading / Progress Behaviour

### States
| State | Control Panel | Viewport | Status Bar |
|-------|--------------|----------|------------|
| **Empty** | Upload visible | Placeholder text | "No mesh loaded" |
| **Uploading** | Upload disabled, spinner | Unchanged | "Uploading..." |
| **Processing** | Progress panel visible | Unchanged | "Processing: [stage]" |
| **Ready (metric)** | Measurement tools ENABLED | Mesh rendered | "Mesh loaded: N vertices — Metric (ENU)" |
| **Ready (non-metric)** | Measurement tools DISABLED/labelled | Mesh rendered | "Mesh loaded: N vertices — Not calibrated" |
| **Measuring** | Active tool highlighted | Click-to-measure enabled | "Mode: Distance" |
| **Error** | Error message + retry + "Load Demo" | Unchanged | "Error: [message]" |

### Polling Logic
```javascript
useEffect(() => {
  if (job?.status !== 'running') return;
  const interval = setInterval(async () => {
    const status = await fetch(`/api/jobs/${job.id}/status`).then(r => r.json());
    setJob(status);
    if (status.status === 'completed' || status.status === 'failed') {
      clearInterval(interval);
    }
  }, 2000);
  return () => clearInterval(interval);
}, [job?.status]);
```

---

## Mesh Loading

### From Pipeline Result
1. Wait for `job.status === 'completed'`
2. Read job result metadata: `GET /api/jobs/{id}/result` → get `is_metric`, `coordinate_frame`
3. `fetch('/api/jobs/{id}/mesh?detail=viewer')` — viewer-optimized
4. Parse response as ArrayBuffer
5. Load with `PLYLoader.parse(buffer)`
6. Apply display transform: `geometry.rotateX(-Math.PI / 2)`
7. Set camera to frame mesh
8. Enable measurement tools based on `is_metric` flag

### From Pre-generated Demo
1. `fetch('/api/demo/mesh')`
2. Same parsing pipeline as above
3. Assume `is_metric = true` for pre-generated demo mesh

### From Local File (Bonus)
1. User drags PLY file into viewport
2. Parse locally via PLYLoader
3. No backend needed
4. Set `is_metric = false` — measurements labelled as "relative"

---

## Export

- "Download Full Mesh" button triggers `window.open('/api/jobs/{id}/mesh')` (full resolution, not viewer-optimized)
- Browser handles the download (Content-Disposition header from backend)
- Future: OBJ/GLTF export (P2)

---

## Demo Fallback

If no GPU is available or the pipeline is too slow for live demo:
1. Pre-generate `outputs/demo/metric_mesh.ply` on the 4090 machine
2. Copy to project directory
3. Frontend loads via `GET /api/demo/mesh`
4. Measurement works (same ENU coordinate system, `is_metric = true`)
5. No pipeline execution required

---

## Local Execution

```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

### Proxy Configuration (vite.config.js)
```javascript
export default defineConfig({
  server: {
    proxy: {
      '/api': 'http://localhost:8000'
    }
  }
})
```

This means:
- Frontend fetches `/api/jobs/...` without full URL
- Vite dev server proxies to backend at port 8000
- No CORS issues in development

---

## Implementation Order

### P0 — Required for working demo

1. **Vite + React scaffold** — `npx create-vite` — **15 min**
2. **Install Three.js deps** — `npm install three @react-three/fiber @react-three/drei` — **5 min**
3. **App layout + CSS** — Header, sidebar, viewport split — **1 hour**
4. **Viewport** — Three.js canvas, PLY loading, display transform, OrbitControls — **2 hours**
5. **Upload panel** — File input + API call — **45 min**
6. **Processing panel** — Polling + stage display — **1 hour**
7. **Measurement tools** — Raycasting + inverse display transform + distance/height/area — **2.5 hours**
8. **is_metric handling** — conditional enable/disable of measurement UI — **30 min**
9. **Demo mesh fallback** — Load pre-generated mesh — **30 min**
10. **End-to-end test** — Upload → process → view → measure — **1 hour**

**Estimated total: ~9.5 hours** (tight for one day — see P0 simplification below)

### P0 Simplification (if time is tight)
- Skip area measurement — implement distance + height only — saves ~45 min
- Skip viewer mesh decimation — load full PLY — saves complexity
- Skip export button — use browser dev tools to save — saves 15 min

### P1 — Strongly useful

11. Export/download button
12. Coordinate display on hover
13. Measurement history
14. Camera reset animation
15. Grid/axis helper toggle
16. Better error messages

### P2 — Future/Research

17. GLTF/OBJ export
18. Point cloud viewer
19. Screenshot/recording
20. Annotation system
21. Multiple mesh comparison

---

## Validation

### Functional Tests
1. PLY loads and renders correctly (vertex colors visible)
2. Display transform correctly maps ENU Z-up → Three.js Y-up
3. OrbitControls work in all directions
4. Raycasting hits mesh surface (not passes through)
5. Inverse display transform correctly maps Three.js coords → ENU coords
6. Distance measurement produces correct values
7. Height measurement uses correct vertical axis (ENU Z / Three.js Y)
8. Area measurement closes polygon correctly
9. Progress polling updates UI during pipeline run
10. Error states display clearly
11. `is_metric = false` correctly disables/labels measurement tools

### Visual Tests
1. Mesh appears similar to what MeshLab shows
2. Lighting is reasonable (no all-black or all-white mesh)
3. Controls feel natural (not inverted, not too fast/slow)
4. Measurement markers are visible and correctly positioned
5. Up direction in the viewer corresponds to real-world up

---

## Failure Handling

| Failure | Frontend Behaviour |
|---------|-------------------|
| Backend unreachable | "Backend not running — start with `uvicorn ...`" |
| Upload fails | "Upload failed: [error message]" |
| Job fails | Show failed stage + error message + "Load Demo" button |
| Mesh load fails | "Could not load mesh — file may be corrupted" |
| Raycaster misses | "Click on the mesh surface to place a point" |
| `is_metric = false` | Amber warning: "Not calibrated — measurements are in relative units (no GPS data)" — disable measurement buttons or label as relative |

---

## Definition of Done

A user can:
1. Open the local application
2. Upload/select the drone dataset
3. Start reconstruction
4. See real processing status
5. Receive a recognizably correct 3D mesh
6. Freely orbit/pan/zoom
7. Measure distance (in metres, when metric)
8. Measure vertical height (in metres, when metric)
9. Measure planar area (in m², when metric)
10. See valid metric units ONLY when `is_metric = true`
11. Export the full-resolution mesh
12. Reload an existing verified demo mesh without rerunning reconstruction

---

## OUT OF SCOPE

- Mobile layout / responsive design
- Authentication / login
- Dark/light theme toggle (dark only)
- Settings page
- Texture mapping viewer
- Point cloud mode
- Splat viewer
- Viser viewer (React + Three.js is the production viewer)
- Video playback
- Before/after comparison
- WebSocket progress (polling is sufficient)
- Service worker / offline mode
- Surface area measurement (irregular terrain) — FUTURE
