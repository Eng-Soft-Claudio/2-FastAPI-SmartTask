# tests/test_main.py

# ========================
# --- Importações ---
# ========================
import logging
from loguru import logger as loguru_logger_obj
from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from httpx import AsyncClient

# --- Módulos da Aplicação ---
from app.core import logging_config 
from app.core.config import Settings, settings 
from app.main import lifespan
from app.main import _setup_cors_middleware


# ======================================
# --- Testes para o Endpoint Raiz ---
# ======================================
@pytest.mark.asyncio
async def test_read_root_endpoint_returns_welcome_message(test_async_client: AsyncClient):
    print("\nTeste: Endpoint raiz ('/').")
    print(f"  Atuando: GET para '/'")
    response = await test_async_client.get("/")

    assert response.status_code == status.HTTP_200_OK, \
        f"Esperado status 200, recebido {response.status_code}. Resposta: {response.text}"
    
    response_json = response.json()
    expected_message_part = f"Bem-vindo à {settings.PROJECT_NAME}!"
    assert "message" in response_json, "Campo 'message' ausente na resposta JSON."
    assert expected_message_part in response_json["message"], \
        f"Mensagem de boas-vindas não contém '{expected_message_part}'. Recebido: '{response_json['message']}'"
    print(f"  Sucesso: Endpoint raiz retornou a mensagem de boas-vindas esperada.")

# ===============================================
# --- Testes para a Função de Ciclo de Vida (Lifespan) ---
# ===============================================
@pytest.mark.asyncio
async def test_lifespan_handles_database_connection_failure_on_startup(
    mocker,
    caplog
):
    caplog.set_level(logging.CRITICAL, logger="app.main") 
    mock_connect_db = mocker.patch('app.main.connect_to_mongo', return_value=None)
    mock_close_db = mocker.patch('app.main.close_mongo_connection', new_callable=AsyncMock)
    mock_create_user_indexes_fn = mocker.patch('app.main.create_user_indexes', new_callable=AsyncMock)
    mock_create_task_indexes_fn = mocker.patch('app.main.create_task_indexes', new_callable=AsyncMock)
    
    test_app_instance = MagicMock(spec=FastAPI)
    test_app_instance.state = MagicMock()
    if hasattr(test_app_instance.state, "db"):
        del test_app_instance.state.db
    
    print("  Atuando: Executando o context manager 'lifespan'...")
    async with lifespan(test_app_instance):
        print("    Dentro do 'yield' do lifespan (após tentativa de conexão).")
        print("DEBUG: test_lifespan_handles_database_connection_failure_on_startup - Pós-yield")
        assert not hasattr(test_app_instance.state, "db") or test_app_instance.state.db is None, \
            "app.state.db não deveria ser definido se a conexão falhou."

    mock_connect_db.assert_awaited_once()
    mock_create_user_indexes_fn.assert_not_called()
    mock_create_task_indexes_fn.assert_not_called()
    
    assert any(
        "Falha fatal ao conectar ao MongoDB" in record.getMessage()
        for record in caplog.records
        if record.name == "app.main" and record.levelname == "CRITICAL"
    ), "Mensagem de log crítico para falha de conexão não encontrada."
    
    mock_close_db.assert_not_called()

@pytest.mark.asyncio
async def test_lifespan_handles_index_creation_failure_on_startup(
    mocker,
    caplog
):
    simulated_index_error = Exception("Erro simulado durante a criação do índice de usuário.")
    mock_db_connection_instance = AsyncMock()
    mocker.patch('app.main.connect_to_mongo', return_value=mock_db_connection_instance)
    mock_close_db = mocker.patch('app.main.close_mongo_connection', new_callable=AsyncMock)
    mock_create_user_idx_fn = mocker.patch('app.main.create_user_indexes', side_effect=simulated_index_error)
    mock_create_task_idx_fn = mocker.patch('app.main.create_task_indexes', new_callable=AsyncMock)
    
    mock_app_instance_for_lifespan = MagicMock(spec=FastAPI)
    mock_app_instance_for_lifespan.state = MagicMock()

    caplog.set_level(logging.ERROR, logger="app.main")

    try:
        async with lifespan(mock_app_instance_for_lifespan):
            print(f"    Dentro do 'yield' do lifespan. app.state.db={mock_app_instance_for_lifespan.state.db}")
            print("DEBUG: test_lifespan_handles_index_creation_failure_on_startup - Pós-yield")
            assert mock_app_instance_for_lifespan.state.db == mock_db_connection_instance, \
                "app.state.db não foi definido corretamente após conexão bem-sucedida."
    except Exception as e:
        pytest.fail(f"Lifespan levantou uma exceção inesperada para fora: {e}")

    mock_create_user_idx_fn.assert_awaited_once_with(mock_db_connection_instance)
    mock_create_task_idx_fn.assert_not_called()
    
    error_log_found = False
    for record in caplog.records:
        if record.name == "app.main" and record.levelname == "ERROR":
            if "Erro durante a criação de índices" in record.getMessage():
                assert record.exc_info is not None and record.exc_info[0] is Exception, \
                    "exc_info=True não foi devidamente logado ou é do tipo errado."
                error_log_found = True
                break
    assert error_log_found, "Mensagem de log de erro para falha na criação de índice não encontrada."
    
    mock_close_db.assert_awaited_once()

# ===============================================
# --- Testes Logging Config Externo ---
# ===============================================
from loguru import logger as loguru_logger_obj 

def test_intercept_handler_emit_unknown_level(mocker):
    handler = logging_config.InterceptHandler()
    mock_loguru_opt_log = mocker.patch.object(loguru_logger_obj, "opt", return_value=loguru_logger_obj)
    mock_loguru_log = mocker.patch.object(loguru_logger_obj, "log")
    invalid_levelname = "INVALIDLEVELNAME"
    numeric_level = 60
    record = logging.LogRecord(
        name='test.logger',
        level=numeric_level,
        pathname='/path/to/file.py',
        lineno=10,
        msg='Test message with invalid level name',
        args=[],
        exc_info=None,
        func='test_func'
    )
    record.levelname = invalid_levelname

    handler.emit(record)

    mock_loguru_opt_log.assert_called_once() 
    final_log_call_args, _ = mock_loguru_log.call_args
    assert final_log_call_args[0] == numeric_level
    assert final_log_call_args[1] == record.getMessage()

# ==================================================
# --- Testes para _setup_cors_middleware ---
# ==================================================
def test_setup_cors_middleware_with_empty_origins_logs_warning(mocker, caplog):
    mock_app = MagicMock(spec=FastAPI)
    mock_settings_empty_cors = Settings(
        MONGODB_URL="mongodb://testhost:27017/testdb",
        JWT_SECRET_KEY="testsecret",
        CORS_ALLOWED_ORIGINS=[]
    )
    caplog.set_level(logging.WARNING, logger="app.main")

    _setup_cors_middleware(mock_app, mock_settings_empty_cors)

    mock_app.add_middleware.assert_not_called()
    assert any(
        "Nenhuma origem CORS configurada" in record.getMessage()
        for record in caplog.records
        if record.name == "app.main" and record.levelname == "WARNING"
    ), "Warning de CORS para origens vazias não encontrado nos logs"
    print("  Sucesso: _setup_cors_middleware logou warning para CORS vazio.")

def test_setup_cors_middleware_with_origins_adds_middleware(mocker, caplog):
    mock_app = MagicMock(spec=FastAPI)
    mock_settings_with_cors = Settings(
        MONGODB_URL="mongodb://testhost:27017/testdb",
        JWT_SECRET_KEY="testsecret",
        CORS_ALLOWED_ORIGINS=["http://localhost:3000", "https://example.com"]
    )
    caplog.set_level(logging.INFO, logger="app.main")

    _setup_cors_middleware(mock_app, mock_settings_with_cors)

    mock_app.add_middleware.assert_called_once()
    args, kwargs = mock_app.add_middleware.call_args
    assert args[0] == CORSMiddleware
    assert kwargs.get("allow_origins") == ["http://localhost:3000", "https://example.com"]
    assert kwargs.get("allow_credentials") is True
    assert kwargs.get("allow_methods") == ["*"]
    assert kwargs.get("allow_headers") == ["*"]

    assert any(
        "Configurando CORS para origens:" in record.getMessage()
        for record in caplog.records
        if record.name == "app.main" and record.levelname == "INFO"
    ), "Log de INFO para configuração CORS não encontrado."
    print("  Sucesso: _setup_cors_middleware adicionou middleware para CORS configurado.")

# ==================================================
# --- Testes para LifeSpan ---
# ==================================================
@pytest.mark.asyncio
async def test_lifespan_successful_startup_and_shutdown(mocker, caplog):
    """
    Testa o caminho feliz completo do lifespan:
    - Conexão com DB bem-sucedida.
    - Criação de ambos os índices bem-sucedida.
    - Logs de INFO apropriados são emitidos.
    - Conexão com DB é fechada no shutdown.
    """
    caplog.set_level(logging.INFO, logger="app.main") 
    
    mock_db_conn = AsyncMock(name="MockDBConnection")
    mock_connect_db = mocker.patch('app.main.connect_to_mongo', return_value=mock_db_conn)
    mock_close_db = mocker.patch('app.main.close_mongo_connection', new_callable=AsyncMock)
    mock_create_user_idx = mocker.patch('app.main.create_user_indexes', new_callable=AsyncMock)
    mock_create_task_idx = mocker.patch('app.main.create_task_indexes', new_callable=AsyncMock)
    
    
    test_app_instance = MagicMock(spec=FastAPI)
    test_app_instance.state = MagicMock() 
    if hasattr(test_app_instance.state, "db"):
        del test_app_instance.state.db


    # --- Act ---
    async with lifespan(test_app_instance):
        print("DEBUG: test_lifespan_successful_startup - Pós-yield (dentro do with)")
        assert test_app_instance.state.db == mock_db_conn, "app.state.db não foi definido corretamente."

    # --- Assert ---
    mock_connect_db.assert_awaited_once()
    mock_create_user_idx.assert_awaited_once_with(mock_db_conn)
    mock_create_task_idx.assert_awaited_once_with(mock_db_conn) 
    
    logs = [record.getMessage() for record in caplog.records if record.name == "app.main"]

    assert "Iniciando ciclo de vida da aplicação..." in logs
    assert "Conectado ao MongoDB." in logs
    assert "Tentando criar/verificar índices..." in logs
    assert "Criação/verificação de índices concluída." in logs 
    assert "Aplicação iniciada e pronta." in logs 
    assert "Iniciando processo de encerramento..." in logs
    assert "Conexão com MongoDB fechada." in logs
    assert "Aplicação encerrada." in logs
    
    mock_close_db.assert_awaited_once()