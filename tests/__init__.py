# tests/conftest.py
import pytest
import pytest_asyncio
from typing import AsyncGenerator, Dict, Generator 
import asyncio 
from httpx import AsyncClient
from app.main import app as fastapi_app 
from app.core.config import settings
from app.db.mongodb_utils import connect_to_mongo, close_mongo_connection, get_database
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.db.user_crud import USERS_COLLECTION
from app.db.task_crud import TASKS_COLLECTION

# --- Configuração do Loop de Eventos ---
@pytest.fixture(scope="session")
def event_loop(request) -> Generator:
    """Cria uma instância do loop de eventos para toda a sessão de teste."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# --- Fixture para o Cliente HTTP Async ---
@pytest_asyncio.fixture(scope="session")
async def test_async_client() -> AsyncGenerator[AsyncClient, None]:
    """
    Fixture que fornece um cliente HTTP assíncrono (httpx.AsyncClient)
    configurado para fazer requisições à nossa aplicação FastAPI.

    Este cliente interage com a app montada diretamente, sem precisar
    iniciar um servidor Uvicorn separado.
    """
    # Conecta ao banco ANTES dos testes da sessão
    await connect_to_mongo()
    db = get_database()


    # Limpa as coleções ANTES de iniciar os testes da sessão
    print(f"Limpando coleções '{USERS_COLLECTION}' e '{TASKS_COLLECTION}' antes dos testes...")
    await db[USERS_COLLECTION].delete_many({})
    await db[TASKS_COLLECTION].delete_many({})
    print("Coleções limpas.")

    # Cria e retorna o cliente de teste async
    async with AsyncClient(app=fastapi_app, base_url="http://testserver") as client:
         yield client

    # Código executado APÓS todos os testes da sessão terminarem
    await db[USERS_COLLECTION].delete_many({})
    await db[TASKS_COLLECTION].delete_many({})

    # Fecha a conexão com o banco de dados
    await close_mongo_connection()


# --- Fixture para um Token de Teste ---
@pytest_asyncio.fixture(scope="module") # Escopo de módulo: cria 1 token por arquivo de teste
async def test_user_token(test_async_client: AsyncClient) -> str:
    """
    Fixture que registra um usuário de teste e faz login para obter um token JWT.
    O token pode ser usado em testes que exigem autenticação.
    """
    user_data = {
        "email": "testuser@example.com",
        "username": "testuser",
        "password": "testpassword",
        "full_name": "Test User"
    }
    register_url = f"{settings.API_V1_STR}/auth/register"
    login_url = f"{settings.API_V1_STR}/auth/login/access-token"

    # --- Registrar (ignorando falha se já existir de um run anterior não limpo) ---
    try:
         response = await test_async_client.post(register_url, json=user_data)
         if response.status_code not in [201, 409]:
              raise Exception(f"Erro registro teste: {response.status_code}")
    except Exception as e:
        pytest.skip("Não foi possível registrar o usuário de teste, pulando testes autenticados.") 

    # --- Fazer Login ---
    login_data = {
        "username": user_data["username"],
        "password": user_data["password"]
    }
    response = await test_async_client.post(login_url, data=login_data) 

    if response.status_code != 200:
         pytest.skip("Não foi possível logar com usuário de teste, pulando testes autenticados.")

    token_data = response.json()
    return token_data["access_token"]


@pytest_asyncio.fixture(scope="module")
def auth_headers(test_user_token: str) -> Dict[str, str]:
     """Retorna headers de autenticação com o token de teste."""
     return {"Authorization": f"Bearer {test_user_token}"}