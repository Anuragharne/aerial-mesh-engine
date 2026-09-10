import { useRef } from "react";

function FileRow({ label, file, accept, onChange, disabled }) {
  const ref = useRef(null);
  return (
    <div className="file-row">
      <div className="file-meta">
        <span className="field-label">{label}</span>
        <span className={file ? "file-name selected" : "file-name"}>
          {file ? file.name : "No file selected"}
        </span>
      </div>
      <button
        className="secondary-button compact"
        type="button"
        disabled={disabled}
        onClick={() => ref.current?.click()}
      >
        Browse
      </button>
      <input
        ref={ref}
        hidden
        type="file"
        accept={accept}
        disabled={disabled}
        onChange={(e) => onChange(e.target.files?.[0] || null)}
      />
    </div>
  );
}

export default function UploadPanel({
  videoFile,
  srtFile,
  setVideoFile,
  setSrtFile,
  mode,
  setMode,
  onDemo,
  onStart,
  busy,
}) {
  return (
    <section className="panel-section">
      <div className="section-heading">
        <span className="section-index">01</span>
        <div>
          <h2>Source</h2>
          <p>Drone capture input</p>
        </div>
      </div>

      <FileRow label="DRONE VIDEO" file={videoFile} accept=".mp4,video/mp4" onChange={setVideoFile} disabled={busy} />
      <FileRow label="SRT / OPTIONAL" file={srtFile} accept=".srt" onChange={setSrtFile} disabled={busy} />

      <div className="mode-selector">
        {["Demo", "Quality"].map((item) => (
          <button
            key={item}
            type="button"
            className={mode === item ? "mode active" : "mode"}
            onClick={() => setMode(item)}
            disabled={busy}
          >
            {item}
          </button>
        ))}
      </div>

      <div className="button-stack">
        <button className="primary-button" type="button" onClick={onDemo} disabled={busy}>
          <span>◈</span> Load Demo Mesh
        </button>
        <button className="secondary-button" type="button" onClick={onStart} disabled={busy || !videoFile}>
          Start Reconstruction
        </button>
      </div>
      {!videoFile && <p className="hint">Select an MP4 to enable reconstruction.</p>}
    </section>
  );
}