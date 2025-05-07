# tests/test_worker.py
"""
Este módulo contém testes unitários para a tarefa ARQ (`check_and_notify_urgent_tasks`)
definida em `app.worker.py`. A tarefa é responsável por verificar periodicamente
tarefas urgentes e notificar os usuários.

Os testes utilizam mocks para simular dependências externas como o banco de dados
e o sistema de envio de e-mails, focando na lógica interna da função do worker.
"""
# ========================
# --- Importações ---
# ========================
import pytest
import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, call 

# --- Módulos da Aplicação ---
from app.worker import check_and_notify_urgent_tasks 
from app.models.task import Task, TaskStatus
from app.models.user import UserInDB
from app.core.config import settings

# ====================================
# --- Marcador Global de Teste ---
# ====================================

pytestmark = pytest.mark.asyncio

# =================================================================
# --- Fixtures de Dados de Teste para Usuários e Tarefas ---
# =================================================================

user_active_with_email = UserInDB(
    id=uuid.uuid4(),
    username="testworkeruser",
    email="worker@example.com",
    full_name="Worker Test User",
    hashed_password="fakehash",
    disabled=False,
    created_at=datetime.now(timezone.utc)
)

user_disabled = UserInDB(
    id=uuid.uuid4(),
    username="disableduser",
    email="disabled@example.com",
    full_name="Disabled User",
    hashed_password="fakehash",
    disabled=True,
    created_at=datetime.now(timezone.utc)
)

task_urgent_score = Task(
    id=uuid.uuid4(),
    owner_id=user_active_with_email.id, 
    title="Urgent High Score Task",
    importance=5,
    status=TaskStatus.PENDING,
    created_at=datetime.now(timezone.utc) - timedelta(days=1),
    priority_score=settings.EMAIL_URGENCY_THRESHOLD + 50.0, 
    due_date=date.today() + timedelta(days=10) 
)

task_urgent_overdue = Task(
    id=uuid.uuid4(),
    owner_id=user_active_with_email.id, 
    title="Urgent Overdue Task",
    importance=1,
    status=TaskStatus.PENDING,
    created_at=datetime.now(timezone.utc) - timedelta(days=5),
    priority_score=10.0, 
    due_date=date.today() - timedelta(days=1) 
)

task_urgent_due_today = Task(
    id=uuid.uuid4(),
    owner_id=user_active_with_email.id, 
    title="Urgent Due Today Task",
    importance=2,
    status=TaskStatus.IN_PROGRESS,
    created_at=datetime.now(timezone.utc) - timedelta(days=2),
    priority_score=20.0, 
    due_date=date.today() 
)

task_not_urgent = Task(
    id=uuid.uuid4(),
    owner_id=user_active_with_email.id, 
    title="Not Urgent Task",
    importance=3,
    status=TaskStatus.PENDING,
    created_at=datetime.now(timezone.utc),
    priority_score=settings.EMAIL_URGENCY_THRESHOLD - 10.0, 
    due_date=date.today() + timedelta(days=5) 
)

task_completed = Task(
    id=uuid.uuid4(),
    owner_id=user_active_with_email.id,
    title="Completed Urgent Task",
    importance=5,
    status=TaskStatus.COMPLETED, 
    created_at=datetime.now(timezone.utc) - timedelta(days=10),
    priority_score=settings.EMAIL_URGENCY_THRESHOLD + 100.0, 
    due_date=date.today() - timedelta(days=2) 
)

task_disabled_user = Task( 
    id=uuid.uuid4(),
    owner_id=user_disabled.id, 
    title="Disabled User Urgent Task",
    importance=5,
    status=TaskStatus.PENDING,
    created_at=datetime.now(timezone.utc),
    priority_score=settings.EMAIL_URGENCY_THRESHOLD + 50.0 
)

# =============================================================
# --- Testes para a função `check_and_notify_urgent_tasks` ---
# =============================================================

async def test_worker_no_urgent_tasks(mocker):
    """
    Testa o comportamento da função do worker ARQ (`check_and_notify_urgent_tasks`)
    quando o banco de dados simulado não retorna nenhuma tarefa que atenda aos
    critérios de urgência.
    Espera-se que nenhuma notificação por e-mail seja enviada.
    """
    mock_db = MagicMock()
    mock_tasks_collection = MagicMock()
    mock_db.__getitem__.return_value = mock_tasks_collection 

    mock_cursor = AsyncMock()
    mock_cursor.__aiter__.return_value = [] 
    mock_tasks_collection.find.return_value = mock_cursor

    mock_get_user = mocker.patch("app.worker.user_crud.get_user_by_id", new_callable=AsyncMock)
    mock_send_email = mocker.patch("app.worker.send_urgent_task_notification", new_callable=AsyncMock)

    ctx = {"db": mock_db}
    await check_and_notify_urgent_tasks(ctx)

    mock_tasks_collection.find.assert_called_once() 
    mock_get_user.assert_not_called()
    mock_send_email.assert_not_called() 

async def test_worker_one_urgent_task_active_user(mocker):
    """
    Testa o cenário onde o worker encontra uma tarefa urgente que pertence
    a um usuário ativo e com e-mail.
    Espera-se que uma notificação por e-mail seja enviada para este usuário.
    """
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
    await check_and_notify_urgent_tasks(ctx)

    mock_tasks_collection.find.assert_called_once()
    mock_get_user.assert_called_once_with(mock_db, task_urgent_score.owner_id) 
    mock_send_email.assert_called_once() 

    call_args = mock_send_email.call_args.kwargs
    assert call_args['user_email'] == user_active_with_email.email
    assert call_args['user_name'] == user_active_with_email.full_name
    assert call_args['task_title'] == task_urgent_score.title
    assert call_args['task_id'] == str(task_urgent_score.id)

async def test_worker_mix_urgent_non_urgent_completed(mocker):
    """
    Testa o worker com uma mistura de tarefas: uma não urgente, uma que é
    efetivamente urgente (atrasada), e uma tarefa concluída (que não deve
    ser processada mesmo se os critérios de urgência batessem).
    Apenas a tarefa urgente e não concluída deve gerar uma notificação.
    """
    mock_db = MagicMock()
    mock_tasks_collection = MagicMock()
    mock_users_collection = MagicMock()
    def db_getitem_side_effect(key):
        if key == "tasks": return mock_tasks_collection
        if key == "users": return mock_users_collection
        raise KeyError(key)
    mock_db.__getitem__.side_effect = db_getitem_side_effect

    tasks_in_db = [ 
        task_not_urgent.model_dump(mode='json'),
        task_urgent_overdue.model_dump(mode='json'), 
        task_completed.model_dump(mode='json'),
    ]
    mock_cursor = AsyncMock()
    filtered_tasks = [task_urgent_overdue.model_dump(mode='json')] 
    mock_cursor.__aiter__.return_value = filtered_tasks
    mock_tasks_collection.find.return_value = mock_cursor

    mock_get_user = mocker.patch(
        "app.worker.user_crud.get_user_by_id",
        new_callable=AsyncMock,
        return_value=user_active_with_email
    )
    mock_send_email = mocker.patch("app.worker.send_urgent_task_notification", new_callable=AsyncMock)

    ctx = {"db": mock_db}
    await check_and_notify_urgent_tasks(ctx)

    mock_tasks_collection.find.assert_called_once() 
    mock_get_user.assert_called_once_with(mock_db, task_urgent_overdue.owner_id)
    mock_send_email.assert_called_once()
    call_args = mock_send_email.call_args.kwargs
    assert call_args['task_title'] == task_urgent_overdue.title 


async def test_worker_urgent_task_disabled_user(mocker):
    """
    Testa que, mesmo que uma tarefa seja urgente, nenhuma notificação é enviada
    se o usuário proprietário da tarefa estiver desativado.
    """
    mock_db = MagicMock()
    mock_tasks_collection = MagicMock()
    mock_users_collection = MagicMock()
    def db_getitem_side_effect(key):
        if key == "tasks": return mock_tasks_collection
        if key == "users": return mock_users_collection
        raise KeyError(key)
    mock_db.__getitem__.side_effect = db_getitem_side_effect

    mock_cursor = AsyncMock()
    mock_cursor.__aiter__.return_value = [task_disabled_user.model_dump(mode='json')] # Nome da var da tarefa corrigido no corpo do teste.
    mock_tasks_collection.find.return_value = mock_cursor

    mock_get_user = mocker.patch(
        "app.worker.user_crud.get_user_by_id",
        new_callable=AsyncMock,
        return_value=user_disabled 
    )
    mock_send_email = mocker.patch("app.worker.send_urgent_task_notification", new_callable=AsyncMock)

    ctx = {"db": mock_db}
    await check_and_notify_urgent_tasks(ctx)

    mock_tasks_collection.find.assert_called_once()
    mock_get_user.assert_called_once_with(mock_db, user_disabled.id)
    mock_send_email.assert_not_called() 


async def test_worker_multiple_urgent_tasks(mocker):
    """
    Testa o cenário com múltiplas tarefas urgentes para usuários ativos.
    Verifica se o worker processa cada uma e envia as notificações correspondentes.
    """
    mock_db = MagicMock()
    mock_tasks_collection = MagicMock()
    mock_users_collection = MagicMock()
    def db_getitem_side_effect(key):
        if key == "tasks": return mock_tasks_collection
        if key == "users": return mock_users_collection
        raise KeyError(key)
    mock_db.__getitem__.side_effect = db_getitem_side_effect

    urgent_tasks_list = [
        task_urgent_score.model_dump(mode='json'),
        task_urgent_overdue.model_dump(mode='json'),
        task_urgent_due_today.model_dump(mode='json')
    ]
    mock_cursor = AsyncMock()
    mock_cursor.__aiter__.return_value = urgent_tasks_list
    mock_tasks_collection.find.return_value = mock_cursor

    mock_get_user = mocker.patch(
        "app.worker.user_crud.get_user_by_id",
        new_callable=AsyncMock,
        return_value=user_active_with_email
    )
    mock_send_email = mocker.patch("app.worker.send_urgent_task_notification", new_callable=AsyncMock)

    ctx = {"db": mock_db}
    await check_and_notify_urgent_tasks(ctx)

    assert mock_tasks_collection.find.call_count == 1
    assert mock_get_user.call_count == len(urgent_tasks_list)
    assert mock_send_email.call_count == len(urgent_tasks_list)

    expected_call_args_score = {
        'user_email': user_active_with_email.email,
        'user_name': user_active_with_email.full_name,
        'task_title': task_urgent_score.title,
        'task_id': str(task_urgent_score.id),
        'task_due_date': str(task_urgent_score.due_date),
        'priority_score': task_urgent_score.priority_score
    }
    mock_send_email.assert_any_call(**expected_call_args_score)


async def test_worker_db_unavailable(mocker):
    """
    Testa o comportamento do worker (`check_and_notify_urgent_tasks`)
    quando o objeto `db` não está presente no contexto `ctx` (simulando
    uma falha na inicialização do worker ARQ onde a conexão com o DB não
    foi estabelecida).
    Espera-se que um erro seja logado e nenhuma outra ação seja tomada.
    """
    mock_send_email = mocker.patch("app.worker.send_urgent_task_notification", new_callable=AsyncMock)
    mock_logger = mocker.patch("app.worker.logger")

    ctx = {}
    await check_and_notify_urgent_tasks(ctx)

    mock_send_email.assert_not_called()
    mock_logger.error.assert_called_once_with(
        "Conexão com o banco de dados não disponível no contexto ARQ."
    )