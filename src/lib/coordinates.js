// Backend canonical coordinates are ENU: X=East, Y=North, Z=Up.
// The mesh is rotated -90° around X when displayed in Three.js.
// Therefore every point crossing back to the backend must be converted here.
export function displayToENU(threePoint) {
  return {
    x: threePoint.x,
    y: -threePoint.z,
    z: threePoint.y,
  };
}

export function distanceENU(a, b) {
  return Math.hypot(b.x - a.x, b.y - a.y, b.z - a.z);
}

export function heightENU(top, base) {
  return Math.abs(top.z - base.z);
}