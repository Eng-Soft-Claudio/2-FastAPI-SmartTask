# tests/test_db_task_crud.py
import pytest
import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch 
from typing import List, Optional, Dict, Any
from pymongo import ASCENDING, DESCENDING 
from pydantic import ValidationError
from app.db import task_crud
from app.models.task import Task, TaskStatus 

pytestmark = pytest.mark.asyncio

# ======================================================
# --- Fixtures ---
# ======================================================

# Fixture para criar uma tarefa de teste válida
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

# Fixture para mock do banco de dados e coleção
@pytest.fixture
def mock_db_collection():
    mock_collection = AsyncMock()
    mock_db = MagicMock()
    # Configurar db['tasks'] para retornar o mock da coleção
    mock_db.__getitem__.return_value = mock_collection
    return mock_db, mock_collection

# ======================================================
# --- Testes para create_task ---
# ======================================================

async def test_create_task_success(mock_db_collection, valid_task_obj):
    """Testa a criação bem-sucedida de uma tarefa."""
    mock_db, mock_collection = mock_db_collection
    # Mock o resultado da inserção
    mock_insert_result = MagicMock()
    mock_insert_result.acknowledged = True
    mock_collection.insert_one.return_value = mock_insert_result

    created_task = await task_crud.create_task(db=mock_db, task_db=valid_task_obj)

    # Verifica se insert_one foi chamado com os dados corretos (convertidos para dict)
    expected_dict = valid_task_obj.model_dump(mode='json')
    mock_collection.insert_one.assert_awaited_once_with(expected_dict)
    # Verifica se a tarefa original foi retornada
    assert created_task == valid_task_obj

async def test_create_task_db_not_acknowledged(mock_db_collection, valid_task_obj):
    """Testa o que acontece se insert_one não for Acknowledged."""
    mock_db, mock_collection = mock_db_collection
    mock_insert_result = MagicMock()
    mock_insert_result.acknowledged = False # Simula falha no ack
    mock_collection.insert_one.return_value = mock_insert_result

    created_task = await task_crud.create_task(db=mock_db, task_db=valid_task_obj)

    mock_collection.insert_one.assert_awaited_once()
    # Espera None porque o acknowledged foi False (cobre linha 47)
    assert created_task is None

async def test_create_task_db_exception(mock_db_collection, valid_task_obj, mocker):
    """Testa o tratamento de exceção durante a inserção no DB."""
    mock_db, mock_collection = mock_db_collection
    # Simular erro de DB
    db_error = Exception("Simulated DB Error")
    mock_collection.insert_one.side_effect = db_error
    # Mockar logger para verificar log
    mock_logger = mocker.patch("app.db.task_crud.logger")

    created_task = await task_crud.create_task(db=mock_db, task_db=valid_task_obj)

    mock_collection.insert_one.assert_awaited_once()
    # Espera None devido à exceção
    assert created_task is None
    # Verifica se logger.exception foi chamado (cobre linhas 49-50)
    mock_logger.exception.assert_called_once()
    assert f"DB Error creating task" in mock_logger.exception.call_args[0][0]

# ======================================================
# --- Testes para get_task_by_id ---
# ======================================================

async def test_get_task_by_id_success(mock_db_collection, valid_task_obj):
    """Testa a busca bem-sucedida por ID."""
    mock_db, mock_collection = mock_db_collection
    # Converte o obj Task para dict, como seria retornado pelo DB
    task_dict_from_db = valid_task_obj.model_dump(mode='json')
    # Adiciona _id, que seria removido pela função
    task_dict_from_db['_id'] = "some_mongo_id"
    mock_collection.find_one.return_value = task_dict_from_db

    owner_id = valid_task_obj.owner_id
    task_id = valid_task_obj.id

    # Mock model_validate para retornar o objeto Task
    with patch("app.db.task_crud.Task.model_validate", return_value=valid_task_obj) as mock_validate:
        found_task = await task_crud.get_task_by_id(db=mock_db, task_id=task_id, owner_id=owner_id)

        expected_query = {"id": str(task_id), "owner_id": str(owner_id)}
        mock_collection.find_one.assert_awaited_once_with(expected_query)
        # Simplificamos: Verificamos apenas o resultado final
        assert found_task == valid_task_obj
        # Garante que a validação foi chamada 
        mock_validate.assert_called_once()
        # Assegura que _id não está no resultado final
        assert "_id" not in found_task.model_dump()

async def test_get_task_by_id_not_found(mock_db_collection):
    """Testa quando a tarefa não é encontrada no DB."""
    mock_db, mock_collection = mock_db_collection
    mock_collection.find_one.return_value = None # Simula não encontrar

    task_id = uuid.uuid4()
    owner_id = uuid.uuid4()

    found_task = await task_crud.get_task_by_id(db=mock_db, task_id=task_id, owner_id=owner_id)

    mock_collection.find_one.assert_awaited_once()
    # Espera None (cobre linha 68)
    assert found_task is None

async def test_get_task_by_id_validation_error(mock_db_collection, mocker):
    """Testa quando os dados do DB falham na validação Pydantic."""
    mock_db, mock_collection = mock_db_collection
    # Retorna um dicionário que causará erro de validação (ex: importance faltando)
    invalid_task_dict = {"id": str(uuid.uuid4()), "owner_id": str(uuid.uuid4()), "title": "Invalid Task"}
    mock_collection.find_one.return_value = invalid_task_dict
    # Mock logger
    mock_logger = mocker.patch("app.db.task_crud.logger")

    task_id = uuid.UUID(invalid_task_dict["id"])
    owner_id = uuid.UUID(invalid_task_dict["owner_id"])

    # Simular que Task.model_validate levanta erro
    validation_error = ValidationError.from_exception_data(title='Task', line_errors=[])
    with patch("app.db.task_crud.Task.model_validate", side_effect=validation_error):
         found_task = await task_crud.get_task_by_id(db=mock_db, task_id=task_id, owner_id=owner_id)

         mock_collection.find_one.assert_awaited_once()
         # Espera None devido ao erro de validação
         assert found_task is None
         # Verifica se logger.error foi chamado (cobre linhas 66-67)
         mock_logger.error.assert_called_once()
         assert f"DB Validation error get_task_by_id {task_id}" in mock_logger.error.call_args[0][0]

# ======================================================
# --- Testes para get_tasks_by_owner ---
# ======================================================

async def test_get_tasks_by_owner_success_no_filters(mock_db_collection, valid_task_obj):
    """Testa a listagem básica sem filtros (mock corrigido)."""
    mock_db, mock_collection = mock_db_collection
    owner_id = valid_task_obj.owner_id
    task_dict = valid_task_obj.model_dump(mode='json')

    # <<< INÍCIO DA CORREÇÃO FINAL DO MOCK >>>
    # 1. Configura o cursor final que será iterado
    mock_cursor = AsyncMock()
    mock_cursor.__aiter__.return_value = [task_dict]

    # 2. Configura find() para retornar um mock que tem métodos skip/limit/sort
    #    e esses métodos retornam o cursor final mockado
    mock_find_result = MagicMock() # Objeto retornado por find()
    mock_find_result.skip.return_value.limit.return_value = mock_cursor # skip().limit() retorna o cursor
    # Mock find para retornar o objeto encadeável
    mock_collection.find.return_value = mock_find_result
    # <<< FIM DA CORREÇÃO >>>

    with patch("app.db.task_crud.Task.model_validate", return_value=valid_task_obj):
        tasks = await task_crud.get_tasks_by_owner(db=mock_db, owner_id=owner_id, limit=50, skip=10) # Usa valores explícitos

        expected_query = {"owner_id": str(owner_id)}
        mock_collection.find.assert_called_once_with(expected_query)
        # Verifica skip e limit no objeto correto retornado por find()
        mock_find_result.skip.assert_called_once_with(10)
        mock_find_result.skip().limit.assert_called_once_with(50) # Verifica limit no objeto retornado por skip

        assert len(tasks) == 1
        assert tasks[0] == valid_task_obj

async def test_get_tasks_by_owner_with_filters_and_sort(mock_db_collection, valid_task_obj):
    """Testa listagem com filtros e sort (mock corrigido)."""
    mock_db, mock_collection = mock_db_collection
    owner_id = valid_task_obj.owner_id
    task_dict = valid_task_obj.model_dump(mode='json')

    # <<< INÍCIO DA CORREÇÃO FINAL DO MOCK >>>
    mock_cursor = AsyncMock()
    mock_cursor.__aiter__.return_value = [task_dict]
    mock_limit = MagicMock()
    mock_limit.limit.return_value.sort.return_value = mock_cursor # limit().sort() retorna o cursor
    mock_skip = MagicMock()
    mock_skip.skip.return_value = mock_limit # skip() retorna obj com limit
    mock_collection.find.return_value = mock_skip # find() retorna obj com skip
    # <<< FIM DA CORREÇÃO >>>

    status_param = TaskStatus.PENDING
    project = "TestProject"
    sort_by = "created_at"
    sort_order = "asc"
    limit = 10
    skip = 5

    with patch("app.db.task_crud.Task.model_validate", return_value=valid_task_obj):
        tasks = await task_crud.get_tasks_by_owner(
            db=mock_db, owner_id=owner_id, status_filter=status_param,
            project_filter=project, sort_by=sort_by, sort_order=sort_order,
            limit=limit, skip=skip
        )

        expected_query = {"owner_id": str(owner_id), "status": status_param.value, "project": project}
        mock_collection.find.assert_called_once_with(expected_query)
        # Verifica a cadeia de chamadas
        mock_skip.skip.assert_called_once_with(skip)
        mock_limit.limit.assert_called_once_with(limit)
        mock_limit.limit().sort.assert_called_once_with([(sort_by, ASCENDING)])

        assert len(tasks) == 1
        assert tasks[0] == valid_task_obj


async def test_get_tasks_by_owner_validation_error_in_loop(mock_db_collection, valid_task_obj, mocker):
    """Testa erro de validação no loop (mock corrigido)."""
    mock_db, mock_collection = mock_db_collection
    owner_id = valid_task_obj.owner_id
    valid_dict = valid_task_obj.model_dump(mode='json')
    invalid_dict = {"id": str(uuid.uuid4()), "owner_id": str(owner_id), "_id": "id2"}

    # <<< INÍCIO DA CORREÇÃO FINAL DO MOCK >>>
    mock_cursor = AsyncMock()
    mock_cursor.__aiter__.return_value = [valid_dict, invalid_dict]
    mock_limit = MagicMock()
    mock_limit.limit.return_value = mock_cursor
    mock_skip = MagicMock()
    mock_skip.skip.return_value = mock_limit
    mock_collection.find.return_value = mock_skip
    # <<< FIM DA CORREÇÃO >>>

    mock_logger = mocker.patch("app.db.task_crud.logger")
    validation_error = ValidationError.from_exception_data(title='Task', line_errors=[])
    def validate_side_effect(data):
        if "title" in data and data["title"] == valid_task_obj.title: return valid_task_obj
        else: raise validation_error

    with patch("app.db.task_crud.Task.model_validate", side_effect=validate_side_effect) as mock_validate:
        tasks = await task_crud.get_tasks_by_owner(db=mock_db, owner_id=owner_id)

        mock_collection.find.assert_called_once()
        mock_skip.skip.assert_called_once_with(0) # Verifica default skip
        mock_limit.limit.assert_called_once_with(100) # Verifica default limit
        assert len(tasks) == 1
        assert tasks[0] == valid_task_obj
        assert mock_validate.call_count == 2
        mock_logger.error.assert_called_once()
async def test_get_tasks_by_owner_db_exception(mock_db_collection, mocker):
    """Testa o tratamento de exceção do DB durante a busca."""
    mock_db, mock_collection = mock_db_collection
    owner_id = uuid.uuid4()
    db_error = Exception("Simulated Find Error")
    mock_collection.find.side_effect = db_error # find levanta exceção
    mock_logger = mocker.patch("app.db.task_crud.logger")

    tasks = await task_crud.get_tasks_by_owner(db=mock_db, owner_id=owner_id)

    # Espera lista vazia
    assert tasks == []
    # Verifica log de exceção (cobre linha 109-111)
    mock_logger.exception.assert_called_once()
    assert f"DB Error listing tasks for owner {owner_id}" in mock_logger.exception.call_args[0][0]

# ======================================================
# --- Testes para update_task --- 
# ======================================================

async def test_update_task_success(mock_db_collection, valid_task_obj):
    """Testa atualização bem-sucedida."""
    mock_db, mock_collection = mock_db_collection
    task_id = valid_task_obj.id
    owner_id = valid_task_obj.owner_id
    update_payload = {"title": "Updated Title", "priority_score": 50.0}

    # Simular o retorno de find_one_and_update com o documento ATUALIZADO
    # Precisamos criar o dicionário como ele seria após o update
    updated_task_dict = valid_task_obj.model_dump(mode='json')
    updated_task_dict.update(update_payload) # Aplica os campos do payload
    # Adiciona/atualiza o campo updated_at que a função insere
    # Pegar o tempo exato é difícil, usar ANY ou mockar datetime.now
    with patch("app.db.task_crud.datetime") as mock_dt:
        mock_now = datetime.now(timezone.utc) # Tempo fixo para o teste
        mock_dt.now.return_value = mock_now
        updated_task_dict['updated_at'] = mock_now

        # find_one_and_update retorna o dict com _id
        db_return_dict = updated_task_dict.copy()
        db_return_dict['_id'] = "some_id"
        mock_collection.find_one_and_update.return_value = db_return_dict

        # Cria o objeto Task esperado como resultado da validação
        expected_updated_task = Task(**updated_task_dict)

        with patch("app.db.task_crud.Task.model_validate", return_value=expected_updated_task) as mock_validate:
            updated_task_result = await task_crud.update_task(
                db=mock_db,
                task_id=task_id,
                owner_id=owner_id,
                update_data=update_payload
            )

            expected_filter = {"id": str(task_id), "owner_id": str(owner_id)}
            # O $set deve conter o payload original MAIS o updated_at adicionado pela função
            expected_update = {"$set": {**update_payload, "updated_at": mock_now}}
            mock_collection.find_one_and_update.assert_awaited_once_with(
                expected_filter,
                expected_update,
                return_document=True
            )
            mock_validate.assert_called_once_with(updated_task_dict) # Sem o _id
            assert updated_task_result == expected_updated_task

# ======================================================
# --- Testes para delete_task --- 
# ======================================================

async def test_delete_task_success(mock_db_collection):
    """Testa deleção bem-sucedida."""
    mock_db, mock_collection = mock_db_collection
    task_id = uuid.uuid4()
    owner_id = uuid.uuid4()

    # Mock do resultado da deleção
    mock_delete_result = MagicMock()
    mock_delete_result.deleted_count = 1 # Indica que 1 documento foi deletado
    mock_collection.delete_one.return_value = mock_delete_result

    deleted = await task_crud.delete_task(db=mock_db, task_id=task_id, owner_id=owner_id)

    expected_filter = {"id": str(task_id), "owner_id": str(owner_id)}
    mock_collection.delete_one.assert_awaited_once_with(expected_filter)
    assert deleted is True

async def test_delete_task_not_found(mock_db_collection):
    """Testa deleção quando tarefa não é encontrada (ou não pertence ao owner)."""
    mock_db, mock_collection = mock_db_collection
    task_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    mock_delete_result = MagicMock()
    mock_delete_result.deleted_count = 0 # Nenhum documento deletado
    mock_collection.delete_one.return_value = mock_delete_result

    deleted = await task_crud.delete_task(db=mock_db, task_id=task_id, owner_id=owner_id)

    mock_collection.delete_one.assert_awaited_once()
    assert deleted is False

# ======================================================
# --- Testes para _parse_sort_params --- 
# ======================================================

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
    """Testa a função _parse_sort_params com vários casos."""
    from app.db.task_crud import _parse_sort_params
    assert _parse_sort_params(sort_by, sort_order) == expected


