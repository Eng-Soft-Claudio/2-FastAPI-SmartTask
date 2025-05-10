# tests/test_heath.py

# ========================
# --- Importações ---
# ========================
import io
import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import status
from unittest.mock import AsyncMock, patch

from redis import RedisError
from app.main import app
from loguru import logger

# ========================
# --- Constantes e Dados de Teste ---
# ========================
log_stream = io.StringIO()
handler_id = logger.add(log_stream, level="DEBUG")

# ========================
# --- Testes para health check ---
# ========================
@pytest.mark.asyncio
async def test_health_check_success(monkeypatch):
    """
    Deve retornar 200 quando Redis e Mongo estiverem operacionais.
    """

    # --- Arrange ---
    monkeypatch.setattr("app.routers.health.Redis", lambda **kwargs: AsyncMock(ping=lambda: True))
    monkeypatch.setattr("app.routers.health.check_mongo_connection", AsyncMock(return_value=True))
    handler_id = logger.add(io.StringIO(), level="DEBUG")
    
    try:
        # --- Act ---
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/health")

        # --- Assert ---
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "ok"}
    finally:
        logger.remove(handler_id)


@pytest.mark.asyncio
async def test_health_check_redis_failure(monkeypatch):
    """
    Deve retornar 503 quando Redis estiver indisponível.
    """

# --- Arrange ---
    class RedisMock:
        def __init__(self, host=None, port=None):
            pass
        def ping(self):
            # Levanta RedisError para ser capturado pelo except RedisError
            raise RedisError("simulated Redis down")

    monkeypatch.setattr("app.routers.health.Redis", RedisMock)
    monkeypatch.setattr("app.routers.health.check_mongo_connection", AsyncMock(return_value=True))

    # Captura logs locais (opcional)
    local_log = io.StringIO()
    handler_id = logger.add(local_log, level="DEBUG")

    try:
        # --- Act ---
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

        # --- Assert ---
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        body = response.json()
        assert body["status"] == "error"
        assert body["message"] == "Redis não está disponível"
    finally:
        # Limpa handler de log
        logger.remove(handler_id)


@pytest.mark.asyncio
async def test_health_check_mongo_failure(monkeypatch):
    """
    Deve retornar 503 quando MongoDB estiver indisponível.
    """

    # --- Arrange ---   
    monkeypatch.setattr("app.routers.health.Redis", lambda **kwargs: AsyncMock(ping=lambda: True))
    monkeypatch.setattr("app.routers.health.check_mongo_connection", AsyncMock(return_value=False))
    local_log_stream = io.StringIO()
    local_handler_id = logger.add(local_log_stream, level="DEBUG")

    try:
        # --- Act ---
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/health")

        # --- Assert ---
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "MongoDB não está disponível" in response.text
    finally:
        logger.remove(local_handler_id)
        log_stream.close()

