import sys
import json
import time
import httpx
import uuid
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from fpdf import FPDF

def create_mock_pdf(filename="mock_lease.pdf"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    text = (
        "MOCK LEASE AGREEMENT\n\n"
        "This Lease Agreement is entered into between Landlord and Tenant.\n"
        "The commencement date is January 1, 2024.\n"
        "The expiry date of this lease is December 31, 2029.\n"
        "The tenant is required to give 90 days notice for renewal.\n"
        "Clause 1: Rent is $1000 per month.\n"
    )
    for _ in range(50):
        text += "The tenant shall abide by all rules and regulations. The landlord promises quiet enjoyment.\n"
    
    pdf.multi_cell(0, 10, text)
    pdf.output(filename)
    return filename

file_path = create_mock_pdf()
session_id = str(uuid.uuid4())
api_base = "https://rem-leases-production.up.railway.app/api"

def run_smoke_test():
    print(f"Creating new session {session_id} on production...")
    with httpx.Client(timeout=60) as client:
        print("Creating workspace...")
        data_ws = {"name": "Smoke Test WS"}
        res = client.post(f"{api_base}/workspaces", data=data_ws, headers={"x-session-id": session_id})
        if res.status_code != 200:
            print("Failed to create workspace:", res.text)
            return
        ws_id = res.json().get("id")
        
        print(f"Uploading a real document {file_path} to workspace {ws_id}...")
        with open(file_path, "rb") as f:
            files = {"file": f}
            res = client.post(f"{api_base}/upload/{ws_id}", files=files, headers={"x-session-id": session_id})
            if res.status_code != 200:
                print(f"Failed to upload document: {res.text}")
                return
            
            data = res.json()
            doc_id = data.get("doc_id")
            print(f"Document uploaded successfully! Created doc_id: {doc_id}")

    print("Waiting for document to finalize...")
    time.sleep(5)

    print(f"\nTriggering smoke test on /api/extract-expiries for {doc_id}...")
    headers = {
        "Content-Type": "application/json",
        "x-session-id": session_id
    }
    payload = {"doc_ids": [doc_id]}

    start = time.time()
    batches = 0
    final_output = None
    status_code = None

    try:
        with httpx.Client(timeout=300) as client:
            with client.stream("POST", f"{api_base}/extract-expiries", json=payload, headers=headers) as response:
                status_code = response.status_code
                print(f"HTTP Response Code: {status_code}")
                
                if status_code != 200:
                    print(f"Error Body: {response.read().decode('utf-8')}")
                    return
                
                for line in response.iter_lines():
                    line = line.strip()
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            if data.get("status") == "processing":
                                batches += 1
                                print(f"Processing... {data.get('message')}")
                            elif data.get("status") == "complete":
                                final_output = data.get("data")
                            elif data.get("status") == "error":
                                final_output = "ERROR: " + data.get("message")
                        except Exception:
                            pass
                            
    except Exception as e:
        print(f"Connection failed: {e}")
        return
        
    end = time.time()
    print("\n=== SMOKE TEST RESULTS ===")
    print(f"HTTP Response Code: {status_code}")
    print(f"MAP Batches processed: {batches}")
    if final_output and isinstance(final_output, dict):
        has_schedule = "expiries" in final_output and len(final_output["expiries"]) > 0
        print(f"Structured Expiry Schedule Returned: {'Yes' if has_schedule else 'No'}")
        print(f"Sample Output: {str(final_output)[:300]}...")
    else:
        print(f"Structured Expiry Schedule Returned: ERROR")
        print(f"Sample Output: {final_output}")
    print(f"Total Response Time: {end - start:.2f}s")


if __name__ == "__main__":
    run_smoke_test()
