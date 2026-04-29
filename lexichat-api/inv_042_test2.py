import json
import urllib.request
import ssl
import subprocess
import hmac
import hashlib
import base64
import time

def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')

def make_jwt(sub_email):
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": sub_email, "exp": int(time.time()) + 3600}
    b_head = b64url(json.dumps(header).encode('utf-8'))
    b_pay = b64url(json.dumps(payload).encode('utf-8'))
    msg = f"{b_head}.{b_pay}".encode('utf-8')
    secret = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7".encode('utf-8')
    sig = b64url(hmac.new(secret, msg, hashlib.sha256).digest())
    return f"{b_head}.{b_pay}.{sig}"

ws_id = "31931dfd-e7e2-4b11-860d-3b1622fd9bd2"
firm_id = "546b1599-c405-4591-9038-e4413cbb3d7c"

cmd = f'psql postgresql://postgres:MpxsytEYlyQXxgDDplPsyqYPUFptTOrA@nozomi.proxy.rlwy.net:13715/railway -t -A -c "SELECT email FROM users WHERE firm_id=\'{firm_id}\' LIMIT 1;"'
user_email = subprocess.check_output(cmd, shell=True).decode('utf-8').strip()
token = make_jwt(user_email)

cmd = f'psql postgresql://postgres:MpxsytEYlyQXxgDDplPsyqYPUFptTOrA@nozomi.proxy.rlwy.net:13715/railway -t -A -c "SELECT pinecone_doc_id, id, filename FROM workspace_documents WHERE workspace_id=\'{ws_id}\';"'
doc_output = subprocess.check_output(cmd, shell=True).decode('utf-8').strip().split('\n')

lease_id = None
franchise_id = None
print("Eikestad Workspace:")
for row in doc_output:
    if not row: continue
    parts = row.split('|')
    final_id = parts[0] if parts[0] else parts[1]
    fname = parts[2]
    print(f"- {fname} ({final_id})")
    if "LEASE" in fname.upper():
        lease_id = final_id
    if "FRANCHISE" in fname.upper() or "BOOTLEGGER" in fname.upper():
        franchise_id = final_id

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
api_base = "https://rem-leases-production.up.railway.app/api"
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "text/event-stream"}

def post_stream(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=120) as response:
            print(f"HTTP Status: {response.status}")
            for line in response:
                line = line.decode('utf-8').strip()
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        if data.get("status") == "complete":
                            res_data = data.get('data', {})
                            if isinstance(res_data, dict):
                                if 'audit' in res_data:
                                    print(f"Audit Complete! Items: {len(res_data['audit'])}")
                                elif 'differences' in res_data:
                                    print(f"Compare Complete! Differences: {len(res_data['differences'])}")
                                elif 'items' in res_data:
                                    print(f"Complete! Items: {len(res_data['items'])}")
                                else:
                                    print(f"Complete! Keys returned: {list(res_data.keys())}")
                            elif isinstance(res_data, list):
                                print(f"Complete! List returned with {len(res_data)} items.")
                    except Exception:
                        pass
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.read().decode('utf-8')}")

print("\n--- Testing Document Audit ---")
audit_payload = {"doc_id": lease_id, "policy": "Standard commercial lease compliance. Check: renewal options, escalation rates, permitted use, deposit requirements, maintenance obligations."}
post_stream(f"{api_base}/audit", audit_payload)

print("\n--- Testing Document Compare ---")
compare_payload = {"doc_id_a": franchise_id, "doc_id_b": lease_id}
post_stream(f"{api_base}/compare", compare_payload)
