import open3d as o3d
import numpy as np

input_ply = r"..\outputs\test_scene\sugar_model\point_cloud\iteration_7000\point_cloud.ply"
output_mesh = r"..\outputs\test_scene\fast_proxy_mesh.obj"

print("Step 1: Reading 7K point cloud...")
pcd = o3d.io.read_point_cloud(input_ply)
print(f"Loaded {len(pcd.points)} points.")

print("Step 2: Estimating surface normals...")
pcd.estimate_normals(
    search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.5, max_nn=30)
)
pcd.orient_normals_consistent_tangent_plane(k=15)

print("Step 3: Running Poisson surface reconstruction (Octree depth=8)...")
mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(pcd, depth=8)

print("Step 4: Pruning low-density artifact triangles...")
densities = np.asarray(densities)
density_threshold = np.quantile(densities, 0.05)
vertices_to_remove = densities < density_threshold
mesh.remove_vertices_by_mask(vertices_to_remove)

mesh.compute_vertex_normals()

print(f"Step 5: Exporting standard mesh to {output_mesh}...")
o3d.io.write_triangle_mesh(output_mesh, mesh)
print("[✓] Mesh conversion complete!")

print("Launching Open3D viewer to inspect the surface mesh...")
o3d.visualization.draw_geometries([mesh], window_name="Fast Proxy Mesh (.obj)")