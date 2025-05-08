# tests/test_main.py
"""
Este módulo contém testes de integração para a aplicação FastAPI principal
definida em `app.main.py`.

Os testes cobrem:
- O endpoint raiz (`/`) para verificar se a API está online.
- O comportamento da função de ciclo de vida (`lifespan`) em cenários
  específicos, como falhas na conexão com o banco de dados ou na
  criação de índices.
"""

# ========================
# --- Importações ---
# ========================
import logging
from loguru import logger as loguru_logger
from unittest.mock import AsyncMock, MagicMock, patch 

import pytest
from fastapi import FastAPI, status 
from httpx import AsyncClient 

# --- Módulos da Aplicação ---
from app.core import logging_config
from app.core.config import settings
from app.main import app as fastapi_app 
from app.main import lifespan

# ======================================
# --- Testes para o Endpoint Raiz ---
# ======================================
@pytest.mark.asyncio
async def test_read_root_endpoint_returns_welcome_message(test_async_client: AsyncClient):
    """
    Testa se o endpoint raiz ('/') da API retorna uma mensagem de boas-vindas
    correta com o nome do projeto e um status code HTTP 200 OK.

    Depende de:
        - `test_async_client`: Fixture para fazer requisições HTTP à API.
    """
    print("\nTeste: Endpoint raiz ('/').")
    # Act: Fazer uma requisição GET para o endpoint raiz.
    print(f"  Atuando: GET para '/'")
    response = await test_async_client.get("/")

    # Assert: Verificar o status code e o conteúdo da resposta.
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
    """
    Testa o comportamento da função `lifespan` quando a tentativa inicial
    de conexão com o MongoDB (`connect_to_mongo`) falha (retorna None).

    Verifica se:
    - `connect_to_mongo` é chamado.
    - Funções de criação de índice NÃO são chamadas.
    - Um log CRÍTICO é emitido indicando a falha na conexão.
    - `close_mongo_connection` NÃO é chamado (já que a conexão não foi estabelecida).
    - `app.state.db` não é definido.
    """

    # ===============================================================
        # --- Arrange ---
    # ===============================================================
    caplog.set_level(logging.CRITICAL) 
    mock_connect_db = mocker.patch('app.main.connect_to_mongo', return_value=None) 
    mock_close_db = mocker.patch('app.main.close_mongo_connection', new_callable=AsyncMock)
    mock_create_user_indexes_fn = mocker.patch('app.main.create_user_indexes', new_callable=AsyncMock)
    mock_create_task_indexes_fn = mocker.patch('app.main.create_task_indexes', new_callable=AsyncMock)
    mock_main_logger = mocker.patch('app.main.logger') 
    test_app_instance = MagicMock(spec=FastAPI) 
    test_app_instance.state = MagicMock()       
    if hasattr(test_app_instance.state, "db"):
        del test_app_instance.state.db
    # ===============================================================
    # --- Act ---
    # ===============================================================
    print("  Atuando: Executando o context manager 'lifespan'...")
    async with lifespan(test_app_instance): 
        print("    Dentro do 'yield' do lifespan (após tentativa de conexão).")
        assert not hasattr(test_app_instance.state, "db") or test_app_instance.state.db is None, \
            "app.state.db não deveria ser definido se a conexão falhou."
        
    # ===============================================================
        # --- Assert ---
    # ===============================================================
    mock_connect_db.assert_awaited_once()
    mock_create_user_indexes_fn.assert_not_called(), "Criação de índice de usuário não deveria ser chamada."
    mock_create_task_indexes_fn.assert_not_called(), "Criação de índice de tarefa não deveria ser chamada."
    mock_main_logger.critical.assert_called_once()
    critical_log_message = mock_main_logger.critical.call_args[0][0]
    assert "Falha fatal ao conectar ao MongoDB" in critical_log_message, \
        f"Mensagem de log crítico incorreta: '{critical_log_message}'"
    
    mock_close_db.assert_not_called(), "close_mongo_connection não deveria ser chamada se a conexão inicial falhou."

@pytest.mark.asyncio
async def test_lifespan_handles_index_creation_failure_on_startup(
    mocker,
    caplog 
):
    """
    Testa o comportamento da função `lifespan` quando a conexão com o MongoDB
    é bem-sucedida, mas ocorre um erro durante a criação dos índices
    (ex: `create_user_indexes` levanta uma exceção).

    Verifica se:
    - `connect_to_mongo` é chamado e `app.state.db` é definido.
    - A função de criação de índice que falha (`create_user_indexes`) é chamada.
    - A função de criação do *outro* índice (`create_task_indexes`) NÃO é chamada após a falha.
    - Um log de ERRO é emitido indicando a falha na criação do índice, com `exc_info=True`.
    - `close_mongo_connection` é chamado na saída do lifespan (limpeza).
    """

    # ===============================================================
        # --- Arrange ---
    # ===============================================================
    simulated_index_error = Exception("Erro simulado durante a criação do índice de usuário.")
    mock_db_connection_instance = AsyncMock() 
    mocker.patch('app.main.connect_to_mongo', return_value=mock_db_connection_instance)
    mock_close_db = mocker.patch('app.main.close_mongo_connection', new_callable=AsyncMock)
    mock_create_user_idx_fn = mocker.patch('app.main.create_user_indexes', side_effect=simulated_index_error)
    mock_create_task_idx_fn = mocker.patch('app.main.create_task_indexes', new_callable=AsyncMock)
    mock_main_logger = mocker.patch('app.main.logger')
    mock_app_instance_for_lifespan = MagicMock(spec=FastAPI)
    mock_app_instance_for_lifespan.state = MagicMock()

    # ===============================================================
    # --- Act ---
    # ===============================================================
    try:
        async with lifespan(mock_app_instance_for_lifespan):
            print(f"    Dentro do 'yield' do lifespan. app.state.db={mock_app_instance_for_lifespan.state.db}")
            assert mock_app_instance_for_lifespan.state.db == mock_db_connection_instance, \
                "app.state.db não foi definido corretamente após conexão bem-sucedida."
    except Exception as e:
        pytest.fail(f"Lifespan levantou uma exceção inesperada para fora: {e}")

    # ===============================================================
    # --- Assert ---
    # ===============================================================
    mock_create_user_idx_fn.assert_awaited_once_with(mock_db_connection_instance)
    mock_create_task_idx_fn.assert_not_called(), \
        "create_task_indexes não deveria ser chamado se create_user_indexes falhou."
    mock_main_logger.error.assert_called_once()
    error_log_call = mock_main_logger.error.call_args
    error_log_message = error_log_call.args[0] 
    assert "Erro durante a criação de índices" in error_log_message, \
        f"Mensagem de log de erro incorreta: '{error_log_message}'"
    assert error_log_call.kwargs.get('exc_info') is True, "exc_info=True não foi passado para logger.error."
    mock_close_db.assert_awaited_once()

# ===============================================
# --- Testes Logging Config Externo ---
# ===============================================
def test_intercept_handler_emit_unknown_level(mocker): 
    """
    Testa se InterceptHandler usa levelno quando levelname é desconhecido.
    """
    # ========================
    # --- Arrange ---
    # ========================
    handler = logging_config.InterceptHandler()
    mock_loguru_opt_log = mocker.patch.object(loguru_logger, "opt", return_value=loguru_logger) 
    mock_loguru_log = mocker.patch.object(loguru_logger, "log") 
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
    mock_frame = MagicMock()
    mock_frame.f_back = None 
    mock_currentframe = mocker.patch("logging.currentframe", return_value=mock_frame)

    # ========================
    # --- Act ---
    # ========================
    handler.emit(record)

    # ========================
    # --- Assert ---
    # ========================
    mock_loguru_opt_log.assert_called_once()
    call_args, _ = mock_loguru_log.call_args
    assert call_args[0] == numeric_level 
    assert call_args[1] == record.getMessage()