from fastapi.testclient import TestClient
from main import app
import httpx
import asyncio

client = TestClient(app)


def test_wikipedia():
    """Test Wikipedia selector extraction"""
    response = client.post("/extract-selectors-csv",
                           json={"url": "wikipedia.com"})
    assert response.status_code == 200
    data = response.json()
    print(data)
    assert data["success"] is True
    assert "selectors_wikipedia_com.csv" in data["message"]
    assert len(data["sample"]) > 0
    assert data["sample"][0]["selector"].startswith("#") or data["sample"][0]["selector"].startswith(".")


def test_invalid_url():
    """Test invalid URL handling"""
    response = client.post("/extract-selectors-csv",
                           json={"url": "invalid@@url"})
    assert response.status_code == 500  # Expect error for bad URL
