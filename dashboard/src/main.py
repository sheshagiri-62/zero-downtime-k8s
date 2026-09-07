from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import httpx
import os
import asyncio
from typing import Optional

# Re-using logic from policy-engine
from src.collector import PrometheusCollector
from src.rules import RuleEngine
from src.scoring import safety_score
from src.rollout_controller import get_rollout_status
from src.db import engine

app = FastAPI()

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "f3c9a1d5-89b2-4d7c-9304-4b486b8c47d2")
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090")

collector = PrometheusCollector(PROMETHEUS_URL)
rule_engine = RuleEngine()

STABLE_URL = "http://myapp-stable-svc.zero-downtime.svc.cluster.local"
CANARY_URL = "http://myapp-canary-svc.zero-downtime.svc.cluster.local"

# Mount static files
app.mount("/ui", StaticFiles(directory="static", html=True), name="static")


@app.get("/api/cluster")
async def get_cluster():
    import subprocess, json
    result = {"nodes_ready": 0, "nodes_total": 0, "pods_running": 0, "pods_total": 0, "error": None}
    try:
        r = subprocess.run(["kubectl", "get", "nodes", "-o", "json"], capture_output=True, text=True, timeout=5)
        nodes = json.loads(r.stdout).get("items", [])
        result["nodes_total"] = len(nodes)
        result["nodes_ready"] = sum(
            1 for n in nodes
            if any(c["type"] == "Ready" and c["status"] == "True" for c in n["status"].get("conditions", []))
        )
        r2 = subprocess.run(["kubectl", "get", "pods", "-n", "zero-downtime", "-o", "json"], capture_output=True, text=True, timeout=5)
        pods = json.loads(r2.stdout).get("items", [])
        result["pods_total"] = len(pods)
        result["pods_running"] = sum(1 for p in pods if p.get("status", {}).get("phase") == "Running")
    except Exception as e:
        result["error"] = str(e)[:200]
    return result


@app.get("/api/metrics")
async def get_metrics():
    try:
        snapshot = collector.get_snapshot("zero-downtime")
        violations = rule_engine.evaluate(snapshot)
        violation_names = {v.rule_name for v in violations}
        score = safety_score(violations)
        classification = "healthy" if score >= 80 else ("critical" if score < 50 else "degraded")
        rules_display = [
            {"name": "Error Rate",   "value": f"{snapshot.get('error_rate_pct', 0):.1f}%",    "threshold": "< 5%",    "status": "fail" if any("error_rate" in n for n in violation_names) else "pass"},
            {"name": "P95 Latency",  "value": f"{snapshot.get('p95_latency_ms', 0):.0f} ms",  "threshold": "< 500ms", "status": "fail" if any("latency" in n for n in violation_names) else "pass"},
            {"name": "Request Rate", "value": f"{snapshot.get('request_rate', 0):.1f} req/s",  "threshold": "N/A",     "status": "pass"},
            {"name": "Ready Pods",   "value": f"{snapshot.get('ready_pods', 0):.0f}",          "threshold": ">= 4",    "status": "fail" if any("pods" in n for n in violation_names) else "pass"},
            {"name": "Pod Restarts", "value": f"{snapshot.get('pod_restarts_5m', 0):.0f}",     "threshold": "0",       "status": "fail" if any("restart" in n for n in violation_names) else "pass"},
        ]
        return {"snapshot": snapshot, "rules": rules_display, "warnings": sum(1 for v in violations if v.severity == "warning"), "criticals": sum(1 for v in violations if v.severity == "critical"), "score": score, "classification": classification}
    except Exception as e:
        return {"snapshot": {}, "rules": [], "warnings": 0, "criticals": 0, "score": None, "classification": "unknown", "error": str(e)[:200]}


@app.get("/api/pipeline")
async def get_pipeline():
    try:
        rollout = get_rollout_status("myapp", "zero-downtime")
        phase = rollout.get("phase", "unknown")
        is_active = phase in ["Progressing", "Paused"]
        steps = [
            {"name": "GitHub Push",    "status": "done"},
            {"name": "GitHub Actions", "status": "done"},
            {"name": "Trivy Scan",     "status": "done"},
            {"name": "Cosign Sign",    "status": "done"},
            {"name": "GHCR Push",      "status": "done"},
            {"name": "Argo CD Sync",   "status": "done"},
            {"name": "Argo Rollouts",  "status": "active" if is_active else "done"},
        ]
        return {"steps": steps, "rollout_phase": phase}
    except Exception as e:
        return {"steps": [], "rollout_phase": "unknown", "error": str(e)[:200]}


@app.get("/api/status")
async def get_status():
    try:
        rollout_info = get_rollout_status("myapp", "zero-downtime")
    except Exception as e:
        rollout_info = {"phase": "unknown", "step_index": None, "weight": 0, "is_canary": False, "error": str(e)[:200]}
    
    try:
        metrics = collector.get_snapshot("zero-downtime")
        evaluations = rule_engine.evaluate(metrics)
        score = safety_score(evaluations)
    except Exception as e:
        metrics = {}
        score = None
        evaluations = []
    
    classification = "unknown"
    action = "unknown"
    if score is not None:
        classification = "healthy" if score >= 80 else ("critical" if score < 50 else "degraded")
        action = "promote" if classification == "healthy" else ("abort" if classification == "critical" else "hold")
        
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
