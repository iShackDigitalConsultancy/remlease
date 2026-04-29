import sys
import json
import time
import httpx

api_base = "https://rem-leases-production.up.railway.app/api"
doc_id = "8a166257-9b50-45d0-b99f-a75fa41868a0"
session_id = "a30213ed-772e-40de-b070-1643145fa253"

def ping_brief():
    try:
        with httpx.Client(timeout=10) as client:
            return client.get(f"{api_base}/documents/{doc_id}/brief", headers={"x-session-id": session_id})
    except Exception:
        return None

def monitor_redeploy_and_verify():
    print("Monitoring API for deployment transition (502 -> 200)...")
    
    went_offline = False
    
    # Wait for the system to go offline (502) or for 3 minutes to pass
    start_wait = time.time()
    while time.time() - start_wait < 300: # 5 minutes max
        res = ping_brief()
        if res is None or res.status_code == 502:
            print(f"\n[{(time.time()-start_wait):.0f}s] Server is OFFLINE (Redeploying container...)")
            went_offline = True
            break
        elif res.status_code == 200:
            print(".", end="", flush=True)
            time.sleep(5)
        else:
            print(f"\nUnexpected status: {res.status_code}")
            time.sleep(5)
            
    if not went_offline:
        print("Warning: Never detected the 502 transition. Continuing anyway...")
        
    print("Waiting for server to come back online...")
    # Wait for it to come completely online (not 502/503)
    while True:
        res = ping_brief()
        if res and res.status_code not in [502, 503]:
            break
        time.sleep(5)
        print(".", end="", flush=True)
        
    print("\n\n=== VERIFICATION PHASE ===")
    res = ping_brief()
    print(f"HTTP Response Code: {res.status_code}")
    if res.status_code == 200:
        print("Brief fetched successfully! The file SURVIVED the redeploy!")
    elif res.status_code == 404:
        print("Brief gave 404 Not Found. The file was WIPED.")
    else:
        print(f"Unknown state: {res.text}")

if __name__ == "__main__":
    monitor_redeploy_and_verify()
