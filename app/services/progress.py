
from __future__ import annotations
import asyncio, time
from typing import Dict, Any

_jobs: Dict[str, Dict[str, Any]] = {}
_lock = asyncio.Lock()

async def create_job(job_id: str):
    async with _lock:
        _jobs[job_id] = {"status": "pending", "progress": 0, "messages": [], "result": None, "started": time.time()}

async def update_job(job_id: str, progress: int, message: str):
    async with _lock:
        if job_id in _jobs:
            _jobs[job_id]["progress"] = progress
            _jobs[job_id]["messages"].append({"ts": time.time(), "msg": message})

async def finish_job(job_id: str, result: Any):
    async with _lock:
        if job_id in _jobs:
            _jobs[job_id]["status"] = "done"
            _jobs[job_id]["progress"] = 100
            _jobs[job_id]["result"] = result

async def get_job(job_id: str) -> Dict[str, Any] | None:
    async with _lock:
        return _jobs.get(job_id)
