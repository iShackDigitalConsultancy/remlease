import sys
import os
import json
import time
import asyncio

# Set env var
os.environ["USE_MAP_REDUCE"] = "True"

from fastapi.testclient import TestClient
from main import app, get_db, get_current_user_optional

DOC_1 = "8762e3a7-fb9a-4a4d-a19f-38a716c7e897"
DOC_2 = "b55e4e10-6c3b-4d5c-a1d1-07d79b8e76d4"

class MockDoc1:
    filename = "master_agreement.pdf"
    pinecone_doc_id = DOC_1
    id = DOC_1
    workspace_id = "test-ws"

class MockDoc2:
    filename = "franchise_agreement.pdf"
    pinecone_doc_id = DOC_2
    id = DOC_2
    workspace_id = "test-ws"

def mock_get_db():
    class MockQuery:
        def join(self, *args, **kwargs): return self
        def filter(self, *args, **kwargs): return self
        def first(self): 
            # We return mockdoc1 for everything except if DOC_2 is explicitly needed
            return MockDoc1()
        def all(self): return [MockDoc1(), MockDoc2()]
        
    class MockSession:
        def query(self, *args, **kwargs): return MockQuery()

    yield MockSession()

app.dependency_overrides[get_db] = mock_get_db
app.dependency_overrides[get_current_user_optional] = lambda: None

client = TestClient(app)

def read_sse(response):
    batches = 0
    final_output = None
    if response.status_code != 200:
        return 0, f"Error {response.status_code}: {response.text}"
    for line in response.iter_lines():
        line = line.strip()
        if line.startswith("data: "):
            try:
                data = json.loads(line[6:])
                if data.get("status") == "processing":
                    batches += 1
                elif data.get("status") == "complete":
                    final_output = data.get("data")
                elif data.get("status") == "error":
                    final_output = "ERROR: " + data.get("message")
            except Exception as e:
                pass
    return batches, final_output

def test_endpoint(endpoint, method, payload):
    start = time.time()
    try:
        if method == "POST":
            response = client.post(endpoint, json=payload, headers={"x-session-id": "test-session"})
        else:
            response = client.get(endpoint, headers={"x-session-id": "test-session"})
        end = time.time()
        
        batches, final_output = read_sse(response)
        print(f"Endpoint: {endpoint}")
        print(f"Total time: {end - start:.2f}s")
        print(f"Batches: {batches}")
        print(f"Final output type: {type(final_output)}")
        out_str = str(final_output)
        print(f"Final output sample: {out_str[:500]}")
        if len(out_str) > 500:
            print("...")
        print("-" * 50)
        return batches, end-start, final_output
    except Exception as e:
        print(f"FAILED on {endpoint}: {e}")

print("=== TEST 1: Full Document Coverage ===")
test_endpoint("/api/extract-expiries", "POST", {"doc_ids": [DOC_1]})
test_endpoint("/api/gap-analysis", "POST", {"doc_ids": [DOC_1, DOC_2]})
test_endpoint("/api/compare", "POST", {"doc_id_a": DOC_1, "doc_id_b": DOC_2})
test_endpoint("/api/extract-timeline", "POST", {"doc_ids": [DOC_1]})
test_endpoint("/api/audit", "POST", {"doc_id": DOC_1, "policy": "Strict compliance needed."})
test_endpoint("/api/portfolio-overview", "GET", None)
