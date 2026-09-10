export default function MeasurementPanel({
  isMetric,
  mode,
  setMode,
  result,
  measurementPoints,
  onClear,
  onFinishArea,
}) {
  return (
    <section className="panel-section">
      <div className="section-heading">
        <span className="section-index">03</span>
        <div>
          <h2>Measure</h2>
          <p>Geometry analysis</p>
        </div>
      </div>

      {!isMetric ? (
        <div className="warning-box">
          <strong>Not calibrated</strong>
          <span>Measurements are in relative units (no GPS data).</span>
        </div>
      ) : (
        <div className="metric-badge"><span>●</span> Metric (ENU)</div>
      )}

      <div className="measurement-grid">
        {["distance", "height", "area"].map((item) => (
          <button
            key={item}
            type="button"
            disabled={!isMetric}
            className={mode === item ? "measure-button active" : "measure-button"}
            onClick={() => setMode(mode === item ? null : item)}
          >
            {item === "distance" ? "Distance" : item === "height" ? "Height" : "Planar Area"}
          </button>
        ))}
      </div>

      {mode && isMetric && (
        <div className="mode-note">
          <span className="pulse" />
          {mode === "area" ? "Click vertices. Double-click to finish." : `Click ${mode === "height" ? "top, then base" : "two points"} on the mesh.`}
        </div>
      )}

      {mode === "area" && isMetric && measurementPoints?.length >= 3 && (
        <button className="secondary-button" type="button" onClick={onFinishArea}>
          Finish Area
        </button>
      )}

      {result && (
        <div className="result-box">
          <div className="result-label">{result.type}</div>
          <div className="result-value">{result.value}{result.type === "Planar area" ? " m²" : " m"}</div>
        </div>
      )}

      <button className="text-button" type="button" onClick={onClear} disabled={!result && !mode}>Clear measurement</button>
    </section>
  );
}