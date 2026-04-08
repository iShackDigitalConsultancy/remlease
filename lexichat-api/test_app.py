import os
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_get_workspaces_no_auth():
    # Attempting to fetch workspaces without any auth or session ID should return an empty list or specific response
    response = client.get("/api/workspaces")
    assert response.status_code == 200
    assert response.json() == []

def test_create_workspace_anon():
    # Test anonymous workspace creation with X-Session-Id
    headers = {"X-Session-Id": "qa_test_session_123"}
    response = client.post("/api/workspaces", data={"name": "QA Test WS"}, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "QA Test WS"
    assert "id" in data
    
    # Clean up workspace immediately
    ws_id = data["id"]
    delete_response = client.delete(f"/api/workspaces/{ws_id}", headers=headers)
    assert delete_response.status_code == 200
