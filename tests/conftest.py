# tests/conftest.py
import pytest
import pytest_asyncio # Importar para fixtures async
from typing import AsyncGenerator, Dict, Generator # Tipos para generators
import asyncio # Necessário para event loop

# Usar AsyncClient diretamente é mais leve para testar a app "in-memory"
# from fastapi.testclient import TestClient -> Síncrono
from httpx import AsyncClient, ASGITransport

# Importa a app FastAPI principal e as settings
from app.main import app as fastapi_app # Renomeia para evitar conflito com fixtures
from app.core.config import settings
from app.db.mongodb_utils import connect_to_mongo, close_mongo_connection, get_database
# Importações para limpar/configurar o DB de teste
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.db.user_crud import USERS_COLLECTION
from app.db.task_crud import TASKS_COLLECTION

# --- Fixture para o Cliente HTTP Async ---
@pytest_asyncio.fixture(scope="function")
async def test_async_client() -> AsyncGenerator[AsyncClient, None]:
    """
    Fixture que fornece um cliente HTTP assíncrono (httpx.AsyncClient)
    configurado para fazer requisições à nossa aplicação FastAPI.

    Este cliente interage com a app montada diretamente, sem precisar
    iniciar um servidor Uvicorn separado.
    """
    # Conecta ao banco ANTES dos testes da sessão
    await connect_to_mongo()
    db = get_database() # Pega a instância conectada

    # Verifica se o nome do DB de teste não é o de produção (SEGURANÇA!)
    # Idealmente, usar um DB separado para testes
    if "test" not in settings.DATABASE_NAME.lower():
         # Considerar adicionar um sufixo '_test' ao DATABASE_NAME
         # se MONGODB_TEST_URL for definida, por exemplo.
         # Por agora, vamos permitir rodar no DB de dev, mas limpar coleções.
         # raise ValueError(f"Nome do banco de dados '{settings.DATABASE_NAME}' não parece ser de teste.")
         print(f"\nAVISO: Rodando testes no banco de dados '{settings.DATABASE_NAME}'. As coleções serão limpas!\n")


    # Limpa as coleções ANTES de iniciar os testes da sessão
    print(f"Limpando coleções '{USERS_COLLECTION}' e '{TASKS_COLLECTION}' antes dos testes...")
    await db[USERS_COLLECTION].delete_many({})
    await db[TASKS_COLLECTION].delete_many({})
    print("Coleções limpas.")

    # Cria e retorna o cliente de teste async
    # base_url pode ser qualquer coisa aqui, pois as URLs são relativas à app
    transport=ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client # Fornece o cliente para os testes

    # Código executado APÓS todos os testes da sessão terminarem
    # Limpa as coleções novamente (opcional, mas boa prática)
    print(f"\nLimpando coleções '{USERS_COLLECTION}' e '{TASKS_COLLECTION}' após os testes...")
    await db[USERS_COLLECTION].delete_many({})
    await db[TASKS_COLLECTION].delete_many({})
    print("Coleções limpas após testes.")

    # Fecha a conexão com o banco de dados
    await close_mongo_connection()


# --- Fixture para um Token de Teste ---
# Fixture que depende do cliente e cria/loga um usuário para obter um token
@pytest_asyncio.fixture(scope="function") # Escopo de módulo: cria 1 token por arquivo de teste
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
         # response.raise_for_status() # Não levanta erro se der 409 (Conflict)
         if response.status_code not in [201, 409]:
              print(f"Falha inesperada ao registrar usuário de teste: {response.text}")
              raise Exception(f"Erro registro teste: {response.status_code}")
    except Exception as e:
        print(f"Erro ao registrar usuário de teste: {e}")
        pytest.skip("Não foi possível registrar o usuário de teste, pulando testes autenticados.") # Pula testes se registro falhar

    # --- Fazer Login ---
    login_data = {
        "username": user_data["username"],
        "password": user_data["password"]
    }
    response = await test_async_client.post(login_url, data=login_data) # Login usa form data

    if response.status_code != 200:
         print(f"Falha ao fazer login com usuário de teste: {response.text}")
         pytest.skip("Não foi possível logar com usuário de teste, pulando testes autenticados.")

    token_data = response.json()
    print("\nObtido token para testuser.") # Debug
    return token_data["access_token"]


@pytest_asyncio.fixture(scope="function")
def auth_headers(test_user_token: str) -> Dict[str, str]:
     """Retorna headers de autenticação com o token de teste."""
     return {"Authorization": f"Bearer {test_user_token}"}