# tests/test_auth.py
"""
Este módulo contém os testes de integração para os endpoints de autenticação
da API SmartTask, definidos em `app.routers.auth`.

Os testes cobrem:
- Registro de novos usuários (sucesso, duplicatas, validação de entrada).
- Login de usuários (sucesso, falha de credenciais).
- Acesso ao endpoint `/users/me` para obter dados do usuário autenticado.
"""

# ========================
# --- Importações ---
# ========================
import uuid
from typing import Any, Dict # Adicionada para tipagem explícita

import pytest
from fastapi import status
from httpx import AsyncClient

# --- Módulos da Aplicação e Configs de Teste ---
from app.core.config import settings
from app.models.user import User # Modelo para verificar o schema de resposta
from tests.conftest import user_a_data # Dados do usuário de teste A importados de conftest

# ====================================
# --- Marcador Global de Teste ---
# ====================================
# Marca todos os testes neste arquivo para serem executados com asyncio.
pytestmark = pytest.mark.asyncio

# ==============================
# --- Testes de Registro (/auth/register) ---
# ==============================
async def test_register_user_success(test_async_client: AsyncClient):
    """
    Testa o registro bem-sucedido de um novo usuário com dados únicos.

    Verifica:
    - Status code HTTP 201 CREATED.
    - Se a resposta JSON contém os dados corretos do usuário (email, username, full_name, id).
    - Se a senha hasheada NÃO está presente na resposta.
    """
    # Dados de um novo usuário, únicos para este caso de teste específico,
    # para evitar conflitos com fixtures globais ou outros testes.
    new_user_data = {
        "email": "newuniqueuser_auth_test@example.com", # Email único
        "username": "newuniqueuser_auth_test",       # Username único
        "password": "newpassword123",
        "full_name": "New Unique Test User"
    }
    register_url = f"{settings.API_V1_STR}/auth/register"
    print(f"Testando registro de sucesso: POST {register_url} com dados: {new_user_data}")

    response = await test_async_client.post(register_url, json=new_user_data)

    # Asserções para o registro bem-sucedido
    assert response.status_code == status.HTTP_201_CREATED, \
        f"Esperado status 201, recebido {response.status_code}. Resposta: {response.text}"
    
    response_data = response.json()
    assert response_data["email"] == new_user_data["email"], "E-mail na resposta não corresponde ao esperado."
    assert response_data["username"] == new_user_data["username"], "Username na resposta não corresponde ao esperado."
    assert response_data["full_name"] == new_user_data["full_name"], "Nome completo na resposta não corresponde ao esperado."
    assert "id" in response_data, "Campo 'id' ausente na resposta de registro."
    # Garante que campos sensíveis como a senha hasheada não são retornados.
    assert "hashed_password" not in response_data, "Campo 'hashed_password' presente indevidamente na resposta."
    print(f"Registro de sucesso verificado para usuário: {response_data['username']}")

async def test_register_user_duplicate_username_case_insensitive_is_actually_sensitive(
    test_async_client: AsyncClient,
):
    """
    Testa o registro com um username que difere apenas em maiúsculas/minúsculas
    de um username existente.
    
    Contexto: Este teste verifica se a validação de unicidade de username
    é, de fato, case-SENSITIVE. Se fosse case-insensitive, o segundo registro falharia.
    Portanto, espera-se que o segundo registro seja bem-sucedido (HTTP 201).
    """
    base_url = f"{settings.API_V1_STR}/auth/register"
    unique_email_prefix = uuid.uuid4().hex[:8] # Para garantir emails únicos

    # 1. Registrar usuário inicial com username em camel case.
    user_initial_data = {
        "email": f"{unique_email_prefix}_initial@example.com",
        "username": "CamelCaseUser", # Username com variação de caixa
        "password": "password123",
    }
    print(f"Registrando usuário inicial para teste case-sensitive: {user_initial_data['username']}")
    response_initial = await test_async_client.post(base_url, json=user_initial_data)
    assert response_initial.status_code == status.HTTP_201_CREATED, \
        f"Falha ao registrar usuário inicial para teste case-sensitive: {response_initial.text}"

    # 2. Tentar registrar um novo usuário com o mesmo username, mas em minúsculas.
    #    Se a validação for case-sensitive (como esperado), este registro deve ser permitido.
    user_variant_case_data = {
        "email": f"{unique_email_prefix}_variant@example.com", # E-mail diferente
        "username": "camelcaseuser", # Mesmo username, mas em minúsculas
        "password": "password123",
    }
    print(f"Tentando registrar usuário com variação de caixa: {user_variant_case_data['username']}")
    response_variant = await test_async_client.post(base_url, json=user_variant_case_data)

    # Asserção: O registro deve ser PERMITIDO (HTTP 201) se for case-sensitive.
    assert response_variant.status_code == status.HTTP_201_CREATED, \
        (f"O registro de '{user_variant_case_data['username']}' deveria ter sido permitido (status 201) "
         f"se a validação de username for case-sensitive, mas falhou com status {response_variant.status_code}. "
         f"Resposta: {response_variant.text}. Isso pode indicar que a validação se tornou case-insensitive.")
    print(f"Registro com variação de caixa permitido para: {user_variant_case_data['username']}, confirmando case-sensitivity.")


async def test_register_user_duplicate_username(
    test_async_client: AsyncClient,
    # `test_user_a_token_and_id` garante que user_a já está registrado.
    test_user_a_token_and_id: tuple[str, uuid.UUID] 
):
    """
    Testa a tentativa de registro de um novo usuário com um username que já existe.
    Espera-se um erro HTTP 409 Conflict.
    """
    # Prepara dados para tentar registrar um novo usuário, mas usando o username do User A (que já existe).
    attempt_data = {
        "email": "anotherunique_email@example.com", # E-mail único
        "username": user_a_data["username"],       # Username do User A (duplicado)
        "password": "anotherpassword",
    }
    register_url = f"{settings.API_V1_STR}/auth/register"
    print(f"Testando registro com username duplicado: {user_a_data['username']}")

    response = await test_async_client.post(register_url, json=attempt_data)

    # Asserções para o erro de conflito
    assert response.status_code == status.HTTP_409_CONFLICT, \
        f"Esperado status 409, recebido {response.status_code}. Resposta: {response.text}"
    assert "já existe" in response.json()["detail"], \
        f"Mensagem de detalhe não contém 'já existe'. Detalhe: {response.json()['detail']}"
    print("Teste de username duplicado concluído com sucesso (conflito esperado).")

async def test_register_user_duplicate_email(
    test_async_client: AsyncClient,
    # `test_user_a_token_and_id` garante que user_a já está registrado.
    test_user_a_token_and_id: tuple[str, uuid.UUID]
):
    """
    Testa a tentativa de registro de um novo usuário com um e-mail que já existe.
    Espera-se um erro HTTP 409 Conflict.
    """
    # Prepara dados para tentar registrar um novo usuário, mas usando o e-mail do User A (que já existe).
    attempt_data = {
        "email": user_a_data["email"],             # E-mail do User A (duplicado)
        "username": "anotherunique_username_for_email_test", # Username único
        "password": "anotherpassword",
    }
    register_url = f"{settings.API_V1_STR}/auth/register"
    print(f"Testando registro com e-mail duplicado: {user_a_data['email']}")

    response = await test_async_client.post(register_url, json=attempt_data)

    # Asserções para o erro de conflito
    assert response.status_code == status.HTTP_409_CONFLICT, \
        f"Esperado status 409, recebido {response.status_code}. Resposta: {response.text}"
    assert "já registrado" in response.json()["detail"], \
        f"Mensagem de detalhe não contém 'já registrado'. Detalhe: {response.json()['detail']}"
    print("Teste de e-mail duplicado concluído com sucesso (conflito esperado).")

# ==================================================
# --- Testes de Validação de Entrada (/auth/register) ---
# ==================================================
# Este teste parametrizado verifica vários cenários de entrada inválida para o registro.
@pytest.mark.parametrize(
    "field, value, error_type, error_msg_part",
    [
        # Casos de teste para validação de campos individuais.
        ("email", "nao-e-um-email-valido", "value_error", "valid email address"),
        ("username", "us", "string_too_short", "String should have at least 3 characters"),
        ("username", "username com espacos", "string_pattern_mismatch", "match pattern"), # Assumindo que o pattern não permite espaços.
        ("username", "username!Inválido", "string_pattern_mismatch", "match pattern"), # Assumindo que o pattern não permite '!'
        ("password", "curta", "string_too_short", "String should have at least 8 characters"),
        # Casos de teste para campos obrigatórios ausentes (valor None indica remoção do campo).
        ("email", None, "missing", "Field required"),
        ("username", None, "missing", "Field required"),
        ("password", None, "missing", "Field required"),
    ]
)
async def test_register_user_invalid_input(
    test_async_client: AsyncClient,
    field: str,              # Campo a ser testado
    value: Any,              # Valor a ser atribuído ao campo (ou None para remover o campo)
    error_type: str,         # Tipo de erro esperado na resposta de validação do Pydantic/FastAPI
    error_msg_part: str      # Parte da mensagem de erro esperada
):
    """
    Testa o registro de usuário com dados de entrada inválidos específicos,
    verificando se a API retorna HTTP 422 Unprocessable Entity e se a
    mensagem de erro corresponde ao campo e tipo de erro esperados.
    """
    # Começa com um payload de dados válidos.
    valid_base_data = {
        "email": "valid_initial_email@example.com",
        "username": "validinitialuser",
        "password": "validinitialpassword",
        "full_name": "Valid Initial Name"
    }

    # Modifica o payload: se `value` for None, remove o campo; senão, define o campo com `value`.
    test_payload = valid_base_data.copy()
    if value is None:
        if field in test_payload:
            del test_payload[field]
    else:
        test_payload[field] = value
    
    register_url = f"{settings.API_V1_STR}/auth/register"
    print(f"Testando input inválido: campo='{field}', valor='{value}', payload='{test_payload}'")

    response = await test_async_client.post(register_url, json=test_payload)

    # Asserções para erro de validação HTTP 422.
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, \
        f"Esperado status 422 para input inválido (campo: {field}), recebido {response.status_code}. Resposta: {response.text}"
    
    error_details = response.json().get("detail", [])
    assert isinstance(error_details, list), "Detalhe do erro HTTP 422 não é uma lista."

    # Verifica se o erro específico esperado está presente na lista de detalhes.
    found_expected_error = False
    for error_item in error_details:
        # `error_item['loc']` é uma lista, ex: ['body', 'email']
        field_location_match = isinstance(error_item.get("loc"), list) and field in error_item["loc"]
        type_match = error_item.get("type") == error_type
        # Verifica se `error_msg_part` está contido na mensagem de erro.
        msg_match = error_msg_part.lower() in error_item.get("msg", "").lower()

        if field_location_match and type_match and msg_match:
            found_expected_error = True
            break
    
    assert found_expected_error, \
        (f"Erro de validação esperado para campo '{field}' com tipo '{error_type}' e mensagem contendo '{error_msg_part}' "
         f"não foi encontrado nos detalhes do erro: {error_details}")
    print(f"Input inválido verificado para campo='{field}', tipo='{error_type}'.")

# ===============================================
# --- Testes de Login (/auth/login/access-token) ---
# ===============================================
async def test_login_success(
    test_async_client: AsyncClient,
    # `test_user_a_token_and_id` garante que User A está registrado e fornece seus dados.
    test_user_a_token_and_id: tuple[str, uuid.UUID]
):
    """
    Testa o login bem-sucedido do Usuário A.

    Verifica:
    - Status code HTTP 200 OK.
    - Se a resposta JSON contém 'access_token' e 'token_type' ("bearer").
    """
    # Usa os dados do Usuário A definidos em conftest.py.
    login_payload_form_data = {
        "username": user_a_data["username"],
        "password": user_a_data["password"]
    }
    login_url = f"{settings.API_V1_STR}/auth/login/access-token"
    print(f"Testando login de sucesso para usuário: {user_a_data['username']}")

    # O endpoint de login espera dados de formulário (form data), não JSON.
    response = await test_async_client.post(login_url, data=login_payload_form_data)

    # Asserções para login bem-sucedido.
    assert response.status_code == status.HTTP_200_OK, \
        f"Esperado status 200, recebido {response.status_code}. Resposta: {response.text}"
    
    token_data = response.json()
    assert "access_token" in token_data, "Campo 'access_token' ausente na resposta de login."
    assert token_data.get("token_type") == "bearer", "Tipo do token não é 'bearer'."
    print(f"Login de sucesso verificado para usuário: {user_a_data['username']}")

async def test_login_wrong_password(
    test_async_client: AsyncClient,
    test_user_a_token_and_id: tuple[str, uuid.UUID]
):
    """
    Testa a tentativa de login do Usuário A com uma senha incorreta.
    Espera-se um erro HTTP 401 Unauthorized.
    """
    login_payload_form_data = {
        "username": user_a_data["username"],
        "password": "thisisawrongpassword" # Senha incorreta.
    }
    login_url = f"{settings.API_V1_STR}/auth/login/access-token"
    print(f"Testando login com senha incorreta para usuário: {user_a_data['username']}")

    response = await test_async_client.post(login_url, data=login_payload_form_data)

    # Asserções para falha de autenticação.
    assert response.status_code == status.HTTP_401_UNAUTHORIZED, \
        f"Esperado status 401, recebido {response.status_code}. Resposta: {response.text}"
    assert "incorretos" in response.json()["detail"].lower(), \
        f"Mensagem de detalhe não contém 'incorretos'. Detalhe: {response.json()['detail']}"
    print("Login com senha incorreta verificado (erro 401 esperado).")

async def test_login_user_not_found(test_async_client: AsyncClient):
    """
    Testa a tentativa de login com um nome de usuário que não existe no sistema.
    Espera-se um erro HTTP 401 Unauthorized.
    """
    login_payload_form_data = {
        "username": "nonexistent_test_user",
        "password": "any_password"
    }
    login_url = f"{settings.API_V1_STR}/auth/login/access-token"
    print(f"Testando login com usuário inexistente: {login_payload_form_data['username']}")

    response = await test_async_client.post(login_url, data=login_payload_form_data)

    # Asserção para falha de autenticação.
    assert response.status_code == status.HTTP_401_UNAUTHORIZED, \
        f"Esperado status 401 para usuário inexistente, recebido {response.status_code}. Resposta: {response.text}"
    print("Login com usuário inexistente verificado (erro 401 esperado).")

# =======================================
# --- Testes de /auth/users/me ---
# =======================================
async def test_read_users_me_success(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str], # Cabeçalhos de autenticação do User A.
    test_user_a_token_and_id: tuple[str, uuid.UUID] # Para obter o ID esperado.
):
    """
    Testa o acesso bem-sucedido ao endpoint `/users/me` para obter
    os dados do usuário autenticado (User A).

    Verifica:
    - Status code HTTP 200 OK.
    - Se os dados retornados correspondem aos dados do User A (ID, email, username, full_name).
    - Se o campo 'disabled' está presente.
    - Se a senha hasheada NÃO está presente.
    - Se o campo 'created_at' está presente.
    """
    users_me_url = f"{settings.API_V1_STR}/auth/users/me"
    _, expected_user_id = test_user_a_token_and_id # Obtém o ID do User A da fixture.
    print(f"Testando /users/me para usuário: {user_a_data['username']}")

    response = await test_async_client.get(users_me_url, headers=auth_headers_a)

    # Asserções para sucesso.
    assert response.status_code == status.HTTP_200_OK, \
        f"Esperado status 200, recebido {response.status_code}. Resposta: {response.text}"
    
    user_response_data = response.json()
    # Verifica se o modelo User é retornado corretamente.
    assert user_response_data["id"] == str(expected_user_id), "ID do usuário não corresponde."
    assert user_response_data["email"] == user_a_data["email"], "E-mail não corresponde."
    assert user_response_data["username"] == user_a_data["username"], "Username não corresponde."
    assert user_response_data["full_name"] == user_a_data["full_name"], "Nome completo não corresponde."
    assert "disabled" in user_response_data, "Campo 'disabled' ausente."
    assert "hashed_password" not in user_response_data, "Campo 'hashed_password' presente indevidamente."
    assert "created_at" in user_response_data, "Campo 'created_at' ausente."
    # Validação opcional contra o modelo Pydantic User (se a resposta não for muito grande/complexa).
    # User.model_validate(user_response_data) 
    print(f"/users/me verificado com sucesso para usuário: {user_a_data['username']}")

async def test_read_users_me_unauthorized_no_token(test_async_client: AsyncClient):
    """
    Testa o acesso ao endpoint `/users/me` sem fornecer um token de autenticação.
    Espera-se um erro HTTP 401 Unauthorized.
    """
    users_me_url = f"{settings.API_V1_STR}/auth/users/me"
    print("Testando /users/me sem token de autenticação.")

    response = await test_async_client.get(users_me_url) # NENHUM header de autenticação.

    # Asserções para não autorizado.
    assert response.status_code == status.HTTP_401_UNAUTHORIZED, \
        f"Esperado status 401, recebido {response.status_code}. Resposta: {response.text}"
    # A mensagem "Not authenticated" é o padrão da FastAPI para falta de token com `OAuth2PasswordBearer`.
    assert "Not authenticated" in response.json()["detail"], \
        f"Mensagem de detalhe não é 'Not authenticated'. Detalhe: {response.json()['detail']}"
    print("/users/me sem token verificado (erro 401 esperado).")

async def test_read_users_me_invalid_token(test_async_client: AsyncClient):
    """
    Testa o acesso ao endpoint `/users/me` fornecendo um token JWT inválido/malformado.
    Espera-se um erro HTTP 401 Unauthorized.
    """
    users_me_url = f"{settings.API_V1_STR}/auth/users/me"
    invalid_token_headers = {"Authorization": "Bearer an.invalid.jwt.token"}
    print("Testando /users/me com token JWT inválido.")

    response = await test_async_client.get(users_me_url, headers=invalid_token_headers)
    
    # Asserções para não autorizado.
    assert response.status_code == status.HTTP_401_UNAUTHORIZED, \
        f"Esperado status 401 para token inválido, recebido {response.status_code}. Resposta: {response.text}"
    error_detail = response.json()["detail"]
    expected_error_message_part_pt = "não foi possível validar as credenciais"
    assert expected_error_message_part_pt.lower() in error_detail.lower(), \
        (f"Mensagem de detalhe para token inválido não contém '{expected_error_message_part_pt}'. "
         f"Detalhe recebido: '{error_detail}'")
    print("/users/me com token inválido verificado (erro 401 esperado).")