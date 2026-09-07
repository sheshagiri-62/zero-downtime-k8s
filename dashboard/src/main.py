from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import httpx
import os
import asyncio
from typing import Optional

# Re-using logic from policy-engine
from src.collector import PrometheusCollector
from src.rules import evaluate_metrics
from src.scoring import calculate_score, determine_action
from src.rollout_controller import get_rollout_status
from src.db import engine

app = FastAPI()

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "f3c9a1d5-89b2-4d7c-9304-4b486b8c47d2")
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090")

collector = PrometheusCollector(PROMETHEUS_URL)

STABLE_URL = "http://myapp-stable-svc.zero-downtime.svc.cluster.local"
CANARY_URL = "http://myapp-canary-svc.zero-downtime.svc.cluster.local"

# Mount static files
app.mount("/ui", StaticFiles(directory="static", html=True), name="static")

@app.get("/api/status")
async def get_status():
    rollout_info = get_rollout_status("myapp", "zero-downtime")
    metrics = collector.collect_all()
    evaluations = evaluate_metrics(metrics)
    score = calculate_score(evaluations)
    action = determine_action(score)
    
    classification = "healthy"
    if score < 50:
        classification = "critical"
    elif score < 80:
        classification = "degraded"
        
    return {
        "rollout": rollout_info,
        "metrics": metrics,
        "score": score,
        "classification": classification,
        "action": action
    }

@app.get("/api/decisions")
async def get_decisions(limit: int = 20):
    try:
        with engine.connect() as conn:
            from sqlalchemy import text
            result = conn.execute(
                text("SELECT id, decision_timestamp, safety_score, action_taken, reason, snapshot FROM decision_log ORDER BY decision_timestamp DESC LIMIT :limit"),
                {"limit": limit}
            )
            rows = result.fetchall()
            
            decisions = []
            for row in rows:
                decisions.append({
                    "id": row[0],
                    "timestamp": row[1].isoformat() if row[1] else None,
                    "score": row[2],
                    "action": row[3],
                    "reason": row[4],
                    "metrics_snapshot": row[5]
                })
            return {"decisions": decisions}
    except Exception as e:
        return {"decisions": [], "error": str(e)}

@app.get("/api/version-check")
async def check_versions():
    async with httpx.AsyncClient(timeout=2.0) as client:
        stable_ver = "unknown"
        canary_ver = "unknown"
        
        try:
            r1 = await client.get(f"{STABLE_URL}/version")
            if r1.status_code == 200:
                stable_ver = r1.json().get("version", "unknown")
        except:
            pass
            
        try:
            r2 = await client.get(f"{CANARY_URL}/version")
            if r2.status_code == 200:
                canary_ver = r2.json().get("version", "unknown")
        except:
            pass
            
        return {"stable": stable_ver, "canary": canary_ver}

@app.post("/api/inject")
async def inject_failure(request: Request):
    data = await request.json()
    target = data.get("target", "canary")
    
    url = CANARY_URL if target == "canary" else STABLE_URL
    headers = {"X-Admin-Token": ADMIN_TOKEN}
    
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(f"{url}/admin/inject", json=data, headers=headers, timeout=5.0)
            return JSONResponse(status_code=r.status_code, content=r.json())
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/inject/clear")
async def clear_injection():
    headers = {"X-Admin-Token": ADMIN_TOKEN}
    results = {}
    async with httpx.AsyncClient() as client:
        try:
            r1 = await client.post(f"{STABLE_URL}/admin/clear", headers=headers, timeout=2.0)
            results["stable"] = r1.json()
        except Exception as e:
            results["stable"] = {"error": str(e)}
            
        try:
            r2 = await client.post(f"{CANARY_URL}/admin/clear", headers=headers, timeout=2.0)
            results["canary"] = r2.json()
        except Exception as e:
            results["canary"] = {"error": str(e)}
            
    return results

@app.get("/api/inject/status")
async def injection_status():
    headers = {"X-Admin-Token": ADMIN_TOKEN}
    results = {}
    async with httpx.AsyncClient() as client:
        try:
            r1 = await client.get(f"{STABLE_URL}/admin/status", headers=headers, timeout=2.0)
            if r1.status_code == 200:
                results["stable"] = r1.json()
            else:
                results["stable"] = {"status": "unknown"}
        except:
            results["stable"] = {"status": "unreachable"}
            
        try:
            r2 = await client.get(f"{CANARY_URL}/admin/status", headers=headers, timeout=2.0)
            if r2.status_code == 200:
                results["canary"] = r2.json()
            else:
                results["canary"] = {"status": "unknown"}
        except:
            results["canary"] = {"status": "unreachable"}
            
    return results
