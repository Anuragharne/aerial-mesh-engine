import { Html, Line } from "@react-three/drei";

function Marker({ point }) {
  return (
    <mesh position={point}>
      <sphereGeometry args={[0.045, 12, 12]} />
      <meshBasicMaterial />
    </mesh>
  );
}

export default function MeasurementOverlay({ measurement }) {
  if (!measurement) return null;

  const { mode, points, result } = measurement;
  if (!points?.length) return null;

  return (
    <group>
      {points.map((point, i) => <Marker key={i} point={point} />)}

      {points.length > 1 && mode !== "area" && (
        <Line points={points} lineWidth={2} />
      )}

      {mode === "area" && points.length > 1 && (
        <Line points={[...points, points[0]]} lineWidth={2} />
      )}

      {result && points.length >= 2 && (
        <Html position={points[points.length - 1]} center distanceFactor={8}>
          <div className="measurement-label">
            {result.value}{result.type === "Planar area" ? " m²" : " m"}
          </div>
        </Html>
      )}
    </group>
  );
}