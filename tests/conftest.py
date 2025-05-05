# tests/conftest.py
import uuid
import pytest
import pytest_asyncio
from typing import AsyncGenerator, Generator, Dict, List 
import asyncio
import logging
from httpx import AsyncClient, ASGITransport
from fastapi import status #
from app.main import app as fastapi_app
from app.core.config import settings
from app.db.mongodb_utils import connect_to_mongo, close_mongo_connection, get_database
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.db.user_crud import USERS_COLLECTION
from app.db.task_crud import TASKS_COLLECTION
from app.models.task import TaskStatus 

logger = logging.getLogger(__name__)

# --- Cliente de Teste (Escopo Function) ---
@pytest_asyncio.fixture(scope="function")

async def test_async_client() -> AsyncGenerator[AsyncClient, None]:
    db = None 
    try:
        # -- Conexão e Limpeza Antes do Teste --
        await connect_to_mongo()
        db = get_database() 

        # --- Verificar db antes de usar ---
        if db is not None:
             if "test" not in settings.DATABASE_NAME.lower():
                  logger.warning(f"Rodando testes no banco '{settings.DATABASE_NAME}'. Coleções serão limpas!")

             logger.debug("Limpando coleções ANTES do teste...")
             await db[USERS_COLLECTION].delete_many({})
             await db[TASKS_COLLECTION].delete_many({})
             logger.debug("Coleções limpas ANTES do teste.")
        else:
            pytest.fail("Falha ao conectar ao MongoDB na fixture test_async_client (setup).")


        # -- Cria e fornece o cliente --
        transport = ASGITransport(app=fastapi_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client 

    finally:
        # --- Código de limpeza no finally ---
        logger.debug("Executando limpeza pós-teste...")
        if db is not None: # Usa a variável 'db' do escopo da fixture
             try:
                 await db[USERS_COLLECTION].delete_many({})
                 await db[TASKS_COLLECTION].delete_many({})
                 logger.debug("Coleções limpas APÓS o teste.")
             except Exception as e:
                 # Loga o erro específico da limpeza, mas não falha o teste principal
                 logger.error(f"Erro ao limpar DB após teste: {e}", exc_info=True)
        else:
            logger.warning("Limpeza pós-teste pulada: Conexão com DB não estava estabelecida.")

# --- Fixtures para Usuário A ---
user_a_data = {
    "email": "testuserA@example.com",
    "username": "testuserA",
    "password": "passwordA",
    "full_name": "Test User A"
}

@pytest_asyncio.fixture(scope="function")

async def test_user_a_token_and_id(test_async_client: AsyncClient) -> tuple[str, uuid.UUID]: 
    """Registra/loga User A e retorna (token, user_id)."""
    register_url = f"{settings.API_V1_STR}/auth/register"
    login_url = f"{settings.API_V1_STR}/auth/login/access-token"
    users_me_url = f"{settings.API_V1_STR}/auth/users/me" 

    # Registrar
    reg_response = await test_async_client.post(register_url, json=user_a_data)
    if reg_response.status_code not in [status.HTTP_201_CREATED, status.HTTP_409_CONFLICT]:
        pytest.fail(f"Falha inesperada ao registrar User A: {reg_response.text}")

    # Logar para obter o token
    login_payload = {"username": user_a_data["username"], "password": user_a_data["password"]}
    login_response = await test_async_client.post(login_url, data=login_payload)
    if login_response.status_code != status.HTTP_200_OK:
         pytest.fail(f"Falha ao fazer login com User A: {login_response.text}")
    token = login_response.json()["access_token"]

    # Obter o ID do usuário via /users/me
    user_me_headers = {"Authorization": f"Bearer {token}"}
    user_me_response = await test_async_client.get(users_me_url, headers=user_me_headers)
    if user_me_response.status_code != status.HTTP_200_OK:
        pytest.fail(f"Falha ao obter dados de User A via /users/me: {user_me_response.text}")
    user_id_str = user_me_response.json()["id"]
    user_id = uuid.UUID(user_id_str) # Converte para UUID

    return token, user_id

@pytest.fixture(scope="function")

def auth_headers_a(test_user_a_token_and_id: tuple[str, uuid.UUID]) -> Dict[str, str]:
     """Retorna headers de autenticação com o token de teste do User A."""
     token, _ = test_user_a_token_and_id 
     return {"Authorization": f"Bearer {token}"}

# --- Fixtures para Usuário B ---
user_b_data = {
    "email": "testuserB@example.com",
    "username": "testuserB",
    "password": "passwordB",
    "full_name": "Test User B"
}

@pytest_asyncio.fixture(scope="function")
async def test_user_b_token(test_async_client: AsyncClient) -> str:
    register_url = f"{settings.API_V1_STR}/auth/register"
    login_url = f"{settings.API_V1_STR}/auth/login/access-token"
    reg_response = await test_async_client.post(register_url, json=user_b_data)
    if reg_response.status_code not in [status.HTTP_201_CREATED, status.HTTP_409_CONFLICT]:
         pytest.fail(f"Falha inesperada ao registrar User B: {reg_response.text}")

    login_payload = {"username": user_b_data["username"], "password": user_b_data["password"]}
    response = await test_async_client.post(login_url, data=login_payload)
    if response.status_code != status.HTTP_200_OK:
         pytest.fail(f"Falha ao fazer login com User B: {response.text}")
    return response.json()["access_token"]

@pytest.fixture(scope="function")
def auth_headers_b(test_user_b_token: str) -> Dict[str, str]:
     return {"Authorization": f"Bearer {test_user_b_token}"}

# Fixture de dados para testes de filtro/sort
@pytest_asyncio.fixture(scope="function")
async def create_filter_sort_tasks(test_async_client: AsyncClient, auth_headers_a: Dict[str, str]) -> List[Dict]:
    url = f"{settings.API_V1_STR}/tasks/"
    tasks_to_create = [
        {"title": "Filter Task P1 High", "importance": 5, "project": "Filtro", "status": TaskStatus.PENDING.value, "due_date": "2026-01-01", "tags": ["t1", "t2"]},
        {"title": "Filter Task P1 Low", "importance": 1, "project": "Filtro", "status": TaskStatus.PENDING.value, "due_date": "2026-02-01"},
        {"title": "Filter Task P2 Medium", "importance": 3, "project": "Outro", "status": TaskStatus.IN_PROGRESS.value, "tags": ["t2"]},
        {"title": "Filter Task P1 Medium", "importance": 3, "project": "Filtro", "status": TaskStatus.PENDING.value, "due_date": "2025-12-15", "tags": ["t3"]},
        {"title": "Filter Task P1 Done", "importance": 4, "project": "Filtro", "status": TaskStatus.COMPLETED.value},
    ]
    created_tasks = []
    for task_data in tasks_to_create:
        response = await test_async_client.post(url, json=task_data, headers=auth_headers_a)
        # --- Usando status importado ---
        assert response.status_code == status.HTTP_201_CREATED, f"Falha ao criar tarefa de teste: {task_data['title']}"
        created_tasks.append(response.json())
    return created_tasks