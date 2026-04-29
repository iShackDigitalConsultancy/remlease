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
    franchise_id = None
    for w in workspaces:
        for d in w.get("documents", []):
            if "lease" in d["name"].lower() and not lease_id:
                lease_id = d["id"]
            if ("franchise" in d["name"].lower() or "f/a" in d["name"].lower() or "agreement" in d["name"].lower()) and d["id"] != lease_id and not franchise_id:
                franchise_id = d["id"]

    print(f"Lease ID: {lease_id}, Franchise ID: {franchise_id}")

    # Test B
    print("\n--- Test B: Extract expiries filename ---")
    req = requests.post(f"{API_URL}/api/extract-expiries", json={"doc_ids": [lease_id]}, headers=headers, stream=True)
    print(f"HTTP Status: {req.status_code}")
    if req.status_code == 200:
        found = False
        acc = ""
        for chunk in req.iter_content(chunk_size=1024):
            if chunk:
                acc += chunk.decode('utf-8')
        for line in acc.split("\n"):
            if line.startswith("data: "):
                data_obj = json.loads(line[6:])
                if data_obj.get("status") == "complete":
                    found = True
                    expiries = data_obj.get("data", {}).get("expiries", [])
                    if expiries:
                        print(f"Document field value: {expiries[0].get('document')}")
                    else:
                        print("Document field value could not be found, empty expiries")
                elif data_obj.get("status") == "error":
                    print(f"API Error Event: {data_obj.get('message')}")
        if not found:
            print("No complete event found. Raw output:", acc)
            
    # Test C
    print("\n--- Test C: Gap analysis filename ---")
    req = requests.post(f"{API_URL}/api/gap-analysis", json={"doc_ids": [lease_id, franchise_id]}, headers=headers, stream=True)
    print(f"HTTP Status: {req.status_code}")
    if req.status_code == 200:
        found = False
        acc = ""
        for chunk in req.iter_content(chunk_size=1024):
            if chunk:
                acc += chunk.decode('utf-8')
        for line in acc.split("\n"):
            if line.startswith("data: "):
                data_obj = json.loads(line[6:])
                if data_obj.get("status") == "complete":
                    found = True
                    payload = data_obj.get("data", {})
                    print(f"Detected lease: {payload.get('detected_lease')}")
                    print(f"Detected franchise: {payload.get('detected_franchise')}")
                elif data_obj.get("status") == "error":
                    print(f"API Error Event: {data_obj.get('message')}")
        if not found:
            print("No complete event found. Raw output:", acc)

if __name__ == "__main__":
    run_tests()
