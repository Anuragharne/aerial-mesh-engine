import os
import numpy as np

def rotmat2qvec(R):
    Rxx, Ryx, Rzx, Rxy, Ryy, Rzy, Rxz, Ryz, Rzz = R.flat
    K = np.array([
        [Rxx - Ryy - Rzz, 0, 0, 0],
        [Ryx + Rxy, Ryy - Rxx - Rzz, 0, 0],
        [Rzx + Rxz, Rzy + Ryz, Rzz - Rxx - Ryy, 0],
        [Ryz - Rzy, Rzx - Rxz, Rxy - Ryx, Rxx + Ryy + Rzz]]) / 3.0
    eigvals, eigvecs = np.linalg.eigh(K)
    qstep = eigvecs[[3, 0, 1, 2], np.argmax(eigvals)]
    if qstep[0] < 0:
        qstep *= -1
    return qstep

def write_colmap_txt(sparse_dir, points3d, points_xyf, points_rgb, extrinsics, intrinsics, original_coords, img_size, base_image_path_list):
    os.makedirs(sparse_dir, exist_ok=True)
    
    N = len(extrinsics)
    P = len(points3d)
    
    # 1. cameras.txt
    with open(os.path.join(sparse_dir, "cameras.txt"), "w") as f:
        f.write("# Camera list with one line of data per camera:\n")
        f.write("#   CAMERA_ID, MODEL, WIDTH, HEIGHT, PARAMS[]\n")
        f.write(f"# Number of cameras: {N}\n")
        
        for fidx in range(N):
            cam_id = fidx + 1
            real_image_size = original_coords[fidx, -2:]
            width, height = int(real_image_size[0]), int(real_image_size[1])
            
            # Pinhole
            resize_ratio = max(real_image_size) / img_size
            fx = intrinsics[fidx][0, 0] * resize_ratio
            fy = intrinsics[fidx][1, 1] * resize_ratio
            cx, cy = width / 2.0, height / 2.0
            
            f.write(f"{cam_id} PINHOLE {width} {height} {fx} {fy} {cx} {cy}\n")

    # Group points by frame
    points_by_frame = {fidx: [] for fidx in range(N)}
    for point3d_id_0based in range(P):
        fidx = int(points_xyf[point3d_id_0based, 2])
        if fidx in points_by_frame:
            points_by_frame[fidx].append(point3d_id_0based)

    # 2. images.txt
    with open(os.path.join(sparse_dir, "images.txt"), "w") as f:
        f.write("# Image list with two lines of data per image:\n")
        f.write("#   IMAGE_ID, QW, QX, QY, QZ, TX, TY, TZ, CAMERA_ID, NAME\n")
        f.write("#   POINTS2D[] as (X, Y, POINT3D_ID)\n")
        f.write(f"# Number of images: {N}\n")
        
        for fidx in range(N):
            img_id = fidx + 1
            cam_id = fidx + 1
            name = base_image_path_list[fidx]
            
            R = extrinsics[fidx][:3, :3]
            T = extrinsics[fidx][:3, 3]
            qvec = rotmat2qvec(R)
            
            f.write(f"{img_id} {qvec[0]} {qvec[1]} {qvec[2]} {qvec[3]} {T[0]} {T[1]} {T[2]} {cam_id} {name}\n")
            
            real_image_size = original_coords[fidx, -2:]
            resize_ratio = max(real_image_size) / img_size
            top_left = original_coords[fidx, :2]
            
            # write points2D
            pt_strs = []
            for point3d_id_0based in points_by_frame[fidx]:
                point3d_id = point3d_id_0based + 1
                xy = points_xyf[point3d_id_0based, :2]
                xy_shifted = (xy - top_left) * resize_ratio
                pt_strs.append(f"{xy_shifted[0]} {xy_shifted[1]} {point3d_id}")
                
            f.write(" ".join(pt_strs) + "\n")

    # 3. points3D.txt
    with open(os.path.join(sparse_dir, "points3D.txt"), "w") as f:
        f.write("# 3D point list with one line of data per point:\n")
        f.write("#   POINT3D_ID, X, Y, Z, R, G, B, ERROR, TRACK[] as (IMAGE_ID, POINT2D_IDX)\n")
        f.write(f"# Number of points: {P}\n")
        
        # Build track info
        # track is IMAGE_ID POINT2D_IDX
        # We need to know the POINT2D_IDX for each point in its image.
        # So we create a mapping from point3d_id_0based to its track.
        
        for fidx in range(N):
            for p2d_idx, point3d_id_0based in enumerate(points_by_frame[fidx]):
                points_by_frame[fidx][p2d_idx] = (point3d_id_0based, p2d_idx)
                
        # Now track_dict[point3d_id_0based] = [(img_id, p2d_idx), ...]
        track_dict = {p: [] for p in range(P)}
        for fidx in range(N):
            img_id = fidx + 1
            for point3d_id_0based, p2d_idx in points_by_frame[fidx]:
                track_dict[point3d_id_0based].append(f"{img_id} {p2d_idx}")
                
        for i in range(P):
            pid = i + 1
            xyz = points3d[i]
            rgb = points_rgb[i]
            track_str = " ".join(track_dict[i])
            f.write(f"{pid} {xyz[0]} {xyz[1]} {xyz[2]} {int(rgb[0])} {int(rgb[1])} {int(rgb[2])} 0.0 {track_str}\n")
