import os
import random
import asyncio
from fastapi import FastAPI, Response, HTTPException
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

APP_VERSION = os.getenv("APP_VERSION", "1.9.0")
FAIL_RATE = float(os.getenv("FAIL_RATE", "0.0"))
EXTRA_LATENCY_MS = int(os.getenv("EXTRA_LATENCY_MS", "0"))

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

@app.get("/")
async def root():
    with LATENCY.labels(endpoint="/").time():
        if EXTRA_LATENCY_MS > 0:
            await asyncio.sleep(EXTRA_LATENCY_MS / 1000.0)
        
        if random.random() < FAIL_RATE:
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
