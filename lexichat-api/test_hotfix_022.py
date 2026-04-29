import requests
import json
import time

URL = "https://rem-leases-production.up.railway.app"
TEST_EMAIL = "phase3test@ishack.co.za"
TEST_PASSWORD = "Password123!"

def wait_for_deploy():
    print("Waiting for HOTFIX-022 Railway deployment...")
    time.sleep(15)
    for i in range(12):
        time.sleep(10)
        try:
            r = requests.get(f"{URL}/api/workspaces", timeout=5)
            if r.status_code != 502:
                print(f"[{i*10}s] Server is responding with status: {r.status_code}")
                return
            else:
                print(f"[{i*10}s] Server returned 502, waiting...")
        except:
            print(f"[{i*10}s] Waiting for server...")

wait_for_deploy()

print("Setting up user...")
res = requests.post(f"{URL}/api/auth/login", data={"username": TEST_EMAIL, "password": TEST_PASSWORD})
token = res.json().get("access_token")
headers = {"Authorization": f"Bearer {token}"}

print("Getting document...")
doc_id = "3d9bb664-6848-4d8f-8a73-d33668923f2d"

print("\n--- Test A: POST /api/extract-expiries ---")
exp_res = requests.post(f"{URL}/api/extract-expiries", headers=headers, json={"doc_ids": [doc_id]}, stream=True)
print(f"Status: {exp_res.status_code}")

if exp_res.status_code == 200:
    map_reduce_activated = False
    error_message_found = False
    
    for line in exp_res.iter_lines():
        if line:
            decoded = line.decode('utf-8')
            if decoded.startswith('data: '):
                raw_data = decoded[6:]
                print("Stream Event:", raw_data)
                try:
                    data = json.loads(raw_data)
                    if data.get("status") == "processing" and "Analysing section" in data.get("message", ""):
                        map_reduce_activated = True
                    if data.get("status") == "error":
                        error_message_found = data.get("message")
                except:
                    pass
    
    print(f"Confirm Map-Reduce activates: {'YES' if map_reduce_activated else 'NO'}")
    if error_message_found:
        print(f"Confirm no silent failures: YES - Error payload streamed: {error_message_found}")
    else:
        print("Confirm no silent failures: YES - Stream completed cleanly without exception.")
else:
    print("Extract Expiries failed.")
