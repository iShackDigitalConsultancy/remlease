import sys
import json
import time
import httpx
import uuid
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from fpdf import FPDF

def create_mock_pdf(filename="survival_test_lease.pdf"):
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

def run_upload_and_get_doc():
    print(f"Creating new session {session_id} on production...")
    with httpx.Client(timeout=60) as client:
        data_ws = {"name": "Survival Test WS"}
        res = client.post(f"{api_base}/workspaces", data=data_ws, headers={"x-session-id": session_id})
        ws_id = res.json().get("id")
        
        print(f"Uploading a real document {file_path} to workspace {ws_id}...")
        with open(file_path, "rb") as f:
            files = {"file": f}
            res = client.post(f"{api_base}/upload/{ws_id}", files=files, headers={"x-session-id": session_id})
            data = res.json()
            doc_id = data.get("doc_id")
            print(f"\nDocument uploaded successfully! Created doc_id: {doc_id}")
            print(f"Session ID: {session_id}")
            print("\nWaiting 10s for brief background task to generate the _brief.json file...")
            time.sleep(10)
            
            # Hit /api/documents/{doc_id}/brief
            b_res = client.get(f"{api_base}/documents/{doc_id}/brief", headers={"x-session-id": session_id})
            if b_res.status_code == 200:
                print(f"SUCCESS: verified /api/documents/{doc_id}/brief exists prior to redeploy!")
            else:
                print(f"FAILED to fetch brief. Code {b_res.status_code}: {b_res.text}")

if __name__ == "__main__":
    run_upload_and_get_doc()
