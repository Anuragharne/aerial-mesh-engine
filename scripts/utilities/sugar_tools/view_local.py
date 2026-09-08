import open3d as o3d

# The default output path where the 3DGS engine saves the 7,000-iteration file
ply_path = r"..\outputs\test_scene\sugar_model\point_cloud\iteration_7000\point_cloud.ply"

print("Loading 7K point cloud...")
pcd = o3d.io.read_point_cloud(ply_path)

print("Launching Open3D Viewer... (Use mouse to rotate, scroll to zoom)")
o3d.visualization.draw_geometries([pcd], window_name="Hackathon 3DGS Point Cloud")