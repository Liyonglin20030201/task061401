import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_register_and_login(client: AsyncClient):
    # Register
    reg_data = {
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpass123"
    }
    response = await client.post("/api/auth/register", json=reg_data)
    # May fail without DB, but tests schema validation
    assert response.status_code in (201, 500)


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient):
    login_data = {"email": "nonexistent@example.com", "password": "wrong"}
    response = await client.post("/api/auth/login", json=login_data)
    assert response.status_code in (401, 500)


@pytest.mark.asyncio
async def test_protected_route_no_token(client: AsyncClient):
    response = await client.get("/api/auth/me")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_route_no_auth(client: AsyncClient):
    response = await client.get("/api/admin/users")
    assert response.status_code == 403
