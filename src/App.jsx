import { useCallback, useEffect, useRef, useState } from "react";
import Header from "./components/Header";
import ControlPanel from "./components/ControlPanel";
import Viewport from "./components/Viewport";
import StatusBar from "./components/StatusBar";
import { checkBackend, getJobResult, getJobStatus, loadDemoMesh, loadJobMesh, measureArea, startReconstruction } from "./lib/api";
import { displayToENU, distanceENU, heightENU } from "./lib/coordinates";

export default function App() {
  const [backendStatus, setBackendStatus] = useState("checking");
  const [videoFile, setVideoFile] = useState(null);
  const [srtFile, setSrtFile] = useState(null);
  const [mode, setMode] = useState("Demo");
  const [job, setJob] = useState(null);
  const [buffer, setBuffer] = useState(null);
  const [meshInfo, setMeshInfo] = useState(null);
  const [isMetric, setIsMetric] = useState(false);
  const [measurementMode, setMeasurementMode] = useState(null);
  const [measurementPoints, setMeasurementPoints] = useState([]);
  const [measurementResult, setMeasurementResult] = useState(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("No mesh loaded");
  const [elapsed, setElapsed] = useState("00:00");
  const [resetNonce, setResetNonce] = useState(0);
  const startedAt = useRef(null);

  useEffect(() => {
    checkBackend()
      .then(() => setBackendStatus("connected"))
      .catch(() => setBackendStatus("offline"));
  }, []);

  useEffect(() => {
    if (!job || job.status !== "running") return;

    const interval = setInterval(async () => {
      try {
        const next = await getJobStatus(job.id);
        setJob(next);
        setStatus(`Processing: ${next.stage || "pipeline"}`);
        if (next.status === "completed") {
          clearInterval(interval);
          const result = await getJobResult(next.id);
          setIsMetric(Boolean(result.is_metric));
          const mesh = await loadJobMesh(next.id);
          setBuffer(mesh);
          setStatus(`Mesh loaded: pending — ${result.is_metric ? "Metric (ENU)" : "Not calibrated"}`);
        }
        if (next.status === "failed") {
          clearInterval(interval);
          setError(next.error || "Reconstruction failed");
          setStatus(`Error: ${next.error || "Reconstruction failed"}`);
        }
      } catch (err) {
        setError(err.message);
        setStatus(`Error: ${err.message}`);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [job]);

  useEffect(() => {
    if (!startedAt.current || !job || job.status !== "running") return;
    const timer = setInterval(() => {
      const seconds = Math.floor((Date.now() - startedAt.current) / 1000);
      setElapsed(`${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`);
    }, 250);
    return () => clearInterval(timer);
  }, [job]);

  const loadMesh = useCallback(async (loader, metric) => {
    setError("");
    setStatus("Loading mesh...");
    try {
      const data = await loader();
      setBuffer(data);
      setIsMetric(metric);
      setMeasurementMode(null);
      setMeasurementPoints([]);
      setMeasurementResult(null);
      setStatus(metric ? "Mesh loaded — Metric (ENU)" : "Mesh loaded — Not calibrated");
    } catch (err) {
      setError(err.message);
      setStatus(`Error: ${err.message}`);
    }
  }, []);

  const handleDemo = () => {
    setJob(null);
    loadMesh(loadDemoMesh, true);
  };

  const handleStart = async () => {
    setError("");
    setStatus("Uploading...");
    try {
      // The plan does not define the upload/start endpoint, so this call
      // deliberately fails rather than inventing a backend contract.
      const createdJob = await startReconstruction({ videoFile, srtFile, mode });
      setJob(createdJob);
      startedAt.current = Date.now();
      setStatus("Processing: starting");
    } catch (err) {
      setError(err.message);
      setStatus(`Error: ${err.message}`);
    }
  };

  const handleMeshLoaded = (info) => {
    if (!info) {
      setError("Could not load mesh — file may be corrupted");
      setStatus("Error: Could not load mesh");
      return;
    }
    setMeshInfo({
      vertices: info.vertices,
      triangles: info.triangles,
      isMetric,
    });
  };

  const handlePoint = async (displayPoint) => {
    if (!measurementMode || !isMetric) return;
    const next = [...measurementPoints, displayPoint];
    setMeasurementPoints(next);

    if (measurementMode === "distance" && next.length === 2) {
      const a = displayToENU(next[0]);
      const b = displayToENU(next[1]);
      const value = distanceENU(a, b);
      setMeasurementResult({ type: "Distance", value: value.toFixed(2) });
      setStatus(`Mode: Distance — ${value.toFixed(2)} m`);
      return;
    }

    if (measurementMode === "height" && next.length === 2) {
      const top = displayToENU(next[0]);
      const base = displayToENU(next[1]);
      const value = heightENU(top, base);
      setMeasurementResult({ type: "Height", value: value.toFixed(2) });
      setStatus(`Mode: Height — ${value.toFixed(2)} m`);
      return;
    }

    if (measurementMode === "area" && next.length >= 3) {
      setStatus("Mode: Area — double-click/Finish to close polygon");
    }
  };

  const finishArea = async () => {
    if (measurementMode !== "area" || measurementPoints.length < 3 || !job?.id) return;
    try {
      const enuPoints = measurementPoints.map(displayToENU);
      const response = await measureArea(job.id, enuPoints);
      const value = Number(response.area ?? response.value);
      if (!Number.isFinite(value)) throw new Error("Area measurement returned an invalid value");
      setMeasurementResult({ type: "Planar area", value: value.toFixed(2) });
      setStatus(`Mode: Area — ${value.toFixed(2)} m²`);
    } catch (err) {
      setError(err.message);
      setStatus(`Error: ${err.message}`);
    }
  };

  const clearMeasurement = () => {
    setMeasurementPoints([]);
    setMeasurementResult(null);
    setMeasurementMode(null);
    setStatus(buffer ? `Mesh loaded — ${isMetric ? "Metric (ENU)" : "Not calibrated"}` : "No mesh loaded");
  };

  const measurement = measurementPoints.length
    ? { mode: measurementMode, points: measurementPoints, result: measurementResult }
    : null;

  return (
    <div className="app-shell">
      <Header backendStatus={backendStatus} />
      <div className="workspace">
        <ControlPanel
          videoFile={videoFile}
          srtFile={srtFile}
          setVideoFile={setVideoFile}
          setSrtFile={setSrtFile}
          mode={mode}
          setMode={setMode}
          onDemo={handleDemo}
          onStart={handleStart}
          busy={job?.status === "running"}
          job={job}
          elapsed={elapsed}
          meshLoaded={Boolean(buffer)}
          isMetric={isMetric}
          measurementMode={measurementMode}
          setMeasurementMode={(value) => {
            setMeasurementMode(value);
            setMeasurementPoints([]);
            setMeasurementResult(null);
            if (value) setStatus(`Mode: ${value[0].toUpperCase()}${value.slice(1)}`);
          }}
          measurementResult={measurementResult}
          measurementPoints={measurementPoints}
          clearMeasurement={clearMeasurement}
          finishArea={finishArea}
          meshInfo={meshInfo}
        />
        <Viewport
          buffer={buffer}
          measurementMode={measurementMode}
          onPoint={handlePoint}
          measurement={measurement}
          onLoaded={handleMeshLoaded}
          resetToken={() => setResetNonce((n) => n + 1)}
          error={error && buffer === null ? error : ""}
          onFinishArea={finishArea}
          resetNonce={resetNonce}
        />
      </div>
      <StatusBar
        isMetric={isMetric}
        meshInfo={meshInfo}
        status={status}
      />
    </div>
  );
}