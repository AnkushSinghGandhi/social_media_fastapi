from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_register_user():
    response = client.post("/register", json={"username": "testuser", "email": "test@test.com", "password": "password123"})
    assert response.status_code == 200
    assert response.json()["message"] == "User registered successfully"
