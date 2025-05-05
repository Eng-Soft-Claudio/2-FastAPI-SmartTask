# tests/test_worker.py

import pytest
import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, call 
import logging
from app.worker import check_and_notify_urgent_tasks 
from app.models.task import Task, TaskStatus
from app.models.user import UserInDB
from app.core.config import settings

pytestmark = pytest.mark.asyncio

# === Fixtures de Dados de Teste ===

# Usuário ativo com e-mail
user_active_with_email = UserInDB(
    id=uuid.uuid4(),
    username="testworkeruser",
    email="worker@example.com",
    full_name="Worker Test User",
    hashed_password="fakehash",
    disabled=False,
    created_at=datetime.now(timezone.utc)
)

# Usuário desativado
user_disabled = UserInDB(
    id=uuid.uuid4(),
    username="disableduser",
    email="disabled@example.com",
    full_name="Disabled User",
    hashed_password="fakehash",
    disabled=True,
    created_at=datetime.now(timezone.utc)
)

# Tarefa Urgente por Score Alto
task_urgent_score = Task(
    id=uuid.uuid4(),
    owner_id=user_active_with_email.id, # Pertence ao usuário ativo
    title="Urgent High Score Task",
    importance=5,
    status=TaskStatus.PENDING,
    created_at=datetime.now(timezone.utc) - timedelta(days=1),
    priority_score=settings.EMAIL_URGENCY_THRESHOLD + 50.0, # Score acima do limiar
    due_date=date.today() + timedelta(days=10) # Prazo futuro (urgente pelo score)
)

# Tarefa Urgente por Prazo Atrasado (mesmo com score baixo)
task_urgent_overdue = Task(
    id=uuid.uuid4(),
    owner_id=user_active_with_email.id, # Pertence ao usuário ativo
    title="Urgent Overdue Task",
    importance=1,
    status=TaskStatus.PENDING,
    created_at=datetime.now(timezone.utc) - timedelta(days=5),
    priority_score=10.0, # Score abaixo do limiar
    due_date=date.today() - timedelta(days=1) # Atrasada
)

# Tarefa Urgente por Prazo Hoje (mesmo com score baixo)
task_urgent_due_today = Task(
    id=uuid.uuid4(),
    owner_id=user_active_with_email.id, # Pertence ao usuário ativo
    title="Urgent Due Today Task",
    importance=2,
    status=TaskStatus.IN_PROGRESS,
    created_at=datetime.now(timezone.utc) - timedelta(days=2),
    priority_score=20.0, # Score abaixo do limiar
    due_date=date.today() # Vence hoje
)

# Tarefa NÃO Urgente
task_not_urgent = Task(
    id=uuid.uuid4(),
    owner_id=user_active_with_email.id, # Pertence ao usuário ativo
    title="Not Urgent Task",
    importance=3,
    status=TaskStatus.PENDING,
    created_at=datetime.now(timezone.utc),
    priority_score=settings.EMAIL_URGENCY_THRESHOLD - 10.0, # Score baixo
    due_date=date.today() + timedelta(days=5) # Prazo futuro
)

# Tarefa Concluída (não deve ser notificada)
task_completed = Task(
    id=uuid.uuid4(),
    owner_id=user_active_with_email.id,
    title="Completed Urgent Task",
    importance=5,
    status=TaskStatus.COMPLETED, # Concluída
    created_at=datetime.now(timezone.utc) - timedelta(days=10),
    priority_score=settings.EMAIL_URGENCY_THRESHOLD + 100.0, # Score alto
    due_date=date.today() - timedelta(days=2) # Atrasada
)

# Tarefa pertencente a usuário desativado
task_disabled_user = Task(
    id=uuid.uuid4(),
    owner_id=user_disabled.id, # Usuário desativado
    title="Disabled User Urgent Task",
    importance=5,
    status=TaskStatus.PENDING,
    created_at=datetime.now(timezone.utc),
    priority_score=settings.EMAIL_URGENCY_THRESHOLD + 50.0 # Score alto
)

# === Testes da Função check_and_notify_urgent_tasks ===

async def test_worker_no_urgent_tasks(mocker):
    """Testa o worker quando não há tarefas urgentes no 'banco'."""
    # Mock DB e Collections
    mock_db = MagicMock()
    mock_tasks_collection = MagicMock()
    mock_db.__getitem__.return_value = mock_tasks_collection 

    # Configura o 'find' para retornar um cursor assíncrono vazio
    mock_cursor = AsyncMock()
    mock_cursor.__aiter__.return_value = [] 
    mock_tasks_collection.find.return_value = mock_cursor

    # Mock get_user_by_id (não deve ser chamado se não houver tarefas)
    mock_get_user = mocker.patch("app.worker.user_crud.get_user_by_id", new_callable=AsyncMock)

    # Mock da função de envio de email (não deve ser chamada)
    mock_send_email = mocker.patch("app.worker.send_urgent_task_notification", new_callable=AsyncMock)

    # Chama a função do worker com o contexto mockado
    ctx = {"db": mock_db}
    await check_and_notify_urgent_tasks(ctx)

    # Asserções
    mock_tasks_collection.find.assert_called_once() 
    mock_get_user.assert_not_called()
    mock_send_email.assert_not_called() 


async def test_worker_one_urgent_task_active_user(mocker):
    """Testa o worker com uma tarefa urgente e usuário ativo."""
    mock_db = MagicMock()
    mock_tasks_collection = MagicMock()
    mock_users_collection = MagicMock() 

    # Fazer db["tasks"] retornar tasks_collection, db["users"] retornar users_collection
    def db_getitem_side_effect(key):
        if key == "tasks": return mock_tasks_collection
        if key == "users": return mock_users_collection
        raise KeyError(key)
    mock_db.__getitem__.side_effect = db_getitem_side_effect

    # Configura 'find' para retornar um cursor com uma tarefa urgente (convertida pra dict)
    task_dict = task_urgent_score.model_dump(mode='json')
    mock_cursor = AsyncMock()
    mock_cursor.__aiter__.return_value = [task_dict]
    mock_tasks_collection.find.return_value = mock_cursor

    # Mock get_user_by_id para retornar o usuário ativo
    mock_get_user = mocker.patch(
        "app.worker.user_crud.get_user_by_id",
        new_callable=AsyncMock,
        return_value=user_active_with_email 
    )

    # Mock da função de envio de email
    mock_send_email = mocker.patch("app.worker.send_urgent_task_notification", new_callable=AsyncMock)

    # Chama a função do worker
    ctx = {"db": mock_db}
    await check_and_notify_urgent_tasks(ctx)

    # Asserções
    mock_tasks_collection.find.assert_called_once()
    mock_get_user.assert_called_once_with(mock_db, task_urgent_score.owner_id) 
    mock_send_email.assert_called_once() 

    # Verificar argumentos do email (opcional, mas bom)
    call_args = mock_send_email.call_args.kwargs
    assert call_args['user_email'] == user_active_with_email.email
    assert call_args['user_name'] == user_active_with_email.full_name
    assert call_args['task_title'] == task_urgent_score.title
    assert call_args['task_id'] == str(task_urgent_score.id)


async def test_worker_mix_urgent_non_urgent_completed(mocker):
    """Testa com mistura de tarefas (urgente, não urgente, concluída)."""
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

    # Mock get_user_by_id
    mock_get_user = mocker.patch(
        "app.worker.user_crud.get_user_by_id",
        new_callable=AsyncMock,
        return_value=user_active_with_email
    )

    # Mock do email
    mock_send_email = mocker.patch("app.worker.send_urgent_task_notification", new_callable=AsyncMock)

    # Chama o worker
    ctx = {"db": mock_db}
    await check_and_notify_urgent_tasks(ctx)

    # Asserções
    mock_tasks_collection.find.assert_called_once() 
    # get_user foi chamado APENAS para a tarefa que a query retornou (urgent_overdue)
    mock_get_user.assert_called_once_with(mock_db, task_urgent_overdue.owner_id)
    # send_email foi chamado APENAS uma vez (para a tarefa urgente)
    mock_send_email.assert_called_once()
    call_args = mock_send_email.call_args.kwargs
    assert call_args['task_title'] == task_urgent_overdue.title


async def test_worker_urgent_task_disabled_user(mocker):
    """Testa que email não é enviado para tarefa urgente de usuário desativado."""
    mock_db = MagicMock()
    mock_tasks_collection = MagicMock()
    mock_users_collection = MagicMock()
    def db_getitem_side_effect(key):
        if key == "tasks": return mock_tasks_collection
        if key == "users": return mock_users_collection
        raise KeyError(key)
    mock_db.__getitem__.side_effect = db_getitem_side_effect

    # Cursor com a tarefa do usuário desativado
    mock_cursor = AsyncMock()
    mock_cursor.__aiter__.return_value = [task_disabled_user.model_dump(mode='json')]
    mock_tasks_collection.find.return_value = mock_cursor

    # Mock get_user_by_id para retornar o usuário desativado
    mock_get_user = mocker.patch(
        "app.worker.user_crud.get_user_by_id",
        new_callable=AsyncMock,
        return_value=user_disabled
    )

    # Mock do email (NÃO deve ser chamado)
    mock_send_email = mocker.patch("app.worker.send_urgent_task_notification", new_callable=AsyncMock)

    # Chama o worker
    ctx = {"db": mock_db}
    await check_and_notify_urgent_tasks(ctx)

    # Asserções
    mock_tasks_collection.find.assert_called_once()
    mock_get_user.assert_called_once_with(mock_db, user_disabled.id)
    mock_send_email.assert_not_called() 


async def test_worker_multiple_urgent_tasks(mocker):
    """Testa o envio de múltiplas notificações."""
    mock_db = MagicMock()
    mock_tasks_collection = MagicMock()
    mock_users_collection = MagicMock()
    def db_getitem_side_effect(key):
        if key == "tasks": return mock_tasks_collection
        if key == "users": return mock_users_collection
        raise KeyError(key)
    mock_db.__getitem__.side_effect = db_getitem_side_effect

    # Cursor com múltiplas tarefas urgentes
    urgent_tasks_list = [
        task_urgent_score.model_dump(mode='json'),
        task_urgent_overdue.model_dump(mode='json'),
        task_urgent_due_today.model_dump(mode='json')
    ]
    mock_cursor = AsyncMock()
    mock_cursor.__aiter__.return_value = urgent_tasks_list
    mock_tasks_collection.find.return_value = mock_cursor

    # Mock get_user_by_id para sempre retornar o usuário ativo
    mock_get_user = mocker.patch(
        "app.worker.user_crud.get_user_by_id",
        new_callable=AsyncMock,
        return_value=user_active_with_email
    )

    # Mock do email
    mock_send_email = mocker.patch("app.worker.send_urgent_task_notification", new_callable=AsyncMock)

    # Chama o worker
    ctx = {"db": mock_db}
    await check_and_notify_urgent_tasks(ctx)

    # Asserções
    assert mock_tasks_collection.find.call_count == 1
    # Verifica se get_user foi chamado para cada tarefa urgente
    assert mock_get_user.call_count == len(urgent_tasks_list)
    # Verifica se send_email foi chamado para cada tarefa urgente
    assert mock_send_email.call_count == len(urgent_tasks_list)

    # Verifica a chamada para a primeira tarefa
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
    Testa o comportamento do worker se o DB não estiver no contexto
    e verifica se o erro é logado.
    """    # Mock para envio de email (não deve ser chamado)
    mock_send_email = mocker.patch("app.worker.send_urgent_task_notification", new_callable=AsyncMock)

    # Cria o mock do log
    mock_logger = mocker.patch("app.worker.logger")

    # Chama a função do worker com contexto VAZIO
    ctx = {}
    # Remover o with caplog:
    await check_and_notify_urgent_tasks(ctx)

    # Verifica que a função de email não foi chamada
    mock_send_email.assert_not_called()

    # <<< ADIÇÃO (Opcional): Verificar se o logger mockado foi chamado >>>
    # Isso substitui a verificação do texto no caplog
    mock_logger.error.assert_called_once_with(
        "Conexão com o banco de dados não disponível no contexto ARQ."
    )