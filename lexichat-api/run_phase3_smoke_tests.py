import requests
import json
import time
import os

URL = "https://rem-leases-production.up.railway.app"
TEST_EMAIL = "phase3test@ishack.co.za"
TEST_PASSWORD = "Password123!"

def wait_for_deploy():
    print("Waiting for Phase 3 Railway deployment...")
    time.sleep(15)
    for i in range(12):
        time.sleep(10)
        try:
            r = requests.get(f"{URL}/api/workspaces", timeout=5)
            # If 502, it's still down. 
            if r.status_code != 502:
                print(f"[{i*10}s] Server is responding with status: {r.status_code}")
                return
            else:
                print(f"[{i*10}s] Server returned 502, waiting...")
        except:
            print(f"[{i*10}s] Waiting for server...")

wait_for_deploy()

print("Setting up User and Workspace...")
requests.post(f"{URL}/api/auth/signup", json={"email": TEST_EMAIL, "password": TEST_PASSWORD, "firm_name": "Phase 3 Testers", "full_name": "Tester", "is_firm_admin": True})

res = requests.post(f"{URL}/api/auth/login", data={"username": TEST_EMAIL, "password": TEST_PASSWORD})
token = res.json().get("access_token")
headers = {"Authorization": f"Bearer {token}"}

ws_res = requests.post(f"{URL}/api/workspaces", headers=headers, data={"name": "Phase 3 WS"})
ws_id = ws_res.json()["id"]

print(f"\n--- Test A: POST /api/upload/{ws_id} ---")
file_path = "survival_test_lease.pdf"
with open(file_path, "rb") as f:
    up_res = requests.post(f"{URL}/api/upload/{ws_id}", headers=headers, files={"file": ("survival_test_lease.pdf", f, "application/pdf")})

print(f"Status: {up_res.status_code}")
if up_res.status_code == 200:
    doc_id = up_res.json()["doc_id"]
    print("Confirm HTTP 200: YES")
    
    ws_check = requests.get(f"{URL}/api/workspaces", headers=headers).json()
    ws = next(w for w in ws_check if w["id"] == ws_id)
    doc_exists = any(d["id"] == doc_id for d in ws["documents"])
    print(f"Confirm document in workspace: {'YES' if doc_exists else 'NO'}")
    
    print("Waiting 15 seconds for background brief job...")
    time.sleep(15)
    brief_res = requests.get(f"{URL}/api/documents/{doc_id}/brief", headers=headers)
    print(f"Brief generation check ({brief_res.status_code}): {'YES' if brief_res.status_code == 200 else 'NO'}")
else:
    print(f"Upload Failed: {up_res.text}")
    exit(1)

print("\n--- Test B: POST /api/chat ---")
chat_payload = {
    "doc_ids": [doc_id],
    "query": "What are the key obligations in this lease?"
}
stream_response = requests.post(f"{URL}/api/chat", headers=headers, json=chat_payload, stream=True)
print(f"Status: {stream_response.status_code}")
if stream_response.status_code == 200:
    content = ""
    for line in stream_response.iter_lines():
        if line:
            decoded = line.decode('utf-8')
            if decoded.startswith('data: '):
                raw_data = decoded[6:]
                if raw_data == "[DONE]":
                    break
                print(raw_data)
                try:
                    data = json.loads(raw_data)
                    if "content" in data:
                        content += data["content"]
                except:
                    pass
        if len(content) > 200:
            break
    print(f"First 200 chars:\n{content[:200]}")
else:
    print("Chat Request Failed.")

print("\n--- Test C: POST /api/admin/migrate-voyage ---")
admin_headers = {"X-Admin-Key": "qp5WtYRjCttUDbeooF8b_NkvLoHehDB4KJPA9bCZs2c"}
mig_res = requests.post(f"{URL}/api/admin/migrate-voyage", headers=admin_headers, json={"dry_run": True})
print(f"Status: {mig_res.status_code}")
if mig_res.status_code == 200:
    print(f"Readable count: {mig_res.json().get('readable', 'N/A')}")
else:
    print(f"Migration Admin failed: {mig_res.text}")

print("\n--- Test D: POST /api/extract-expiries ---")
exp_res = requests.post(f"{URL}/api/extract-expiries", headers=headers, json={"doc_ids": [doc_id]}, stream=True)
print(f"Status: {exp_res.status_code}")
if exp_res.status_code == 200:
    map_reduce_activated = False
    for line in exp_res.iter_lines():
        if line:
            decoded = line.decode('utf-8')
            if decoded.startswith('data: '):
                raw_data = decoded[6:]
                print("Stream Event:", raw_data)
                try:
                    data = json.loads(raw_data)
                    if data["status"] == "processing" and "Analysing section" in data["message"]:
                        map_reduce_activated = True
                except:
                    pass
    print(f"Confirm Map-Reduce activates: {'YES' if map_reduce_activated else 'NO'}")
else:
    print("Extract Expiries failed.")
