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
from src.rollout_controller import get_rollout_status, promote, abort
from src.db import engine

app = FastAPI()

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "f3c9a1d5-89b2-4d7c-9304-4b486b8c47d2")
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090")

collector = PrometheusCollector(PROMETHEUS_URL)
rule_engine = RuleEngine()

STABLE_URL = "http://myapp-stable-svc.zero-downtime.svc.cluster.local"
CANARY_URL = "http://myapp-canary-svc.zero-downtime.svc.cluster.local"

# NOTE: app.mount() is at the BOTTOM of this file to ensure
# all /api/* routes are registered before the static file catch-all.

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

auto_policy_enabled = False

def log_decision_to_db(rollout_phase: str, step_weight: int, score: float, classification: str, decision: str, action_taken: str, reason: str, snapshot: dict = None):
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            import json
            conn.execute(
                text("""
                    INSERT INTO decision_log (
                        rollout_name, namespace, rollout_phase, step_weight,
                        safety_score, classification, decision, action_taken, action_success, reason, snapshot
                    ) VALUES (
                        'myapp', 'zero-downtime', :phase, :weight,
                        :score, :classification, :decision, :action_taken, true, :reason, :snapshot
                    )
                """),
                {
                    "phase": rollout_phase,
                    "weight": step_weight,
                    "score": score,
                    "classification": classification.upper() if classification else "UNKNOWN",
                    "decision": decision.upper() if decision else "UNKNOWN",
                    "action_taken": action_taken,
                    "reason": reason,
                    "snapshot": json.dumps(snapshot) if snapshot else None
                }
            )
            conn.commit()
    except Exception as e:
        print(f"Error logging decision to DB: {e}")

async def auto_policy_background_worker():
    global auto_policy_enabled
    while True:
        await asyncio.sleep(10)
        if not auto_policy_enabled:
            continue
        try:
            r_status = get_rollout_status("myapp", "zero-downtime")
            phase = r_status.get("phase")
            if phase == "Paused":
                metrics = collector.get_snapshot("zero-downtime")
                evaluations = rule_engine.evaluate(metrics)
                score = safety_score(evaluations)
                classification = "healthy" if score >= 80 else ("critical" if score < 50 else "degraded")
                if classification == "healthy":
                    promote("myapp", "zero-downtime")
                    log_decision_to_db(phase, r_status.get("weight", 0), score, classification, "PROMOTE", "promote", f"Auto-policy promoted step (score: {score:.1f})", metrics)
                elif classification == "critical":
                    abort("myapp", "zero-downtime")
                    log_decision_to_db(phase, r_status.get("weight", 0), score, classification, "ABORT", "abort", f"Auto-policy aborted rollout due to critical score: {score:.1f}", metrics)
        except Exception as e:
            print(f"Auto policy worker error: {e}")

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(auto_policy_background_worker())

@app.get("/api/version-check")
async def check_versions():
    stable_ver = "unknown"
    canary_ver = "unknown"
    
    # Check pod image tags in Kubernetes directly
    try:
        import subprocess, json
        r_rollout = subprocess.run(["kubectl", "get", "rollout", "myapp", "-n", "zero-downtime", "-o", "json"], capture_output=True, text=True, timeout=5)
        stable_hash = None
        canary_hash = None
        if r_rollout.returncode == 0:
            ro_data = json.loads(r_rollout.stdout)
            stable_hash = ro_data.get("status", {}).get("stableRS")
            canary_hash = ro_data.get("status", {}).get("currentPodHash")
            
        r_pods = subprocess.run(["kubectl", "get", "pods", "-n", "zero-downtime", "-l", "app=myapp", "-o", "json"], capture_output=True, text=True, timeout=5)
        if r_pods.returncode == 0:
            items = json.loads(r_pods.stdout).get("items", [])
            for p in items:
                img = p.get("spec", {}).get("containers", [{}])[0].get("image", "")
                clean_img = img.split("@")[0]
                tag = clean_img.split(":")[-1] if ":" in clean_img else clean_img
                pod_hash = p.get("metadata", {}).get("labels", {}).get("rollouts-pod-template-hash")
                
                if canary_hash and pod_hash == canary_hash:
                    canary_ver = tag
                elif stable_hash and pod_hash == stable_hash:
                    stable_ver = tag
                elif not canary_hash and "c5977c65c" in str(pod_hash):
                    canary_ver = tag
                elif not stable_hash and "6d7d77ccd7" in str(pod_hash):
                    stable_ver = tag
    except Exception:
        pass
        
    # Fallback to HTTP endpoints if pod check didn't resolve
    if stable_ver == "unknown" or canary_ver == "unknown":
        async with httpx.AsyncClient(timeout=2.0) as client:
            try:
                r1 = await client.get(f"{STABLE_URL}/version")
                if r1.status_code == 200 and stable_ver == "unknown":
                    stable_ver = r1.json().get("version", "unknown")
            except:
                pass
            try:
                r2 = await client.get(f"{CANARY_URL}/version")
                if r2.status_code == 200 and canary_ver == "unknown":
                    canary_ver = r2.json().get("version", "unknown")
            except:
                pass
                
    return {"stable": stable_ver, "canary": canary_ver}

@app.post("/api/rollout/promote")
async def api_promote():
    try:
        promote("myapp", "zero-downtime")
        status = get_rollout_status("myapp", "zero-downtime")
        metrics = collector.get_snapshot("zero-downtime")
        evals = rule_engine.evaluate(metrics)
        score = safety_score(evals)
        log_decision_to_db(status.get("phase", "Paused"), status.get("weight", 0), score, "healthy", "PROMOTE", "promote", "Manual UI Promote clicked", metrics)
        return {"status": "promoted", "rollout": status}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/rollout/abort")
async def api_abort():
    try:
        abort("myapp", "zero-downtime")
        status = get_rollout_status("myapp", "zero-downtime")
        metrics = collector.get_snapshot("zero-downtime")
        evals = rule_engine.evaluate(metrics)
        score = safety_score(evals)
        log_decision_to_db(status.get("phase", "Aborted"), status.get("weight", 0), score, "critical", "ABORT", "abort", "Manual UI Abort clicked", metrics)
        return {"status": "aborted", "rollout": status}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/policy/auto")
async def get_auto_policy():
    global auto_policy_enabled
    return {"auto_policy": auto_policy_enabled}

@app.post("/api/policy/auto")
async def toggle_auto_policy(request: Request):
    global auto_policy_enabled
    try:
        body = await request.json()
        auto_policy_enabled = bool(body.get("enabled", not auto_policy_enabled))
    except:
        auto_policy_enabled = not auto_policy_enabled
    return {"auto_policy": auto_policy_enabled}

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
                results["stable"] = {"status": "normal"}
        except:
            results["stable"] = {"status": "unreachable"}
            
        try:
            r2 = await client.get(f"{CANARY_URL}/admin/status", headers=headers, timeout=2.0)
            if r2.status_code == 200:
                results["canary"] = r2.json()
            else:
                results["canary"] = {"status": "normal"}
        except:
            results["canary"] = {"status": "unreachable"}
            
    return results

# Mount static files LAST — must be after all /api/* routes
app.mount("/ui", StaticFiles(directory="static", html=True), name="static")

