# tests/conftest.py
# Inibir warnings de depreciação de bibliotecas
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="passlib")

# ========================
# --- Configuração .env.test ---
# ========================
from dotenv import load_dotenv
import os
load_dotenv(dotenv_path='.env.test')

"""
Este módulo define fixtures do Pytest que são compartilhadas entre diferentes
arquivos de teste na suíte de testes da aplicação SmartTask.

Fixtures incluem:
- Cliente HTTP assíncrono (`test_async_client`) para interagir com a API FastAPI.
  Este cliente também gerencia a conexão com o banco de dados de teste e realiza
  a limpeza das coleções antes e depois de cada teste.
- Dados de teste para usuários (User A e User B).
- Fixtures para registrar/logar usuários de teste e obter seus tokens/IDs.
- Fixtures para gerar cabeçalhos de autenticação.
- Fixtures para criar dados de exemplo (como tarefas) para testes específicos
  de listagem, filtragem e ordenação.

O objetivo é prover um ambiente de teste limpo e consistente para cada caso de teste.
"""

# ========================
# --- Importações ---
# ========================
import asyncio
import logging
import uuid
from typing import AsyncGenerator, Dict, List, Any, Optional
import pytest
import pytest_asyncio
from fastapi import status
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorDatabase

# --- Módulos da Aplicação ---
from app.core.config import settings
from app.db.mongodb_utils import (close_mongo_connection, connect_to_mongo, get_database)
from app.db.task_crud import TASKS_COLLECTION
from app.db.user_crud import USERS_COLLECTION
from app.main import app as fastapi_app
from app.models.task import TaskStatus

# ========================
# --- Configurações e Constantes ---
# ========================
logger = logging.getLogger(__name__)

# ========================
# --- Fixture Principal: Cliente de Teste HTTP ---
# ========================
@pytest_asyncio.fixture(scope="function")
async def test_async_client() -> AsyncGenerator[AsyncClient, None]:
    """
    Fixture assíncrona com escopo de função para prover um cliente HTTP (`AsyncClient`)
    para interagir com a aplicação FastAPI.

    Responsabilidades:
    - Estabelece e fecha a conexão com o MongoDB de teste.
    - **Limpa as coleções `USERS_COLLECTION` e `TASKS_COLLECTION` antes e depois de cada teste**
      para garantir a isolação e idempotência dos testes.
    - Emite um aviso se o nome do banco de dados não contiver "test", como precaução.
    - Fornece o `AsyncClient` configurado com `ASGITransport` para testar a aplicação
      diretamente, sem passar por uma camada de rede real.

    Yields:
        AsyncClient: Uma instância do cliente HTTP assíncrona.

    Raises:
        pytest.fail: Se a conexão com o MongoDB falhar durante o setup.
    """
    db_instance: Optional[AsyncIOMotorDatabase] = None
    logger.debug("Fixture 'test_async_client': Iniciando setup...")

    try:
        await connect_to_mongo()
        db_instance = get_database()

        if db_instance is not None:
            if "test" not in settings.DATABASE_NAME.lower(): 
                logger.warning(
                    f"ATENÇÃO: Testes estão sendo executados no banco de dados '{settings.DATABASE_NAME}'. "
                    "As coleções de usuários e tarefas serão limpas!"
                )

            logger.debug(f"Fixture 'test_async_client': Limpando coleções ANTES do teste no DB '{settings.DATABASE_NAME}'...")
            await db_instance[USERS_COLLECTION].delete_many({})
            await db_instance[TASKS_COLLECTION].delete_many({})
            logger.info(f"Fixture 'test_async_client': Coleções '{USERS_COLLECTION}' e '{TASKS_COLLECTION}' limpas ANTES do teste.")
        else: 
            logger.error("Fixture 'test_async_client': Falha crítica ao conectar ao MongoDB durante o setup.")
            pytest.fail("Falha ao obter instância do banco de dados na fixture test_async_client (setup).")

        transport = ASGITransport(app=fastapi_app) 
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            logger.debug("Fixture 'test_async_client': Cliente HTTP fornecido ao teste.")
            yield client

    finally:
        logger.debug("Fixture 'test_async_client': Iniciando limpeza PÓS-teste...")
        if db_instance is not None:
            try:
                logger.debug(f"Fixture 'test_async_client': Limpando coleções APÓS o teste no DB '{settings.DATABASE_NAME}'...")
                await db_instance[USERS_COLLECTION].delete_many({})
                await db_instance[TASKS_COLLECTION].delete_many({})
                logger.info(f"Fixture 'test_async_client': Coleções '{USERS_COLLECTION}' e '{TASKS_COLLECTION}' limpas APÓS o teste.")
            except Exception as e_cleanup: 
                logger.error(f"Fixture 'test_async_client': Erro durante a limpeza do DB PÓS-teste: {e_cleanup}", exc_info=True)
        else: 
            logger.warning("Fixture 'test_async_client': Limpeza PÓS-teste pulada - conexão com DB não estabelecida.")

        logger.debug("Fixture 'test_async_client': Fechando conexão MongoDB principal (se houver)...")
        await close_mongo_connection()
        logger.debug("Fixture 'test_async_client': Setup e teardown concluídos.")

# ========================
# --- Fixtures para Usuário de Teste A ---
# ========================
user_a_data: Dict[str, str] = {
    "email": "testuserA@example.com",
    "username": "testuserA",
    "password": "passwordA",
    "full_name": "Test User A"
}

@pytest_asyncio.fixture(scope="function")
async def test_user_a_token_and_id(test_async_client: AsyncClient) -> tuple[str, uuid.UUID]:
    """
    Fixture para registrar e logar o Usuário A.

    Esta fixture garante que o Usuário A exista no banco de dados de teste.
    Em seguida, realiza o login para obter um token de acesso e o ID do usuário.

    Depende de:
        - `test_async_client`: Para fazer requisições HTTP à API.

    Returns:
        tuple[str, uuid.UUID]: Uma tupla contendo (access_token, user_id) para o Usuário A.
    """
    logger.debug("Fixture 'test_user_a_token_and_id': Configurando Usuário A...")
    register_url = f"{settings.API_V1_STR}/auth/register"
    login_url = f"{settings.API_V1_STR}/auth/login/access-token"
    users_me_url = f"{settings.API_V1_STR}/auth/users/me"

    reg_response = await test_async_client.post(register_url, json=user_a_data)
    if reg_response.status_code == status.HTTP_201_CREATED:
        logger.info(f"Usuário A ('{user_a_data['username']}') registrado com sucesso para o teste.")
    elif reg_response.status_code == status.HTTP_409_CONFLICT: 
        logger.warning(f"Registro do Usuário A ('{user_a_data['username']}') resultou em conflito (já existe). Prosseguindo para login.")
    else: 
        pytest.fail(f"Falha inesperada ao tentar registrar Usuário A: {reg_response.status_code} - {reg_response.text}")

    login_payload = {"username": user_a_data["username"], "password": user_a_data["password"]}
    login_response = await test_async_client.post(login_url, data=login_payload)
    if login_response.status_code != status.HTTP_200_OK: 
        pytest.fail(f"Falha ao fazer login com Usuário A ('{user_a_data['username']}'): {login_response.status_code} - {login_response.text}")
    token: str = login_response.json()["access_token"]
    logger.debug(f"Usuário A ('{user_a_data['username']}') logado com sucesso. Token obtido.")

    user_me_headers = {"Authorization": f"Bearer {token}"}
    user_me_response = await test_async_client.get(users_me_url, headers=user_me_headers)
    if user_me_response.status_code != status.HTTP_200_OK: 
        pytest.fail(f"Falha ao obter dados do Usuário A via /users/me: {user_me_response.status_code} - {user_me_response.text}")
    user_id_str: str = user_me_response.json()["id"]
    user_id: uuid.UUID = uuid.UUID(user_id_str)
    logger.info(f"ID do Usuário A ({user_id}) obtido com sucesso.")
    return token, user_id

@pytest.fixture(scope="function")
def auth_headers_a(test_user_a_token_and_id: tuple[str, uuid.UUID]) -> Dict[str, str]:
    """
    Fixture síncrona que retorna um dicionário de cabeçalhos de autenticação
    (Authorization Bearer token) para o Usuário A.
    """
    token, _ = test_user_a_token_and_id
    return {"Authorization": f"Bearer {token}"}

# ========================
# --- Fixtures para Usuário de Teste B ---
# ========================
user_b_data: Dict[str, str] = {
    "email": "testuserB@example.com",
    "username": "testuserB",
    "password": "passwordB",
    "full_name": "Test User B"
}

@pytest_asyncio.fixture(scope="function")
async def test_user_b_token(test_async_client: AsyncClient) -> str:
    """
    Fixture para registrar e logar o Usuário B, retornando apenas seu token de acesso.
    """
    logger.debug("Fixture 'test_user_b_token': Configurando Usuário B...")
    register_url = f"{settings.API_V1_STR}/auth/register"
    login_url = f"{settings.API_V1_STR}/auth/login/access-token"

    reg_response = await test_async_client.post(register_url, json=user_b_data)
    if reg_response.status_code == status.HTTP_201_CREATED:
        logger.info(f"Usuário B ('{user_b_data['username']}') registrado com sucesso para o teste.")
    elif reg_response.status_code == status.HTTP_409_CONFLICT: 
        logger.warning(f"Registro do Usuário B ('{user_b_data['username']}') resultou em conflito (já existe). Prosseguindo para login.")
    else: 
        pytest.fail(f"Falha inesperada ao tentar registrar Usuário B: {reg_response.status_code} - {reg_response.text}")

    login_payload = {"username": user_b_data["username"], "password": user_b_data["password"]}
    login_response = await test_async_client.post(login_url, data=login_payload)
    if login_response.status_code != status.HTTP_200_OK: 
        pytest.fail(f"Falha ao fazer login com Usuário B ('{user_b_data['username']}'): {login_response.status_code} - {login_response.text}")
    token: str = login_response.json()["access_token"]
    logger.info(f"Usuário B ('{user_b_data['username']}') logado com sucesso. Token obtido.")
    return token

@pytest.fixture(scope="function")
def auth_headers_b(test_user_b_token: str) -> Dict[str, str]:
    """
    Fixture síncrona que retorna cabeçalhos de autenticação para o Usuário B.
    """
    return {"Authorization": f"Bearer {test_user_b_token}"}

# ========================
# --- Fixture para Criação de Tarefas (Filtro/Ordenação) ---
# ========================
@pytest_asyncio.fixture(scope="function")
async def create_filter_sort_tasks(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str]
) -> List[Dict[str, Any]]:
    """
    Cria um conjunto de tarefas de teste no banco de dados para o Usuário A.

    Util para testes de listagem, filtragem e ordenação.
    """
    logger.info("Fixture 'create_filter_sort_tasks': Criando conjunto de tarefas de teste para Usuário A...")
    tasks_creation_url = f"{settings.API_V1_STR}/tasks/"
    tasks_to_create_data: List[Dict[str, Any]] = [
        {"title": "Task A Filter High Priority", "importance": 5, "project": "Projeto Filtro", "status": TaskStatus.PENDING.value, "due_date": "2026-01-01", "tags": ["importante", "relatório"]},
        {"title": "Task B Filter Low Priority", "importance": 1, "project": "Projeto Filtro", "status": TaskStatus.PENDING.value, "due_date": "2026-02-01", "tags": ["comum"]},
        {"title": "Task C Another Project InProgress", "importance": 3, "project": "Projeto Secundário", "status": TaskStatus.IN_PROGRESS.value, "tags": ["desenvolvimento"]},
        {"title": "Task D Filter Medium Due Soon", "importance": 3, "project": "Projeto Filtro", "status": TaskStatus.PENDING.value, "due_date": "2025-12-15", "tags": ["urgente", "financeiro"]},
        {"title": "Task E Filter Completed", "importance": 4, "project": "Projeto Filtro", "status": TaskStatus.COMPLETED.value, "tags": ["finalizado"]},
    ]
    created_tasks_list: List[Dict[str, Any]] = []
    for task_payload in tasks_to_create_data:
        response = await test_async_client.post(tasks_creation_url, json=task_payload, headers=auth_headers_a)
        assert response.status_code == status.HTTP_201_CREATED, \
            f"Falha ao criar tarefa de teste (Título: '{task_payload['title']}'). Resposta: {response.text}" 
        created_tasks_list.append(response.json())
        logger.debug(f"Tarefa de teste criada: {task_payload['title']} (ID: {response.json()['id']})")

    logger.info(f"Fixture 'create_filter_sort_tasks': {len(created_tasks_list)} tarefas de teste criadas com sucesso.")
    return created_tasks_list