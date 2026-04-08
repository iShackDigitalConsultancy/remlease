import requests
import uuid


if __name__ == "__main__":
    API_BASE = 'http://localhost:8000/api'
    SESSION_ID = str(uuid.uuid4())
    print(f"Testing with Session ID: {SESSION_ID}")

    headers = {'X-Session-Id': SESSION_ID}

    # 1. Create Workspace
    print("\n--- 1. Creating Workspace ---")
    r = requests.post(f"{API_BASE}/workspaces", data={'name': 'Anon Test'}, headers=headers)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        ws_id = r.json()['id']
        print(f"Workspace ID: {ws_id}")
    else:
        print(r.text)
        exit(1)

    # 2. Get Workspaces
    print("\n--- 2. Fetching Workspaces ---")
    r = requests.get(f"{API_BASE}/workspaces", headers=headers)
    print(f"Status: {r.status_code}")
    print(r.json())

    # 3. Create a dummy PDF and upload it
    print("\n--- 3. Uploading Document ---")
    with open("dummy.pdf", "wb") as f:
        f.write(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n4 0 obj\n<< /Length 51 >>\nstream\nBT\n/F1 24 Tf\n100 700 Td\n(Hello World) Tj\nET\nendstream\nendobj\n5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\nxref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000222 00000 n \n0000000324 00000 n \ntrailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n412\n%%EOF\n")

    with open("dummy.pdf", "rb") as f:
        r = requests.post(f"{API_BASE}/upload/{ws_id}", files={"file": ("dummy.pdf", f, "application/pdf")}, headers=headers)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        doc_id = r.json()['doc_id']
        print(f"Doc ID: {doc_id}")
    else:
        print(r.text)

    # 4. Chat Queries
    print("\n--- 4. Sending Chat Queries ---")
    chat_headers = headers.copy()
    chat_headers['Content-Type'] = 'application/json'

    chat_payload = {
        "doc_ids": [doc_id],
        "query": "What does the document say?",
        "is_timeline": False,
        "jurisdictions": []
    }

    for i in range(1, 6):
        print(f"\nQuery {i}...")
        r = requests.post(f"{API_BASE}/chat", json=chat_payload, headers=chat_headers)
        print(f"Status Code: {r.status_code}")
        if r.status_code == 200:
            print("Success (Streaming Response Intentionally Ignored)")
        elif r.status_code == 402:
            print("Blocked - 402 Limit Reached (Expected on Query 4)")
        else:
            print(r.text)

    print("\nAll Tests Executed.")
