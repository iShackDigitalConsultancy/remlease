import requests
import json
import time

API_URL = "https://rem-leases-production.up.railway.app"

def run_tests():
    res = requests.post(f"{API_URL}/api/auth/login", data={
        "username": "jack@bootlegger.co.za",
        "password": "123456789"
    })
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    ws_res = requests.get(f"{API_URL}/api/workspaces", headers=headers)
    workspaces = ws_res.json()

    lease_id = None
    for w in workspaces:
        for d in w.get("documents", []):
            if "lease" in d["name"].lower() and not lease_id:
                lease_id = d["id"]

    print(f"Lease ID: {lease_id}")
    
    def time_request():
        start = time.time()
        req = requests.post(
            f"{API_URL}/api/extract-expiries", 
            json={"doc_ids": [lease_id]}, 
            headers=headers, 
            stream=True
        )
        acc = ""
        for chunk in req.iter_content(chunk_size=1024):
            if chunk:
                acc += chunk.decode('utf-8')
        end = time.time()
        return end - start, acc

    print("\n--- Cache Test: Part 1 (First Call) ---")
    first_time, _ = time_request()
    print(f"First call response time: {first_time:.2f} seconds")

    print("\n--- Cache Test: Part 2 (Second Call) ---")
    second_time, _ = time_request()
    print(f"Second call response time: {second_time:.2f} seconds")

if __name__ == "__main__":
    run_tests()
