import requests
import time

API_URL = "https://rem-leases-production.up.railway.app"
HEADERS = {"X-Session-Id": "6f6b1302-a165-46a1-a181-235aef40c859", "Content-Type": "application/json"}
DOC_ID = "0ae5e1d0-15e8-47b0-9003-66760929a8e1"

print("Waiting for deployment...")
time.sleep(15)

print("\n--- Test A: GET /api/workspaces ---")
resp_a = requests.get(f"{API_URL}/api/workspaces", headers={"X-Session-Id": "6f6b1302-a165-46a1-a181-235aef40c859"})
print(f"Status: {resp_a.status_code}")
print(f"Response: {resp_a.text[:200]}")

print("\n--- Test B: POST /api/chat ---")
payload_b = {
    "doc_ids": [DOC_ID],
    "query": "What are the key dates in this lease?",
    "is_timeline": False,
    "jurisdictions": []
}
resp_b = requests.post(f"{API_URL}/api/chat", headers=HEADERS, json=payload_b)
print(f"Status: {resp_b.status_code}")
print(f"Response (first 200 chars): {resp_b.text[:200]}")

print("\n--- Test C: POST /api/extract-expiries ---")
payload_c = {"doc_ids": [DOC_ID]}
resp_c = requests.post(f"{API_URL}/api/extract-expiries", headers=HEADERS, json=payload_c)
print(f"Status: {resp_c.status_code}")
print(f"Response: {resp_c.text[:200]}")

print("\n--- Test D: POST /api/gap-analysis ---")
payload_d = {"doc_ids": [DOC_ID, "fake-doc-2"]}
resp_d = requests.post(f"{API_URL}/api/gap-analysis", headers=HEADERS, json=payload_d)
print(f"Status: {resp_d.status_code}")

