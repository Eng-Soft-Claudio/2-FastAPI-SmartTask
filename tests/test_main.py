# tests/test_main.py

from fastapi import FastAPI
import pytest
import logging
from unittest.mock import MagicMock, patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from app.main import app as fastapi_app, lifespan
from app.core.config import settings 

pytestmark = pytest.mark.asyncio

async def test_read_root(test_async_client: AsyncClient):
    """Testa o endpoint raiz '/'."""
    response = await test_async_client.get("/")
    assert response.status_code == 200
    assert f"Bem-vindo à {settings.PROJECT_NAME}!" in response.json()["message"]

async def test_lifespan_db_connection_failure(mocker, caplog):
    """
    Testa o 'lifespan' (manual) quando a conexão inicial falha.
    Verifica se o log crítico é chamado via logger (Loguru) mockado.
    """
    caplog.set_level(logging.CRITICAL)

    # Mockar funções do lifespan
    mock_connect = mocker.patch('app.main.connect_to_mongo', return_value=None)
    mock_close = mocker.patch('app.main.close_mongo_connection', new_callable=AsyncMock)
    mock_create_user_idx = mocker.patch('app.main.create_user_indexes', new_callable=AsyncMock)
    mock_create_task_idx = mocker.patch('app.main.create_task_indexes', new_callable=AsyncMock)

    # Mockar o logger do módulo main 
    mock_logger = mocker.patch('app.main.logger')

    # Simular a execução do context manager do lifespan
    async with lifespan(fastapi_app):
        pass
        
     # Verifica chamadas
    mock_connect.assert_awaited_once()
    mock_create_user_idx.assert_not_called()
    mock_create_task_idx.assert_not_called()
    mock_logger.critical.assert_called_once()
    assert "Falha fatal ao conectar ao MongoDB" in mock_logger.critical.call_args[0][0]
    mock_close.assert_not_called()

async def test_lifespan_index_creation_failure(mocker, caplog):
    """
    Testa o 'lifespan' (manual) quando ocorre erro na criação de índices.
    Verifica se o log de erro é chamado via logger (Loguru) mockado.
    """
    test_exception = Exception("Erro simulado no índice")
    mock_db_instance = AsyncMock()

    # Mockar funções do lifespan
    mock_connect = mocker.patch('app.main.connect_to_mongo', return_value=mock_db_instance)
    mock_close = mocker.patch('app.main.close_mongo_connection', new_callable=AsyncMock)
    mock_create_user_idx = mocker.patch('app.main.create_user_indexes', side_effect=test_exception)
    mock_create_task_idx = mocker.patch('app.main.create_task_indexes', new_callable=AsyncMock)

    # Mockar o logger do módulo main
    mock_logger = mocker.patch('app.main.logger')

    # Mockar o app e state
    mock_state = MagicMock()
    mock_state.db = mock_db_instance
    mock_app = MagicMock(spec=FastAPI)
    mock_app.state = mock_state

    # Simular execução
    try:
        async with lifespan(mock_app):
             pass
    except Exception as e:
         pytest.fail(f"Lifespan levantou uma exceção inesperada: {e}")

    # Verifica chamadas
    mock_connect.assert_awaited_once()
    mock_create_user_idx.assert_awaited_once_with(mock_db_instance)
    mock_create_task_idx.assert_not_called()
    # Verifica se logger.error foi chamado
    mock_logger.error.assert_called_once()
    assert "Erro durante a criação de índices" in mock_logger.error.call_args.args[0]
    # Verifica se exc_info=True foi passado para o log de erro
    assert mock_logger.error.call_args.kwargs.get('exc_info') is True
    mock_close.assert_awaited_once()