# SIH26158 Aerial Mesh Engine

Desktop React/Vite frontend for the drone-to-3D reconstruction workflow.

## Run

```bash
npm install
npm run dev
```

Vite proxies `/api` to `http://localhost:8000`.

## Implemented

- Dark engineering-tool UI
- Header/backend status
- MP4 + optional SRT selectors
- Demo mesh loading
- Three.js / React Three Fiber PLY viewer
- ENU → Three.js `rotateX(-Math.PI / 2)` display transform
- Three.js → ENU inverse transform for measurement boundaries
- Orbit/pan/zoom
- Camera framing/reset
- Metric-aware measurement UI
- Distance and height client-side calculations
- Planar-area API integration with Finish Area / double-click
- Camera auto-framing and reset
- Full-resolution PLY export
- Processing polling at 2 seconds
- Error/status states

## Important backend-contract note

The supplied implementation plan specifies the mesh, result, status and area endpoints, but it does **not** specify the endpoint or request schema used to upload an MP4/SRT and create a reconstruction job. The frontend therefore does not invent one. `src/lib/api.js` contains `startReconstruction()` as the single integration point to wire to the actual backend contract.

This is intentional: the UI reports the missing contract instead of pretending reconstruction succeeded.

## Known P1/P2 omissions

The implementation keeps the requested P0 architecture focused. Measurement history, coordinate hover readout, camera reset animation, and helper toggles are not required for the core workflow.