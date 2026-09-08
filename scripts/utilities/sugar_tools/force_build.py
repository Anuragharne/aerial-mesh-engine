import os
import sys
import subprocess
import torch

print("Initiating Override Protocol...")

# 1. Hack PyTorch to include the deleted Microsoft math header
header = os.path.join(os.path.dirname(torch.__file__), 'include', 'c10', 'util', 'safe_numerics.h')
with open(header, 'r') as f:
    content = f.read()
if '#include <intrin.h>' not in content:
    with open(header, 'w') as f:
        f.write('#include <intrin.h>\n' + content)
    print("[✓] Restored missing Microsoft intrin.h header")

# 2. Inject environment variables directly into Python (Terminal cannot drop them now)
os.environ["DISTUTILS_USE_SDK"] = "1"
# Force 64-bit architecture and bypass the VS 2026 STL blockade
os.environ["CL"] = "/D_WIN64 /D_ALLOW_COMPILER_AND_STL_VERSION_MISMATCH"
os.environ["TORCH_NVCC_FLAGS"] = "-D_WIN64 -m64 -D_ALLOW_COMPILER_AND_STL_VERSION_MISMATCH -allow-unsupported-compiler"
print("[✓] Hardcoded pure 64-bit architecture and compiler bypass")

# 3. Force Compilation
print("\n[>>] Compiling Diff-Gaussian-Rasterization (Takes 1-2 mins)...")
subprocess.run([sys.executable, "-m", "pip", "install", ".\\gaussian_splatting\\submodules\\diff-gaussian-rasterization", "--no-build-isolation"], check=True)

print("\n[>>] Compiling Simple-KNN...")
subprocess.run([sys.executable, "-m", "pip", "install", ".\\gaussian_splatting\\submodules\\simple-knn", "--no-build-isolation"], check=True)

print("\n[✓] ALL 3D ENGINES SUCCESSFULLY COMPILED!")