"""
verify_pipeline_imports.py — Verify that all pipeline modules and third-party bindings import properly.
"""
import sys
from pathlib import Path

# Add repo root to path
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))

print(f"Python Executable: {sys.executable}")
print(f"Python Version:    {sys.version.split()[0]}")
print(f"Repository Root:   {repo_root}\n")

failures = []

modules_to_test = [
    ("src.pipeline.ingest_telemetry", "Telemetry Ingestion"),
    ("src.pipeline.vggt_inference", "VGGT Dense Inference"),
    ("src.pipeline.vggt_quality_gate", "VGGT Quality Gate"),
    ("src.pipeline.metric_alignment", "Sim3 Metric Alignment"),
    ("src.pipeline.depth_fusion", "TSDF Depth Fusion"),
    ("src.pipeline.mask_dynamics", "Dynamic Masking"),
    ("run_mesh_pipeline", "Root Mesh Pipeline CLI")
]

for mod_name, desc in modules_to_test:
    try:
        __import__(mod_name)
        print(f"  [PASS] {desc} ({mod_name})")
    except Exception as e:
        print(f"  [FAIL] {desc} ({mod_name}): {e}")
        failures.append((mod_name, str(e)))

print("\n" + "=" * 50)
if failures:
    print(f"FAIL: {len(failures)} module(s) failed import verification.")
    for mod, err in failures:
        print(f"  - {mod}: {err}")
    sys.exit(1)
else:
    print("SUCCESS: All pipeline modules imported cleanly!")
    sys.exit(0)
