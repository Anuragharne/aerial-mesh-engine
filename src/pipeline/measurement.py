import numpy as np
import argparse
import sys
import json
import os
import open3d as o3d

def calculate_distance(ptA, ptB):
    """Calculates Euclidean distance between two 3D points."""
    return np.linalg.norm(np.array(ptA) - np.array(ptB))

def measure_distance_on_mesh(mesh_path, ptA, ptB, is_metric):
    """
    Measures the distance between two points. 
    Optionally snaps the points to the closest vertices on the mesh.
    """
    if not os.path.exists(mesh_path):
        raise FileNotFoundError(f"Mesh not found at {mesh_path}")
        
    if not is_metric:
        print("Warning: Model lacks metric Sim3 alignment. Measurements are relative only.", file=sys.stderr)
        
    mesh = o3d.io.read_triangle_mesh(mesh_path)
    if len(mesh.vertices) == 0:
        raise ValueError("Mesh has no vertices.")
        
    # Snap points to the closest mesh surface points (vertices for simplicity)
    pcd = o3d.geometry.PointCloud()
    pcd.points = mesh.vertices
    kd_tree = o3d.geometry.KDTreeFlann(pcd)
    
    _, idxA, _ = kd_tree.search_knn_vector_3d(ptA, 1)
    _, idxB, _ = kd_tree.search_knn_vector_3d(ptB, 1)
    
    snapped_A = np.asarray(mesh.vertices)[idxA[0]]
    snapped_B = np.asarray(mesh.vertices)[idxB[0]]
    
    distance = calculate_distance(snapped_A, snapped_B)
    
    return {
        "ptA_input": ptA,
        "ptB_input": ptB,
        "ptA_snapped": snapped_A.tolist(),
        "ptB_snapped": snapped_B.tolist(),
        "distance": float(distance),
        "is_metric": is_metric
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Measure distance on mesh")
    parser.add_argument("--mesh", type=str, required=True, help="Path to the mesh PLY file")
    parser.add_argument("--p1", type=float, nargs=3, required=True, help="Point A (X Y Z)")
    parser.add_argument("--p2", type=float, nargs=3, required=True, help="Point B (X Y Z)")
    parser.add_argument("--metric", action="store_true", help="Is the mesh metrically aligned?")
    
    args = parser.parse_args()
    
    try:
        result = measure_distance_on_mesh(args.mesh, args.p1, args.p2, args.metric)
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
