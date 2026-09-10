export default function Header({ backendStatus }) {
  const states = {
    connected: ["Connected", "online"],
    offline: ["Backend offline", "offline"],
    checking: ["Checking connection", "checking"],
  };
  const [label, cls] = states[backendStatus] || states.checking;

  return (
    <header className="app-header">
      <div className="brand">
        <span className="brand-mark">AE</span>
        <div>
          <div className="eyebrow">AERIAL MESH ENGINE</div>
          <h1>SIH26158 Aerial Mesh Engine</h1>
        </div>
      </div>

      <div className={`connection ${cls}`}>
        <span className="status-dot" />
        {label}
      </div>
    </header>
  );
}
