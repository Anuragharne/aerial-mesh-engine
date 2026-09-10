const stages = ["upload", "preprocess", "reconstruct", "mesh"];

function stateFor(stage, current) {
  const order = stages.indexOf(current);
  const index = stages.indexOf(stage);
  if (order < 0) return "pending";
  if (index < order) return "done";
  if (index === order) return "running";
  return "pending";
}

export default function ProcessingPanel({ job, elapsed }) {
  if (!job || job.status !== "running") return null;

  const current = job.stage || "preprocess";

  return (
    <section className="panel-section processing">
      <div className="section-heading">
        <span className="section-index">02</span>
        <div>
          <h2>Processing</h2>
          <p>Live pipeline state</p>
        </div>
      </div>

      <div className="progress-track">
        <div className="progress-fill" style={{ width: `${Math.max(0, Math.min(100, job.progress ?? 0))}%` }} />
      </div>
      <div className="progress-readout">
        <strong>{job.progress ?? 0}%</strong>
        <span>{elapsed}</span>
      </div>

      <div className="stage-list">
        {stages.map((stage) => {
          const state = stateFor(stage, current);
          return (
            <div className="stage-row" key={stage}>
              <span className={`stage-icon ${state}`}>{state === "done" ? "✓" : state === "running" ? "•" : "○"}</span>
              <span>{stage.replace("_", " ")}</span>
              <span className="stage-state">{state}</span>
            </div>
          );
        })}
      </div>

      {job.error && <div className="error-box">{job.error}</div>}
    </section>
  );
}