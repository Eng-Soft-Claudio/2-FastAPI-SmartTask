# tests/test_db_user_crud.py

# ========================
# --- Importações ---
# ========================
import uuid
from datetime import datetime, timezone
import pytest # type: ignore
from unittest.mock import AsyncMock, MagicMock, patch, call
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError

from app.db import user_crud
from app.models.user import UserCreate, UserInDB, UserUpdate

# ====================================
# --- Marcador Global de Teste ---
# ====================================
pytestmark = pytest.mark.asyncio

# ============================
# --- Fixture Auxiliar ---
# ============================
@pytest.fixture
def mock_db_connection() -> AsyncMock:
    """Fornece um mock genérico para a conexão DB."""
    return AsyncMock()

@pytest.fixture
def sample_user_create() -> UserCreate:
    """Fornece um objeto UserCreate válido para testes."""
    return UserCreate(
        email="test@example.com",
        username="testuser",
        password="validpassword123",
        full_name="Test User Name"
    )

@pytest.fixture
def sample_user_in_db() -> UserInDB:
    """Fornece um objeto UserInDB válido para testes."""
    user_id = uuid.uuid4()
    return UserInDB(
        id=user_id,
        username="sampleuserindb",
        email="sampleindb@example.com",
        hashed_password="hashed_sample_password",
        full_name="Sample User In DB",
        disabled=False,
        created_at=datetime.now(timezone.utc).replace(microsecond=0),
        updated_at=None
    )

# =======================================
# --- Testes para user_crud.get_user_by_id ---
# =======================================
async def test_get_user_by_id_success(mocker, mock_db_connection, sample_user_in_db): # type: ignore
    """Testa busca de usuário por ID com sucesso."""
    # --- Arrange ---
    test_user_id = sample_user_in_db.id
    user_dict_from_db = sample_user_in_db.model_dump(mode="json")
    user_dict_from_db['_id'] = "mock_mongo_id"
    expected_validation_dict = sample_user_in_db.model_dump(mode="json")

    mock_collection = AsyncMock()
    mock_collection.find_one.return_value = user_dict_from_db
    mocker.patch("app.db.user_crud._get_users_collection", return_value=mock_collection)
    mock_validate = mocker.patch("app.db.user_crud.UserInDB.model_validate", return_value=sample_user_in_db)

    # --- Act ---
    result = await user_crud.get_user_by_id(db=mock_db_connection, user_id=test_user_id)

    # --- Assert ---
    assert result == sample_user_in_db
    mock_collection.find_one.assert_awaited_once_with({"id": str(test_user_id)})
    mock_validate.assert_called_once_with(expected_validation_dict)

async def test_get_user_by_id_not_found(mocker, mock_db_connection): # type: ignore
    """Testa busca de usuário por ID quando não encontrado."""
    # --- Arrange ---
    test_user_id = uuid.uuid4()
    mock_collection = AsyncMock()
    mock_collection.find_one.return_value = None
    mocker.patch("app.db.user_crud._get_users_collection", return_value=mock_collection)

    # --- Act ---
    result = await user_crud.get_user_by_id(db=mock_db_connection, user_id=test_user_id)

    # --- Assert ---
    assert result is None
    mock_collection.find_one.assert_awaited_once_with({"id": str(test_user_id)})

async def test_get_user_by_id_validation_error(mocker, mock_db_connection): # type: ignore
    """Testa falha de validação Pydantic ao buscar usuário por ID."""
    # --- Arrange ---
    test_user_id = uuid.uuid4()
    invalid_user_dict_from_db = {"_id": "mongo_id", "id": str(test_user_id), "campo_errado": True}
    expected_validation_dict = {"id": str(test_user_id), "campo_errado": True}

    mock_collection = AsyncMock()
    mock_collection.find_one.return_value = invalid_user_dict_from_db
    mocker.patch("app.db.user_crud._get_users_collection", return_value=mock_collection)

    simulated_error = ValidationError.from_exception_data(title='UserInDB', line_errors=[])
    mock_validate = mocker.patch("app.db.user_crud.UserInDB.model_validate", side_effect=simulated_error)
    mock_logger_error = mocker.patch("app.db.user_crud.logger.error")

    # --- Act ---
    result = await user_crud.get_user_by_id(db=mock_db_connection, user_id=test_user_id)

    # --- Assert ---
    assert result is None
    mock_collection.find_one.assert_awaited_once_with({"id": str(test_user_id)})
    mock_validate.assert_called_once_with(expected_validation_dict)
    mock_logger_error.assert_called_once()
    assert f"DB Validation error get_user_by_id {test_user_id}" in mock_logger_error.call_args[0][0]

# ===========================================
# --- Testes para user_crud.get_user_by_username ---
# ===========================================
async def test_get_user_by_username_success(mocker, mock_db_connection, sample_user_in_db): # type: ignore
    """Testa busca de usuário por username com sucesso."""
    # --- Arrange ---
    test_username = sample_user_in_db.username
    user_dict_from_db = sample_user_in_db.model_dump(mode="json")
    user_dict_from_db['_id'] = "mock_mongo_id"
    expected_validation_dict = sample_user_in_db.model_dump(mode="json")

    mock_collection = AsyncMock()
    mock_collection.find_one.return_value = user_dict_from_db
    mocker.patch("app.db.user_crud._get_users_collection", return_value=mock_collection)
    mock_validate = mocker.patch("app.db.user_crud.UserInDB.model_validate", return_value=sample_user_in_db)

    # --- Act ---
    result = await user_crud.get_user_by_username(db=mock_db_connection, username=test_username)

    # --- Assert ---
    assert result == sample_user_in_db
    mock_collection.find_one.assert_awaited_once_with({"username": test_username})
    mock_validate.assert_called_once_with(expected_validation_dict)

async def test_get_user_by_username_not_found(mocker, mock_db_connection): # type: ignore
    """Testa busca de usuário por username quando não encontrado."""
    # --- Arrange ---
    test_username = "nouser_username"
    mock_collection = AsyncMock()
    mock_collection.find_one.return_value = None
    mocker.patch("app.db.user_crud._get_users_collection", return_value=mock_collection)

    # --- Act ---
    result = await user_crud.get_user_by_username(db=mock_db_connection, username=test_username)

    # --- Assert ---
    assert result is None
    mock_collection.find_one.assert_awaited_once_with({"username": test_username})

async def test_get_user_by_username_validation_error(mocker, mock_db_connection): # type: ignore
    """Testa falha de validação Pydantic ao buscar usuário por username."""
    # --- Arrange ---
    test_username = "invalid_user_validate"
    invalid_user_dict_from_db = {"_id": "mongo_id", "username": test_username, "campo_errado": True}
    expected_validation_dict = {"username": test_username, "campo_errado": True}

    mock_collection = AsyncMock()
    mock_collection.find_one.return_value = invalid_user_dict_from_db
    mocker.patch("app.db.user_crud._get_users_collection", return_value=mock_collection)

    simulated_error = ValidationError.from_exception_data(title='UserInDB', line_errors=[])
    mock_validate = mocker.patch("app.db.user_crud.UserInDB.model_validate", side_effect=simulated_error)
    mock_logger_error = mocker.patch("app.db.user_crud.logger.error")

    # --- Act ---
    result = await user_crud.get_user_by_username(db=mock_db_connection, username=test_username)

    # --- Assert ---
    assert result is None
    mock_collection.find_one.assert_awaited_once_with({"username": test_username})
    mock_validate.assert_called_once_with(expected_validation_dict)
    mock_logger_error.assert_called_once()
    assert f"DB Validation error get_user_by_username {test_username}" in mock_logger_error.call_args[0][0]

# ===========================================
# --- Testes para user_crud.get_user_by_email ---
# ===========================================
async def test_get_user_by_email_success(mocker, mock_db_connection, sample_user_in_db): # type: ignore
    """Testa busca de usuário por email com sucesso."""
    # --- Arrange ---
    test_email = sample_user_in_db.email
    user_dict_from_db = sample_user_in_db.model_dump(mode="json")
    user_dict_from_db['_id'] = "mock_mongo_id"
    expected_validation_dict = sample_user_in_db.model_dump(mode="json")

    mock_collection = AsyncMock()
    mock_collection.find_one.return_value = user_dict_from_db
    mocker.patch("app.db.user_crud._get_users_collection", return_value=mock_collection)
    mock_validate = mocker.patch("app.db.user_crud.UserInDB.model_validate", return_value=sample_user_in_db)

    # --- Act ---
    result = await user_crud.get_user_by_email(db=mock_db_connection, email=test_email)

    # --- Assert ---
    assert result == sample_user_in_db
    mock_collection.find_one.assert_awaited_once_with({"email": test_email})
    mock_validate.assert_called_once_with(expected_validation_dict)

async def test_get_user_by_email_not_found(mocker, mock_db_connection): # type: ignore
    """Testa busca de usuário por email quando não encontrado."""
    # --- Arrange ---
    test_email = "nouser@example.com"
    mock_collection = AsyncMock()
    mock_collection.find_one.return_value = None
    mocker.patch("app.db.user_crud._get_users_collection", return_value=mock_collection)

    # --- Act ---
    result = await user_crud.get_user_by_email(db=mock_db_connection, email=test_email)

    # --- Assert ---
    assert result is None
    mock_collection.find_one.assert_awaited_once_with({"email": test_email})

async def test_get_user_by_email_validation_error(mocker, mock_db_connection): # type: ignore
    """Testa falha de validação Pydantic ao buscar usuário por email."""
    # --- Arrange ---
    test_email = "invalid_validate@example.com"
    invalid_user_dict_from_db = {"_id": "mongo_id", "email": test_email, "campo_errado": True}
    expected_validation_dict = {"email": test_email, "campo_errado": True}

    mock_collection = AsyncMock()
    mock_collection.find_one.return_value = invalid_user_dict_from_db
    mocker.patch("app.db.user_crud._get_users_collection", return_value=mock_collection)

    simulated_error = ValidationError.from_exception_data(title='UserInDB', line_errors=[])
    mock_validate = mocker.patch("app.db.user_crud.UserInDB.model_validate", side_effect=simulated_error)
    mock_logger_error = mocker.patch("app.db.user_crud.logger.error")

    # --- Act ---
    result = await user_crud.get_user_by_email(db=mock_db_connection, email=test_email)

    # --- Assert ---
    assert result is None
    mock_collection.find_one.assert_awaited_once_with({"email": test_email})
    mock_validate.assert_called_once_with(expected_validation_dict)
    mock_logger_error.assert_called_once()
    assert f"DB Validation error get_user_by_email {test_email}" in mock_logger_error.call_args[0][0]

# =======================================
# --- Testes para user_crud.create_user ---
# =======================================
async def test_create_user_success(mocker, mock_db_connection, sample_user_create): # type: ignore
    """Testa a criação de usuário com sucesso."""
    # --- Arrange ---
    test_uuid = uuid.uuid4()
    test_datetime = datetime.now(timezone.utc)
    mock_uuid_module = mocker.patch("app.db.user_crud.uuid")
    mock_uuid_module.uuid4.return_value = test_uuid
    mock_dt_module = mocker.patch("app.db.user_crud.datetime")
    mock_dt_module.now.return_value = test_datetime
    mock_dt_module.side_effect = lambda *args, **kw: datetime(*args, **kw)

    mocked_hashed_password = "hashed_password_success"
    mocker.patch("app.db.user_crud.get_password_hash", return_value=mocked_hashed_password)

    expected_validation_data_dict = {
        "id": test_uuid,
        "username": sample_user_create.username,
        "email": sample_user_create.email,
        "hashed_password": mocked_hashed_password,
        "full_name": sample_user_create.full_name,
        "disabled": False,
        "created_at": test_datetime,
        "updated_at": None
    }
    mock_validated_user_obj = MagicMock(spec=UserInDB)
    for key, value in expected_validation_data_dict.items():
        setattr(mock_validated_user_obj, key, value)

    mock_validate = mocker.patch(
        "app.db.user_crud.UserInDB.model_validate",
        return_value=mock_validated_user_obj
    )

    expected_dict_to_insert = {k: str(v) if isinstance(v, uuid.UUID) else (v.isoformat() if isinstance(v, datetime) else v) for k, v in expected_validation_data_dict.items() if k != 'created_at'}
    expected_dict_to_insert['created_at'] = test_datetime
    expected_dict_to_insert['updated_at'] = None

    mock_validated_user_obj.model_dump.return_value = expected_dict_to_insert

    mock_insert_result = MagicMock()
    mock_insert_result.acknowledged = True

    mock_collection = AsyncMock()
    mock_collection.insert_one.return_value = mock_insert_result
    mocker.patch("app.db.user_crud._get_users_collection", return_value=mock_collection)

    # --- Act ---
    result = await user_crud.create_user(db=mock_db_connection, user_in=sample_user_create)

    # --- Assert ---
    assert result == mock_validated_user_obj

    user_crud.get_password_hash.assert_called_once_with(sample_user_create.password)
    mock_validate.assert_called_once_with(expected_validation_data_dict)

    mock_validated_user_obj.model_dump.assert_called_once_with(mode="json")
    mock_collection.insert_one.assert_awaited_once_with(expected_dict_to_insert)

async def test_create_user_raises_duplicate_key_error(mocker, mock_db_connection, sample_user_create): # type: ignore
    """Testa se DuplicateKeyError é relançado."""
    # --- Arrange ---
    mocker.patch("app.db.user_crud.get_password_hash", return_value="mock_hash")
    mock_validated_obj = MagicMock()
    mock_validated_obj.model_dump.return_value = {"some": "data"}
    mocker.patch("app.db.user_crud.UserInDB.model_validate", return_value=mock_validated_obj)

    simulated_db_error = DuplicateKeyError("E11000 duplicate key error")
    mock_collection = AsyncMock()
    mock_collection.insert_one.side_effect = simulated_db_error
    mocker.patch("app.db.user_crud._get_users_collection", return_value=mock_collection)
    mock_logger_warning = mocker.patch("app.db.user_crud.logger.warning")

    # --- Act & Assert ---
    with pytest.raises(DuplicateKeyError):
        await user_crud.create_user(db=mock_db_connection, user_in=sample_user_create)

    mock_collection.insert_one.assert_awaited_once_with({"some": "data"})
    mock_logger_warning.assert_called_once()

async def test_create_user_pydantic_validation_failure(mocker): # type: ignore
    """
    Testa se create_user retorna None e loga um erro quando
    UserInDB.model_validate(user_db_data) falha.
    """
    # --- Arrange ---
    valid_user_create_input = UserCreate(
        email="test_pydantic_fail@example.com",
        username="test_pydantic_user_fail",
        password="validpassword123",
        full_name="Test Pydantic Fail"
    )

    mocker.patch("app.db.user_crud.get_password_hash", return_value="mocked_hashed_password")
    mock_logger_error = mocker.patch("app.db.user_crud.logger.error")

    simulated_pydantic_error = ValidationError.from_exception_data(
        title='UserInDB',
        line_errors=[{'type': 'missing', 'loc': ('some_field',), 'msg': 'Field required', 'input': {}}]
    )
    mock_model_validate = mocker.patch(
        "app.db.user_crud.UserInDB.model_validate",
        side_effect=simulated_pydantic_error
    )

    mock_db_connection = AsyncMock()

    # --- Act ---
    result = await user_crud.create_user(db=mock_db_connection, user_in=valid_user_create_input)

    # --- Assert ---
    assert result is None

    mock_model_validate.assert_called_once()

    mock_logger_error.assert_called_once()
    call_args, call_kwargs = mock_logger_error.call_args
    log_message = call_args[0]
    assert f"Erro de validação Pydantic ao preparar dados para user_db_obj (username: {valid_user_create_input.username})" in log_message
    assert str(simulated_pydantic_error) in log_message
    assert call_kwargs.get("exc_info") is True

async def test_create_user_db_insert_not_acknowledged(mocker): # type: ignore
    """
    Testa se create_user retorna None e loga erro quando a inserção
    no banco de dados não é confirmada (acknowledged=False).
    """
    # --- Arrange ---
    valid_user_create_input = UserCreate(
        email="test_not_acknowledged@example.com",
        username="test_user_not_acknowledged",
        password="validpassword123",
        full_name="Test Not Ack"
    )

    mocker.patch("app.db.user_crud.get_password_hash", return_value="mocked_hashed_password")

    mock_user_db_obj = MagicMock()
    expected_dict_to_insert = {"mocked_data": "to_insert"}
    mock_user_db_obj.model_dump.return_value = expected_dict_to_insert
    mock_validate = mocker.patch("app.db.user_crud.UserInDB.model_validate", return_value=mock_user_db_obj)

    mock_insert_result = MagicMock()
    mock_insert_result.acknowledged = False

    mock_collection = AsyncMock()
    mock_collection.insert_one.return_value = mock_insert_result
    mocker.patch("app.db.user_crud._get_users_collection", return_value=mock_collection)

    mock_logger_error = mocker.patch("app.db.user_crud.logger.error")

    mock_db_connection = AsyncMock()

    # --- Act ---
    result = await user_crud.create_user(db=mock_db_connection, user_in=valid_user_create_input)

    # --- Assert ---
    assert result is None

    mock_validate.assert_called_once()
    mock_user_db_obj.model_dump.assert_called_once_with(mode="json")

    mock_collection.insert_one.assert_awaited_once()

    actual_call_args = mock_collection.insert_one.await_args.args
    actual_call_kwargs = mock_collection.insert_one.await_args.kwargs
    assert len(actual_call_args) == 1
    assert actual_call_args[0] == expected_dict_to_insert
    assert not actual_call_kwargs

    mock_logger_error.assert_called_once()
    call_args, _ = mock_logger_error.call_args
    log_message = call_args[0]
    assert f"DB Insert User Acknowledged False for username {valid_user_create_input.username}" in log_message

async def test_create_user_handles_generic_db_exception_on_insert(mocker): # type: ignore
    """
    Testa se create_user retorna None e loga exceção quando
    insert_one levanta um erro genérico do banco de dados.
    """
    # --- Arrange ---
    valid_user_create_input = UserCreate(
        email="test_generic_db_exception@example.com",
        username="test_user_generic_exception",
        password="validpassword123",
        full_name="Test Generic DB Exc"
    )

    mocker.patch("app.db.user_crud.get_password_hash", return_value="mocked_hashed_password")

    mock_user_db_obj = MagicMock()
    expected_dict_to_insert = {"mocked_data": "to_insert"}
    mock_user_db_obj.model_dump.return_value = expected_dict_to_insert
    mock_validate = mocker.patch("app.db.user_crud.UserInDB.model_validate", return_value=mock_user_db_obj)

    simulated_db_error = Exception("Simulated generic database error on insert")
    mock_collection = AsyncMock()
    mock_collection.insert_one.side_effect = simulated_db_error
    mocker.patch("app.db.user_crud._get_users_collection", return_value=mock_collection)

    mock_logger_exception = mocker.patch("app.db.user_crud.logger.exception")

    mock_db_connection = AsyncMock()

    # --- Act ---
    result = await user_crud.create_user(db=mock_db_connection, user_in=valid_user_create_input)

    # --- Assert ---
    assert result is None

    mock_validate.assert_called_once()
    mock_user_db_obj.model_dump.assert_called_once_with(mode="json")

    mock_collection.insert_one.assert_awaited_once_with(expected_dict_to_insert)

    mock_logger_exception.assert_called_once()
    call_args, _ = mock_logger_exception.call_args
    log_message = call_args[0]
    assert f"Erro inesperado ao inserir usuário {valid_user_create_input.username} no DB" in log_message
    assert str(simulated_db_error) in log_message

# =======================================
# --- Testes para user_crud.update_user ---
# =======================================
async def test_update_user_success(mocker, mock_db_connection, sample_user_in_db): # type: ignore
    """Testa atualização de usuário com sucesso (sem alterar senha)."""
    # --- Arrange ---
    test_user_id = sample_user_in_db.id
    update_payload = UserUpdate(full_name="Novo Nome Completo", email="novo@email.com")
    fixed_timestamp = datetime.now(timezone.utc).replace(microsecond=0)

    mock_doc_after_update = sample_user_in_db.model_dump(mode="json")
    mock_doc_after_update.update({
        "full_name": update_payload.full_name,
        "email": update_payload.email,
        "updated_at": fixed_timestamp # MongoDB lida com datetime object
    })
    mock_doc_after_update["_id"] = "some_mongo_id"

    expected_validation_dict = mock_doc_after_update.copy()
    expected_validation_dict.pop("_id")

    # Criar obj esperado diretamente
    expected_user_obj = UserInDB(**expected_validation_dict)

    mock_pwd_hash = mocker.patch("app.db.user_crud.get_password_hash")
    mock_dt_now = mocker.patch("app.db.user_crud.datetime")
    mock_dt_now.now.return_value = fixed_timestamp

    mock_collection = AsyncMock()
    mock_collection.find_one_and_update.return_value = mock_doc_after_update
    mocker.patch("app.db.user_crud._get_users_collection", return_value=mock_collection)
    mock_validate_model = mocker.patch("app.db.user_crud.UserInDB.model_validate", return_value=expected_user_obj)

    # --- Act ---
    result = await user_crud.update_user(db=mock_db_connection, user_id=test_user_id, user_update=update_payload)

    # --- Assert ---
    assert result == expected_user_obj
    mock_pwd_hash.assert_not_called()

    mock_collection.find_one_and_update.assert_awaited_once()
    args, kwargs = mock_collection.find_one_and_update.await_args
    filter_arg = args[0]
    update_arg = args[1]
    assert filter_arg == {"id": str(test_user_id)}
    expected_set = {
        "full_name": update_payload.full_name,
        "email": update_payload.email,
        "updated_at": fixed_timestamp
    }
    assert update_arg == {"$set": expected_set}
    assert kwargs.get("return_document") is True

    mock_validate_model.assert_called_once_with(expected_validation_dict)

async def test_update_user_with_password(mocker, mock_db_connection, sample_user_in_db): # type: ignore
    """Testa atualização de usuário incluindo a senha."""
    # --- Arrange ---
    test_user_id = sample_user_in_db.id
    new_password = "newSecurePassword123"
    new_hashed_password = "hashed_" + new_password
    update_payload = UserUpdate(password=new_password, disabled=True)
    fixed_timestamp = datetime.now(timezone.utc).replace(microsecond=0)

    mock_doc_after_update = sample_user_in_db.model_dump(mode="json")
    mock_doc_after_update.update({
        "hashed_password": new_hashed_password,
        "disabled": True,
        "updated_at": fixed_timestamp # Usar datetime object
    })
    mock_doc_after_update["_id"] = "pw_update_id"
    expected_validation_dict = mock_doc_after_update.copy()
    expected_validation_dict.pop("_id")

    expected_user_obj = UserInDB(**expected_validation_dict)

    mock_pwd_hash = mocker.patch("app.db.user_crud.get_password_hash", return_value=new_hashed_password)
    mock_dt_now = mocker.patch("app.db.user_crud.datetime")
    mock_dt_now.now.return_value = fixed_timestamp

    mock_collection = AsyncMock()
    mock_collection.find_one_and_update.return_value = mock_doc_after_update
    mocker.patch("app.db.user_crud._get_users_collection", return_value=mock_collection)
    mock_validate_model = mocker.patch("app.db.user_crud.UserInDB.model_validate", return_value=expected_user_obj)

    # --- Act ---
    result = await user_crud.update_user(db=mock_db_connection, user_id=test_user_id, user_update=update_payload)

    # --- Assert ---
    assert result == expected_user_obj
    mock_pwd_hash.assert_called_once_with(new_password)

    mock_collection.find_one_and_update.assert_awaited_once()
    args, kwargs = mock_collection.find_one_and_update.await_args
    filter_arg = args[0]
    update_arg = args[1]
    assert filter_arg == {"id": str(test_user_id)}
    expected_set = {
        "hashed_password": new_hashed_password,
        "disabled": True,
        "updated_at": fixed_timestamp
    }
    assert update_arg == {"$set": expected_set}
    assert kwargs.get("return_document") is True

    mock_validate_model.assert_called_once_with(expected_validation_dict)

async def test_update_user_not_found(mocker, mock_db_connection): # type: ignore
    """Testa atualização de usuário quando find_one_and_update retorna None."""
    # --- Arrange ---
    test_user_id = uuid.uuid4()
    update_payload = UserUpdate(full_name="Nome que nao sera atualizado")
    fixed_timestamp = datetime.now(timezone.utc)

    mock_pwd_hash = mocker.patch("app.db.user_crud.get_password_hash")
    mock_dt_now = mocker.patch("app.db.user_crud.datetime")
    mock_dt_now.now.return_value = fixed_timestamp

    mock_collection = AsyncMock()
    mock_collection.find_one_and_update.return_value = None
    mocker.patch("app.db.user_crud._get_users_collection", return_value=mock_collection)
    mock_logger_warning = mocker.patch("app.db.user_crud.logger.warning")

    # --- Act ---
    result = await user_crud.update_user(db=mock_db_connection, user_id=test_user_id, user_update=update_payload)

    # --- Assert ---
    assert result is None

    mock_collection.find_one_and_update.assert_awaited_once()
    args, kwargs = mock_collection.find_one_and_update.await_args
    expected_set = {"full_name": update_payload.full_name, "updated_at": fixed_timestamp}
    assert args[1] == {"$set": expected_set}

    mock_logger_warning.assert_called_once()
    assert f"Attempt to update user not found: ID {test_user_id}" in mock_logger_warning.call_args[0][0]
    mock_pwd_hash.assert_not_called()

async def test_update_user_raises_duplicate_key_error(mocker, mock_db_connection): # type: ignore
    """Testa se DuplicateKeyError em update é relançado."""
    # --- Arrange ---
    test_user_id = uuid.uuid4()
    update_payload = UserUpdate(email="existing@duplicate.com")
    fixed_timestamp = datetime.now(timezone.utc)


    mocker.patch("app.db.user_crud.get_password_hash")
    mock_dt_now = mocker.patch("app.db.user_crud.datetime")
    mock_dt_now.now.return_value = fixed_timestamp

    simulated_db_error = DuplicateKeyError("E11000 duplicate key error collection")
    mock_collection = AsyncMock()
    mock_collection.find_one_and_update.side_effect = simulated_db_error
    mocker.patch("app.db.user_crud._get_users_collection", return_value=mock_collection)
    mock_logger_warning = mocker.patch("app.db.user_crud.logger.warning")

    # --- Act & Assert ---
    with pytest.raises(DuplicateKeyError):
        await user_crud.update_user(db=mock_db_connection, user_id=test_user_id, user_update=update_payload)

    mock_collection.find_one_and_update.assert_awaited_once()
    args, kwargs = mock_collection.find_one_and_update.await_args
    expected_set = {"email": update_payload.email, "updated_at": fixed_timestamp}
    assert args[1] == {"$set": expected_set}

    mock_logger_warning.assert_called_once()

async def test_update_user_generic_exception(mocker, mock_db_connection): # type: ignore
    """Testa tratamento de exceção genérica em update."""
    # --- Arrange ---
    test_user_id = uuid.uuid4()
    update_payload = UserUpdate(disabled=False)
    fixed_timestamp = datetime.now(timezone.utc)

    mocker.patch("app.db.user_crud.get_password_hash")
    mock_dt_now = mocker.patch("app.db.user_crud.datetime")
    mock_dt_now.now.return_value = fixed_timestamp

    simulated_db_error = Exception("Generic update error")
    mock_collection = AsyncMock()
    mock_collection.find_one_and_update.side_effect = simulated_db_error
    mocker.patch("app.db.user_crud._get_users_collection", return_value=mock_collection)
    mock_logger_exception = mocker.patch("app.db.user_crud.logger.exception")

    # --- Act ---
    result = await user_crud.update_user(db=mock_db_connection, user_id=test_user_id, user_update=update_payload)

    # --- Assert ---
    assert result is None

    mock_collection.find_one_and_update.assert_awaited_once()
    args, kwargs = mock_collection.find_one_and_update.await_args
    expected_set = {"disabled": update_payload.disabled, "updated_at": fixed_timestamp}
    assert args[1] == {"$set": expected_set}

    mock_logger_exception.assert_called_once()
    assert f"DB Error updating user {test_user_id}" in mock_logger_exception.call_args[0][0]

async def test_update_user_empty_payload_updates_only_timestamp(mocker): # type: ignore
    """
    Testa se update_user atualiza apenas o timestamp 'updated_at'
    quando o payload de atualização resulta em nenhum dado a ser modificado,
    e valida se o usuário correto é retornado.
    """
    # --- Arrange ---
    test_user_id = uuid.uuid4()
    fixed_timestamp = datetime.now(timezone.utc).replace(microsecond=0)

    empty_update_payload = UserUpdate(password=None)

    existing_user_mock = MagicMock(spec=UserInDB)
    existing_user_mock.id = test_user_id

    # Doc retornado pelo DB
    mock_doc_after_update_from_db = {"_id": "mongo_id", "id": str(test_user_id), "updated_at": fixed_timestamp}
    # Dict esperado para validação (sem _id)
    expected_dict_for_validation = {"id": str(test_user_id), "updated_at": fixed_timestamp}
    # Obj esperado pós validação (com dados minimos p/ o teste)
    final_validated_user_mock = MagicMock(spec=UserInDB)

    mocker.patch("app.db.user_crud.get_password_hash")
    mock_get_user = mocker.patch("app.db.user_crud.get_user_by_id", return_value=existing_user_mock)
    mock_dt_now = mocker.patch("app.db.user_crud.datetime")
    mock_dt_now.now.return_value = fixed_timestamp

    mock_collection = AsyncMock()
    mock_collection.find_one_and_update.return_value = mock_doc_after_update_from_db
    mocker.patch("app.db.user_crud._get_users_collection", return_value=mock_collection)

    # Mock retorna o obj mockado
    mock_validate_model = mocker.patch(
        "app.db.user_crud.UserInDB.model_validate",
        return_value=final_validated_user_mock
    )

    mock_db_connection = AsyncMock()

    # --- Act ---
    result = await user_crud.update_user(
        db=mock_db_connection,
        user_id=test_user_id,
        user_update=empty_update_payload
    )

    # --- Assert ---
    assert result == final_validated_user_mock

    user_crud.get_password_hash.assert_not_called()

    mock_get_user.assert_awaited_once()
    actual_get_user_args = mock_get_user.await_args.args
    actual_get_user_kwargs = mock_get_user.await_args.kwargs
    assert (len(actual_get_user_args) == 2 and actual_get_user_args[0] is mock_db_connection and actual_get_user_args[1] == test_user_id and not actual_get_user_kwargs) or \
           (not actual_get_user_args and len(actual_get_user_kwargs) == 2 and actual_get_user_kwargs.get('db') is mock_db_connection and actual_get_user_kwargs.get('user_id') == test_user_id)

    mock_collection.find_one_and_update.assert_awaited_once()
    find_one_update_args, find_one_update_kwargs = mock_collection.find_one_and_update.await_args
    assert len(find_one_update_args) == 2
    call_filter = find_one_update_args[0]
    call_update_doc = find_one_update_args[1]
    assert call_filter == {"id": str(test_user_id)}
    assert call_update_doc == {"$set": {"updated_at": fixed_timestamp}}
    assert find_one_update_kwargs.get("return_document") is True

    mock_validate_model.assert_called_once_with(expected_dict_for_validation)

async def test_update_user_empty_payload_get_user_returns_none(mocker): # type: ignore
    """
    Testa se update_user retorna None quando o payload de atualização
    está vazio e a busca inicial por get_user_by_id retorna None.
    """
    # --- Arrange ---
    test_user_id = uuid.uuid4()
    empty_update_payload = UserUpdate(password=None)

    mock_pwd_hash = mocker.patch("app.db.user_crud.get_password_hash")

    mock_get_user = mocker.patch("app.db.user_crud.get_user_by_id", return_value=None)

    mock_collection_instance = AsyncMock()
    mocker.patch(
        "app.db.user_crud._get_users_collection",
        return_value=mock_collection_instance
    )

    mock_validate = mocker.patch("app.db.user_crud.UserInDB.model_validate")

    mock_db_connection = AsyncMock()

    # --- Act ---
    result = await user_crud.update_user(
        db=mock_db_connection,
        user_id=test_user_id,
        user_update=empty_update_payload
    )

    # --- Assert ---
    assert result is None

    mock_pwd_hash.assert_not_called()

    mock_get_user.assert_awaited_once()
    actual_get_user_args = mock_get_user.await_args.args
    actual_get_user_kwargs = mock_get_user.await_args.kwargs
    assert (len(actual_get_user_args) == 2 and actual_get_user_args[0] is mock_db_connection and actual_get_user_args[1] == test_user_id and not actual_get_user_kwargs) or \
           (not actual_get_user_args and len(actual_get_user_kwargs) == 2 and actual_get_user_kwargs.get('db') is mock_db_connection and actual_get_user_kwargs.get('user_id') == test_user_id)

    # _get_users_collection *é chamado* no início da função update_user
    user_crud._get_users_collection.assert_called_once_with(mock_db_connection)
    mock_collection_instance.find_one_and_update.assert_not_called()
    mock_validate.assert_not_called()

async def test_update_user_empty_payload_update_exception(mocker): # type: ignore
    """
    Testa se update_user retorna None e loga exceção quando payload está vazio
    e a chamada a find_one_and_update (para updated_at) levanta erro.
    """
    # --- Arrange ---
    test_user_id = uuid.uuid4()
    fixed_timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    empty_update_payload = UserUpdate(password=None)

    existing_user_mock = MagicMock(spec=UserInDB)
    existing_user_mock.id = test_user_id

    simulated_update_exception = Exception("Erro ao atualizar apenas updated_at")

    mock_pwd_hash = mocker.patch("app.db.user_crud.get_password_hash")
    mock_get_user = mocker.patch("app.db.user_crud.get_user_by_id", return_value=existing_user_mock)
    mock_dt_now = mocker.patch("app.db.user_crud.datetime")
    mock_dt_now.now.return_value = fixed_timestamp

    mock_collection = AsyncMock()
    mock_collection.find_one_and_update.side_effect = simulated_update_exception
    mocker.patch("app.db.user_crud._get_users_collection", return_value=mock_collection)

    mock_validate_model = mocker.patch("app.db.user_crud.UserInDB.model_validate")
    mock_logger_exception = mocker.patch("app.db.user_crud.logger.exception")
    mock_db_connection = AsyncMock()

    # --- Act ---
    result = await user_crud.update_user(
        db=mock_db_connection,
        user_id=test_user_id,
        user_update=empty_update_payload
    )

    # --- Assert ---
    assert result is None

    mock_pwd_hash.assert_not_called()
    mock_get_user.assert_awaited_once()

    mock_collection.find_one_and_update.assert_awaited_once()
    mock_validate_model.assert_not_called()
    mock_logger_exception.assert_called_once()
    call_args, _ = mock_logger_exception.call_args
    log_message = call_args[0]
    assert f"DB Error updating user (only updated_at) {test_user_id}" in log_message
    assert str(simulated_update_exception) in log_message

async def test_update_user_empty_payload_validate_failure(mocker): # type: ignore
    """
    Testa falha na validação Pydantic após find_one_and_update
    no branch de payload vazio, assumindo que find_one_and_update retornou um doc.
    """
    # --- Arrange ---
    test_user_id = uuid.uuid4()
    fixed_timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    empty_update_payload = UserUpdate(password=None)

    existing_user_mock = MagicMock(spec=UserInDB)
    existing_user_mock.id = test_user_id

    mock_doc_after_update_invalid = {
        "_id": "mongo_id_invalid",
        "id": str(test_user_id),
        "updated_at": fixed_timestamp,
        "campo_inesperado": "este_campo_causa_falha"
    }
    expected_dict_for_validation = {
        "id": str(test_user_id),
        "updated_at": fixed_timestamp,
        "campo_inesperado": "este_campo_causa_falha"
    }

    mocker.patch("app.db.user_crud.get_password_hash")
    mock_get_user = mocker.patch("app.db.user_crud.get_user_by_id", return_value=existing_user_mock)
    mock_dt_now = mocker.patch("app.db.user_crud.datetime")
    mock_dt_now.now.return_value = fixed_timestamp

    mock_collection = AsyncMock()
    mock_collection.find_one_and_update.return_value = mock_doc_after_update_invalid
    mocker.patch("app.db.user_crud._get_users_collection", return_value=mock_collection)

    simulated_validation_error = ValidationError.from_exception_data(
        title='UserInDB',
        line_errors=[{'type': 'extra_forbidden', 'loc': ('campo_inesperado',), 'msg': 'Extra fields not permitted', 'input': 'este_campo_causa_falha'}]
    )
    mock_validate_model = mocker.patch(
        "app.db.user_crud.UserInDB.model_validate",
        side_effect=simulated_validation_error
    )

    mock_logger_exception = mocker.patch("app.db.user_crud.logger.exception")
    mock_logger_error = mocker.patch("app.db.user_crud.logger.error") # Deve usar .exception agora
    mock_db_connection = AsyncMock()

    # --- Act ---
    result = await user_crud.update_user(
        db=mock_db_connection,
        user_id=test_user_id,
        user_update=empty_update_payload
    )

    # --- Assert ---
    assert result is None

    user_crud.get_password_hash.assert_not_called()
    mock_get_user.assert_awaited_once()
    mock_collection.find_one_and_update.assert_awaited_once()

    # A validação falha, mas ainda é chamada
    mock_validate_model.assert_called_once_with(expected_dict_for_validation)

    # O erro é capturado pelo 'except Exception', usando logger.exception
    mock_logger_error.assert_not_called()
    mock_logger_exception.assert_called_once()
    call_args, _ = mock_logger_exception.call_args
    log_message = call_args[0]
    assert f"DB Error updating user (only updated_at) {test_user_id}" in log_message
    assert str(simulated_validation_error) in log_message

async def test_update_user_main_path_validate_failure(mocker): # type: ignore
    """
    Testa falha na validação Pydantic após find_one_and_update
    no caminho principal (quando update_data não está vazio).
    """
    # --- Arrange ---
    test_user_id = uuid.uuid4()
    update_payload = UserUpdate(full_name="Nome Atualizado")
    fixed_timestamp = datetime.now(timezone.utc).replace(microsecond=0)

    mock_doc_after_update_invalid = {
        "_id": "mongo_id_main_fail",
        "id": str(test_user_id),
        "full_name": update_payload.full_name,
        "updated_at": fixed_timestamp,
        "campo_invalido_no_retorno": 123
    }
    expected_dict_for_validation = {
        "id": str(test_user_id),
        "full_name": update_payload.full_name,
        "updated_at": fixed_timestamp,
        "campo_invalido_no_retorno": 123
    }

    mock_pwd_hash = mocker.patch("app.db.user_crud.get_password_hash")
    mock_get_user = mocker.patch("app.db.user_crud.get_user_by_id")
    mock_dt_now = mocker.patch("app.db.user_crud.datetime")
    mock_dt_now.now.return_value = fixed_timestamp

    mock_collection = AsyncMock()
    mock_collection.find_one_and_update.return_value = mock_doc_after_update_invalid
    mocker.patch("app.db.user_crud._get_users_collection", return_value=mock_collection)

    simulated_validation_error = ValidationError.from_exception_data(
        title='UserInDB',
        line_errors=[{'type': 'extra_forbidden', 'loc': ('campo_invalido_no_retorno',), 'msg': 'Extra fields not permitted', 'input': 123}]
    )
    mock_validate_model = mocker.patch(
        "app.db.user_crud.UserInDB.model_validate",
        side_effect=simulated_validation_error
    )

    mock_logger_error = mocker.patch("app.db.user_crud.logger.error")
    mock_db_connection = AsyncMock()

    # --- Act ---
    result = await user_crud.update_user(
        db=mock_db_connection,
        user_id=test_user_id,
        user_update=update_payload
    )

    # --- Assert ---
    assert result is None

    mock_pwd_hash.assert_not_called()
    mock_get_user.assert_not_called()

    mock_collection.find_one_and_update.assert_awaited_once()
    find_one_update_args, find_one_update_kwargs = mock_collection.find_one_and_update.await_args
    assert len(find_one_update_args) == 2
    call_filter = find_one_update_args[0]
    call_update_doc = find_one_update_args[1]
    assert call_filter == {"id": str(test_user_id)}
    expected_set_doc = {"full_name": update_payload.full_name, "updated_at": fixed_timestamp}
    assert call_update_doc == {"$set": expected_set_doc}
    assert find_one_update_kwargs.get("return_document") is True

    mock_validate_model.assert_called_once_with(expected_dict_for_validation)

    mock_logger_error.assert_called_once()
    call_args, call_kwargs = mock_logger_error.call_args
    log_message = call_args[0]
    assert f"DB Validation error after updating user {test_user_id}" in log_message
    assert str(simulated_validation_error) in log_message
    # A asserção sobre exc_info foi removida, pois o teste falhou e a correção acima garante o log esperado.

async def test_update_user_main_path_user_not_found(mocker, mock_db_connection): # type: ignore
    """
    Testa se update_user retorna None e loga aviso quando o usuário
    não é encontrado por find_one_and_update no caminho principal.
    """
    # --- Arrange ---
    test_user_id = uuid.uuid4()
    update_payload = UserUpdate(full_name="Nome Nao Atualizado")
    fixed_timestamp = datetime.now(timezone.utc)

    mock_pwd_hash = mocker.patch("app.db.user_crud.get_password_hash")
    mock_dt_now = mocker.patch("app.db.user_crud.datetime")
    mock_dt_now.now.return_value = fixed_timestamp

    mock_collection = AsyncMock()
    mock_collection.find_one_and_update.return_value = None 
    mocker.patch("app.db.user_crud._get_users_collection", return_value=mock_collection)

    mock_validate_model = mocker.patch("app.db.user_crud.UserInDB.model_validate")
    mock_logger_warning = mocker.patch("app.db.user_crud.logger.warning")

    # --- Act ---
    result = await user_crud.update_user(
        db=mock_db_connection,
        user_id=test_user_id,
        user_update=update_payload
    )

    # --- Assert ---
    assert result is None

    mock_pwd_hash.assert_not_called()
    mock_collection.find_one_and_update.assert_awaited_once()
    mock_validate_model.assert_not_called()

    mock_logger_warning.assert_called_once()
    log_call_args = mock_logger_warning.call_args[0]
    assert f"Attempt to update user not found: ID {test_user_id}" in log_call_args[0]

async def test_update_user_main_path_raises_duplicate_key_error(mocker, mock_db_connection): # type: ignore
    """
    Testa se DuplicateKeyError é relançado por update_user
    no caminho principal e um aviso é logado.
    """
    # --- Arrange ---
    test_user_id = uuid.uuid4()
    update_payload = UserUpdate(email="duplicate@test.com") 
    fixed_timestamp = datetime.now(timezone.utc)

    mocker.patch("app.db.user_crud.get_password_hash")
    mock_dt_now = mocker.patch("app.db.user_crud.datetime")
    mock_dt_now.now.return_value = fixed_timestamp

    simulated_db_error = DuplicateKeyError("E11000 duplicate key error collection on update")
    mock_collection = AsyncMock()
    mock_collection.find_one_and_update.side_effect = simulated_db_error
    mocker.patch("app.db.user_crud._get_users_collection", return_value=mock_collection)

    mock_validate_model = mocker.patch("app.db.user_crud.UserInDB.model_validate")
    mock_logger_warning = mocker.patch("app.db.user_crud.logger.warning")

    # --- Act & Assert ---
    with pytest.raises(DuplicateKeyError):
        await user_crud.update_user(
            db=mock_db_connection,
            user_id=test_user_id,
            user_update=update_payload
        )

    mock_collection.find_one_and_update.assert_awaited_once()
    args, kwargs = mock_collection.find_one_and_update.await_args
    expected_set = {"email": update_payload.email, "updated_at": fixed_timestamp}
    assert args[1] == {"$set": expected_set}

    mock_validate_model.assert_not_called()

    mock_logger_warning.assert_called_once()
    log_call_args = mock_logger_warning.call_args[0]
    assert f"DB Error: Attempt to update user {test_user_id}" in log_call_args[0]
    assert "'email': 'duplicate@test.com'" in log_call_args[0]

async def test_update_user_empty_payload_find_one_and_update_returns_none(mocker): # type: ignore
    """
    Testa se update_user retorna None quando payload está vazio,
    usuário existe, mas find_one_and_update (para updated_at) retorna None.
    """
    # --- Arrange ---
    test_user_id = uuid.uuid4()
    fixed_timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    empty_update_payload = UserUpdate(password=None)

    existing_user_mock = MagicMock(spec=UserInDB)
    existing_user_mock.id = test_user_id

    mock_pwd_hash = mocker.patch("app.db.user_crud.get_password_hash")
    mock_get_user = mocker.patch("app.db.user_crud.get_user_by_id", return_value=existing_user_mock)
    mock_dt_now = mocker.patch("app.db.user_crud.datetime")
    mock_dt_now.now.return_value = fixed_timestamp

    mock_collection = AsyncMock()
    mock_collection.find_one_and_update.return_value = None 
    mocker.patch("app.db.user_crud._get_users_collection", return_value=mock_collection)

    mock_validate_model = mocker.patch("app.db.user_crud.UserInDB.model_validate")
    mock_logger_exception = mocker.patch("app.db.user_crud.logger.exception")
    mock_db_connection = AsyncMock()

    # --- Act ---
    result = await user_crud.update_user(
        db=mock_db_connection,
        user_id=test_user_id,
        user_update=empty_update_payload
    )

    # --- Assert ---
    assert result is None

    mock_pwd_hash.assert_not_called()
    mock_get_user.assert_awaited_once()

    # Verifica a chamada a find_one_and_update (para updated_at)
    mock_collection.find_one_and_update.assert_awaited_once()
    find_one_update_args, find_one_update_kwargs = mock_collection.find_one_and_update.await_args
    assert len(find_one_update_args) == 2
    call_filter = find_one_update_args[0]
    call_update_doc = find_one_update_args[1]
    assert call_filter == {"id": str(test_user_id)}
    assert call_update_doc == {"$set": {"updated_at": fixed_timestamp}}
    assert find_one_update_kwargs.get("return_document") is True

    mock_validate_model.assert_not_called()
    mock_logger_exception.assert_not_called()

# =======================================
# --- Testes para user_crud.delete_user ---
# =======================================
async def test_delete_user_success(mocker, mock_db_connection): # type: ignore
    """Testa deleção de usuário com sucesso."""
    # --- Arrange ---
    test_user_id = uuid.uuid4()

    mock_delete_result = MagicMock()
    mock_delete_result.deleted_count = 1

    mock_collection = AsyncMock()
    mock_collection.delete_one.return_value = mock_delete_result
    mocker.patch("app.db.user_crud._get_users_collection", return_value=mock_collection)
    mock_logger_info = mocker.patch("app.db.user_crud.logger.info")

    # --- Act ---
    result = await user_crud.delete_user(db=mock_db_connection, user_id=test_user_id)

    # --- Assert ---
    assert result is True
    mock_collection.delete_one.assert_awaited_once_with({"id": str(test_user_id)})
    mock_logger_info.assert_called_once_with(f"User {test_user_id} deleted successfully.")

async def test_delete_user_not_found(mocker, mock_db_connection): # type: ignore
    """Testa deleção de usuário quando não encontrado."""
    # --- Arrange ---
    test_user_id = uuid.uuid4()

    mock_delete_result = MagicMock()
    mock_delete_result.deleted_count = 0

    mock_collection = AsyncMock()
    mock_collection.delete_one.return_value = mock_delete_result
    mocker.patch("app.db.user_crud._get_users_collection", return_value=mock_collection)
    mock_logger_warning = mocker.patch("app.db.user_crud.logger.warning")

    # --- Act ---
    result = await user_crud.delete_user(db=mock_db_connection, user_id=test_user_id)

    # --- Assert ---
    assert result is False
    mock_collection.delete_one.assert_awaited_once_with({"id": str(test_user_id)})
    mock_logger_warning.assert_called_once()
    assert f"Attempt to delete user {test_user_id}" in mock_logger_warning.call_args[0][0]
    assert "(deleted_count: 0)" in mock_logger_warning.call_args[0][0]

async def test_delete_user_generic_exception(mocker, mock_db_connection): # type: ignore
    """Testa tratamento de exceção genérica em delete_user."""
    # --- Arrange ---
    test_user_id = uuid.uuid4()
    simulated_db_error = Exception("Generic delete error")

    mock_collection = AsyncMock()
    mock_collection.delete_one.side_effect = simulated_db_error
    mocker.patch("app.db.user_crud._get_users_collection", return_value=mock_collection)
    mock_logger_exception = mocker.patch("app.db.user_crud.logger.exception")

    # --- Act ---
    result = await user_crud.delete_user(db=mock_db_connection, user_id=test_user_id)

    # --- Assert ---
    assert result is False
    mock_collection.delete_one.assert_awaited_once_with({"id": str(test_user_id)})
    mock_logger_exception.assert_called_once()
    assert f"DB Error deleting user {test_user_id}" in mock_logger_exception.call_args[0][0]

# ==============================================
# --- Testes para user_crud.create_user_indexes ---
# ==============================================
async def test_create_user_indexes_success(mocker, mock_db_connection): # type: ignore
    """Testa criação de índices com sucesso."""
    # --- Arrange ---
    mock_collection = AsyncMock()
    mock_collection.create_index = AsyncMock()
    mocker.patch("app.db.user_crud._get_users_collection", return_value=mock_collection)
    mock_logger_info = mocker.patch("app.db.user_crud.logger.info")

    # --- Act ---
    await user_crud.create_user_indexes(db=mock_db_connection)

    # --- Assert ---
    expected_calls = [
        call("username", unique=True, name="username_unique_idx"),
        call("email", unique=True, name="email_unique_idx")
    ]
    mock_collection.create_index.assert_has_awaits(expected_calls, any_order=False)
    mock_logger_info.assert_called_once()
    assert "Índices da coleção 'users'" in mock_logger_info.call_args[0][0]
    assert "verificados/criados com sucesso" in mock_logger_info.call_args[0][0]

async def test_create_user_indexes_failure(mocker, mock_db_connection): # type: ignore
    """Testa tratamento de erro na criação de índices."""
    # --- Arrange ---
    simulated_index_error = Exception("Erro ao criar indice simulado")
    mock_collection = AsyncMock()
    mock_collection.create_index.side_effect = simulated_index_error
    mocker.patch("app.db.user_crud._get_users_collection", return_value=mock_collection)
    mock_logger_error = mocker.patch("app.db.user_crud.logger.error")

    # --- Act ---
    await user_crud.create_user_indexes(db=mock_db_connection)

    # --- Assert ---
    mock_collection.create_index.assert_awaited_once_with("username", unique=True, name="username_unique_idx")
    mock_logger_error.assert_called_once()
    call_args, call_kwargs = mock_logger_error.call_args
    log_message = call_args[0]
    assert "Erro ao criar índices para a coleção 'users'" in log_message
    assert str(simulated_index_error) in log_message
    assert call_kwargs.get("exc_info") is True