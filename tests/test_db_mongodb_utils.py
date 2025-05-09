# tests/test_db_mongodb_utils.py

# ========================
# --- Importações ---
# ========================
import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch
from app.db import mongodb_utils # Importa o módulo para mockar e chamar

# ========================
# --- Testes para get_database ---
# ========================
def test_get_database_not_initialized(mocker):
    """
    Testa se get_database levanta RuntimeError quando db_instance é None.
    """
    # --- Arrange ---
    mocker.patch("app.db.mongodb_utils.db_instance", None)
    mock_logger_error = mocker.patch("app.db.mongodb_utils.logger.error")

    # --- Act & Assert ---
    with pytest.raises(RuntimeError) as excinfo:
        mongodb_utils.get_database()

    assert "A conexão com o banco de dados não foi inicializada" in str(excinfo.value)
    mock_logger_error.assert_called_once_with("Tentativa de obter instância do DB antes da inicialização!")

# ========================
# --- Testes para close_mongo_connection ---
# ========================
@pytest.mark.asyncio
async def test_close_mongo_connection_no_client(mocker):
    """
    Testa close_mongo_connection quando db_client global é None.
    """
    # --- Arrange ---
    mocker.patch("app.db.mongodb_utils.db_client", None)
    mock_logger_warning = mocker.patch("app.db.mongodb_utils.logger.warning")
    mock_logger_info = mocker.patch("app.db.mongodb_utils.logger.info")

    # --- Act ---
    await mongodb_utils.close_mongo_connection()

    # --- Assert ---
    mock_logger_info.assert_any_call("Tentando fechar conexão com MongoDB...")
    mock_logger_warning.assert_called_once_with("Tentativa de fechar conexão com MongoDB, mas cliente não estava inicializado.")
    # Verifica se o log de "conexão fechada" NÃO foi chamado
    log_info_calls = [c.args[0] for c in mock_logger_info.call_args_list if c.args]
    assert "Conexão com MongoDB fechada." not in log_info_calls

@pytest.mark.asyncio
async def test_close_mongo_connection_with_client(mocker):
    """
    Testa close_mongo_connection quando db_client existe.
    """
    # --- Arrange ---
    mock_client_instance = MagicMock()
    mocker.patch("app.db.mongodb_utils.db_client", mock_client_instance)
    mock_logger_info = mocker.patch("app.db.mongodb_utils.logger.info")
    mock_logger_warning = mocker.patch("app.db.mongodb_utils.logger.warning")

    # --- Act ---
    await mongodb_utils.close_mongo_connection()

    # --- Assert ---
    mock_client_instance.close.assert_called_once()
    assert call("Tentando fechar conexão com MongoDB...") in mock_logger_info.call_args_list
    assert call("Conexão com MongoDB fechada.") in mock_logger_info.call_args_list
    mock_logger_warning.assert_not_called()

# ========================
# --- Testes para connect_to_mongo ---
# ========================
@pytest.mark.asyncio
async def test_connect_to_mongo_failure_client_init(mocker):
    """
    Testa falha em connect_to_mongo durante a inicialização do AsyncIOMotorClient.
    """
    # --- Arrange ---
    simulated_error = Exception("Erro ao instanciar Motor Client")
    mocker.patch("motor.motor_asyncio.AsyncIOMotorClient", side_effect=simulated_error)
    mock_logger_error = mocker.patch("app.db.mongodb_utils.logger.error")
    mocker.patch("app.db.mongodb_utils.settings.MONGODB_URL", "mongodb://dummy_url")
    # Garante que os globais estejam resetados para o teste
    mocker.patch("app.db.mongodb_utils.db_client", None)
    mocker.patch("app.db.mongodb_utils.db_instance", None)

    # --- Act ---
    result = await mongodb_utils.connect_to_mongo()

    # --- Assert ---
    assert result is None
    mock_logger_error.assert_called_once()
    log_args, log_kwargs = mock_logger_error.call_args
    assert "Não foi possível conectar ao MongoDB" in log_args[0]
    assert str(simulated_error) in log_args[0]
    assert log_kwargs.get("exc_info") is True
    assert mongodb_utils.db_client is None # Verifica se o global não foi setado
    assert mongodb_utils.db_instance is None # Verifica se o global não foi setado

@pytest.mark.asyncio
async def test_connect_to_mongo_failure_ping(mocker):
    """
    Testa falha em connect_to_mongo durante o comando ping.
    """
    # --- Arrange ---
    simulated_error = Exception("Erro no comando ping")
    mock_motor_client = AsyncMock()
    mock_motor_client.admin.command.side_effect = simulated_error
    mocker.patch("motor.motor_asyncio.AsyncIOMotorClient", return_value=mock_motor_client)
    mock_logger_error = mocker.patch("app.db.mongodb_utils.logger.error")
    mocker.patch("app.db.mongodb_utils.settings.MONGODB_URL", "mongodb://dummy_ping_url")
    # Garante que os globais estejam resetados
    mocker.patch("app.db.mongodb_utils.db_client", None)
    mocker.patch("app.db.mongodb_utils.db_instance", None)

    # --- Act ---
    result = await mongodb_utils.connect_to_mongo()

    # --- Assert ---
    assert result is None
    mock_motor_client.admin.command.assert_awaited_once_with('ping')
    mock_logger_error.assert_called_once()
    log_args, log_kwargs = mock_logger_error.call_args
    assert "Não foi possível conectar ao MongoDB" in log_args[0]
    assert str(simulated_error) in log_args[0]
    assert log_kwargs.get("exc_info") is True
    assert mongodb_utils.db_client is None # Verifica se o global não foi setado com o mock que falhou no ping
    assert mongodb_utils.db_instance is None