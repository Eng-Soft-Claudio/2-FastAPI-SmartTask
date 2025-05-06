# tests/test_db_task_crud.py

import pytest
import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch # Para mocks
from typing import List, Optional, Dict, Any

# Importar pymongo e pydantic Error para simular falhas
from pymongo import ASCENDING, DESCENDING # Usado para verificar sort
from pydantic import ValidationError

# Importar o módulo a ser testado e seus modelos
from app.db import task_crud
from app.models.task import Task, TaskStatus # Usar o modelo final para fixtures

# --- Fixture de Dados de Teste (Mantida) ---
@pytest.fixture
def valid_task_obj() -> Task:
    owner_id = uuid.uuid4()
    return Task(
        id=uuid.uuid4(),
        owner_id=owner_id,
        title="Test Task Title",
        description="Test task description.",
        importance=3,
        status=TaskStatus.PENDING,
        created_at=datetime.now(timezone.utc),
    )

# --- Testes para create_task ---

@pytest.mark.asyncio
async def test_create_task_success(valid_task_obj):
    """Testa a criação bem-sucedida de uma tarefa."""
    mock_collection = AsyncMock() # Mock síncrono da coleção
    mock_insert_result = MagicMock()
    mock_insert_result.acknowledged = True
    mock_collection.insert_one = AsyncMock(return_value=mock_insert_result) # Mock async do método

    with patch("app.db.task_crud._get_tasks_collection", return_value=mock_collection):
        created_task = await task_crud.create_task(db=MagicMock(), task_db=valid_task_obj) # db mockado simples

    expected_dict = valid_task_obj.model_dump(mode='json')
    mock_collection.insert_one.assert_awaited_once_with(expected_dict)
    assert created_task == valid_task_obj

@pytest.mark.asyncio
async def test_create_task_db_not_acknowledged(valid_task_obj):
    """Testa o que acontece se insert_one não for Acknowledged."""
    mock_collection = AsyncMock()
    mock_insert_result = MagicMock()
    mock_insert_result.acknowledged = False
    mock_collection.insert_one = AsyncMock(return_value=mock_insert_result)

    with patch("app.db.task_crud._get_tasks_collection", return_value=mock_collection):
        created_task = await task_crud.create_task(db=MagicMock(), task_db=valid_task_obj)

    mock_collection.insert_one.assert_awaited_once()
    assert created_task is None

@pytest.mark.asyncio
async def test_create_task_db_exception(valid_task_obj, mocker):
    """Testa o tratamento de exceção durante a inserção no DB."""
    mock_collection = AsyncMock()
    db_error = Exception("Simulated DB Error")
    mock_collection.insert_one = AsyncMock(side_effect=db_error) # Mock com side_effect
    mock_logger = mocker.patch("app.db.task_crud.logger")

    with patch("app.db.task_crud._get_tasks_collection", return_value=mock_collection):
        created_task = await task_crud.create_task(db=MagicMock(), task_db=valid_task_obj)

    mock_collection.insert_one.assert_awaited_once()
    assert created_task is None
    mock_logger.exception.assert_called_once()

# --- Testes para get_task_by_id ---

@pytest.mark.asyncio
async def test_get_task_by_id_success(valid_task_obj):
    """Testa a busca bem-sucedida por ID."""
    mock_collection = MagicMock()
    task_dict_from_db = valid_task_obj.model_dump(mode='json')
    task_dict_from_db['_id'] = "some_mongo_id"
    mock_collection.find_one = AsyncMock(return_value=task_dict_from_db) # Mock async

    owner_id = valid_task_obj.owner_id
    task_id = valid_task_obj.id

    with patch("app.db.task_crud._get_tasks_collection", return_value=mock_collection):
        with patch("app.db.task_crud.Task.model_validate", return_value=valid_task_obj) as mock_validate:
            found_task = await task_crud.get_task_by_id(db=MagicMock(), task_id=task_id, owner_id=owner_id)

    expected_query = {"id": str(task_id), "owner_id": str(owner_id)}
    mock_collection.find_one.assert_awaited_once_with(expected_query)
    # Verifica se a validação foi chamada com o dicionário SEM o _id
    expected_validate_dict = task_dict_from_db.copy()
    expected_validate_dict.pop('_id', None)
    mock_validate.assert_called_once_with(expected_validate_dict)
    assert found_task == valid_task_obj

@pytest.mark.asyncio
async def test_get_task_by_id_not_found():
    """Testa quando a tarefa não é encontrada no DB."""
    mock_collection = MagicMock()
    mock_collection.find_one = AsyncMock(return_value=None) # Mock async

    task_id = uuid.uuid4()
    owner_id = uuid.uuid4()

    with patch("app.db.task_crud._get_tasks_collection", return_value=mock_collection):
        found_task = await task_crud.get_task_by_id(db=MagicMock(), task_id=task_id, owner_id=owner_id)

    mock_collection.find_one.assert_awaited_once()
    assert found_task is None

@pytest.mark.asyncio
async def test_get_task_by_id_validation_error(mocker):
    """Testa quando os dados do DB falham na validação Pydantic."""
    mock_collection = MagicMock()
    invalid_task_dict = {"id": str(uuid.uuid4()), "owner_id": str(uuid.uuid4()), "title": "Invalid Task"}
    mock_collection.find_one = AsyncMock(return_value=invalid_task_dict)
    mock_logger = mocker.patch("app.db.task_crud.logger")

    task_id = uuid.UUID(invalid_task_dict["id"])
    owner_id = uuid.UUID(invalid_task_dict["owner_id"])

    validation_error = ValidationError.from_exception_data(title='Task', line_errors=[])
    with patch("app.db.task_crud._get_tasks_collection", return_value=mock_collection):
        with patch("app.db.task_crud.Task.model_validate", side_effect=validation_error):
            found_task = await task_crud.get_task_by_id(db=MagicMock(), task_id=task_id, owner_id=owner_id)

    mock_collection.find_one.assert_awaited_once()
    assert found_task is None
    mock_logger.error.assert_called_once()

# --- Testes para get_tasks_by_owner ---

@pytest.mark.asyncio
async def test_get_tasks_by_owner_success_no_filters(valid_task_obj):
    """Testa a listagem básica (mock simplificado)."""
    owner_id = valid_task_obj.owner_id
    task_dict = valid_task_obj.model_dump(mode='json')

    # Mock para o cursor final que será iterado
    mock_cursor = AsyncMock()
    mock_cursor.__aiter__.return_value = [task_dict]

    # Mock para o objeto chainable que find retorna
    mock_chain = MagicMock()
    mock_chain.skip.return_value = mock_chain # Retorna a si mesmo
    mock_chain.limit.return_value = mock_cursor # O último método retorna o cursor iterável

    # Mock para a coleção que retorna o objeto chainable
    mock_collection = MagicMock()
    mock_collection.find.return_value = mock_chain # find retorna o obj chainable

    with patch("app.db.task_crud._get_tasks_collection", return_value=mock_collection):
        with patch("app.db.task_crud.Task.model_validate", return_value=valid_task_obj):
            tasks = await task_crud.get_tasks_by_owner(db=MagicMock(), owner_id=owner_id, limit=50, skip=10)

    expected_query = {"owner_id": str(owner_id)}
    mock_collection.find.assert_called_once_with(expected_query)
    mock_chain.skip.assert_called_once_with(10)
    mock_chain.limit.assert_called_once_with(50)
    assert len(tasks) == 1
    assert tasks[0] == valid_task_obj

@pytest.mark.asyncio
async def test_get_tasks_by_owner_with_filters_and_sort(valid_task_obj):
    """Testa listagem com filtros e sort (mock simplificado)."""
    owner_id = valid_task_obj.owner_id
    task_dict = valid_task_obj.model_dump(mode='json')

    mock_cursor = AsyncMock()
    mock_cursor.__aiter__.return_value = [task_dict]
    mock_sort_chain = MagicMock()
    mock_sort_chain.sort.return_value = mock_cursor # sort retorna cursor final
    mock_limit_chain = MagicMock()
    mock_limit_chain.limit.return_value = mock_sort_chain # limit retorna obj com sort
    mock_skip_chain = MagicMock()
    mock_skip_chain.skip.return_value = mock_limit_chain # skip retorna obj com limit
    mock_collection = MagicMock()
    mock_collection.find.return_value = mock_skip_chain # find retorna obj com skip

    status_param = TaskStatus.PENDING
    project = "TestProject"
    sort_by = "created_at"
    sort_order = "asc"
    limit = 10
    skip = 5

    with patch("app.db.task_crud._get_tasks_collection", return_value=mock_collection):
        with patch("app.db.task_crud.Task.model_validate", return_value=valid_task_obj):
            tasks = await task_crud.get_tasks_by_owner(
                db=MagicMock(), owner_id=owner_id, status_filter=status_param,
                project_filter=project, sort_by=sort_by, sort_order=sort_order,
                limit=limit, skip=skip
            )

    expected_query = {"owner_id": str(owner_id), "status": status_param.value, "project": project}
    mock_collection.find.assert_called_once_with(expected_query)
    mock_skip_chain.skip.assert_called_once_with(skip)
    mock_limit_chain.limit.assert_called_once_with(limit)
    mock_sort_chain.sort.assert_called_once_with([(sort_by, ASCENDING)])
    assert len(tasks) == 1
    assert tasks[0] == valid_task_obj

@pytest.mark.asyncio
async def test_get_tasks_by_owner_validation_error_in_loop(valid_task_obj, mocker):
    """Testa erro de validação no loop (mock simplificado)."""
    owner_id = valid_task_obj.owner_id
    valid_dict = valid_task_obj.model_dump(mode='json')
    invalid_dict = {"id": str(uuid.uuid4()), "owner_id": str(owner_id), "_id": "id2"}

    mock_cursor = AsyncMock()
    mock_cursor.__aiter__.return_value = [valid_dict, invalid_dict] # <<<---- IMPORTANTE: Iterador retorna lista!
    mock_limit_chain = MagicMock()
    mock_limit_chain.limit.return_value = mock_cursor
    mock_skip_chain = MagicMock()
    mock_skip_chain.skip.return_value = mock_limit_chain
    mock_collection = MagicMock()
    mock_collection.find.return_value = mock_skip_chain
    mock_logger = mocker.patch("app.db.task_crud.logger")

    validation_error = ValidationError.from_exception_data(title='Task', line_errors=[])
    def validate_side_effect(data):
        if "title" in data and data["title"] == valid_task_obj.title: return valid_task_obj
        else: raise validation_error

    with patch("app.db.task_crud._get_tasks_collection", return_value=mock_collection):
        with patch("app.db.task_crud.Task.model_validate", side_effect=validate_side_effect) as mock_validate:
            tasks = await task_crud.get_tasks_by_owner(db=MagicMock(), owner_id=owner_id)

    mock_collection.find.assert_called_once()
    mock_skip_chain.skip.assert_called_once_with(0)
    mock_limit_chain.limit.assert_called_once_with(100)
    assert len(tasks) == 1
    assert tasks[0] == valid_task_obj
    assert mock_validate.call_count == 2
    mock_logger.error.assert_called_once()

@pytest.mark.asyncio
async def test_get_tasks_by_owner_db_exception(mocker):
    """Testa o tratamento de exceção do DB durante a busca."""
    mock_collection = MagicMock()
    owner_id = uuid.uuid4()
    db_error = Exception("Simulated Find Error")
    mock_collection.find.side_effect = db_error
    mock_logger = mocker.patch("app.db.task_crud.logger")

    with patch("app.db.task_crud._get_tasks_collection", return_value=mock_collection):
        tasks = await task_crud.get_tasks_by_owner(db=MagicMock(), owner_id=owner_id)

    assert tasks == []
    mock_logger.exception.assert_called_once()
    assert f"DB Error listing tasks for owner {owner_id}" in mock_logger.exception.call_args[0][0]

# --- Testes para update_task ---

@pytest.mark.asyncio
async def test_update_task_success(valid_task_obj):
    mock_collection = MagicMock()
    task_id = valid_task_obj.id
    owner_id = valid_task_obj.owner_id
    update_payload = {"title": "Updated Title"}

    # Precisa mockar datetime para controlar updated_at
    mock_now = datetime.now(timezone.utc)
    with patch("app.db.task_crud.datetime") as mock_dt:
        mock_dt.now.return_value = mock_now

        # O dicionário que esperamos que find_one_and_update retorne
        db_return_dict = valid_task_obj.model_dump(mode='json')
        db_return_dict.update(update_payload)
        db_return_dict['updated_at'] = mock_now
        db_return_dict['_id'] = 'mongo_id' # Adicionar _id que seria retornado

        # O objeto Task que esperamos após a validação
        expected_task_obj = Task(**db_return_dict)

        mock_collection.find_one_and_update = AsyncMock(return_value=db_return_dict)

        with patch("app.db.task_crud._get_tasks_collection", return_value=mock_collection):
             # Mockar Task.model_validate para retornar o objeto final
            with patch("app.db.task_crud.Task.model_validate", return_value=expected_task_obj) as mock_validate:
                result = await task_crud.update_task(MagicMock(), task_id, owner_id, update_payload)

    expected_filter = {"id": str(task_id), "owner_id": str(owner_id)}
    expected_update = {"$set": {**update_payload, "updated_at": mock_now}}
    mock_collection.find_one_and_update.assert_awaited_once_with(
        expected_filter, expected_update, return_document=True
    )
    mock_validate.assert_called_once_with(db_return_dict) # Deve ser chamado com o dict retornado pelo db
    assert result == expected_task_obj

# --- Testes para delete_task ---

@pytest.mark.asyncio
async def test_delete_task_success():
    mock_collection = MagicMock()
    mock_delete_result = MagicMock()
    mock_delete_result.deleted_count = 1
    mock_collection.delete_one = AsyncMock(return_value=mock_delete_result)
    task_id, owner_id = uuid.uuid4(), uuid.uuid4()

    with patch("app.db.task_crud._get_tasks_collection", return_value=mock_collection):
        deleted = await task_crud.delete_task(MagicMock(), task_id, owner_id)

    mock_collection.delete_one.assert_awaited_once_with({"id": str(task_id), "owner_id": str(owner_id)})
    assert deleted is True

@pytest.mark.asyncio
async def test_delete_task_not_found():
    mock_collection = MagicMock()
    mock_delete_result = MagicMock()
    mock_delete_result.deleted_count = 0
    mock_collection.delete_one = AsyncMock(return_value=mock_delete_result)
    task_id, owner_id = uuid.uuid4(), uuid.uuid4()

    with patch("app.db.task_crud._get_tasks_collection", return_value=mock_collection):
        deleted = await task_crud.delete_task(MagicMock(), task_id, owner_id)

    mock_collection.delete_one.assert_awaited_once()
    assert deleted is False

# --- Testes para _parse_sort_params ---

@pytest.mark.parametrize(
    "sort_by, sort_order, expected", [
        ("due_date", "asc", [("due_date", ASCENDING)]),
        ("priority_score", "desc", [("priority_score", DESCENDING)]),
        ("created_at", "ASC", [("created_at", ASCENDING)]),
        ("importance", "DESC", [("importance", DESCENDING)]),
        ("due_date", "ascending", [("due_date", DESCENDING)]),
        ("due_date", "", [("due_date", DESCENDING)]),
        ("invalid_field", "desc", None),
        (None, "desc", None),
    ]
)
def test_parse_sort_params(sort_by, sort_order, expected):
    from app.db.task_crud import _parse_sort_params
    assert _parse_sort_params(sort_by, sort_order) == expected

# (Testes para create_task_indexes omitidos por complexidade de mock de create_index)