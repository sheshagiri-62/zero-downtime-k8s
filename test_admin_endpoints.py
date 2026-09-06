import sys
import time
import requests
import subprocess
import json

ADMIN_TOKEN = "f3c9a1d5-89b2-4d7c-9304-4b486b8c47d2"
HEADERS = {"X-Admin-Token": ADMIN_TOKEN}
CANARY_URL = "http://localhost:8081"
STABLE_URL = "http://localhost:8080"

def inject(type_, duration, intensity="medium"):
    url = f"{CANARY_URL}/admin/inject"
    data = {"type": type_, "duration_seconds": duration, "intensity": intensity}
    resp = requests.post(url, headers=HEADERS, json=data)
    print(f"Inject {type_}: {resp.status_code} {resp.text}")
    return resp

def check_status(url, name):
    try:
        resp = requests.get(f"{url}/admin/status")
        print(f"{name} status: {resp.status_code} {resp.text}")
        return resp
    except Exception as e:
        print(f"{name} status error: {e}")

def check_traffic(url, name):
    try:
        start = time.time()
        resp = requests.get(url, timeout=2)
        elapsed = time.time() - start
        print(f"{name} traffic: {resp.status_code} in {elapsed:.3f}s")
        return resp.status_code, elapsed
    except Exception as e:
        print(f"{name} traffic error: {e}")
        return 500, 0

def test_failure(type_, duration, intensity="medium"):
    print(f"\n--- Testing {type_} ({intensity}) ---")
    inject(type_, duration, intensity)
    check_status(CANARY_URL, "Canary")
    check_status(STABLE_URL, "Stable")
    
    print("Checking traffic during injection...")
    time.sleep(1) # wait for effect
    for _ in range(3):
        check_traffic(CANARY_URL, "Canary")
        check_traffic(STABLE_URL, "Stable")
        time.sleep(0.5)
        
    print(f"Waiting for {duration}s for auto-revert...")
    time.sleep(duration + 1)
    
    check_status(CANARY_URL, "Canary")

def main():
    print("Starting port-forwards...")
    stable_pf = subprocess.Popen(["kubectl", "port-forward", "svc/myapp-stable-svc", "8080:80", "-n", "zero-downtime"], stdout=subprocess.DEVNULL)
    canary_pf = subprocess.Popen(["kubectl", "port-forward", "svc/myapp-canary-svc", "8081:80", "-n", "zero-downtime"], stdout=subprocess.DEVNULL)
    
    time.sleep(3) # wait for port-forward
    
    try:
        # Test 500
        test_failure("http_500", 5, "high")
        
        # Test latency
        test_failure("latency", 5, "high")
        
        # Test CPU stress
        test_failure("cpu_stress", 5, "medium")
        
        # Test Memory stress
        test_failure("memory_stress", 5, "high")
        
        # Test Crash
        print("\n--- Testing crash ---")
        inject("crash", 5, "medium")
        time.sleep(3)
        print("Checking pod restarts...")
        subprocess.run(["kubectl", "get", "pods", "-n", "zero-downtime", "-l", "app=myapp"])
    finally:
        stable_pf.terminate()
        canary_pf.terminate()

if __name__ == "__main__":
    main()
