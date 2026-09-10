export default function ExportPanel({ jobId, meshInfo }) {
  return (
    <section className="panel-section export-section">
      <div className="section-heading">
        <span className="section-index">04</span>
        <div>
          <h2>Export</h2>
          <p>Full-resolution output</p>
        </div>
      </div>

      <div className="mesh-info">
        <div><span>Vertices</span><strong>{meshInfo?.vertices?.toLocaleString() ?? "—"}</strong></div>
        <div><span>Triangles</span><strong>{meshInfo?.triangles?.toLocaleString() ?? "—"}</strong></div>
        <div><span>Metric</span><strong>{meshInfo ? (meshInfo.isMetric ? "Yes" : "No") : "—"}</strong></div>
      </div>

      <a
        className={`primary-button export-button ${!jobId ? "disabled" : ""}`}
        href={jobId ? `/api/jobs/${jobId}/mesh` : undefined}
        download
        aria-disabled={!jobId}
        onClick={(e) => { if (!jobId) e.preventDefault(); }}
      >
        ↓ Download Full Mesh
      </a>
    </section>
  );
}