import { Canvas, useThree } from "@react-three/fiber";
import { OrbitControls, Grid, Html, Line } from "@react-three/drei";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { PLYLoader } from "three/examples/jsm/loaders/PLYLoader.js";
import MeasurementOverlay from "./MeasurementOverlay";

function Motor({ position }) {
  return (
    <group position={position}>
      <mesh>
        <cylinderGeometry args={[0.16, 0.16, 0.08, 24]} />
        <meshStandardMaterial color="#30343a" metalness={0.7} roughness={0.32} />
      </mesh>
      <mesh position={[0, 0.065, 0]}>
        <cylinderGeometry args={[0.055, 0.055, 0.055, 20]} />
        <meshStandardMaterial color="#101214" metalness={0.85} roughness={0.2} />
      </mesh>
      <mesh position={[0, 0.115, 0]} rotation={[0, 0, Math.PI / 2]}>
        <boxGeometry args={[0.52, 0.012, 0.045]} />
        <meshStandardMaterial color="#15181c" metalness={0.35} roughness={0.5} />
      </mesh>
      <mesh position={[0, 0.118, 0]} rotation={[0, 0, Math.PI / 2]} scale={[0.45, 1, 1]}>
        <boxGeometry args={[0.52, 0.008, 0.025]} />
        <meshStandardMaterial color="#3d4248" metalness={0.2} roughness={0.6} />
      </mesh>
    </group>
  );
}

function Arm({ from, to }) {
  const start = new THREE.Vector3(...from);
  const end = new THREE.Vector3(...to);
  const direction = end.clone().sub(start);
  const length = direction.length();
  const mid = start.clone().add(end).multiplyScalar(0.5);

  return (
    <mesh position={mid} quaternion={new THREE.Quaternion().setFromUnitVectors(
      new THREE.Vector3(0, 1, 0), direction.normalize()
    )}>
      <boxGeometry args={[0.14, length, 0.11]} />
      <meshStandardMaterial color="#24282e" metalness={0.65} roughness={0.34} />
    </mesh>
  );
}

function DroneModel({ onReady }) {
  const group = useRef();

  useEffect(() => {
    onReady?.(group.current);
  }, [onReady]);

  const motors = [
    [-1.35, 0.05, -1.05],
    [1.35, 0.05, -1.05],
    [-1.35, 0.05, 1.05],
    [1.35, 0.05, 1.05],
  ];

  return (
    <group ref={group} scale={1.08} rotation={[0.05, -0.28, 0]}>
      <mesh position={[0, 0.08, 0]} scale={[1.15, 0.36, 0.76]}>
        <boxGeometry args={[1.55, 0.75, 1.15]} />
        <meshStandardMaterial color="#34383d" metalness={0.68} roughness={0.28} />
      </mesh>
      <mesh position={[0, 0.3, 0]} scale={[0.9, 0.25, 0.58]}>
        <boxGeometry args={[1.45, 0.62, 1.0]} />
        <meshStandardMaterial color="#454a50" metalness={0.52} roughness={0.32} />
      </mesh>
      <mesh position={[0, 0.48, 0]} scale={[0.7, 0.11, 0.44]}>
        <boxGeometry args={[1.25, 0.6, 0.86]} />
        <meshStandardMaterial color="#24282c" metalness={0.58} roughness={0.3} />
      </mesh>

      <mesh position={[0, 0.57, 0.02]} rotation={[0, Math.PI / 4, 0]}>
        <boxGeometry args={[0.38, 0.018, 0.38]} />
        <meshStandardMaterial color="#111316" metalness={0.2} roughness={0.5} />
      </mesh>

      <Arm from={[-0.45, 0.06, -0.26]} to={[-1.35, 0.05, -1.05]} />
      <Arm from={[0.45, 0.06, -0.26]} to={[1.35, 0.05, -1.05]} />
      <Arm from={[-0.45, 0.06, 0.26]} to={[-1.35, 0.05, 1.05]} />
      <Arm from={[0.45, 0.06, 0.26]} to={[1.35, 0.05, 1.05]} />

      {motors.map((position, i) => <Motor key={i} position={position} />)}

      <group position={[0, -0.48, 0.25]}>
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.28, 0.22, 0.38, 32]} />
          <meshStandardMaterial color="#15181b" metalness={0.7} roughness={0.22} />
        </mesh>
        <mesh position={[0, -0.01, -0.2]} rotation={[Math.PI / 2, 0, 0]}>
          <sphereGeometry args={[0.13, 24, 16]} />
          <meshStandardMaterial color="#070809" metalness={0.35} roughness={0.12} />
        </mesh>
        <mesh position={[0, -0.01, -0.27]} rotation={[Math.PI / 2, 0, 0]}>
          <sphereGeometry args={[0.075, 20, 14]} />
          <meshStandardMaterial color="#17444a" emissive="#0c3338" emissiveIntensity={1.5} roughness={0.15} />
        </mesh>
      </group>

      <mesh position={[0, 0.72, 0]}>
        <boxGeometry args={[0.16, 0.04, 0.06]} />
        <meshStandardMaterial color="#d6d8da" metalness={0.4} roughness={0.25} />
      </mesh>
    </group>
  );
}

function ProceduralDroneScene({ onHover }) {
  const { camera } = useThree();
  const controls = useRef();

  useEffect(() => {
    camera.position.set(4.7, 2.8, 5.4);
    camera.lookAt(0, 0.1, 0);
    controls.current?.target.set(0, 0.1, 0);
    controls.current?.update();
  }, [camera]);

  return (
    <>
      <ambientLight intensity={0.32} />
      <directionalLight position={[4, 7, 4]} intensity={3.1} />
      <directionalLight position={[-5, 3, -4]} intensity={1.2} />
      <pointLight position={[0, 1, 2]} intensity={1.1} distance={7} />
      <Grid
        args={[35, 35]}
        cellSize={0.5}
        cellThickness={0.45}
        cellColor="#172331"
        sectionSize={2.5}
        sectionThickness={0.8}
        sectionColor="#203444"
        fadeDistance={18}
        fadeStrength={1.4}
        infiniteGrid
      />
      <DroneModel onReady={onHover} />
      <OrbitControls
        ref={controls}
        makeDefault
        enablePan
        enableZoom
        enableRotate
        minDistance={2.4}
        maxDistance={13}
        target={[0, 0.1, 0]}
      />
    </>
  );
}

function LoadedMeshScene({ buffer, measurementMode, onPoint, measurement, onLoaded, resetToken }) {
  const controls = useRef();
  const { camera } = useThree();
  const [geometry, setGeometry] = useState(null);

  useEffect(() => {
    if (!buffer) return;
    try {
      const loader = new PLYLoader();
      const parsed = loader.parse(buffer);
      parsed.computeBoundingBox();
      parsed.computeBoundingSphere();

      // ENU Z-up -> Three.js Y-up at the display boundary.
      parsed.rotateX(-Math.PI / 2);

      if (!parsed.getAttribute("normal")) parsed.computeVertexNormals();
      setGeometry(parsed);

      const pos = parsed.getAttribute("position");
      onLoaded({
        vertices: pos?.count ?? 0,
        triangles: parsed.index ? parsed.index.count / 3 : Math.floor((pos?.count ?? 0) / 3),
      });
    } catch {
      onLoaded(null);
    }
  }, [buffer, onLoaded]);

  const material = useMemo(() => new THREE.MeshStandardMaterial({
    vertexColors: Boolean(geometry?.getAttribute("color")),
    roughness: 0.72,
    metalness: 0.08,
    side: THREE.DoubleSide,
  }), [geometry]);

  useEffect(() => {
    if (!geometry) return;
    const sphere = geometry.boundingSphere || geometry.computeBoundingSphere();
    const radius = Math.max(sphere.radius, 1);
    const center = sphere.center;
    camera.position.set(center.x + radius * 1.5, center.y + radius * 0.8, center.z + radius * 1.5);
    camera.up.set(0, 1, 0);
    camera.lookAt(center);
    controls.current?.target.copy(center);
    controls.current?.update();
  }, [geometry, camera, resetToken]);

  if (!geometry) return null;

  return (
    <>
      <mesh
        geometry={geometry}
        material={material}
        onClick={(e) => {
          e.stopPropagation();
          if (measurementMode) onPoint(e.point.clone());
        }}
      />
      <MeasurementOverlay measurement={measurement} />
      <OrbitControls ref={controls} makeDefault enablePan enableZoom enableRotate />
    </>
  );
}

export default function Viewport({
  buffer,
  measurementMode,
  onPoint,
  measurement,
  onLoaded,
  resetToken,
  error,
  onFinishArea,
}) {
  const [droneInteracting, setDroneInteracting] = useState(false);

  return (
    <main className="viewport">
      <div className="viewport-toolbar">
        <div className="viewport-title">
          <span className="crosshair">+</span>
          <span>3D VIEWPORT</span>
        </div>
        <div className="viewport-tools">
          <span className="tool-hint">DRAG TO ORBIT · SCROLL TO ZOOM · SHIFT+DRAG TO PAN</span>
          <button className="viewport-reset" type="button" onClick={() => resetToken()}>
            Reset
          </button>
        </div>
      </div>

      <Canvas
        camera={{ position: [4.7, 2.8, 5.4], fov: 42, near: 0.01, far: 10000 }}
        dpr={[1, 2]}
        onPointerDown={() => setDroneInteracting(true)}
        onPointerUp={() => setDroneInteracting(false)}
        onDoubleClick={() => {
          if (measurementMode === "area") onFinishArea?.();
        }}
      >
        {buffer ? (
          <LoadedMeshScene
            buffer={buffer}
            measurementMode={measurementMode}
            onPoint={onPoint}
            measurement={measurement}
            onLoaded={onLoaded}
            resetToken={resetToken}
          />
        ) : (
          <ProceduralDroneScene onHover={() => {}} />
        )}
      </Canvas>

      {!buffer && !error && (
        <>
          <div className="drone-welcome">
            <div className="welcome-kicker"><span /> WELCOME</div>
            <h2>SIH26158 Aerial Mesh Engine</h2>
            <p>Turn drone footage into precise 3D models</p>
            <div className="workflow-strip">
              <div><b>▣</b><strong>Upload Video</strong><span>MP4 + optional SRT</span></div>
              <i />
              <div><b>◇</b><strong>Reconstruct</strong><span>AI-powered pipeline</span></div>
              <i />
              <div><b>△</b><strong>Measure & Export</strong><span>Distance, height, area</span></div>
            </div>
          </div>
          <div className="drone-state">
            {droneInteracting ? "INTERACTIVE 3D MODEL" : "DRAG TO ORBIT · SCROLL TO ZOOM"}
          </div>
        </>
      )}

      {error && (
        <div className="viewport-error">
          <strong>Mesh load failed</strong>
          <span>{error}</span>
        </div>
      )}
    </main>
  );
}
