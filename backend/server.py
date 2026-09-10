from fastapi import FastAPI, BackgroundTasks, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uuid
import os
import shutil
import time
import subprocess
import json

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

JOBS = {}

class JobStatus:
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

def run_pipeline(job_id: str):
    job = JOBS[job_id]
    job["status"] = JobStatus.RUNNING
    out_dir = os.path.join("outputs", job_id)
    
    try:
        # 1. Ingestion
        job["stage"] = "frame_extraction"
        cmd1 = [
            "python", "src/pipeline/ingest_telemetry.py",
            "--video", job["video_path"],
            "--out", out_dir,
            "--frames", str(job["config"]["frames"])
        ]
        if job["srt_path"]:
            cmd1.extend(["--srt", job["srt_path"]])
        subprocess.run(cmd1, check=True)
        
        # 2. VGGT Inference
        job["stage"] = "vggt_inference"
        print("Running REAL VGGT inference...")
        cmd2 = [
            "python", "src/pipeline/vggt_inference.py",
            "--scene_dir", out_dir
        ]
        subprocess.run(cmd2, check=True)
            
        # 3. Metric Alignment
        job["stage"] = "metric_alignment"
        if job["srt_path"]:
            cmd3 = [
                "python", "src/pipeline/metric_alignment.py",
                "--scene_dir", out_dir,
                "--telemetry", os.path.join(out_dir, "telemetry_index.json")
            ]
            # We add pythonioencoding just to be safe on Windows
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf8"
            subprocess.run(cmd3, check=True, env=env)
            job["is_metric"] = True
        else:
            job["is_metric"] = False
            
        # 4. Depth Fusion
        job["stage"] = "mesh_reconstruction"
        cmd4 = [
            "python", "src/pipeline/depth_fusion.py",
            "--scene_dir", out_dir,
            "--method", job["config"]["mesh_method"],
            "--output", "metric_mesh.ply" if job["is_metric"] else "raw_mesh.ply"
        ]
        subprocess.run(cmd4, check=True)
        
        job["status"] = JobStatus.COMPLETED
        job["mesh_file"] = "metric_mesh.ply" if job["is_metric"] else "raw_mesh.ply"
        
    except subprocess.CalledProcessError as e:
        job["status"] = JobStatus.FAILED
        job["error"] = f"Command failed with exit code {e.returncode}"
    except Exception as e:
        job["status"] = JobStatus.FAILED
        job["error"] = str(e)


@app.post("/api/jobs")
async def create_job(
    video: UploadFile = File(...),
    srt: UploadFile = File(None),
    mode: str = Form("demo"),
    frames: int = Form(8),
    skip_masking: bool = Form(True),
    mesh_method: str = Form("poisson")
):
    job_id = str(uuid.uuid4())[:8]
    job_dir = os.path.join("outputs", job_id, "input")
    os.makedirs(job_dir, exist_ok=True)
    
    video_path = os.path.join(job_dir, video.filename)
    with open(video_path, "wb") as buffer:
        shutil.copyfileobj(video.file, buffer)
        
    srt_path = None
    if srt:
        srt_path = os.path.join(job_dir, srt.filename)
        with open(srt_path, "wb") as buffer:
            shutil.copyfileobj(srt.file, buffer)
            
    JOBS[job_id] = {
        "job_id": job_id,
        "status": JobStatus.CREATED,
        "config": {
            "mode": mode,
            "frames": frames,
            "skip_masking": skip_masking,
            "mesh_method": mesh_method,
            "has_srt": bool(srt)
        },
        "video_path": video_path,
        "srt_path": srt_path,
        "is_metric": False,
        "created_at": time.time()
    }
    
    return {"job_id": job_id, "status": "created", "config": JOBS[job_id]["config"]}


@app.post("/api/jobs/{job_id}/start")
async def start_job(job_id: str, background_tasks: BackgroundTasks):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
        
    job = JOBS[job_id]
    if job["status"] != JobStatus.CREATED:
        raise HTTPException(status_code=409, detail="Job already running or completed")
        
    background_tasks.add_task(run_pipeline, job_id)
    return {"job_id": job_id, "status": "running", "message": "Processing started"}


@app.get("/api/jobs/{job_id}/status")
def get_job_status(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    job = JOBS[job_id]
    return {
        "job_id": job_id,
        "status": job["status"],
        "stage": job.get("stage", "pending"),
        "error": job.get("error")
    }

@app.get("/api/jobs/{job_id}/result")
def get_job_result(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    job = JOBS[job_id]
    if job["status"] != JobStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Job not yet completed")
        
    return {
        "job_id": job_id,
        "status": "completed",
        "mesh_file": job["mesh_file"],
        "mesh_url": f"/api/jobs/{job_id}/mesh",
        "viewer_mesh_url": f"/api/jobs/{job_id}/mesh?detail=viewer",
        "is_metric": job.get("is_metric", False),
        "coordinate_frame": "enu" if job.get("is_metric") else "vggt_arbitrary"
    }

@app.get("/api/jobs/{job_id}/mesh")
def get_job_mesh(job_id: str, detail: str = "full"):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    job = JOBS[job_id]
    mesh_path = os.path.join("outputs", job_id, job["mesh_file"])
    if not os.path.exists(mesh_path):
        raise HTTPException(status_code=404, detail="Mesh file not found")
    return FileResponse(mesh_path)

@app.get("/api/jobs")
def list_jobs():
    return {"jobs": [
        {
            "job_id": jid,
            "status": j["status"],
            "is_metric": j.get("is_metric", False)
        } for jid, j in JOBS.items()
    ]}

class MeasureDistanceReq(BaseModel):
    point_a: list[float]
    point_b: list[float]

@app.post("/api/jobs/{job_id}/measure/distance")
def measure_distance(job_id: str, req: MeasureDistanceReq):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    job = JOBS[job_id]
    if job["status"] != JobStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Job not completed")
        
    mesh_path = os.path.join("outputs", job_id, job["mesh_file"])
    
    cmd = [
        "python", "src/pipeline/measurement.py",
        "--mesh", mesh_path,
        "--p1", str(req.point_a[0]), str(req.point_a[1]), str(req.point_a[2]),
        "--p2", str(req.point_b[0]), str(req.point_b[1]), str(req.point_b[2])
    ]
    if job.get("is_metric"):
        cmd.append("--metric")
        
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Measurement failed: {res.stderr}")
        
    try:
        out = json.loads(res.stdout)
        return {
            "value": out["distance"],
            "unit": "m" if out["is_metric"] else "arbitrary",
            "is_metric": out["is_metric"],
            "point_a": req.point_a,
            "point_b": req.point_b
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to parse measurement output")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000)
