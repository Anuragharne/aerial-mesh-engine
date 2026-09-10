async function readError(response, fallback) {
  let detail = fallback;
  try {
    const data = await response.json();
    detail = data.detail || data.error || data.message || fallback;
  } catch {
    // Backend may return non-JSON error text.
  }
  throw new Error(detail);
}

export async function checkBackend() {
  // The plan does not define a /health endpoint. Use the specified demo
  // mesh endpoint as the connectivity probe instead of inventing one.
  const response = await fetch("/api/demo/mesh");
  if (!response.ok) throw new Error("Backend unavailable");
  try { await response.body?.cancel(); } catch {}
  return true;
}

export async function getJobStatus(jobId) {
  const response = await fetch(`/api/jobs/${jobId}/status`);
  if (!response.ok) await readError(response, "Could not read job status");
  return response.json();
}

export async function getJobResult(jobId) {
  const response = await fetch(`/api/jobs/${jobId}/result`);
  if (!response.ok) await readError(response, "Could not read job result");
  return response.json();
}

export async function loadJobMesh(jobId) {
  const response = await fetch(`/api/jobs/${jobId}/mesh?detail=viewer`);
  if (!response.ok) await readError(response, "Could not load mesh — file may be corrupted");
  return response.arrayBuffer();
}

export async function loadDemoMesh() {
  const response = await fetch("/api/demo/mesh");
  if (!response.ok) await readError(response, "Could not load mesh — file may be corrupted");
  return response.arrayBuffer();
}

export async function measureArea(jobId, points) {
  const response = await fetch(`/api/jobs/${jobId}/measure/area`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ points }),
  });
  if (!response.ok) await readError(response, "Area measurement failed");
  return response.json();
}

export function fullMeshUrl(jobId) {
  return `/api/jobs/${jobId}/mesh`;
}

/*
 * Upload/reconstruction endpoint intentionally is not guessed here.
 * The supplied implementation plan specifies the UI flow but does not
 * define the upload/start endpoint or request schema. Wire the exact
 * backend contract here once it exists.
 */
export async function startReconstruction() {
  throw new Error("Upload/start endpoint is not specified by FRONTEND_IMPLEMENTATION_PLAN.md");
}