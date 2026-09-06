import os
import sys
import random
import asyncio
import time
import threading
import math
import json
from typing import Optional, List
from fastapi import FastAPI, Response, HTTPException, Header, BackgroundTasks, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from passlib.context import CryptContext
from jose import jwt
from sqlalchemy import text
from src.db import engine, init_db

APP_VERSION = os.getenv("APP_VERSION", "1.11.0")
FAIL_RATE = float(os.getenv("FAIL_RATE", "0.0"))
EXTRA_LATENCY_MS = int(os.getenv("EXTRA_LATENCY_MS", "0"))
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "f3c9a1d5-89b2-4d7c-9304-4b486b8c47d2")
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-jwt-key")

init_db()

app = FastAPI()

app.mount("/static", StaticFiles(directory="src/../static"), name="static")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
def get_password_hash(password):
    return pwd_context.hash(password)
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)
def create_access_token(data: dict):
    return jwt.encode(data, JWT_SECRET, algorithm="HS256")

carts: dict[str, list] = {}

PRODUCTS = [
    {"id": 1, "name": "Kubernetes T-Shirt", "price": 25.00, "image": "https://via.placeholder.com/150?text=K8s+T-Shirt"},
    {"id": 2, "name": "Docker Mug", "price": 15.00, "image": "https://via.placeholder.com/150?text=Docker+Mug"},
    {"id": 3, "name": "ArgoCD Hoodie", "price": 45.00, "image": "https://via.placeholder.com/150?text=Argo+Hoodie"},
    {"id": 4, "name": "Prometheus Sticker", "price": 3.00, "image": "https://via.placeholder.com/150?text=Prometheus+Sticker"},
    {"id": 5, "name": "Grafana Dashboard Print", "price": 30.00, "image": "https://via.placeholder.com/150?text=Grafana+Print"},
    {"id": 6, "name": "Kyverno Keychain", "price": 8.00, "image": "https://via.placeholder.com/150?text=Kyverno+Keychain"}
]

class UserAuth(BaseModel):
    email: str
    password: str

class CartItem(BaseModel):
    product_id: int

class OrderRequest(BaseModel):
    items: list[int]
    total: float

@app.get("/api/products")
async def get_products():
    return PRODUCTS

@app.post("/api/auth/register")
async def register(user: UserAuth):
    hashed = get_password_hash(user.password)
    try:
        with engine.connect() as conn:
            conn.execute(
                text("INSERT INTO users (email, hashed_password) VALUES (:email, :hashed)"),
                {"email": user.email, "hashed": hashed}
            )
            conn.commit()
    except Exception:
        raise HTTPException(status_code=400, detail="Email already exists")
    return {"message": "registered successfully"}

@app.post("/api/auth/login")
async def login(user: UserAuth):
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT id, hashed_password FROM users WHERE email = :email"),
            {"email": user.email}
        ).fetchone()
    if not result or not verify_password(user.password, result[1]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_access_token({"sub": str(result[0]), "email": user.email})
    return {"token": token}

def get_current_user(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return int(payload.get("sub"))
    except:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.get("/api/cart")
async def get_cart(authorization: str = Header(None)):
    token = authorization.split(" ")[1] if authorization else "anonymous"
    return carts.get(token, [])

@app.post("/api/cart")
async def add_to_cart(item: CartItem, authorization: str = Header(None)):
    token = authorization.split(" ")[1] if authorization else "anonymous"
    if token not in carts:
        carts[token] = []
    carts[token].append(item.product_id)
    return {"status": "added"}

@app.post("/api/orders")
async def create_order(req: OrderRequest, user_id: int = Depends(get_current_user)):
    with engine.connect() as conn:
        conn.execute(
            text("INSERT INTO orders (user_id, items, total, app_version) VALUES (:u, :i, :t, :v)"),
            {"u": user_id, "i": json.dumps(req.items), "t": req.total, "v": APP_VERSION}
        )
        conn.commit()
    # clear cart after order
    # (simplification: we don't clear the in-memory cart here to avoid needing the raw token, 
    # but the frontend will clear it)
    return {"status": "order placed"}

@app.get("/api/orders")
async def get_orders(user_id: int = Depends(get_current_user)):
    with engine.connect() as conn:
        results = conn.execute(
            text("SELECT id, items, total, app_version, created_at FROM orders WHERE user_id = :u ORDER BY created_at DESC"),
            {"u": user_id}
        ).fetchall()
    orders = []
    for r in results:
        orders.append({
            "id": r[0],
            "items": json.loads(r[1]),
            "total": r[2],
            "app_version": r[3],
            "created_at": str(r[4])
        })
    return orders

# ADMIN INJECTION ENDPOINTS
REQUESTS = Counter("app_requests_total", "Total app requests", ["endpoint", "status"])
LATENCY = Histogram("app_request_latency_seconds", "App request latency", ["endpoint"])
active_failure = None
stress_event = threading.Event()
memory_stress_ref = None

class InjectRequest(BaseModel):
    type: str
    duration_seconds: int
    intensity: str

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
    if req.type == "cpu_stress":
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
    return {"status": "active_failure", "failure": active_failure, "remaining_seconds": int(remaining)}

@app.get("/", response_class=HTMLResponse)
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
        
        # Read the static index.html and return it
        try:
            # When running in uvicorn, CWD is usually app/
            with open("static/index.html", "r") as f:
                content = f.read()
            return HTMLResponse(content=content)
        except Exception:
            return HTMLResponse(content="<h1>Welcome</h1><p>index.html not found</p>")

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/version")
async def version():
    return {"version": APP_VERSION}

@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
