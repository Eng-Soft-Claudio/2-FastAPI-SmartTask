# tests/test_auth.py
import pytest
from httpx import AsyncClient
from fastapi import status

from app.core.config import settings # Para construir URLs

# Marca todos os testes neste módulo para usar asyncio
pytestmark = pytest.mark.asyncio

# --- Testes de Registro ---
async def test_register_user_success(test_async_client: AsyncClient):
    """Testa registro de usuário bem-sucedido."""
    user_data = {
        "email": "newuser@example.com",
        "username": "newuser",
        "password": "newpassword123",
        "full_name": "New Test User"
    }
    url = f"{settings.API_V1_STR}/auth/register"

    response = await test_async_client.post(url, json=user_data)

    assert response.status_code == status.HTTP_201_CREATED
    response_data = response.json()
    assert response_data["email"] == user_data["email"]
    assert response_data["username"] == user_data["username"]
    assert response_data["full_name"] == user_data["full_name"]
    assert "id" in response_data
    assert "hashed_password" not in response_data # Garante que senha não vaza

async def test_register_user_duplicate_username(test_async_client: AsyncClient, test_user_token: str): # Usa test_user_token para garantir que 'testuser' exista
    """Testa registro com username duplicado."""
    user_data = {
        "email": "another@example.com",
        "username": "testuser", # Username já usado pela fixture test_user_token
        "password": "anotherpassword",
    }
    url = f"{settings.API_V1_STR}/auth/register"

    response = await test_async_client.post(url, json=user_data)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert "já existe" in response.json()["detail"]

async def test_register_user_duplicate_email(test_async_client: AsyncClient, test_user_token: str):
    """Testa registro com email duplicado."""
    user_data = {
        "email": "testuser@example.com", # Email já usado pela fixture
        "username": "unique_username",
        "password": "anotherpassword",
    }
    url = f"{settings.API_V1_STR}/auth/register"
    response = await test_async_client.post(url, json=user_data)
    assert response.status_code == status.HTTP_409_CONFLICT
    assert "já registrado" in response.json()["detail"]


# --- Testes de Login ---
async def test_login_success(test_async_client: AsyncClient, test_user_token: str): # Garante que 'testuser' existe
     """Testa login bem-sucedido."""
     login_data = {"username": "testuser", "password": "testpassword"}
     url = f"{settings.API_V1_STR}/auth/login/access-token"

     response = await test_async_client.post(url, data=login_data) # Form data

     assert response.status_code == status.HTTP_200_OK
     token_data = response.json()
     assert "access_token" in token_data
     assert token_data["token_type"] == "bearer"

async def test_login_wrong_password(test_async_client: AsyncClient, test_user_token: str):
     """Testa login com senha incorreta."""
     login_data = {"username": "testuser", "password": "wrongpassword"}
     url = f"{settings.API_V1_STR}/auth/login/access-token"
     response = await test_async_client.post(url, data=login_data)
     assert response.status_code == status.HTTP_401_UNAUTHORIZED
     assert "incorretos" in response.json()["detail"]

async def test_login_user_not_found(test_async_client: AsyncClient):
     """Testa login com usuário inexistente."""
     login_data = {"username": "nonexistentuser", "password": "password"}
     url = f"{settings.API_V1_STR}/auth/login/access-token"
     response = await test_async_client.post(url, data=login_data)
     assert response.status_code == status.HTTP_401_UNAUTHORIZED # Mesmo erro para user/pwd errados