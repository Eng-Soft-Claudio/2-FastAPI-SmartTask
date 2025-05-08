# tests/test_worker.py

# ========================
# --- Importações ---
# ========================
import pytest # type: ignore
import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch
from pydantic import ValidationError
import app.worker 
from importlib import reload

# --- Módulos da Aplicação ---
from app.worker import check_and_notify_urgent_tasks
from app.models.task import Task, TaskStatus
from app.models.user import UserInDB
from app.core.config import settings


# =================================================================
# --- Fixtures de Dados de Teste para Usuários e Tarefas ---
# =================================================================
@pytest.fixture
def user_active_with_email() -> UserInDB:
    return UserInDB(
        id=uuid.uuid4(),
        username="testworkeruser",
        email="worker@example.com",
        full_name="Worker Test User",
        hashed_password="fakehash",
        disabled=False,
        created_at=datetime.now(timezone.utc)
    )

@pytest.fixture
def user_disabled_fixture() -> UserInDB: 
    return UserInDB(
        id=uuid.uuid4(),
        username="disableduser",
        email="disabled@example.com",
        full_name="Disabled User",
        hashed_password="fakehash",
        disabled=True,
        created_at=datetime.now(timezone.utc)
    )

@pytest.fixture
def task_urgent_score(user_active_with_email: UserInDB) -> Task:
    return Task(
        id=uuid.uuid4(),
        owner_id=user_active_with_email.id,
        title="Urgent High Score Task",
        importance=5,
        status=TaskStatus.PENDING,
        created_at=datetime.now(timezone.utc) - timedelta(days=1),
        priority_score=settings.EMAIL_URGENCY_THRESHOLD + 50.0,
        due_date=date.today() + timedelta(days=10)
    )

@pytest.fixture
def task_urgent_overdue(user_active_with_email: UserInDB) -> Task:
    return Task(
        id=uuid.uuid4(),
        owner_id=user_active_with_email.id,
        title="Urgent Overdue Task",
        importance=1,
        status=TaskStatus.PENDING,
        created_at=datetime.now(timezone.utc) - timedelta(days=5),
        priority_score=10.0,
        due_date=date.today() - timedelta(days=1)
    )

@pytest.fixture
def task_urgent_due_today(user_active_with_email: UserInDB) -> Task:
    return Task(
        id=uuid.uuid4(),
        owner_id=user_active_with_email.id,
        title="Urgent Due Today Task",
        importance=2,
        status=TaskStatus.IN_PROGRESS,
        created_at=datetime.now(timezone.utc) - timedelta(days=2),
        priority_score=20.0,
        due_date=date.today()
    )

@pytest.fixture
def task_not_urgent(user_active_with_email: UserInDB) -> Task:
    return Task(
        id=uuid.uuid4(),
        owner_id=user_active_with_email.id,
        title="Not Urgent Task",
        importance=3,
        status=TaskStatus.PENDING,
        created_at=datetime.now(timezone.utc),
        priority_score=settings.EMAIL_URGENCY_THRESHOLD - 10.0,
        due_date=date.today() + timedelta(days=5)
    )

@pytest.fixture
def task_completed(user_active_with_email: UserInDB) -> Task:
    return Task(
        id=uuid.uuid4(),
        owner_id=user_active_with_email.id,
        title="Completed Urgent Task",
        importance=5,
        status=TaskStatus.COMPLETED,
        created_at=datetime.now(timezone.utc) - timedelta(days=10),
        priority_score=settings.EMAIL_URGENCY_THRESHOLD + 100.0,
        due_date=date.today() - timedelta(days=2)
    )

@pytest.fixture
def task_disabled_user(user_disabled_fixture: UserInDB) -> Task: 
    return Task(
        id=uuid.uuid4(),
        owner_id=user_disabled_fixture.id,
        title="Disabled User Urgent Task",
        importance=5,
        status=TaskStatus.PENDING,
        created_at=datetime.now(timezone.utc),
        priority_score=settings.EMAIL_URGENCY_THRESHOLD + 50.0
    )

# =============================================================
# --- Testes para a função `check_and_notify_urgent_tasks` ---
# =============================================================
@pytest.mark.asyncio
async def test_worker_no_urgent_tasks(mocker): 
    """
    Testa o comportamento da função do worker ARQ quando o banco
    de dados simulado não retorna nenhuma tarefa urgente.
    """
    # ========================
    # --- Arrange ---
    # ========================
    mock_db = MagicMock()
    mock_tasks_collection = MagicMock()
    mock_db.__getitem__.return_value = mock_tasks_collection

    mock_cursor = AsyncMock()
    mock_cursor.__aiter__.return_value = []
    mock_tasks_collection.find.return_value = mock_cursor

    mock_get_user = mocker.patch("app.worker.user_crud.get_user_by_id", new_callable=AsyncMock)
    mock_send_email = mocker.patch("app.worker.send_urgent_task_notification", new_callable=AsyncMock)

    ctx = {"db": mock_db}
    # ========================
    # --- Act ---
    # ========================
    await check_and_notify_urgent_tasks(ctx)

    # ========================
    # --- Assert ---
    # ========================
    mock_tasks_collection.find.assert_called_once()
    mock_get_user.assert_not_called()
    mock_send_email.assert_not_called()

@pytest.mark.asyncio
async def test_worker_one_urgent_task_active_user(mocker, user_active_with_email, task_urgent_score): 
    """
    Testa o cenário onde o worker encontra uma tarefa urgente
    pertencente a um usuário ativo e com e-mail.
    """
    # ========================
    # --- Arrange ---
    # ========================
    mock_db = MagicMock()
    mock_tasks_collection = MagicMock()
    mock_users_collection = MagicMock()
    def db_getitem_side_effect(key):
        if key == "tasks": return mock_tasks_collection
        if key == "users": return mock_users_collection
        raise KeyError(key)
    mock_db.__getitem__.side_effect = db_getitem_side_effect

    task_dict = task_urgent_score.model_dump(mode='json')
    mock_cursor = AsyncMock()
    mock_cursor.__aiter__.return_value = [task_dict]
    mock_tasks_collection.find.return_value = mock_cursor

    mock_get_user = mocker.patch(
        "app.worker.user_crud.get_user_by_id",
        new_callable=AsyncMock,
        return_value=user_active_with_email
    )
    mock_send_email = mocker.patch("app.worker.send_urgent_task_notification", new_callable=AsyncMock)

    ctx = {"db": mock_db}
    # ========================
    # --- Act ---
    # ========================
    await check_and_notify_urgent_tasks(ctx)

    # ========================
    # --- Assert ---
    # ========================
    mock_tasks_collection.find.assert_called_once()
    mock_get_user.assert_called_once_with(mock_db, task_urgent_score.owner_id)
    mock_send_email.assert_called_once()

    call_args = mock_send_email.call_args.kwargs
    assert call_args['user_email'] == user_active_with_email.email
    assert call_args['user_name'] == user_active_with_email.full_name
    assert call_args['task_title'] == task_urgent_score.title
    assert call_args['task_id'] == str(task_urgent_score.id)

@pytest.mark.asyncio
async def test_worker_mix_urgent_non_urgent_completed(mocker, user_active_with_email, task_not_urgent, task_urgent_overdue, task_completed): 
    """
    Testa o worker com uma mistura de tarefas.
    """
    # ========================
    # --- Arrange ---
    # ========================
    mock_db = MagicMock()
    mock_tasks_collection = MagicMock()
    mock_users_collection = MagicMock()
    def db_getitem_side_effect(key):
        if key == "tasks": return mock_tasks_collection
        if key == "users": return mock_users_collection
        raise KeyError(key)
    mock_db.__getitem__.side_effect = db_getitem_side_effect

    # Simular que a query `find` retorna apenas a tarefa urgente e não completada
    filtered_task_dict = task_urgent_overdue.model_dump(mode='json')
    mock_cursor = AsyncMock()
    mock_cursor.__aiter__.return_value = [filtered_task_dict]
    mock_tasks_collection.find.return_value = mock_cursor

    mock_get_user = mocker.patch(
        "app.worker.user_crud.get_user_by_id",
        new_callable=AsyncMock,
        return_value=user_active_with_email
    )
    mock_send_email = mocker.patch("app.worker.send_urgent_task_notification", new_callable=AsyncMock)

    ctx = {"db": mock_db}
    # ========================
    # --- Act ---
    # ========================
    await check_and_notify_urgent_tasks(ctx)

    # ========================
    # --- Assert ---
    # ========================
    mock_tasks_collection.find.assert_called_once()
    mock_get_user.assert_called_once_with(mock_db, task_urgent_overdue.owner_id)
    mock_send_email.assert_called_once()
    call_args = mock_send_email.call_args.kwargs
    assert call_args['task_title'] == task_urgent_overdue.title

@pytest.mark.asyncio
async def test_worker_urgent_task_disabled_user(mocker, user_disabled_fixture, task_disabled_user): 
    """
    Testa que nenhuma notificação é enviada se o usuário estiver desativado.
    """
    # ========================
    # --- Arrange ---
    # ========================
    mock_db = MagicMock()
    mock_tasks_collection = MagicMock()
    mock_users_collection = MagicMock()
    def db_getitem_side_effect(key):
        if key == "tasks": return mock_tasks_collection
        if key == "users": return mock_users_collection
        raise KeyError(key)
    mock_db.__getitem__.side_effect = db_getitem_side_effect

    mock_cursor = AsyncMock()
    mock_cursor.__aiter__.return_value = [task_disabled_user.model_dump(mode='json')]
    mock_tasks_collection.find.return_value = mock_cursor

    mock_get_user = mocker.patch(
        "app.worker.user_crud.get_user_by_id",
        new_callable=AsyncMock,
        return_value=user_disabled_fixture
    )
    mock_send_email = mocker.patch("app.worker.send_urgent_task_notification", new_callable=AsyncMock)

    ctx = {"db": mock_db}
    # ========================
    # --- Act ---
    # ========================
    await check_and_notify_urgent_tasks(ctx)

    # ========================
    # --- Assert ---
    # ========================
    mock_tasks_collection.find.assert_called_once()
    mock_get_user.assert_called_once_with(mock_db, user_disabled_fixture.id)
    mock_send_email.assert_not_called()

@pytest.mark.asyncio
async def test_worker_multiple_urgent_tasks(mocker, user_active_with_email, task_urgent_score, task_urgent_overdue, task_urgent_due_today): 
    """
    Testa o cenário com múltiplas tarefas urgentes para usuários ativos.
    """
    # ========================
    # --- Arrange ---
    # ========================
    mock_db = MagicMock()
    mock_tasks_collection = MagicMock()
    mock_users_collection = MagicMock()
    def db_getitem_side_effect(key):
        if key == "tasks": return mock_tasks_collection
        if key == "users": return mock_users_collection
        raise KeyError(key)
    mock_db.__getitem__.side_effect = db_getitem_side_effect

    urgent_tasks_list_dicts = [
        task_urgent_score.model_dump(mode='json'),
        task_urgent_overdue.model_dump(mode='json'),
        task_urgent_due_today.model_dump(mode='json')
    ]
    mock_cursor = AsyncMock()
    mock_cursor.__aiter__.return_value = urgent_tasks_list_dicts
    mock_tasks_collection.find.return_value = mock_cursor

    mock_get_user = mocker.patch(
        "app.worker.user_crud.get_user_by_id",
        new_callable=AsyncMock,
        return_value=user_active_with_email
    )
    mock_send_email = mocker.patch("app.worker.send_urgent_task_notification", new_callable=AsyncMock)

    ctx = {"db": mock_db}
    # ========================
    # --- Act ---
    # ========================
    await check_and_notify_urgent_tasks(ctx)

    # ========================
    # --- Assert ---
    # ========================
    assert mock_tasks_collection.find.call_count == 1
    assert mock_get_user.call_count == len(urgent_tasks_list_dicts)
    assert mock_send_email.call_count == len(urgent_tasks_list_dicts)

    expected_call_args_score = {
        'user_email': user_active_with_email.email,
        'user_name': user_active_with_email.full_name,
        'task_title': task_urgent_score.title,
        'task_id': str(task_urgent_score.id),
        'task_due_date': str(task_urgent_score.due_date),
        'priority_score': task_urgent_score.priority_score
    }
    expected_call_args_overdue = {
        'user_email': user_active_with_email.email,
        'user_name': user_active_with_email.full_name,
        'task_title': task_urgent_overdue.title,
        'task_id': str(task_urgent_overdue.id),
        'task_due_date': str(task_urgent_overdue.due_date),
        'priority_score': task_urgent_overdue.priority_score
    }
    expected_call_args_today = {
        'user_email': user_active_with_email.email,
        'user_name': user_active_with_email.full_name,
        'task_title': task_urgent_due_today.title,
        'task_id': str(task_urgent_due_today.id),
        'task_due_date': str(task_urgent_due_today.due_date),
        'priority_score': task_urgent_due_today.priority_score
    }
    mock_send_email.assert_has_calls([
        call(**expected_call_args_score),
        call(**expected_call_args_overdue),
        call(**expected_call_args_today)
    ], any_order=True)

@pytest.mark.asyncio
async def test_worker_db_unavailable(mocker): 
    """
    Testa o comportamento do worker quando 'db' não está no contexto.
    """
    # ========================
    # --- Arrange ---
    # ========================
    mock_send_email = mocker.patch("app.worker.send_urgent_task_notification", new_callable=AsyncMock)
    mock_logger = mocker.patch("app.worker.logger")

    ctx = {}
    # ========================
    # --- Act ---
    # ========================
    await check_and_notify_urgent_tasks(ctx)

    # ========================
    # --- Assert ---
    # ========================
    mock_send_email.assert_not_called()
    mock_logger.error.assert_called_once_with(
        "Conexão com o banco de dados não disponível no contexto ARQ."
    )

@pytest.mark.asyncio
async def test_worker_user_not_found(mocker, task_urgent_score): 
    """
    Testa o caso onde uma tarefa urgente é encontrada, mas o usuário
    proprietário não é encontrado no banco de dados.
    """
    # ========================
    # --- Arrange ---
    # ========================
    mock_db = MagicMock()
    mock_tasks_collection = MagicMock()
    mock_users_collection = MagicMock()
    def db_getitem_side_effect(key):
        if key == "tasks": return mock_tasks_collection
        if key == "users": return mock_users_collection
        raise KeyError(key)
    mock_db.__getitem__.side_effect = db_getitem_side_effect

    urgent_task_dict = task_urgent_score.model_dump(mode='json')
    mock_cursor = AsyncMock()
    mock_cursor.__aiter__.return_value = [urgent_task_dict]
    mock_tasks_collection.find.return_value = mock_cursor

    mock_get_user = mocker.patch(
        "app.worker.user_crud.get_user_by_id",
        new_callable=AsyncMock,
        return_value=None
    )
    mock_send_email = mocker.patch("app.worker.send_urgent_task_notification", new_callable=AsyncMock)
    mock_logger_warning = mocker.patch("app.worker.logger.warning")

    ctx = {"db": mock_db}

    # ========================
    # --- Act ---
    # ========================
    await check_and_notify_urgent_tasks(ctx)

    # ========================
    # --- Assert ---
    # ========================
    mock_tasks_collection.find.assert_called_once()
    mock_get_user.assert_called_once_with(mock_db, task_urgent_score.owner_id)
    mock_send_email.assert_not_called()
    mock_logger_warning.assert_called_once()
    log_message = mock_logger_warning.call_args[0][0]
    assert f"Usuário com ID '{task_urgent_score.owner_id}' associado à tarefa urgente '{task_urgent_score.id}' não foi encontrado" in log_message

@pytest.mark.asyncio
async def test_worker_user_missing_details(mocker, user_active_with_email, task_urgent_due_today): 
    """
    Testa o caso onde o usuário é encontrado, mas falta email ou nome.
    """
    # ========================
    # --- Arrange ---
    # ========================
    for missing_field in ["email", "full_name"]:
        mock_db = MagicMock()
        mock_tasks_collection = MagicMock()
        mock_users_collection = MagicMock()
        def db_getitem_side_effect(key):
            if key == "tasks": return mock_tasks_collection
            if key == "users": return mock_users_collection
            raise KeyError(key)
        mock_db.__getitem__.side_effect = db_getitem_side_effect

        urgent_task_dict = task_urgent_due_today.model_dump(mode='json')
        mock_cursor = AsyncMock()
        mock_cursor.__aiter__.return_value = [urgent_task_dict]
        mock_tasks_collection.find.return_value = mock_cursor

        user_missing_details_mock = user_active_with_email.model_copy(deep=True)
        setattr(user_missing_details_mock, missing_field, None)

        mock_get_user = mocker.patch(
            "app.worker.user_crud.get_user_by_id",
            new_callable=AsyncMock,
            return_value=user_missing_details_mock
        )
        mock_send_email = mocker.patch("app.worker.send_urgent_task_notification", new_callable=AsyncMock)
        mock_logger_warning = mocker.patch("app.worker.logger.warning")

        ctx = {"db": mock_db}

        # ========================
        # --- Act ---
        # ========================
        await check_and_notify_urgent_tasks(ctx)

        # ========================
        # --- Assert ---
        # ========================
        mock_tasks_collection.find.assert_called_once()
        mock_get_user.assert_called_once_with(mock_db, task_urgent_due_today.owner_id)
        mock_send_email.assert_not_called()
        mock_logger_warning.assert_called_once()
        log_message = mock_logger_warning.call_args[0][0]
        assert f"Usuário '{user_missing_details_mock.username}'" in log_message
        assert "não possui e-mail ou nome completo configurado" in log_message

        mocker.resetall()

@pytest.mark.asyncio
async def test_worker_task_processing_exception(mocker, user_active_with_email, task_urgent_score, task_urgent_overdue): 
    """
    Testa o tratamento de exceção dentro do loop de processamento de tarefas.
    """
    # ========================
    # --- Arrange ---
    # ========================
    mock_db = MagicMock()
    mock_tasks_collection = MagicMock()
    mock_users_collection = MagicMock()
    def db_getitem_side_effect(key):
        if key == "tasks": return mock_tasks_collection
        if key == "users": return mock_users_collection
        raise KeyError(key)
    mock_db.__getitem__.side_effect = db_getitem_side_effect

    invalid_task_dict = task_urgent_score.model_dump(mode='json')
    invalid_task_dict.pop("title")
    invalid_task_dict["_id"] = "temp_id"
    dict_for_invalid_call = invalid_task_dict.copy()
    dict_for_invalid_call.pop('_id', None)

    valid_task_dict = task_urgent_overdue.model_dump(mode='json')
    valid_task_dict["_id"] = "valid_id"
    dict_for_valid_call = valid_task_dict.copy()
    dict_for_valid_call.pop('_id', None)


    mock_cursor = AsyncMock()
    mock_cursor.__aiter__.return_value = [valid_task_dict, invalid_task_dict]
    mock_tasks_collection.find.return_value = mock_cursor

    mock_get_user = mocker.patch(
        "app.worker.user_crud.get_user_by_id",
        new_callable=AsyncMock,
        return_value=user_active_with_email
    )

    validation_error = ValidationError.from_exception_data(title="Task", line_errors=[{'type': 'missing', 'loc':('title',)}])
    mock_model_validate = mocker.patch(
        "app.worker.Task.model_validate",
        side_effect=[task_urgent_overdue, validation_error]
    )

    mock_send_email = mocker.patch("app.worker.send_urgent_task_notification", new_callable=AsyncMock)
    mock_logger_exception = mocker.patch("app.worker.logger.exception")

    ctx = {"db": mock_db}

    # ========================
    # --- Act ---
    # ========================
    await check_and_notify_urgent_tasks(ctx)

    # ========================
    # --- Assert ---
    # ========================
    mock_tasks_collection.find.assert_called_once()
    assert mock_get_user.call_count == 1
    mock_get_user.assert_called_with(mock_db, task_urgent_overdue.owner_id)
    assert mock_model_validate.call_count == 2 
    mock_send_email.assert_called_once() 
    mock_logger_exception.assert_called_once()
    log_message = mock_logger_exception.call_args[0][0]
    assert f"Erro ao processar tarefa urgente (ID no dict: {invalid_task_dict.get('id')})" in log_message
    assert str(validation_error) in log_message

@pytest.mark.asyncio
async def test_startup_generic_exception(mocker): 
    """
    Testa o tratamento de erro no startup do worker quando
    connect_to_mongo lança uma exceção genérica.
    """
    # ========================
    # --- Arrange ---
    # ========================
    simulated_connect_error = Exception("Erro genérico na conexão inicial")
    mock_connect = mocker.patch("app.worker.connect_to_mongo", side_effect=simulated_connect_error)
    mock_logger_error = mocker.patch("app.worker.logger.error")
    ctx = {}

    # ========================
    # --- Act & Assert ---
    # ========================
    with pytest.raises(Exception, match="Erro genérico na conexão inicial"):
        await app.worker.startup(ctx)

    mock_connect.assert_awaited_once()
    mock_logger_error.assert_not_called()
    assert ctx.get("db") is None

@pytest.mark.asyncio
async def test_worker_send_email_exception(mocker, user_active_with_email, task_urgent_score): 
    """
    Testa o tratamento de exceção genérica ao tentar enviar email no worker.
    """
    # ========================
    # --- Arrange ---
    # ========================
    mock_db = MagicMock()
    mock_tasks_collection = MagicMock()
    mock_users_collection = MagicMock()
    def db_getitem_side_effect(key):
        if key == "tasks": return mock_tasks_collection
        if key == "users": return mock_users_collection
        raise KeyError(key)
    mock_db.__getitem__.side_effect = db_getitem_side_effect
    urgent_task_dict = task_urgent_score.model_dump(mode='json')
    urgent_task_dict['_id'] = "task_email_exc_id"
    mock_cursor = AsyncMock()
    mock_cursor.__aiter__.return_value = [urgent_task_dict]
    mock_tasks_collection.find.return_value = mock_cursor
    mock_get_user = mocker.patch(
        "app.worker.user_crud.get_user_by_id",
        new_callable=AsyncMock,
        return_value=user_active_with_email
    )
    mocker.patch("app.worker.Task.model_validate", return_value=task_urgent_score)
    simulated_email_error = Exception("Erro simulado no envio de email")
    mock_send_email = mocker.patch(
        "app.worker.send_urgent_task_notification",
        new_callable=AsyncMock,
        side_effect=simulated_email_error
    )
    mock_logger_exception = mocker.patch("app.worker.logger.exception")
    ctx = {"db": mock_db}

    # ========================
    # --- Act ---
    # ========================
    await check_and_notify_urgent_tasks(ctx)

    # ========================
    # --- Assert ---
    # ========================
    mock_tasks_collection.find.assert_called_once()
    mock_get_user.assert_called_once_with(mock_db, task_urgent_score.owner_id)
    mock_send_email.assert_called_once()
    mock_logger_exception.assert_called_once()
    log_message = mock_logger_exception.call_args.args[0]
    assert f"Erro ao processar tarefa urgente (ID no dict: {task_urgent_score.id})" in log_message
    assert str(simulated_email_error) in log_message

def test_worker_settings_no_redis_url(mocker): 
    """
    Testa se WorkerSettings levanta ValueError quando settings.REDIS_URL é None.
    """
    # ========================
    # --- Arrange ---
    # ========================
    mocker.patch("app.worker.settings.REDIS_URL", None)
    mock_logger_error = mocker.patch("app.worker.logger.error")

    # ========================
    # --- Act & Assert ---
    # ========================
    with pytest.raises(ValueError) as excinfo:
        reload(app.worker)

    assert "REDIS_URL não está definida nas configurações" in str(excinfo.value)
    mock_logger_error.assert_called_with("Configuração crítica ausente: REDIS_URL não está definida. Worker ARQ não pode iniciar.")

# =============================================================
# --- Testes para a função `shutdown` ---
# =============================================================

@pytest.mark.asyncio
async def test_shutdown_with_db(mocker): 
    """Testa a função shutdown quando existe conexão DB no contexto."""
    # ========================
    # --- Arrange ---
    # ========================
    mock_close_conn = mocker.patch("app.worker.close_mongo_connection", new_callable=AsyncMock)
    mock_logger_info = mocker.patch("app.worker.logger.info")
    mock_db = MagicMock() 
    ctx = {"db": mock_db}

    # ========================
    # --- Act ---
    # ========================
    await app.worker.shutdown(ctx) 

    # ========================
    # --- Assert ---
    # ========================
    mock_logger_info.assert_any_call("Worker ARQ: Iniciando rotinas de shutdown...")
    mock_close_conn.assert_awaited_once()
    mock_logger_info.assert_any_call("Worker ARQ: Conexão com MongoDB fechada.")

@pytest.mark.asyncio
async def test_shutdown_without_db(mocker): 
    """Testa a função shutdown quando não existe conexão DB no contexto."""
    # ========================
    # --- Arrange ---
    # ========================
    mock_close_conn = mocker.patch("app.worker.close_mongo_connection", new_callable=AsyncMock)
    mock_logger_info = mocker.patch("app.worker.logger.info")
    ctx = {"db": None} 

    # ========================
    # --- Act ---
    # ========================
    await app.worker.shutdown(ctx)

    # ========================
    # --- Assert ---
    # ========================
    mock_logger_info.assert_any_call("Worker ARQ: Iniciando rotinas de shutdown...")
    mock_close_conn.assert_not_called()
    mock_logger_info.assert_any_call("Worker ARQ: Nenhuma conexão com MongoDB para fechar (não estava disponível ou já fechada).")

# =============================================================
# --- Testes para a StartUp ---
# =============================================================
@pytest.mark.asyncio
async def test_startup_success(mocker): 
    """
    Testa o caminho de sucesso da função startup.
    """
    # ========================
    # --- Arrange ---
    # ========================
    mock_db_connection = MagicMock()
    mock_connect = mocker.patch("app.worker.connect_to_mongo", return_value=mock_db_connection)
    mock_logger_info = mocker.patch("app.worker.logger.info")
    mock_logger_error = mocker.patch("app.worker.logger.error") 
    ctx = {} 

    # ========================
    # --- Act ---
    # ========================
    await app.worker.startup(ctx)

    # ========================
    # --- Assert ---
    # ========================
    mock_connect.assert_awaited_once()
    assert ctx.get("db") == mock_db_connection 
    mock_logger_info.assert_any_call("Worker ARQ: Iniciando rotinas de startup...")
    mock_logger_info.assert_any_call("Worker ARQ: Conexão com MongoDB estabelecida e armazenada no contexto.")
    mock_logger_error.assert_not_called()

@pytest.mark.asyncio
async def test_startup_connect_returns_none(mocker): 
    """
    Testa o caminho de falha da função startup quando connect_to_mongo retorna None.
    """
    # ========================
    # --- Arrange ---
    # ========================
    mock_connect = mocker.patch("app.worker.connect_to_mongo", return_value=None) 
    mock_logger_info = mocker.patch("app.worker.logger.info")
    mock_logger_error = mocker.patch("app.worker.logger.error")
    ctx = {}

    # ========================
    # --- Act ---
    # ========================
    await app.worker.startup(ctx)

    # ========================
    # --- Assert ---
    # ========================
    mock_connect.assert_awaited_once()
    assert ctx.get("db") is None 
    mock_logger_info.assert_called_once_with("Worker ARQ: Iniciando rotinas de startup...") 
    mock_logger_error.assert_called_once_with(
        "Worker ARQ: Falha crítica ao conectar ao MongoDB durante o startup. "
        "A conexão não estará disponível para as tarefas."
    )