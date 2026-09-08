import os

for module in ["diff-gaussian-rasterization", "simple-knn"]:
    path = f"gaussian_splatting/submodules/{module}/setup.py"
    with open(path, "r") as f:
        code = f.read()
    
    if "-allow-unsupported-compiler" not in code:
        code = code.replace('"nvcc": [', '"nvcc": ["-allow-unsupported-compiler", ')
        code = code.replace("'nvcc': [", "'nvcc': ['-allow-unsupported-compiler', ")
        with open(path, "w") as f:
            f.write(code)
        print(f"[✓] Secured {module}")