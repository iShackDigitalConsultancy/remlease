import requests
import time
import os

URL = "https://rem-leases-production.up.railway.app"
TEST_EMAIL = "phase2test@ishack.co.za"
TEST_PASSWORD = "Password123!"

def wait_for_deploy():
    print("Waiting for Phase 2 Railway deployment...")
    # Wait for Railway to pick up the push and deploy. Usually takes 60 seconds.
    for i in range(12):
        time.sleep(10)
        try:
            r = requests.get(f"{URL}/api/workspaces", timeout=5)
            # If we get a response (even 401), server is up
            print(f"[{i*10}s] Ping status: {r.status_code}")
        except:
            print(f"[{i*10}s] Waiting for server...")

wait_for_deploy()

# Setup test user if needed
print("Ensuring test user exists...")
r = requests.post(f"{URL}/api/auth/signup", json={"email": TEST_EMAIL, "password": TEST_PASSWORD, "firm_name": "Phase 2 Testers"})

print("\n--- Test A: POST /api/auth/login ---")
res = requests.post(f"{URL}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
print(f"Status: {res.status_code}")
if res.status_code == 200:
    token = res.json().get("access_token")
    print(f"Confirmed JWT Token returned: {'YES' if token else 'NO'}")
else:
    print(f"Response: {res.text}")
    print("FATAL: Auth failed")
    exit(1)

print("\n--- Test B: GET /api/workspaces ---")
headers = {"Authorization": f"Bearer {token}"}
res = requests.get(f"{URL}/api/workspaces", headers=headers)
print(f"Status: {res.status_code}")
if res.status_code == 200:
    workspaces = res.json()
    print(f"Workspace count: {len(workspaces)}")
    
    # Create workspace if empty
    if len(workspaces) == 0:
        print("Creating a test workspace to rename...")
        ws_res = requests.post(f"{URL}/api/workspaces", headers=headers, data={"name": "Temp WS"})
        ws = ws_res.json()
        ws_id = ws["id"]
        original_name = ws["name"]
    else:
        ws_id = workspaces[0]["id"]
        original_name = workspaces[0]["name"]
else:
    print(f"Response: {res.text}")
    exit(1)

print(f"\n--- Test C: PUT /api/workspaces/{ws_id} ---")
print(f"Renaming to 'Phase 2 Test'...")
res = requests.put(f"{URL}/api/workspaces/{ws_id}", headers=headers, json={"name": "Phase 2 Test"})
print(f"Status: {res.status_code}")
if res.status_code == 200:
    print("Rename succeeded: YES")
else:
    print("Rename succeeded: NO - " + res.text)

print(f"Reverting name back to '{original_name}'...")
requests.put(f"{URL}/api/workspaces/{ws_id}", headers=headers, json={"name": original_name})

print("\nDone!")
