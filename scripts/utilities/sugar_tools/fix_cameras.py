import os
import struct
import shutil

cam_path = r"..\outputs\test_scene\sparse\0\cameras.bin"
backup_path = r"..\outputs\test_scene\sparse\0\cameras_backup.bin"

print("Reading COLMAP camera binary...")

# Create a safe backup of your original data
if not os.path.exists(backup_path):
    shutil.copy(cam_path, backup_path)

with open(backup_path, "rb") as f:
    num_cameras = struct.unpack("<Q", f.read(8))[0]
    cams = []
    for _ in range(num_cameras):
        camera_id = struct.unpack("<I", f.read(4))[0]
        model_id = struct.unpack("<i", f.read(4))[0]
        width = struct.unpack("<Q", f.read(8))[0]
        height = struct.unpack("<Q", f.read(8))[0]
        
        # Read the exact number of parameters based on the distortion model
        if model_id == 0: num_params = 3
        elif model_id in [1, 2]: num_params = 4
        elif model_id == 3: num_params = 5
        elif model_id == 6: num_params = 12
        else: num_params = 8
        
        params = struct.unpack("<" + "d"*num_params, f.read(8*num_params))
        cams.append((camera_id, model_id, width, height, params))

print(f"Found {num_cameras} camera(s). Forcing PINHOLE conversion...")

# Overwrite with clean PINHOLE parameters to bypass the 3DGS block
with open(cam_path, "wb") as f:
    f.write(struct.pack("<Q", num_cameras))
    for cam in cams:
        cam_id, mod_id, w, h, p = cam
        
        if mod_id in [0, 2, 3]: # Simple Pinhole, Simple Radial, Radial
            fx = fy = p[0]
            cx, cy = p[1], p[2]
        else:
            fx, fy, cx, cy = p[0], p[1], p[2], p[3]
        
        f.write(struct.pack("<I", cam_id))
        f.write(struct.pack("<i", 1)) # Force Model ID 1 (PINHOLE)
        f.write(struct.pack("<Q", w))
        f.write(struct.pack("<Q", h))
        f.write(struct.pack("<dddd", fx, fy, cx, cy))

print("[✓] Camera distortion successfully bypassed!")