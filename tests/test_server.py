import os
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from assistant.server import app

client = TestClient(app)

def test_health_check():
    """Verify that the health check endpoint returns status ok and config details."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "models" in data

@patch("assistant.server.query_vector_db")
def test_retrieve_endpoint(mock_retrieve):
    """Verify retrieve endpoint calls vector DB helper and returns results."""
    mock_retrieve.return_value = {"documents": [["chunk1", "chunk2"]], "metadatas": [[{"title": "doc1"}, {"title": "doc2"}]]}
    
    payload = {
        "query": "cycle~",
        "domain": "msp",
        "version": "8",
        "results": 2
    }
    response = client.post("/api/retrieve", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "documents" in data
    assert len(data["documents"][0]) == 2
    mock_retrieve.assert_called_once_with(query_text="cycle~", domain="msp", max_version="8", n_results=2)

@patch("assistant.server.validate_patch")
def test_validate_endpoint(mock_validate):
    """Verify validate endpoint invokes validator and returns result."""
    mock_validate.return_value = {"valid": True, "errors": [], "warnings": [], "domain": "msp", "device_type": "unknown"}
    
    payload = {
        "patch": {"patcher": {}},
        "domain": "msp"
    }
    response = client.post("/api/validate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    mock_validate.assert_called_once_with(patch_data={"patcher": {}}, domain_override="msp", device_type_override=None)

@patch("assistant.server.explain_query")
def test_explain_endpoint_streaming(mock_explain):
    """Verify explain endpoint streams SSE tokens successfully."""
    # Define a side_effect to invoke callback with mocked tokens
    def mock_explain_impl(*args, **kwargs):
        callback = kwargs.get("callback")
        if callback:
            callback("Hello ")
            callback("world")

    mock_explain.side_effect = mock_explain_impl
    
    payload = {
        "query": "explain cycle~",
        "domain": "msp",
        "version": "8"
    }
    
    response = client.post("/api/explain", json=payload)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    
    # Read the streamed lines
    lines = [line for line in response.iter_lines() if line]
    assert len(lines) == 2
    assert json.loads(lines[0].replace("data: ", "")) == {"token": "Hello "}
    assert json.loads(lines[1].replace("data: ", "")) == {"token": "world"}

@pytest.mark.anyio
async def test_explain_cancellation():
    """Verify that client disconnection aborts explanation streaming."""
    from assistant.server import explain_patch_query, ExplainRequest
    req = ExplainRequest(query="explain cycle~")
    
    # Mock request indicating immediate disconnect
    mock_request = MagicMock()
    async def mock_is_disconnected():
        return True
    mock_request.is_disconnected = mock_is_disconnected
    
    response = await explain_patch_query(req, mock_request)
    
    # Consume response stream
    body = []
    async for chunk in response.body_iterator:
        body.append(chunk)
        
    assert len(body) == 0

