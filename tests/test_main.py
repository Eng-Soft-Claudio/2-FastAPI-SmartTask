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
from unittest.mock import AsyncMock, MagicMock, patch 

import pytest
from fastapi import FastAPI, status 
from httpx import AsyncClient 

# --- Módulos da Aplicação ---
from app.core.config import settings
from app.main import app as fastapi_app 
from app.main import lifespan

# ====================================
# --- Marcador Global de Teste ---
# ====================================
pytestmark = pytest.mark.asyncio

# ======================================
# --- Testes para o Endpoint Raiz ---
# ======================================

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
# Estes testes verificam o comportamento da função `lifespan` em
# `app.main.py` quando chamada manualmente (simulando o ciclo de vida da aplicação),
# especialmente em cenários de falha.

async def test_lifespan_handles_database_connection_failure_on_startup(
    mocker, # Fixture do Pytest-mock para patching
    caplog  # Fixture do Pytest para capturar logs
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
    print("\nTeste: lifespan com falha na conexão inicial com o DB.")
    caplog.set_level(logging.CRITICAL) 

    # --- Arrange: Mockar as dependências da função lifespan ---
    print("  Mockando funções do ciclo de vida e logger...")
    mock_connect_db = mocker.patch('app.main.connect_to_mongo', return_value=None) 
    mock_close_db = mocker.patch('app.main.close_mongo_connection', new_callable=AsyncMock)
    mock_create_user_indexes_fn = mocker.patch('app.main.create_user_indexes', new_callable=AsyncMock)
    mock_create_task_indexes_fn = mocker.patch('app.main.create_task_indexes', new_callable=AsyncMock)
    mock_main_logger = mocker.patch('app.main.logger') 
    
    # `fastapi_app` é a instância real da aplicação, mas seu estado pode não ser modificado
    # aqui diretamente da maneira que `lifespan` espera se não for o contexto real da FastAPI.
    # A função lifespan modifica `app.state.db`.
    test_app_instance = MagicMock(spec=FastAPI) 
    test_app_instance.state = MagicMock()       
    # Garantir que `state.db` comece como não definido ou None.
    if hasattr(test_app_instance.state, "db"):
        del test_app_instance.state.db


    # --- Act: Simular a execução do context manager do lifespan ---
    print("  Atuando: Executando o context manager 'lifespan'...")
    async with lifespan(test_app_instance): 
        # O código dentro do `yield` do lifespan seria executado aqui.
        # Neste cenário de falha de conexão, o `yield` ocorre, mas app.state.db é None.
        print("    Dentro do 'yield' do lifespan (após tentativa de conexão).")
        assert not hasattr(test_app_instance.state, "db") or test_app_instance.state.db is None, \
            "app.state.db não deveria ser definido se a conexão falhou."
        
    # --- Assert: Verificar as chamadas aos mocks ---
    print("  Verificando chamadas aos mocks e logs...")
    mock_connect_db.assert_awaited_once()
    mock_create_user_indexes_fn.assert_not_called(), "Criação de índice de usuário não deveria ser chamada."
    mock_create_task_indexes_fn.assert_not_called(), "Criação de índice de tarefa não deveria ser chamada."
    
    # Verificar se o log crítico foi emitido.
    mock_main_logger.critical.assert_called_once()
    critical_log_message = mock_main_logger.critical.call_args[0][0]
    assert "Falha fatal ao conectar ao MongoDB" in critical_log_message, \
        f"Mensagem de log crítico incorreta: '{critical_log_message}'"
    
    mock_close_db.assert_not_called(), "close_mongo_connection não deveria ser chamada se a conexão inicial falhou."
    print("  Sucesso: Lifespan lidou corretamente com falha na conexão do DB.")


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
    print("\nTeste: lifespan com falha na criação de índices.")
    # --- Arrange: Definir o comportamento dos mocks ---
    simulated_index_error = Exception("Erro simulado durante a criação do índice de usuário.")
    mock_db_connection_instance = AsyncMock() 

    print("  Mockando funções do ciclo de vida e logger...")
    mocker.patch('app.main.connect_to_mongo', return_value=mock_db_connection_instance)
    mock_close_db = mocker.patch('app.main.close_mongo_connection', new_callable=AsyncMock)
    # `create_user_indexes` simula uma falha levantando uma exceção.
    mock_create_user_idx_fn = mocker.patch('app.main.create_user_indexes', side_effect=simulated_index_error)
    mock_create_task_idx_fn = mocker.patch('app.main.create_task_indexes', new_callable=AsyncMock)
    mock_main_logger = mocker.patch('app.main.logger')

    # Mockar um objeto `app` com um `state` para a função `lifespan` operar.
    # Isso é necessário porque `lifespan` espera `app.state.db = db_connection`.
    mock_app_instance_for_lifespan = MagicMock(spec=FastAPI)
    # Importante: o atributo `state` deve existir no `mock_app_instance_for_lifespan`
    # ANTES de chamar `lifespan`. A função `lifespan` tentará atribuir `state.db`.
    mock_app_instance_for_lifespan.state = MagicMock()
    # Inicialmente, app.state.db não existirá ou será None.

    # --- Act: Simular a execução do context manager do lifespan ---
    print("  Atuando: Executando o context manager 'lifespan'...")
    # A exceção de criação de índice é capturada DENTRO do lifespan e logada,
    # então o context manager não deve levantar a exceção para fora.
    try:
        async with lifespan(mock_app_instance_for_lifespan):
            # O código dentro do `yield` do lifespan é executado aqui.
            # Esperamos que app.state.db seja definido.
            print(f"    Dentro do 'yield' do lifespan. app.state.db={mock_app_instance_for_lifespan.state.db}")
            assert mock_app_instance_for_lifespan.state.db == mock_db_connection_instance, \
                "app.state.db não foi definido corretamente após conexão bem-sucedida."
    except Exception as e:
        # Se a exceção de índice não for tratada internamente no lifespan, falhará aqui.
        pytest.fail(f"Lifespan levantou uma exceção inesperada para fora: {e}")

    # --- Assert: Verificar as chamadas aos mocks ---
    print("  Verificando chamadas aos mocks e logs...")
    mock_create_user_idx_fn.assert_awaited_once_with(mock_db_connection_instance)
    # Como create_user_indexes falha, create_task_indexes não deve ser chamado se estiver após.
    # Verifique a ordem no seu main.py:
    #   await create_user_indexes(db_instance)
    #   await create_task_indexes(db_instance)  <-- Não será chamado se o anterior falhar e a exceção for geral
    # A lógica no seu main.py captura `Exception as e`, então se user_indexes falha,
    # o task_indexes DENTRO DO try não é chamado.
    mock_create_task_idx_fn.assert_not_called(), \
        "create_task_indexes não deveria ser chamado se create_user_indexes falhou."
    
    # Verificar se logger.error foi chamado.
    mock_main_logger.error.assert_called_once()
    error_log_call = mock_main_logger.error.call_args
    error_log_message = error_log_call.args[0] 
    assert "Erro durante a criação de índices" in error_log_message, \
        f"Mensagem de log de erro incorreta: '{error_log_message}'"
    # Verificar se `exc_info=True` foi passado para `logger.error`.
    assert error_log_call.kwargs.get('exc_info') is True, "exc_info=True não foi passado para logger.error."
    
    # `close_mongo_connection` deve ser sempre chamado na saída do lifespan se a conexão foi feita.
    mock_close_db.assert_awaited_once()
    print("  Sucesso: Lifespan lidou corretamente com falha na criação de índices.")