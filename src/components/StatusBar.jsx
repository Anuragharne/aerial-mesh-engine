export default function StatusBar({ isMetric, meshInfo, status, mousePosition }) {
  return (
    <footer className="status-bar">
      <div className="status-group">
        <span className="status-key">FRAME</span>
        <strong>{isMetric ? "ENU (metric)" : "VGGT (arbitrary)"}</strong>
      </div>
      <div className="status-group">
        <span className={`metric-dot ${isMetric ? "good" : "warn"}`} />
        <strong>{isMetric ? "Metric" : "Not calibrated"}</strong>
      </div>
      <div className="status-group">
        <span className="status-key">VERTICES</span>
        <strong>{meshInfo?.vertices?.toLocaleString() ?? "—"}</strong>
      </div>
      <div className="status-group">
        <span className="status-key">TRIANGLES</span>
        <strong>{meshInfo?.triangles?.toLocaleString() ?? "—"}</strong>
      </div>
      {mousePosition && (
        <div className="status-group position">
          <span className="status-key">POSITION</span>
          <strong>{mousePosition.x.toFixed(2)}, {mousePosition.y.toFixed(2)}, {mousePosition.z.toFixed(2)}</strong>
        </div>
      )}
      <div className="status-message">{status}</div>
    </footer>
  );
}