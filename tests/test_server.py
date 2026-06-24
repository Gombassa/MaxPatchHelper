import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# Add assistant directory to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assistant"))

from server import app

client = TestClient(app)

def test_health_check():
    """Verify that the health check endpoint returns status ok and config details."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "models" in data

@patch("server.query_vector_db")
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

@patch("server.validate_patch")
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

@patch("server.explain_query")
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

@patch("server.generate_patch")
def test_generate_endpoint_streaming(mock_generate):
    """Verify generate endpoint streams SSE validation attempts, tokens, and final patch successfully."""
    def mock_generate_impl(*args, **kwargs):
        callback = kwargs.get("callback")
        if callback:
            callback({"type": "status", "content": "Attempt 1"})
            callback({"type": "token", "content": "{"})
            callback({"type": "token", "content": "}"})
            callback({"type": "patch", "content": {"patcher": {}}})

    mock_generate.side_effect = mock_generate_impl
    
    payload = {
        "query": "sine wave",
        "domain": "msp",
        "version": "8"
    }
    
    response = client.post("/api/generate", json=payload)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    
    lines = [line for line in response.iter_lines() if line]
    assert len(lines) == 4
    
    evt0 = json.loads(lines[0].replace("data: ", ""))
    assert evt0["type"] == "status"
    assert evt0["content"] == "Attempt 1"
    
    evt1 = json.loads(lines[1].replace("data: ", ""))
    assert evt1["type"] == "token"
    
    evt3 = json.loads(lines[3].replace("data: ", ""))
    assert evt3["type"] == "patch"
    assert evt3["content"] == {"patcher": {}}

@patch("server.load_personal_idioms")
def test_websocket_guided_initialization(mock_idioms):
    """Verify that WebSocket guided build initializes, sends idioms, and welcomes user."""
    mock_idioms.return_value = "### Lesson 1: Test idiom"
    
    with client.websocket_connect("/api/ws/guided") as websocket:
        # 1. First message: status loading idioms
        msg1 = websocket.receive_json()
        assert msg1["type"] == "status"
        assert "Loading past design history" in msg1["content"]
        
        # 2. Second message: idioms content
        msg2 = websocket.receive_json()
        assert msg2["type"] == "idioms"
        assert "Test idiom" in msg2["content"]
        
        # 3. Third message: welcome status
        msg3 = websocket.receive_json()
        assert msg3["type"] == "status"
        assert "Guided Build Mode" in msg3["content"]


@pytest.mark.anyio
async def test_generate_cancellation():
    """Verify that client disconnection aborts generation streaming."""
    from server import generate_max_patch, GenerateRequest
    req = GenerateRequest(query="sine wave")
    
    # Mock request indicating immediate disconnect
    mock_request = MagicMock()
    async def mock_is_disconnected():
        return True
    mock_request.is_disconnected = mock_is_disconnected
    
    response = await generate_max_patch(req, mock_request)
    
    # Consume response stream
    body = []
    async for chunk in response.body_iterator:
        body.append(chunk)
        
    assert len(body) == 0


@pytest.mark.anyio
async def test_explain_cancellation():
    """Verify that client disconnection aborts explanation streaming."""
    from server import explain_patch_query, ExplainRequest
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

