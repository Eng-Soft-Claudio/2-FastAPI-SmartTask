# tests/test_auth.py
"""
Este módulo contém testes de integração para os endpoints de autenticação
da API SmartTask, definidos em `app.routers.auth`.

Os testes cobrem:
- Registro de novos usuários, incluindo cenários de sucesso e conflito (duplicidade).
- Validação de entrada para o registro de usuários.
- Login de usuários, incluindo sucesso, senha incorreta e usuário não encontrado/desativado.
- Acesso a dados do usuário autenticado (`/users/me`).
- Atualização de dados do usuário autenticado.
- Deleção da conta do usuário autenticado.

As fixtures para cliente HTTP e usuários de teste são definidas em `conftest.py`.
"""

# ========================
# --- Importações ---
# ========================
import uuid
from typing import Any, Dict

import pytest
from fastapi import status
from httpx import AsyncClient
from unittest.mock import MagicMock, patch
from pymongo.errors import DuplicateKeyError

# --- Módulos da Aplicação e Configs de Teste ---
from app.core.config import settings
from app.db import user_crud
from app.models.user import User, UserInDB, UserUpdate
from app.routers import auth
from tests.conftest import user_a_data

# ========================
# --- Marcador Global de Teste ---
# ========================
pytestmark = pytest.mark.asyncio

# ========================
# --- Testes de Registro (/auth/register) ---
# ========================
async def test_register_user_success(test_async_client: AsyncClient):
    """
    Testa o registro bem-sucedido de um novo usuário com dados únicos.
    """
    # --- Arrange ---
    new_user_data = {
        "email": "newuniqueuser_auth_test@example.com",
        "username": "newuniqueuser_auth_test",
        "password": "newpassword123",
        "full_name": "New Unique Test User"
    }
    register_url = f"{settings.API_V1_STR}/auth/register"

    # --- Act ---
    response = await test_async_client.post(register_url, json=new_user_data)

    # --- Assert ---
    assert response.status_code == status.HTTP_201_CREATED
    response_data = response.json()
    assert response_data["email"] == new_user_data["email"]
    assert response_data["username"] == new_user_data["username"]
    assert response_data["full_name"] == new_user_data["full_name"]
    assert "id" in response_data
    assert "hashed_password" not in response_data

async def test_register_user_duplicate_username_case_insensitive_is_actually_sensitive(
    test_async_client: AsyncClient,
):
    """
    Testa o registro com um username que difere apenas em maiúsculas/minúsculas
    de um username existente.
    """
    # --- Arrange ---
    base_url = f"{settings.API_V1_STR}/auth/register"
    unique_email_prefix = uuid.uuid4().hex[:8]

    user_initial_data = {
        "email": f"{unique_email_prefix}_initial@example.com",
        "username": "CamelCaseUser",
        "password": "password123",
    }
    response_initial = await test_async_client.post(base_url, json=user_initial_data)
    assert response_initial.status_code == status.HTTP_201_CREATED

    user_variant_case_data = {
        "email": f"{unique_email_prefix}_variant@example.com",
        "username": "camelcaseuser",
        "password": "password123",
    }

    # --- Act ---
    response_variant = await test_async_client.post(base_url, json=user_variant_case_data)

    # --- Assert ---
    assert response_variant.status_code == status.HTTP_201_CREATED

async def test_register_user_duplicate_username(
    test_async_client: AsyncClient,
    test_user_a_token_and_id: tuple[str, uuid.UUID]
):
    """
    Testa a tentativa de registro de um novo usuário com um username que já existe.
    """
    # --- Arrange ---
    attempt_data = {
        "email": "anotherunique_email@example.com",
        "username": user_a_data["username"],
        "password": "anotherpassword",
    }
    register_url = f"{settings.API_V1_STR}/auth/register"

    # --- Act ---
    response = await test_async_client.post(register_url, json=attempt_data)

    # --- Assert ---
    assert response.status_code == status.HTTP_409_CONFLICT
    assert "já existe" in response.json()["detail"]

async def test_register_user_duplicate_email(
    test_async_client: AsyncClient,
    test_user_a_token_and_id: tuple[str, uuid.UUID]
):
    """
    Testa a tentativa de registro de um novo usuário com um e-mail que já existe.
    """
    # --- Arrange ---
    attempt_data = {
        "email": user_a_data["email"],
        "username": "anotherunique_username_for_email_test",
        "password": "anotherpassword",
    }
    register_url = f"{settings.API_V1_STR}/auth/register"

    # --- Act ---
    response = await test_async_client.post(register_url, json=attempt_data)

    # --- Assert ---
    assert response.status_code == status.HTTP_409_CONFLICT
    assert "já registrado" in response.json()["detail"]

async def test_register_user_crud_returns_none(test_async_client: AsyncClient, mocker): # type: ignore
    """
    Testa o registro quando user_crud.create_user retorna None.
    Deve resultar em erro 500 com a mensagem genérica devido à estrutura do try/except.
    """
    # --- Arrange ---
    user_data = {
        "email": "crudnone@example.com",
        "username": "crudnoneuser",
        "password": "password123"
    }
    register_url = f"{settings.API_V1_STR}/auth/register"

    mocker.patch("app.routers.auth.user_crud.get_user_by_username", return_value=None)
    mocker.patch("app.routers.auth.user_crud.get_user_by_email", return_value=None)
    mocker.patch("app.routers.auth.user_crud.create_user", return_value=None)

    # --- Act ---
    response = await test_async_client.post(register_url, json=user_data)

    # --- Assert ---
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    # Espera a mensagem do except Exception genérico
    assert "Ocorreu um erro inesperado" in response.json()["detail"]

async def test_register_user_crud_generic_exception(test_async_client: AsyncClient, mocker):
    """
    Testa o registro quando user_crud.create_user levanta Exception genérica.
    """
    # --- Arrange ---
    user_data = {
        "email": "crudexception@example.com",
        "username": "crudexcuser",
        "password": "password123"
    }
    register_url = f"{settings.API_V1_STR}/auth/register"
    simulated_error = Exception("Erro genérico simulado no CRUD")

    mocker.patch("app.routers.auth.user_crud.get_user_by_username", return_value=None)
    mocker.patch("app.routers.auth.user_crud.get_user_by_email", return_value=None)
    mocker.patch("app.routers.auth.user_crud.create_user", side_effect=simulated_error)

    # --- Act ---
    response = await test_async_client.post(register_url, json=user_data)

    # --- Assert ---
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Ocorreu um erro inesperado" in response.json()["detail"]

# ========================
# --- Testes de Validação de Entrada (/auth/register) ---
# ========================
@pytest.mark.parametrize(
    "field, value, error_type, error_msg_part",
    [
        ("email", "nao-e-um-email-valido", "value_error", "valid email address"),
        ("username", "us", "string_too_short", "String should have at least 3 characters"),
        ("username", "username com espacos", "string_pattern_mismatch", "match pattern"),
        ("username", "username!Inválido", "string_pattern_mismatch", "match pattern"),
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
    """
    Testa o registro de usuário com dados de entrada inválidos específicos.
    """
    # --- Arrange ---
    valid_base_data = {
        "email": "valid_initial_email@example.com",
        "username": "validinitialuser",
        "password": "validinitialpassword",
        "full_name": "Valid Initial Name"
    }
    test_payload = valid_base_data.copy()
    if value is None:
        if field in test_payload:
            del test_payload[field]
    else:
        test_payload[field] = value

    register_url = f"{settings.API_V1_STR}/auth/register"

    # --- Act ---
    response = await test_async_client.post(register_url, json=test_payload)

    # --- Assert ---
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    error_details = response.json().get("detail", [])
    assert isinstance(error_details, list)
    found_expected_error = False
    for error_item in error_details:
        field_location_match = isinstance(error_item.get("loc"), list) and field in error_item["loc"]
        type_match = error_item.get("type") == error_type
        msg_match = error_msg_part.lower() in error_item.get("msg", "").lower()

        if field_location_match and type_match and msg_match:
            found_expected_error = True
            break
    assert found_expected_error

# ========================
# --- Testes de Login (/auth/login/access-token) ---
# ========================
async def test_login_success(
    test_async_client: AsyncClient,
    test_user_a_token_and_id: tuple[str, uuid.UUID]
):
    """
    Testa o login bem-sucedido do Usuário A.
    """
    # --- Arrange ---
    login_payload_form_data = {
        "username": user_a_data["username"],
        "password": user_a_data["password"]
    }
    login_url = f"{settings.API_V1_STR}/auth/login/access-token"

    # --- Act ---
    response = await test_async_client.post(login_url, data=login_payload_form_data)

    # --- Assert ---
    assert response.status_code == status.HTTP_200_OK
    token_data = response.json()
    assert "access_token" in token_data
    assert token_data.get("token_type") == "bearer"

async def test_login_wrong_password(
    test_async_client: AsyncClient,
    test_user_a_token_and_id: tuple[str, uuid.UUID]
):
    """
    Testa a tentativa de login do Usuário A com uma senha incorreta.
    """
    # --- Arrange ---
    login_payload_form_data = {
        "username": user_a_data["username"],
        "password": "thisisawrongpassword"
    }
    login_url = f"{settings.API_V1_STR}/auth/login/access-token"

    # --- Act ---
    response = await test_async_client.post(login_url, data=login_payload_form_data)

    # --- Assert ---
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "incorretos" in response.json()["detail"].lower()

async def test_login_user_not_found(test_async_client: AsyncClient):
    """
    Testa a tentativa de login com um nome de usuário que não existe no sistema.
    """
    # --- Arrange ---
    login_payload_form_data = {
        "username": "nonexistent_test_user",
        "password": "any_password"
    }
    login_url = f"{settings.API_V1_STR}/auth/login/access-token"

    # --- Act ---
    response = await test_async_client.post(login_url, data=login_payload_form_data)

    # --- Assert ---
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

async def test_login_disabled_user(test_async_client: AsyncClient, mocker):
    """
    Testa a tentativa de login com um usuário que está desabilitado.
    Espera-se um erro HTTP 400 Bad Request.
    """
    # --- Arrange ---
    disabled_username = "disabled_user_login"
    password = "password_for_disabled"
    login_url = f"{settings.API_V1_STR}/auth/login/access-token"
    login_payload_form_data = {
        "username": disabled_username,
        "password": password
    }

    disabled_user_mock = MagicMock(spec=UserInDB)
    disabled_user_mock.username = disabled_username
    disabled_user_mock.hashed_password = "some_valid_hash"
    disabled_user_mock.disabled = True

    mock_get_user_by_username = mocker.patch("app.routers.auth.user_crud.get_user_by_username", return_value=disabled_user_mock)
    mock_verify_password = mocker.patch("app.routers.auth.verify_password", return_value=True)
    mock_create_token = mocker.patch("app.routers.auth.create_access_token")

    # --- Act ---
    response = await test_async_client.post(login_url, data=login_payload_form_data)

    # --- Assert ---
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "A conta do usuário está inativa." == response.json()["detail"]
    mock_create_token.assert_not_called()
    mock_get_user_by_username.assert_called_once_with(mocker.ANY, disabled_username)
    mock_verify_password.assert_called_once_with(password, disabled_user_mock.hashed_password)

# ========================
# --- Testes de /auth/users/me ---
# ========================
async def test_read_users_me_success(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    test_user_a_token_and_id: tuple[str, uuid.UUID]
):
    """
    Testa o acesso bem-sucedido ao endpoint `/users/me` para obter
    os dados do usuário autenticado (User A).
    """
    # --- Arrange ---
    users_me_url = f"{settings.API_V1_STR}/auth/users/me"
    _, expected_user_id = test_user_a_token_and_id

    # --- Act ---
    response = await test_async_client.get(users_me_url, headers=auth_headers_a)

    # --- Assert ---
    assert response.status_code == status.HTTP_200_OK
    user_response_data = response.json()
    assert user_response_data["id"] == str(expected_user_id)
    assert user_response_data["email"] == user_a_data["email"]
    assert user_response_data["username"] == user_a_data["username"]
    assert user_response_data["full_name"] == user_a_data["full_name"]
    assert "disabled" in user_response_data
    assert "hashed_password" not in user_response_data
    assert "created_at" in user_response_data

async def test_read_users_me_unauthorized_no_token(test_async_client: AsyncClient):
    """
    Testa o acesso ao endpoint `/users/me` sem fornecer um token de autenticação.
    """
    # --- Arrange ---
    users_me_url = f"{settings.API_V1_STR}/auth/users/me"

    # --- Act ---
    response = await test_async_client.get(users_me_url)

    # --- Assert ---
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Not authenticated" in response.json()["detail"]

async def test_read_users_me_invalid_token(test_async_client: AsyncClient, mocker):
    """
    Testa o acesso ao endpoint `/users/me` fornecendo um token JWT inválido/malformado.
    """
    # --- Arrange ---
    users_me_url = f"{settings.API_V1_STR}/auth/users/me"
    invalid_token_headers = {"Authorization": "Bearer an.invalid.jwt.token"}
    mocker.patch("app.core.security.logger")

    # --- Act ---
    response = await test_async_client.get(users_me_url, headers=invalid_token_headers)

    # --- Assert ---
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    error_detail = response.json()["detail"]
    expected_error_message_part_pt = "não foi possível validar as credenciais"
    assert expected_error_message_part_pt.lower() in error_detail.lower()

# ========================
# --- Testes de PUT /users/me ---
# ========================
async def test_update_me_success(test_async_client: AsyncClient, mocker, auth_headers_a, test_user_a_token_and_id):
    """
    Testa a atualização bem-sucedida dos dados do usuário autenticado.
    """
    # --- Arrange ---
    token, user_id_a = test_user_a_token_and_id
    url = f"{settings.API_V1_STR}/auth/users/me"
    update_payload = {"full_name": "User A Updated Name"}

    mock_updated_user = MagicMock(spec=UserInDB)
    mock_api_user_return = MagicMock(spec=User)
    mock_api_user_return.id = user_id_a
    mock_api_user_return.username = user_a_data["username"]
    mock_api_user_return.email = user_a_data["email"]
    mock_api_user_return.full_name = update_payload["full_name"]
    mock_api_user_return.disabled = False
    mock_crud_update = mocker.patch("app.routers.auth.user_crud.update_user", return_value=mock_updated_user)
    mocker.patch("app.routers.auth.User.model_validate", return_value=mock_api_user_return)

    # --- Act ---
    response = await test_async_client.put(url, json=update_payload, headers=auth_headers_a)

    # --- Assert ---
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert response_data["full_name"] == update_payload["full_name"]
    assert response_data["id"] == str(user_id_a)

    mock_crud_update.assert_called_once()
    call_args, call_kwargs = mock_crud_update.call_args
    assert call_kwargs['user_id'] == user_id_a
    crud_update_payload_arg = None
    if 'user_update' in call_kwargs:
        crud_update_payload_arg = call_kwargs['user_update']
    else:
         pytest.fail("Argumento 'user_update' não encontrado na chamada mockada do CRUD.")

    assert isinstance(crud_update_payload_arg, UserUpdate)
    assert crud_update_payload_arg.full_name == update_payload["full_name"]
    assert crud_update_payload_arg.email is None

async def test_update_me_password_success(test_async_client: AsyncClient, mocker, auth_headers_a, test_user_a_token_and_id):
    """
    Testa a atualização bem-sucedida da senha do usuário autenticado.
    """
    # --- Arrange ---
    token, user_id_a = test_user_a_token_and_id
    url = f"{settings.API_V1_STR}/auth/users/me"
    new_password = "newpassword123!"
    update_payload = {"password": new_password}

    mock_updated_user = MagicMock(spec=UserInDB)
    mock_api_user_return = MagicMock(spec=User)
    mock_api_user_return.id = user_id_a
    mock_api_user_return.username = user_a_data["username"]
    mock_api_user_return.email = user_a_data["email"]
    mock_api_user_return.full_name = user_a_data["full_name"]
    mock_api_user_return.disabled = False
    mock_crud_update = mocker.patch("app.routers.auth.user_crud.update_user", return_value=mock_updated_user)
    mocker.patch("app.routers.auth.User.model_validate", return_value=mock_api_user_return)

    # --- Act ---
    response = await test_async_client.put(url, json=update_payload, headers=auth_headers_a)

    # --- Assert ---
    assert response.status_code == status.HTTP_200_OK

    mock_crud_update.assert_called_once()
    call_args, call_kwargs = mock_crud_update.call_args
    assert call_kwargs['user_id'] == user_id_a

    crud_update_payload_arg = call_kwargs.get('user_update')
    assert crud_update_payload_arg is not None
    assert isinstance(crud_update_payload_arg, UserUpdate)
    assert crud_update_payload_arg.password == new_password
    assert crud_update_payload_arg.full_name is None

async def test_update_me_user_crud_returns_none(test_async_client: AsyncClient, mocker, auth_headers_a, test_user_a_token_and_id):
    """
    Testa o comportamento da rota PUT /users/me quando
    user_crud.update_user retorna None (resultando em 500 devido ao except genérico).
    """
    # --- Arrange ---
    token, user_id_a = test_user_a_token_and_id
    url = f"{settings.API_V1_STR}/auth/users/me"
    update_payload = {"full_name": "Nome Nao Aplicado"}
    mock_crud_update = mocker.patch("app.routers.auth.user_crud.update_user", return_value=None)

    # --- Act ---
    response = await test_async_client.put(url, json=update_payload, headers=auth_headers_a)

    # --- Assert ---
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Ocorreu um erro inesperado durante a atualização do usuário." in response.json()["detail"] # Mensagem mantida do original

    mock_crud_update.assert_called_once()
    call_args, call_kwargs = mock_crud_update.call_args
    assert call_kwargs['user_id'] == user_id_a
    crud_update_payload_arg = call_kwargs.get('user_update')
    assert isinstance(crud_update_payload_arg, UserUpdate)
    assert crud_update_payload_arg.full_name == update_payload["full_name"]

async def test_update_me_duplicate_key_error(test_async_client: AsyncClient, mocker, auth_headers_a, test_user_a_token_and_id):
    """
    Testa o tratamento de DuplicateKeyError na rota PUT /users/me.
    """
    # --- Arrange ---
    token, user_id_a = test_user_a_token_and_id
    url = f"{settings.API_V1_STR}/auth/users/me"
    duplicate_email = "email.duplicado@teste.com"
    update_payload = {"email": duplicate_email}

    simulated_error = DuplicateKeyError("Erro de chave duplicada simulado")
    mock_crud_update = mocker.patch("app.routers.auth.user_crud.update_user", side_effect=simulated_error)

    # --- Act ---
    response = await test_async_client.put(url, json=update_payload, headers=auth_headers_a)

    # --- Assert ---
    assert response.status_code == status.HTTP_409_CONFLICT
    assert f"o e-mail '{duplicate_email}' já está em uso" in response.json()["detail"]

    mock_crud_update.assert_called_once()
    call_args, call_kwargs = mock_crud_update.call_args
    assert call_kwargs['user_id'] == user_id_a
    crud_update_payload_arg = call_kwargs.get('user_update')
    assert isinstance(crud_update_payload_arg, UserUpdate)
    assert crud_update_payload_arg.email == update_payload["email"]

async def test_update_me_generic_exception(test_async_client: AsyncClient, mocker, auth_headers_a, test_user_a_token_and_id):
    """
    Testa o tratamento de exceção genérica na rota PUT /users/me.
    """
    # --- Arrange ---
    token, user_id_a = test_user_a_token_and_id
    url = f"{settings.API_V1_STR}/auth/users/me"
    update_payload = {"full_name": "Nome Inalterado"}

    simulated_error = Exception("Erro genérico simulado no update do CRUD")
    mock_crud_update = mocker.patch("app.routers.auth.user_crud.update_user", side_effect=simulated_error)

    # --- Act ---
    response = await test_async_client.put(url, json=update_payload, headers=auth_headers_a)

    # --- Assert ---
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Ocorreu um erro inesperado durante a atualização do usuário." in response.json()["detail"]

    mock_crud_update.assert_called_once()
    call_args, call_kwargs = mock_crud_update.call_args
    assert call_kwargs['user_id'] == user_id_a
    crud_update_payload_arg = call_kwargs.get('user_update')
    assert isinstance(crud_update_payload_arg, UserUpdate)
    assert crud_update_payload_arg.full_name == update_payload["full_name"]

# ========================
# --- Testes de DELETE /users/me ---
# ========================
async def test_delete_me_success(test_async_client: AsyncClient, mocker, auth_headers_a, test_user_a_token_and_id):
    """
    Testa a deleção bem-sucedida da conta do usuário autenticado.
    """
    # --- Arrange ---
    token, user_id_a = test_user_a_token_and_id
    url = f"{settings.API_V1_STR}/auth/users/me"

    mock_crud_delete = mocker.patch("app.routers.auth.user_crud.delete_user", return_value=True)

    # --- Act ---
    response = await test_async_client.delete(url, headers=auth_headers_a)

    # --- Assert ---
    assert response.status_code == status.HTTP_204_NO_CONTENT

    mock_crud_delete.assert_called_once()
    call_args, call_kwargs = mock_crud_delete.call_args
    found_user_id_arg = False
    if len(call_args) > 1 and call_args[1] == user_id_a:
         found_user_id_arg = True
    elif call_kwargs.get('user_id') == user_id_a:
         found_user_id_arg = True
    assert found_user_id_arg is True

async def test_delete_me_crud_returns_false(test_async_client: AsyncClient, mocker, auth_headers_a, test_user_a_token_and_id):
    """
    Testa o comportamento de DELETE /users/me quando
    user_crud.delete_user retorna False (resultando em 500 devido ao except genérico).
    """
    # --- Arrange ---
    token, user_id_a = test_user_a_token_and_id
    url = f"{settings.API_V1_STR}/auth/users/me"

    mock_crud_delete = mocker.patch("app.routers.auth.user_crud.delete_user", return_value=False)

    # --- Act ---
    response = await test_async_client.delete(url, headers=auth_headers_a)

    # --- Assert ---
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Ocorreu um erro inesperado durante a deleção do usuário." in response.json()["detail"]

    mock_crud_delete.assert_called_once()
    call_args, call_kwargs = mock_crud_delete.call_args
    found_user_id_arg = False
    if len(call_args) > 1 and call_args[1] == user_id_a:
         found_user_id_arg = True
    elif call_kwargs.get('user_id') == user_id_a:
         found_user_id_arg = True
    assert found_user_id_arg is True

async def test_delete_me_crud_generic_exception(test_async_client: AsyncClient, mocker, auth_headers_a, test_user_a_token_and_id): # type: ignore
    """
    Testa o tratamento de exceção genérica na rota DELETE /users/me
    quando o CRUD levanta um erro.
    """
    # --- Arrange ---
    token, user_id_a = test_user_a_token_and_id
    url = f"{settings.API_V1_STR}/auth/users/me"

    # Mock user_crud.delete_user para levantar Exception genérica
    simulated_error = Exception("Erro genérico simulado no delete do CRUD")
    mock_crud_delete = mocker.patch("app.routers.auth.user_crud.delete_user", side_effect=simulated_error)

    # --- Act ---
    response = await test_async_client.delete(url, headers=auth_headers_a)

    # --- Assert ---
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Ocorreu um erro inesperado durante a deleção do usuário." in response.json()["detail"]

    # Verificar se user_crud.delete_user foi chamado
    mock_crud_delete.assert_called_once()
    call_args, call_kwargs = mock_crud_delete.call_args
    found_user_id_arg = False
    if len(call_args) > 1 and call_args[1] == user_id_a:
         found_user_id_arg = True
    elif call_kwargs.get('user_id') == user_id_a:
         found_user_id_arg = True
    assert found_user_id_arg is True