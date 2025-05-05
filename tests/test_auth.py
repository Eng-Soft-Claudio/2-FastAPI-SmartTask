# tests/test_auth.py
import uuid
import pytest
from httpx import AsyncClient
from fastapi import status
from typing import Any, Dict
from app.core.config import settings 
from tests.conftest import user_a_data
from app.models.user import User


pytestmark = pytest.mark.asyncio

# ==============================
# --- Testes de Registro ---
# ==============================
async def test_register_user_success(
        test_async_client: AsyncClient
):
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

async def test_register_user_duplicate_username_case_insensitive(
    test_async_client: AsyncClient,
):
    """
    Testa o registro com um username que difere apenas em maiúsculas/minúsculas
    de um username existente. Como o desejado é ser case-sensitive, espera-se sucesso (201).
    """
    # 1. Registrar usuário inicial
    user_initial_data = {
        "email": "case@example.com",
        "username": "CaseTestUser", 
        "password": "password123",
    }
    url = f"{settings.API_V1_STR}/auth/register"
    response_initial = await test_async_client.post(url, json=user_initial_data)
    assert response_initial.status_code == status.HTTP_201_CREATED, \
        f"Falha ao registrar usuário inicial para teste case-insensitive: {response_initial.text}"

    # 2. Tentar registrar com o mesmo username, mas minúsculo
    user_duplicate_case_data = {
        "email": "case_different@example.com", 
        "username": "casetestuser",
        "password": "password123",
    }
    response_duplicate = await test_async_client.post(url, json=user_duplicate_case_data)

    # Assert: Verifica se o registro foi permitido (201), confirmando case-sensitivity.
    assert response_duplicate.status_code == status.HTTP_201_CREATED, \
        f"O registro deveria ter sido permitido (201), mas falhou com status {response_duplicate.status_code}. " \
        "Verificar se a lógica de validação de username inesperadamente se tornou case-insensitive."

async def test_register_user_duplicate_username(
    test_async_client: AsyncClient,
    test_user_a_token_and_id: tuple[str, uuid.UUID]
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
    test_user_a_token_and_id: tuple[str, uuid.UUID]
):
    """Testa registro com email duplicado."""
    attempt_data = {
        "email": user_a_data["email"],
        "username": "anotherunique_username",
        "password": "anotherpassword",
    }
    url = f"{settings.API_V1_STR}/auth/register"

    response = await test_async_client.post(url, json=attempt_data)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert "já registrado" in response.json()["detail"]

# ==============================
# --- Testes de Validação ---
# ==============================
@pytest.mark.parametrize(
        "field, value, error_type, error_msg_part", [
            ("email", "não-é-um-email", "value_error", "valid email address"),
            ("username", "us", "string_too_short", "String should have at least 3 characters"),
            ("username", "user name com espaco", "string_pattern_mismatch", "match pattern"),
            ("password", "curta", "string_too_short", "String should have at least 8 characters"),
            ("email", None, "missing", "Field required"),
            ("username", None, "missing", "Field required"),
            ("password", None, "missing", "Field required"),
        ]
)

async def test_register_user_invalid_input(
    test_async_client: AsyncClient,
    field: str,
    value: Any,
    error_type: str,
    error_msg_part: str
):
    """Testa registro com dados inválidos específicos."""
    invalid_data = {
        "email": "valid@example.com",
        "username": "validusername",
        "password": "validpassword",
        "full_name": "Valid Name"
    }
    if value is None:
        if field in invalid_data:
           del invalid_data[field]
    else:
        invalid_data[field] = value

    url = f"{settings.API_V1_STR}/auth/register"
    response = await test_async_client.post(url, json=invalid_data)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    error_details = response.json()["detail"]
    found_error = False
    for error in error_details:
        if field in error.get("loc", []) and error.get("type") == error_type:
             if error_msg_part in error.get("msg", ""):
                  found_error = True
                  break
    assert found_error, f"Erro esperado para campo '{field}' com tipo '{error_type}' e msg contendo '{error_msg_part}' não encontrado em {error_details}"

# =============================
# --- Testes de Login ---
# =============================
async def test_login_success(
    test_async_client: AsyncClient,
    test_user_a_token_and_id: tuple[str, uuid.UUID]
):
    """Testa login bem-sucedido do Usuário A."""
    login_data = {
        "username": user_a_data["username"],
        "password": user_a_data["password"]
    } # Usa dados do User A
    url = f"{settings.API_V1_STR}/auth/login/access-token"

    response = await test_async_client.post(url, data=login_data) # Form data

    assert response.status_code == status.HTTP_200_OK
    token_data = response.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"

async def test_login_wrong_password(
    test_async_client: AsyncClient,
    test_user_a_token_and_id: tuple[str, uuid.UUID]
):
    """Testa login com senha incorreta para o Usuário A."""
    login_data = {
        "username": user_a_data["username"],
        "password": "wrongpassword"
    } 
    url = f"{settings.API_V1_STR}/auth/login/access-token"

    response = await test_async_client.post(url, data=login_data)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "incorretos" in response.json()["detail"]

async def test_login_user_not_found(
        test_async_client: AsyncClient
):
    """Testa login com usuário inexistente."""
    login_data = {"username": "nonexistentuser", "password": "password"}
    url = f"{settings.API_V1_STR}/auth/login/access-token"

    response = await test_async_client.post(url, data=login_data)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED 

# =============================
# --- Testes de User /me ---
# =============================

async def test_read_users_me_success(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str], 
    test_user_a_token_and_id: tuple[str, uuid.UUID] 
):
    """Testa obter dados do usuário logado com sucesso."""
    url = f"{settings.API_V1_STR}/auth/users/me"
    _, expected_user_id = test_user_a_token_and_id 

    response = await test_async_client.get(url, headers=auth_headers_a)

    assert response.status_code == status.HTTP_200_OK
    user_data = response.json()
    # Verifica se os campos esperados do modelo User (sem senha) estão presentes
    assert user_data["id"] == str(expected_user_id) 
    assert user_data["email"] == user_a_data["email"]
    assert user_data["username"] == user_a_data["username"]
    assert user_data["full_name"] == user_a_data["full_name"]
    assert "disabled" in user_data
    assert "hashed_password" not in user_data 
    assert "created_at" in user_data

async def test_read_users_me_unauthorized(test_async_client: AsyncClient):
    """Testa acessar /users/me sem autenticação."""
    url = f"{settings.API_V1_STR}/auth/users/me"
    response = await test_async_client.get(url)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Not authenticated" in response.json()["detail"] 

