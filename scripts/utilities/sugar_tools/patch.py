import os
import torch

print("Applying C++ Build Patches...")

# 1. Patch PyTorch Math Headers
header = os.path.join(os.path.dirname(torch.__file__), 'include', 'c10', 'util', 'safe_numerics.h')
with open(header, 'r') as f:
    content = f.read()
if '#include <intrin.h>' not in content:
    with open(header, 'w') as f:
        f.write('#include <intrin.h>\n' + content)
    print("[✓] Patched PyTorch safe_numerics.h")

# 2. Force NVCC to bypass Visual Studio locks
for module in ["diff-gaussian-rasterization", "simple-knn"]:
    setup_file = os.path.join("gaussian_splatting", "submodules", module, "setup.py")
    with open(setup_file, 'r') as f:
        code = f.read()
    if 'TORCH_NVCC_FLAGS' not in code:
        code = 'import os\nos.environ["TORCH_NVCC_FLAGS"] = "-allow-unsupported-compiler"\n' + code
        with open(setup_file, 'w') as f:
            f.write(code)
        print(f"[✓] Patched {module} setup.py")