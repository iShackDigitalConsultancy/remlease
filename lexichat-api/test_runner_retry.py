import sys
import os
import json
import time
import logging
from unittest.mock import patch

logging.basicConfig(level=logging.WARNING)

# Set env var
os.environ["USE_MAP_REDUCE"] = "True"

from fastapi.testclient import TestClient
from main import app, get_db, get_current_user_optional

DOC_1 = "8762e3a7-fb9a-4a4d-a19f-38a716c7e897"

class MockDoc1:
    filename = "master_agreement.pdf"
    pinecone_doc_id = DOC_1
    id = DOC_1
    workspace_id = "test-ws"

def mock_get_db():
    class MockQuery:
        def join(self, *args, **kwargs): return self
        def filter(self, *args, **kwargs): return self
        def first(self): return MockDoc1()
        def all(self): return [MockDoc1()]
    class MockSession:
        def query(self, *args, **kwargs): return MockQuery()
    yield MockSession()

app.dependency_overrides[get_db] = mock_get_db
app.dependency_overrides[get_current_user_optional] = lambda: None

client = TestClient(app)

import services.map_reduce
from tenacity import after_log
logger = logging.getLogger("tenacity.retry")

# Modify retry dynamically to add logging
original_retry = services.map_reduce.map_phase.retry
original_retry.after = after_log(logger, logging.WARNING)

from groq import RateLimitError
import httpx

def test_3():
    print("=== TEST 3: Groq 429 Retry Logic ===")
    
    services.map_reduce.batch_document = lambda text, target_batch_size=20000: [text[:100]]

    # Mock the groq client
    original_client = services.map_reduce.get_async_groq_client
    
    class FakeGroqClient:
        class Chat:
            class Completions:
                call_count = 0
                async def create(self, **kwargs):
                    self.call_count += 1
                    if self.call_count <= 2:
                        print(f"Artificial 429 triggered (attempt {self.call_count})")
                        raise RateLimitError(
                            "Rate limit exceeded.",
                            response=httpx.Response(status_code=429, request=httpx.Request("POST", "url")),
                            body={"error": {"message": "Rate limit"}}
                        )
                    class MockMsg:
                        content = '{"status": "recovered"}'
                    class MockChoice:
                        message = MockMsg()
                    class MockResp:
                        choices = [MockChoice()]
                    return MockResp()
            completions = Completions()
        chat = Chat()
        
    fake_client = FakeGroqClient()
    services.map_reduce.get_async_groq_client = lambda: fake_client

    start = time.time()
    response = client.post("/api/extract-timeline", json={"doc_ids": [DOC_1]}, headers={"x-session-id": "test-session"})
    
    for line in response.iter_lines():
        line = line.strip()
        if line.startswith("data: "):
            try:
                data = json.loads(line[6:])
                print("UI Event:", data)
            except Exception:
                pass
    
    end = time.time()
    num_calls = fake_client.chat.completions.call_count
    
    print(f"Number of Groq calls made for the batch: {num_calls}")
    if num_calls > 2:
        print("Tenacity retry logic successfully recovered from 429.")
    else:
        print("Failed to retry.")

    print(f"Total time for TEST 3: {end - start:.2f}s")
    
test_3()
