# tests/test_auth.py
import pytest
from httpx import AsyncClient
from fastapi import status

from app.core.config import settings # Para construir URLs
# --- IMPORTAR DADOS DE USUÁRIO DO CONFTEST ---
from tests.conftest import user_a_data

# Marca todos os testes neste módulo para usar asyncio
pytestmark = pytest.mark.asyncio

# ==============================
# --- Testes de Registro ---
# ==============================
async def test_register_user_success(test_async_client: AsyncClient):
    """Testa registro de usuário bem-sucedido."""
    # Usa dados únicos para este teste específico
    new_user_data = {
        "email": "newuniqueuser@example.com",
        "username": "newuniqueuser",
        "password": "newpassword123",
        "full_name": "New Test User"
    }
    url = f"{settings.API_V1_STR}/auth/register"

    response = await test_async_client.post(url, json=new_user_data)

    assert response.status_code == status.HTTP_201_CREATED
    response_data = response.json()
    assert response_data["email"] == new_user_data["email"]
    assert response_data["username"] == new_user_data["username"]
    assert response_data["full_name"] == new_user_data["full_name"]
    assert "id" in response_data
    assert "hashed_password" not in response_data 

async def test_register_user_duplicate_username(
    test_async_client: AsyncClient,
    test_user_a_token: str
):
    """Testa registro com username duplicado."""
    attempt_data = {
        "email": "anotherunique@example.com",
        "username": user_a_data["username"], 
        "password": "anotherpassword",
    }
    url = f"{settings.API_V1_STR}/auth/register"

    response = await test_async_client.post(url, json=attempt_data)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert "já existe" in response.json()["detail"]

async def test_register_user_duplicate_email(
    test_async_client: AsyncClient,
    test_user_a_token: str # Pede a fixture correta User A
):
    """Testa registro com email duplicado."""
    attempt_data = {
        "email": user_a_data["email"], # << Usa email do User A
        "username": "anotherunique_username",
        "password": "anotherpassword",
    }
    url = f"{settings.API_V1_STR}/auth/register"

    response = await test_async_client.post(url, json=attempt_data)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert "já registrado" in response.json()["detail"]

# ========================
# --- Testes de Login ---
# ========================
async def test_login_success(
    test_async_client: AsyncClient,
    test_user_a_token: str # Pede a fixture correta User A (garante que existe)
):
     """Testa login bem-sucedido do Usuário A."""
     login_data = {"username": user_a_data["username"], "password": user_a_data["password"]} # Usa dados do User A
     url = f"{settings.API_V1_STR}/auth/login/access-token"

     response = await test_async_client.post(url, data=login_data) # Form data

     assert response.status_code == status.HTTP_200_OK
     token_data = response.json()
     assert "access_token" in token_data
     assert token_data["token_type"] == "bearer"

async def test_login_wrong_password(
    test_async_client: AsyncClient,
    test_user_a_token: str # Pede a fixture correta User A (garante que existe)
):
     """Testa login com senha incorreta para o Usuário A."""
     login_data = {"username": user_a_data["username"], "password": "wrongpassword"} # Usa user A, senha errada
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