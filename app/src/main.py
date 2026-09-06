import os
import sys
import random
import asyncio
import time
import threading
import math
from typing import Optional
from fastapi import FastAPI, Response, HTTPException, Header, BackgroundTasks, Depends
from pydantic import BaseModel
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

APP_VERSION = os.getenv("APP_VERSION", "1.10.0")
FAIL_RATE = float(os.getenv("FAIL_RATE", "0.0"))
EXTRA_LATENCY_MS = int(os.getenv("EXTRA_LATENCY_MS", "0"))
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "f3c9a1d5-89b2-4d7c-9304-4b486b8c47d2")

app = FastAPI()

REQUESTS = Counter(
    "app_requests_total",
    "Total app requests",
    ["endpoint", "status"]
)

LATENCY = Histogram(
    "app_request_latency_seconds",
    "App request latency",
    ["endpoint"]
)

active_failure = None
stress_event = threading.Event()
memory_stress_ref = None

class InjectRequest(BaseModel):
    type: str # http_500, latency, cpu_stress, memory_stress, crash
    duration_seconds: int
    intensity: str # low, medium, high

async def _auto_revert(duration: int):
    await asyncio.sleep(duration)
    global active_failure, memory_stress_ref
    active_failure = None
    stress_event.set()
    memory_stress_ref = None

def _cpu_stress_worker():
    while not stress_event.is_set():
        math.factorial(1000)

def require_admin_token(x_admin_token: str = Header(...)):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")

@app.post("/admin/inject")
async def inject_failure(req: InjectRequest, bg_tasks: BackgroundTasks, _ = Depends(require_admin_token)):
    global active_failure, memory_stress_ref
    
    active_failure = None
    stress_event.set()
    memory_stress_ref = None
    
    active_failure = {
        "type": req.type,
        "intensity": req.intensity,
        "duration_seconds": req.duration_seconds,
        "expires_at": time.time() + req.duration_seconds
    }
    
    if req.type == "http_500":
        pass
    elif req.type == "latency":
        pass
    elif req.type == "cpu_stress":
        stress_event.clear()
        threads = 1
        if req.intensity == "medium": threads = 2
        elif req.intensity == "high": threads = 4
        for _ in range(threads):
            threading.Thread(target=_cpu_stress_worker, daemon=True).start()
    elif req.type == "memory_stress":
        size_mb = 100
        if req.intensity == "medium": size_mb = 300
        elif req.intensity == "high": size_mb = 600
        memory_stress_ref = bytearray(size_mb * 1024 * 1024)
    elif req.type == "crash":
        def _crash_delayed():
            time.sleep(2)
            os._exit(1)
        threading.Thread(target=_crash_delayed, daemon=True).start()
        return {"status": "crashing in 2s"}
    
    bg_tasks.add_task(_auto_revert, req.duration_seconds)
    
    return {"status": "injected", "state": active_failure}

@app.post("/admin/clear")
async def clear_failure(_ = Depends(require_admin_token)):
    global active_failure, memory_stress_ref
    active_failure = None
    stress_event.set()
    memory_stress_ref = None
    return {"status": "cleared"}

@app.get("/admin/status")
async def get_status():
    if not active_failure:
        return {"status": "normal"}
    remaining = active_failure["expires_at"] - time.time()
    if remaining <= 0:
        return {"status": "normal"}
    return {
        "status": "active_failure",
        "failure": active_failure,
        "remaining_seconds": int(remaining)
    }

@app.get("/")
async def root():
    current_latency = EXTRA_LATENCY_MS
    current_fail_rate = FAIL_RATE
    
    if active_failure and active_failure["expires_at"] > time.time():
        if active_failure["type"] == "latency":
            if active_failure["intensity"] == "low": current_latency = 500
            elif active_failure["intensity"] == "medium": current_latency = 1500
            elif active_failure["intensity"] == "high": current_latency = 4000
        elif active_failure["type"] == "http_500":
            if active_failure["intensity"] == "low": current_fail_rate = 0.2
            elif active_failure["intensity"] == "medium": current_fail_rate = 0.5
            elif active_failure["intensity"] == "high": current_fail_rate = 0.9

    with LATENCY.labels(endpoint="/").time():
        if current_latency > 0:
            await asyncio.sleep(current_latency / 1000.0)
        
        if random.random() < current_fail_rate:
            REQUESTS.labels(endpoint="/", status=500).inc()
            raise HTTPException(status_code=500, detail="Random failure injected")
            
        REQUESTS.labels(endpoint="/", status=200).inc()
        return {"message": "hello", "version": APP_VERSION}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/version")
async def version():
    return {"version": APP_VERSION}

@app.get("/api")
async def api():
    return {"data": "sample", "version": APP_VERSION}

@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
