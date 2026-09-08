import os
import sys
import subprocess

print("[>>] Installing Prerequisites...")
subprocess.run([sys.executable, "-m", "pip", "install", "fvcore", "iopath"], check=True)

print("[>>] Injecting 64-bit Compiler Override...")
os.environ["DISTUTILS_USE_SDK"] = "1"
os.environ["CL"] = "/D_WIN64 /D_ALLOW_COMPILER_AND_STL_VERSION_MISMATCH"
os.environ["TORCH_NVCC_FLAGS"] = "-D_WIN64 -m64 -D_ALLOW_COMPILER_AND_STL_VERSION_MISMATCH -allow-unsupported-compiler"

print("[>>] Compiling PyTorch3D from Source (This takes 15-30 minutes)...")
subprocess.run([sys.executable, "-m", "pip", "install", "git+https://github.com/facebookresearch/pytorch3d.git", "--no-build-isolation"], check=True)

print("\n[✓] PyTorch3D Installed. Backend 100% Complete.")