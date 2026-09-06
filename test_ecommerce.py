import sys
import time
import requests
import subprocess
import json
import random

ADMIN_TOKEN = "f3c9a1d5-89b2-4d7c-9304-4b486b8c47d2"
CANARY_URL = "http://localhost:8081"
STABLE_URL = "http://localhost:8080"

def test_endpoints(url, name):
    print(f"\n--- Testing Endpoints on {name} ({url}) ---")
    
    # 1. Root / UI
    r = requests.get(url)
    assert r.status_code == 200
    assert "html" in r.headers.get("content-type", "").lower()
    print("✅ Frontend loads correctly")

    # 2. Health
    r = requests.get(f"{url}/health")
    assert r.status_code == 200
    print("✅ /health works")

    # 3. Metrics
    r = requests.get(f"{url}/metrics")
    assert r.status_code == 200
    assert "app_requests_total" in r.text
    print("✅ /metrics works")

    # 4. E-commerce: Products
    r = requests.get(f"{url}/api/products")
    assert r.status_code == 200
    products = r.json()
    assert len(products) > 0
    print("✅ /api/products returns products")

    # 5. E-commerce: Auth Flow
    email = f"test_{random.randint(1000, 9999)}@example.com"
    pw = "password123"
    r = requests.post(f"{url}/api/auth/register", json={"email": email, "password": pw})
    assert r.status_code == 200
    print(f"✅ Registered {email}")

    r = requests.post(f"{url}/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200
    token = r.json()["token"]
    print("✅ Logged in successfully")

    headers = {"Authorization": f"Bearer {token}"}

    # 6. E-commerce: Cart
    r = requests.post(f"{url}/api/cart", json={"product_id": products[0]["id"]}, headers=headers)
    assert r.status_code == 200
    r = requests.get(f"{url}/api/cart", headers=headers)
    assert len(r.json()) > 0
    print("✅ Added to cart")

    # 7. E-commerce: Order
    total = products[0]["price"]
    r = requests.post(f"{url}/api/orders", json={"items": r.json(), "total": total}, headers=headers)
    assert r.status_code == 200
    print("✅ Placed order")

    # 8. E-commerce: Check orders
    r = requests.get(f"{url}/api/orders", headers=headers)
    assert r.status_code == 200
    orders = r.json()
    assert len(orders) > 0
    print(f"✅ Retrieved orders. App version recorded: {orders[0]['app_version']}")

def main():
    print("Starting port-forwards...")
    stable_pf = subprocess.Popen(["kubectl", "port-forward", "svc/myapp-stable-svc", "8080:80", "-n", "zero-downtime"], stdout=subprocess.DEVNULL)
    canary_pf = subprocess.Popen(["kubectl", "port-forward", "svc/myapp-canary-svc", "8081:80", "-n", "zero-downtime"], stdout=subprocess.DEVNULL)
    
    time.sleep(3) # wait for port-forward
    
    try:
        # Test Stable (v1.10.0)
        print("NOTE: Stable is 1.10.0 and will NOT have the new ecommerce endpoints, only health/metrics!")
        try:
            r = requests.get(f"{STABLE_URL}/health")
            assert r.status_code == 200
            print("✅ Stable /health works")
        except Exception as e:
            print(f"Stable test failed: {e}")

        # Test Canary (v1.11.0)
        test_endpoints(CANARY_URL, "Canary")
        
    finally:
        stable_pf.terminate()
        canary_pf.terminate()

if __name__ == "__main__":
    main()
