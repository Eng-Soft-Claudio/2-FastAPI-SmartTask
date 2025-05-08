# tests/test_db_task_crud.py
"""
Este módulo contém testes unitários para as funções CRUD (Create, Read, Update, Delete)
de tarefas, definidas em `app.db.task_crud`.

Os testes utilizam mocks (principalmente `unittest.mock.AsyncMock` e `unittest.mock.patch`)
para simular as interações com a coleção do MongoDB, permitindo testar a lógica
das funções CRUD de forma isolada.

São testados:
- Criação de tarefas (`create_task`) em cenários de sucesso e falha.
- Busca de tarefas por ID (`get_task_by_id`) em cenários de sucesso, não encontrado e erro de validação.
- Listagem de tarefas por proprietário (`get_tasks_by_owner`) com e sem filtros/ordenação,
  incluindo tratamento de erros de validação e DB.
- Atualização de tarefas (`update_task`).
- Deleção de tarefas (`delete_task`).
- A função auxiliar `_parse_sort_params`.
"""

# ========================
# --- Importações ---
# ========================
import uuid
from datetime import date, datetime, timedelta, timezone 
from typing import Any, Dict, List, Optional 
from unittest.mock import AsyncMock, MagicMock, call, patch
from venv import logger 

import pytest
from pydantic import ValidationError 
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError
from pytest_mock import MockerFixture

# --- Módulos da Aplicação ---
from app.db import task_crud 
from app.models.task import Task, TaskStatus, TaskUpdate

# ============================
# --- Fixture de Dados ---
# ============================

@pytest.fixture
def valid_task_obj() -> Task:
    """
    Fixture que retorna um objeto `Task` válido e completo,
    pronto para ser usado nos testes como entrada para criação
    ou como valor esperado de retorno.
    """
    owner_unique_id = uuid.uuid4()
    task_unique_id = uuid.uuid4()
    print(f"  Fixture 'valid_task_obj': Criando Task ID={task_unique_id}, Owner ID={owner_unique_id}")
    return Task(
        id=task_unique_id,
        owner_id=owner_unique_id,
        title="Tarefa de Teste Padrão",
        description="Uma descrição detalhada para a tarefa de teste padrão.",
        importance=3, 
        status=TaskStatus.PENDING,
        created_at=datetime.now(timezone.utc)
        )

@pytest.fixture
def sample_owner_id() -> uuid.UUID:
    """Fornece um UUID fixo para testes."""
    return uuid.UUID("123e4567-e89b-12d3-a456-426614174000")

@pytest.fixture
def sample_task_in_db(sample_owner_id: uuid.UUID) -> Task:
    """Fornece um objeto Task completo válido para testes."""
    task_id = uuid.uuid4()
    return Task(
        id=task_id,
        owner_id=sample_owner_id,
        title="Sample Task in DB",
        description="Description for sample task in DB",
        importance=4,
        status=TaskStatus.IN_PROGRESS,
        created_at=datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=2),
        updated_at=None,
        due_date=date.today() + timedelta(days=5),
        priority_score=55.5,
        tags=["sample", "db"]
    )

@pytest.fixture
def sample_task_create_data() -> Dict[str, Any]:
    """Fornece um dicionário válido para criar uma tarefa."""
    return {
        "title": "Sample Task Create",
        "description": "Desc for create",
        "importance": 3,
        "due_date": (date.today() + timedelta(days=10)).isoformat(),
        "status": TaskStatus.PENDING.value,
        "tags": ["create_test"],
        "project": "Project Alpha"
    }

# ===================================
# --- Testes para `create_task` ---
# ===================================
@pytest.mark.asyncio
async def test_create_task_successfully(valid_task_obj: Task):
    """
    Testa a criação bem-sucedida de uma tarefa.
    Verifica se `_get_tasks_collection` é chamado, se `insert_one` na coleção
    é chamado com os dados corretos e se a função retorna o objeto da tarefa
    quando a inserção é confirmada (acknowledged).
    """
    print(f"\nTeste: create_task - Sucesso (Task ID: {valid_task_obj.id})")
    # --- Arrange: Configurar mocks ---
    mock_mongodb_collection = AsyncMock() 
    mock_insert_operation_result = MagicMock()
    mock_insert_operation_result.acknowledged = True 
    mock_mongodb_collection.insert_one = AsyncMock(return_value=mock_insert_operation_result)
    print("  Mock: Coleção MongoDB e resultado de insert_one configurados para sucesso.")

    with patch("app.db.task_crud._get_tasks_collection", return_value=mock_mongodb_collection):
        # --- Act: Chamar a função `create_task` ---
        print(f"  Atuando: Chamando task_crud.create_task com objeto Task.")
        created_task_result = await task_crud.create_task(db=MagicMock(), task_db=valid_task_obj)

    # --- Assert: Verificar chamadas e resultado ---
    expected_dict_for_db = valid_task_obj.model_dump(mode='json') 
    mock_mongodb_collection.insert_one.assert_awaited_once_with(expected_dict_for_db)
    assert created_task_result == valid_task_obj, "A tarefa retornada não é a mesma que foi passada."
    print("  Sucesso: Tarefa criada e retornada corretamente.")

@pytest.mark.asyncio
async def test_create_task_when_db_insert_not_acknowledged(valid_task_obj: Task):
    """
    Testa o comportamento de `create_task` quando a operação `insert_one`
    do MongoDB não é confirmada (`acknowledged = False`).
    Espera-se que a função retorne `None`.
    """
    # ========================
    # --- Arrange ---
    # ========================
    mock_mongodb_collection = AsyncMock()
    mock_insert_operation_result = MagicMock()
    mock_insert_operation_result.acknowledged = False 
    mock_mongodb_collection.insert_one = AsyncMock(return_value=mock_insert_operation_result)

    # ========================
    # --- Act ---
    # ========================
    with patch("app.db.task_crud._get_tasks_collection", return_value=mock_mongodb_collection):
        created_task_result = await task_crud.create_task(db=MagicMock(), task_db=valid_task_obj)

    # ========================
    # --- Assert ---
    # ========================
    mock_mongodb_collection.insert_one.assert_awaited_once()
    assert created_task_result is None, "Deveria retornar None se a inserção não for acknowledged."

@pytest.mark.asyncio
async def test_create_task_handles_db_exception_on_insert(valid_task_obj: Task, mocker):
    """
    Testa o tratamento de exceção em `create_task` quando `insert_one`
    levanta uma exceção (simulando um erro do banco de dados).
    Espera-se que a exceção seja capturada, logada, e que a função retorne `None`.
    """
    # ========================
    # --- Arrange ---
    # ========================
    mock_mongodb_collection = AsyncMock()
    simulated_db_error = Exception("Erro de Simulação na Inserção no DB")
    mock_mongodb_collection.insert_one = AsyncMock(side_effect=simulated_db_error)
    mock_task_crud_logger = mocker.patch("app.db.task_crud.logger")

    # ========================
    # --- Act ---
    # ========================
    with patch("app.db.task_crud._get_tasks_collection", return_value=mock_mongodb_collection):
        created_task_result = await task_crud.create_task(db=MagicMock(), task_db=valid_task_obj)

    # ========================
    # --- Assert ---
    # ========================
    mock_mongodb_collection.insert_one.assert_awaited_once() 
    assert created_task_result is None, "Deveria retornar None em caso de exceção no DB."
    mock_task_crud_logger.exception.assert_called_once(), "logger.exception não foi chamado."

@pytest.mark.asyncio
async def test_create_task_indexes_success(mocker): 
    """
    Testa a criação bem-sucedida de todos os índices de tarefa.
    """
    # ========================
    # --- Arrange ---
    # ========================
    mock_db_object = MagicMock()
    mock_collection = AsyncMock()
    mock_collection.create_index = AsyncMock() 
    mocker.patch("app.db.task_crud._get_tasks_collection", return_value=mock_collection)
    mock_logger_info = mocker.patch("app.db.task_crud.logging.info")

    # ========================
    # --- Act ---
    # ========================
    await task_crud.create_task_indexes(db=mock_db_object)

    # ========================
    # --- Assert ---
    # ========================
    expected_calls = [
        call("id", unique=True, name="task_id_unique_idx"),
        call("owner_id", name="task_owner_idx"),
        call([("owner_id", ASCENDING), ("due_date", DESCENDING)], name="task_owner_due_date_idx"),
        call([("owner_id", ASCENDING), ("priority_score", DESCENDING)], name="task_owner_priority_idx"),
        call("tags", name="task_tags_idx")
    ]
    mock_collection.create_index.assert_has_awaits(expected_calls, any_order=False)
    mock_logger_info.assert_called_once_with("Índices da coleção 'tasks' verificados/criados.")

@pytest.mark.asyncio
async def test_create_task_indexes_failure(mocker): 
    """
    Testa o tratamento de erro durante a criação de um índice de tarefa.
    """
    # ========================
    # --- Arrange ---
    # ========================
    mock_db_object = MagicMock()
    simulated_db_error = Exception("Erro simulado ao criar índice 'owner_id'")
    mock_collection = AsyncMock()
    mock_collection.create_index.side_effect = [
        AsyncMock(), 
        simulated_db_error 
    ]
    mocker.patch("app.db.task_crud._get_tasks_collection", return_value=mock_collection)
    mock_logger_error = mocker.patch("app.db.task_crud.logging.error")
    mock_logger_info = mocker.patch("app.db.task_crud.logging.info")

    # ========================
    # --- Act ---
    # ========================
    await task_crud.create_task_indexes(db=mock_db_object)

    # ========================
    # --- Assert ---
    # ========================
    assert mock_collection.create_index.await_count == 2
    first_call_args = mock_collection.create_index.await_args_list[0].args
    second_call_args = mock_collection.create_index.await_args_list[1].args
    assert first_call_args[0] == "id"
    assert second_call_args[0] == "owner_id"
    mock_logger_error.assert_called_once()
    call_args, call_kwargs = mock_logger_error.call_args
    log_message = call_args[0]
    assert "Erro ao criar índices da coleção 'tasks'" in log_message
    assert str(simulated_db_error) in log_message
    assert call_kwargs.get("exc_info") is True
    mock_logger_info.assert_not_called()

# =====================================
# --- Testes para `get_task_by_id` ---
# =====================================
@pytest.mark.asyncio
async def test_get_task_by_id_successfully(valid_task_obj: Task):
    """
    Testa a busca bem-sucedida de uma tarefa por ID.
    Verifica se `find_one` é chamado com a query correta, se `Task.model_validate`
    é chamado com os dados corretos (sem `_id`), e se a tarefa é retornada.
    """
    print(f"\nTeste: get_task_by_id - Sucesso (Task ID: {valid_task_obj.id})")
    # --- Arrange ---
    task_dict_from_db = valid_task_obj.model_dump(mode='json')
    task_dict_from_db['_id'] = "some_random_mongodb_object_id" 
    
    mock_mongodb_collection = AsyncMock() 
    mock_mongodb_collection.find_one = AsyncMock(return_value=task_dict_from_db)
    print(f"  Mock: find_one para retornar dados da tarefa (incluindo _id).")
    
    target_task_id = valid_task_obj.id
    target_owner_id = valid_task_obj.owner_id

    with patch("app.db.task_crud._get_tasks_collection", return_value=mock_mongodb_collection), \
         patch("app.db.task_crud.Task.model_validate", return_value=valid_task_obj) as mock_pydantic_validate:
        # --- Act ---
        print("  Atuando: Chamando task_crud.get_task_by_id...")
        found_task_result = await task_crud.get_task_by_id(
            db=MagicMock(), task_id=target_task_id, owner_id=target_owner_id
        )

    # --- Assert ---
    expected_query_for_find_one = {"id": str(target_task_id), "owner_id": str(target_owner_id)}
    mock_mongodb_collection.find_one.assert_awaited_once_with(expected_query_for_find_one)
    
    expected_dict_for_validation = task_dict_from_db.copy()
    expected_dict_for_validation.pop('_id', None) 
    mock_pydantic_validate.assert_called_once_with(expected_dict_for_validation)
    
    assert found_task_result == valid_task_obj, "A tarefa encontrada não corresponde à esperada."
    print("  Sucesso: Tarefa encontrada e validada corretamente.")

@pytest.mark.asyncio
async def test_get_task_by_id_when_not_found_in_db():
    """
    Testa o comportamento de `get_task_by_id` quando `find_one` retorna `None`
    (indicando que a tarefa não foi encontrada no banco de dados).
    Espera-se que a função retorne `None`.
    """
    task_id_not_in_db = uuid.uuid4()
    owner_id_for_test = uuid.uuid4()
    print(f"\nTeste: get_task_by_id - Tarefa não encontrada (Task ID: {task_id_not_in_db})")
    # --- Arrange ---
    mock_mongodb_collection = AsyncMock()
    mock_mongodb_collection.find_one = AsyncMock(return_value=None) 
    print("  Mock: find_one para retornar None.")

    with patch("app.db.task_crud._get_tasks_collection", return_value=mock_mongodb_collection):
        # --- Act ---
        print("  Atuando: Chamando task_crud.get_task_by_id...")
        found_task_result = await task_crud.get_task_by_id(
            db=MagicMock(), task_id=task_id_not_in_db, owner_id=owner_id_for_test
        )

    # --- Assert ---
    mock_mongodb_collection.find_one.assert_awaited_once() 
    assert found_task_result is None, "Deveria retornar None se a tarefa não for encontrada."
    print("  Sucesso: get_task_by_id retornou None como esperado.")

@pytest.mark.asyncio
async def test_get_task_by_id_handles_pydantic_validation_error(mocker):
    """
    Testa o tratamento de erro em `get_task_by_id` quando os dados retornados
    do banco de dados falham na validação do modelo Pydantic `Task.model_validate`.
    Espera-se que a exceção seja capturada, logada, e que a função retorne `None`.
    """
    print("\nTeste: get_task_by_id - Erro de validação Pydantic ao processar dados do DB.")
    # --- Arrange ---
    invalid_task_dict_from_db = {"id": str(uuid.uuid4()), "owner_id": str(uuid.uuid4()), "title_erroneo": "Tarefa Inválida"}
    invalid_task_dict_from_db['_id'] = "another_mongo_id"

    mock_mongodb_collection = AsyncMock()
    mock_mongodb_collection.find_one = AsyncMock(return_value=invalid_task_dict_from_db)
    mock_task_crud_logger = mocker.patch("app.db.task_crud.logger")
    print(f"  Mock: find_one para retornar dados inválidos, logger mockado.")

    task_id_for_test = uuid.UUID(invalid_task_dict_from_db["id"])
    owner_id_for_test = uuid.UUID(invalid_task_dict_from_db["owner_id"])

    simulated_validation_error = ValidationError.from_exception_data(title='TaskModel', line_errors=[])
    
    with patch("app.db.task_crud._get_tasks_collection", return_value=mock_mongodb_collection), \
         patch("app.db.task_crud.Task.model_validate", side_effect=simulated_validation_error): 
        # --- Act ---
        print("  Atuando: Chamando task_crud.get_task_by_id (esperando erro de validação interno)...")
        found_task_result = await task_crud.get_task_by_id(
            db=MagicMock(), task_id=task_id_for_test, owner_id=owner_id_for_test
        )

    # --- Assert ---
    mock_mongodb_collection.find_one.assert_awaited_once()
    assert found_task_result is None, "Deveria retornar None em caso de erro de validação."
    mock_task_crud_logger.error.assert_called_once(), "logger.error não foi chamado."
    print("  Sucesso: Erro de validação tratado, retornou None e erro foi logado.")

# ===========================================
# --- Testes para `get_tasks_by_owner` ---
# ===========================================
@pytest.mark.asyncio
async def test_get_tasks_by_owner_list_basic_success(valid_task_obj: Task):
    """
    Testa a listagem básica de tarefas para um proprietário, sem filtros ou ordenação complexa.
    Verifica se a query `find` é construída corretamente e se skip/limit são aplicados.
    """
    target_owner_id = valid_task_obj.owner_id
    task_dict_from_db_iter = valid_task_obj.model_dump(mode='json')
    task_dict_from_db_iter['_id'] = "id_from_db" 
    print(f"\nTeste: get_tasks_by_owner - Listagem básica para Owner ID: {target_owner_id}")

    # --- Arrange: Configurar a cadeia de mocks ---
    mock_motor_cursor = AsyncMock() 
    mock_motor_cursor.__aiter__.return_value = [task_dict_from_db_iter]
    mock_motor_cursor.skip = MagicMock(return_value=mock_motor_cursor)
    mock_motor_cursor.limit = MagicMock(return_value=mock_motor_cursor)

    mock_mongodb_collection = MagicMock() 

    mock_mongodb_collection.find = MagicMock(return_value=mock_motor_cursor) 
    
    print("  Mock: Cadeia de find().skip().limit().sort() e validação de modelo configurados.")

    test_limit = 50
    test_skip = 10

    with patch("app.db.task_crud._get_tasks_collection", return_value=mock_mongodb_collection), \
         patch("app.db.task_crud.Task.model_validate", return_value=valid_task_obj):
        # --- Act ---
        print(f"  Atuando: Chamando get_tasks_by_owner com limit={test_limit}, skip={test_skip}...")
        retrieved_tasks_list = await task_crud.get_tasks_by_owner(
            db=MagicMock(), owner_id=target_owner_id, limit=test_limit, skip=test_skip
        )

    # --- Assert ---
    expected_base_query = {"owner_id": str(target_owner_id)}
    mock_mongodb_collection.find.assert_called_once_with(expected_base_query)
    mock_motor_cursor.skip.assert_called_once_with(test_skip)
    mock_motor_cursor.limit.assert_called_once_with(test_limit)
    
    assert len(retrieved_tasks_list) == 1, "Número de tarefas retornadas incorreto."
    assert retrieved_tasks_list[0] == valid_task_obj, "Tarefa retornada não corresponde à esperada."
    print(f"  Sucesso: Listagem básica funcionou, {len(retrieved_tasks_list)} tarefa(s) retornada(s).")

@pytest.mark.asyncio
async def test_get_tasks_by_owner_with_all_filters_and_sorting(valid_task_obj: Task):
    """
    Testa a listagem de tarefas com todos os filtros (status, projeto) e ordenação.
    Verifica se a query `find` inclui os filtros e se `sort` é chamado corretamente.
    """
    target_owner_id = valid_task_obj.owner_id
    task_dict_from_db_iter = valid_task_obj.model_dump(mode='json')
    task_dict_from_db_iter['_id'] = "id_for_sort_test"

    # ========================
    # --- Arrange ---
    # ========================
    mock_motor_cursor = AsyncMock() 
    mock_motor_cursor.__aiter__.return_value = [task_dict_from_db_iter]
    mock_motor_cursor.skip = MagicMock(return_value=mock_motor_cursor)  
    mock_motor_cursor.limit = MagicMock(return_value=mock_motor_cursor) 
    mock_motor_cursor.sort = MagicMock(return_value=mock_motor_cursor)
    mock_mongodb_collection = MagicMock()
    mock_mongodb_collection.find = MagicMock(return_value=mock_motor_cursor) 
    

    # ========================
    # --- Act ---
    # ========================
    filter_status = TaskStatus.PENDING
    filter_project = "ProjetoX_Filtro"
    sort_field = "created_at"
    sort_direction = "asc"
    test_limit_val = 10
    test_skip_val = 5

    with patch("app.db.task_crud._get_tasks_collection", return_value=mock_mongodb_collection), \
         patch("app.db.task_crud.Task.model_validate", return_value=valid_task_obj):
        print(f"  Atuando: Chamando get_tasks_by_owner com status, projeto, sort, limit, skip...")
        retrieved_tasks_list = await task_crud.get_tasks_by_owner(
            db=MagicMock(),
            owner_id=target_owner_id,
            status_filter=filter_status,
            project_filter=filter_project,
            sort_by=sort_field,
            sort_order=sort_direction,
            limit=test_limit_val,
            skip=test_skip_val
        )

    expected_query_with_filters = {
        "owner_id": str(target_owner_id),
        "status": filter_status.value,
        "project": filter_project
    }

    # ========================
    # --- Assert ---
    # ========================
    mock_mongodb_collection.find.assert_called_once_with(expected_query_with_filters)
    mock_motor_cursor.skip.assert_called_once_with(test_skip_val)
    mock_motor_cursor.limit.assert_called_once_with(test_limit_val)
    mock_motor_cursor.sort.assert_called_once_with([(sort_field, ASCENDING)])
    assert len(retrieved_tasks_list) == 1
    assert retrieved_tasks_list[0] == valid_task_obj

@pytest.mark.asyncio
async def test_get_tasks_by_owner_handles_validation_error_during_iteration(valid_task_obj: Task, mocker):
    """
    Testa o tratamento de erro em `get_tasks_by_owner` quando `Task.model_validate`
    levanta uma `ValidationError` para um dos documentos durante a iteração do cursor.
    Espera-se que o erro seja logado, o item inválido seja pulado, e os itens válidos sejam retornados.
    """
    # ========================
    # --- Arrange ---
    # ========================
    target_owner_id = uuid.uuid4()
    simulated_db_error_on_find = Exception("Erro de Simulação de Conexão Perdida no Find")
    mock_collection_object = MagicMock()
    mock_collection_object.find.side_effect = simulated_db_error_on_find
    patch_get_collection = patch("app.db.task_crud._get_tasks_collection", return_value=mock_collection_object)
    mock_task_crud_logger = mocker.patch("app.db.task_crud.logger")

    # ========================
    # --- Act ---
    # ========================
    with patch_get_collection: 
        retrieved_tasks_list = await task_crud.get_tasks_by_owner(db=MagicMock(), owner_id=target_owner_id)

    # ========================
    # --- Assert ---
    # ========================
    assert retrieved_tasks_list == [], "Deveria retornar lista vazia em caso de exceção no DB."
    mock_task_crud_logger.exception.assert_called_once(), "logger.exception não foi chamado."
    
    log_call_args_tuple = mock_task_crud_logger.exception.call_args[0]
    assert f"DB Error listing tasks for owner {target_owner_id}" in log_call_args_tuple[0], \
        "Mensagem de log de exceção não contém as informações esperadas."
    
    mock_collection_object.find.assert_called_once()

@pytest.mark.asyncio
async def test_get_tasks_by_owner_handles_general_db_exception(mocker):
    """
    Testa o tratamento de exceção em `get_tasks_by_owner` quando ocorre um erro
    geral no banco de dados durante a operação `find` (ou iteração).
    Espera-se que a função retorne uma lista vazia e logue a exceção.
    """
    # ========================
    # --- Arrange ---
    # ========================
    mock_collection = MagicMock()
    owner_id = uuid.uuid4()
    db_error = Exception("Simulated Find Error")
    mock_collection.find.side_effect = db_error
    mock_logger = mocker.patch("app.db.task_crud.logger")

    # ========================
    # --- Act ---
    # ========================
    with patch("app.db.task_crud._get_tasks_collection", return_value=mock_collection):
        tasks = await task_crud.get_tasks_by_owner(db=MagicMock(), owner_id=owner_id)

    # ========================
    # --- Assert ---
    # ========================
    assert tasks == []
    mock_logger.exception.assert_called_once()
    assert f"DB Error listing tasks for owner {owner_id}" in mock_logger.exception.call_args[0][0]

@pytest.mark.asyncio
async def test_get_tasks_by_owner_generic_db_exception(mocker): 
    """
    Testa get_tasks_by_owner quando ocorre uma exceção genérica do DB.
    """
    # ========================
    # --- Arrange ---
    # ========================
    owner_id = uuid.uuid4()
    simulated_db_error = Exception("Simulated DB Error during find/iteration")
    mock_db_object = MagicMock()
    mock_collection = MagicMock()
    mock_collection.find.side_effect = simulated_db_error
    mocker.patch("app.db.task_crud._get_tasks_collection", return_value=mock_collection)

    mock_logger_exception = mocker.patch("app.db.task_crud.logger.exception")

    # ========================
    # --- Act ---
    # ========================
    result = await task_crud.get_tasks_by_owner(db=mock_db_object, owner_id=owner_id)

    # ========================
    # --- Assert ---
    # ========================
    assert result == []
    mock_collection.find.assert_called_once()
    mock_logger_exception.assert_called_once()
    call_args, _ = mock_logger_exception.call_args
    assert f"DB Error listing tasks for owner {owner_id}" in call_args[0]
    assert str(simulated_db_error) in call_args[0]

@pytest.mark.asyncio
async def test_get_tasks_by_owner_validation_error_in_loop(mocker, sample_owner_id): 
    """
    Testa get_tasks_by_owner quando um item falha na validação Pydantic
    dentro do loop, mas outros são válidos (simulando iteração).
    """
    # ========================
    # --- Arrange ---
    # ========================
    mock_db_object = MagicMock()
    owner_id = sample_owner_id

    valid_task_dict_db = {
        "_id": "valid_id_direct_list", "id": str(uuid.uuid4()), "owner_id": str(owner_id),
        "title": "Valid Task Direct List", "importance": 3, "status": "pendente",
        "created_at": datetime.now(timezone.utc)
    }
    invalid_task_dict_db = {
        "_id": "invalid_id_direct_list", "id": str(uuid.uuid4()), "owner_id": str(owner_id),
        "title": "Invalid Task Direct List", "status": "invalid_status"
    }
    valid_task_obj = Task(
        id=uuid.UUID(valid_task_dict_db['id']), owner_id=sample_owner_id,
        title="Valid Task Direct List", importance=3, status=TaskStatus.PENDING,
        created_at=valid_task_dict_db['created_at']
    )
    mock_final_chain_link = AsyncMock()
    mock_final_chain_link.to_list.return_value = [valid_task_dict_db, invalid_task_dict_db] 
    mock_collection = AsyncMock()
    mock_collection.find.return_value.skip.return_value.limit.return_value = mock_final_chain_link
    mocker.patch("app.db.task_crud._get_tasks_collection", return_value=mock_collection)
    validation_error = ValidationError.from_exception_data(title="Task", line_errors=[])
    dict_for_valid_call = valid_task_dict_db.copy(); dict_for_valid_call.pop("_id")
    dict_for_invalid_call = invalid_task_dict_db.copy(); dict_for_invalid_call.pop("_id")
    mock_validate = mocker.patch(
        "app.db.task_crud.Task.model_validate",
        side_effect=[valid_task_obj, validation_error]
    )
    async def mock_async_for(*args, **kwargs):
        tasks = []
        items = await mock_final_chain_link.to_list() 
        for item in items:
            item.pop('_id', None)
            try:
                tasks.append(Task.model_validate(item)) 
            except (ValidationError, Exception) as e:
                task_crud.logger.error(f"DB Validation error list_tasks owner {owner_id} task {item.get('id', 'N/A')}: {e}")
                continue
        return tasks
    mock_get_tasks_internal = mocker.patch("app.db.task_crud.get_tasks_by_owner", side_effect=mock_async_for)
    mock_logger_error = mocker.patch("app.db.task_crud.logger.error")
    mock_logger_exception = mocker.patch("app.db.task_crud.logger.exception")

    # ========================
    # --- Act ---
    # ========================
    # Chamar a função (que agora está substituída pelo mock_async_for)
    result = await task_crud.get_tasks_by_owner(db=mock_db_object, owner_id=owner_id)

    # ========================
    # --- Assert ---
    # ========================
    assert len(result) == 1
    assert result[0] == valid_task_obj
    mock_get_tasks_internal.assert_awaited_once_with(db=mock_db_object, owner_id=owner_id)
    assert mock_validate.call_count == 2
    mock_validate.assert_has_calls([call(dict_for_valid_call), call(dict_for_invalid_call)], any_order=False)
    mock_logger_error.assert_called_once()
    call_args_log, _ = mock_logger_error.call_args
    log_message = call_args_log[0]
    assert f"DB Validation error list_tasks owner {sample_owner_id} task {invalid_task_dict_db['id']}" in log_message
    assert str(validation_error) in log_message
    mock_logger_exception.assert_not_called() 

@pytest.mark.asyncio
async def test_get_tasks_by_owner_validation_error_handling(caplog):
    """
    Testa o tratamento de erro de validação dentro do loop
    de get_tasks_by_owner, verificando se o erro é logado e
    a lista resultante é vazia (ou contém apenas itens válidos).
    """
      # ========================
    # --- Arrange ---
    # ========================
    db_mock = MagicMock()
    collection_mock = MagicMock()
    db_mock.__getitem__.return_value = collection_mock
    db_mock.tasks = collection_mock
    invalid_task = {"id": "fake-id", "invalid_field": "invalid"}
    cursor_mock = MagicMock()
    cursor_mock.__aiter__.return_value = [invalid_task]
    cursor_mock.skip.return_value = cursor_mock
    cursor_mock.limit.return_value = cursor_mock
    cursor_mock.sort.return_value = cursor_mock
    collection_mock.find = MagicMock()
    collection_mock.find.return_value = cursor_mock
    owner_id = uuid.uuid4()
    

    # ========================
    # --- Act ---
    # ========================
    with patch("app.db.task_crud.logger.error") as mock_logger:
        result = await task_crud.get_tasks_by_owner(db_mock, owner_id)

    # ========================
    # --- Assert ---
    # ========================
    assert result == []
    mock_logger.assert_called()

# ===================================
# --- Testes para `update_task` ---
# ===================================
@pytest.mark.asyncio
async def test_update_task_successfully(valid_task_obj: Task):
    """
    Testa a atualização bem-sucedida de uma tarefa.
    Verifica se `find_one_and_update` é chamado com os parâmetros corretos
    (filtro, dados de atualização com `$set` e `updated_at`), e se
    `Task.model_validate` é chamado com o documento retornado pelo DB.
    """
    target_task_id = valid_task_obj.id
    target_owner_id = valid_task_obj.owner_id
    update_payload_data = {"title": "Título da Tarefa Atualizado via Teste", "status": TaskStatus.IN_PROGRESS.value}
    
    print(f"\nTeste: update_task - Sucesso (Task ID: {target_task_id})")

    # --- Arrange ---
    fixed_current_time_utc = datetime.now(timezone.utc).replace(microsecond=0)
    
    db_document_after_update = valid_task_obj.model_dump(mode='json')
    db_document_after_update.update(update_payload_data) 
    db_document_after_update['updated_at'] = fixed_current_time_utc 
    db_document_after_update['_id'] = 'some_mongo_id_for_update' 

    expected_final_task_object = Task(**db_document_after_update)
    
    mock_mongodb_collection = AsyncMock()
    mock_mongodb_collection.find_one_and_update = AsyncMock(return_value=db_document_after_update)
    print("  Mock: Coleção MongoDB, find_one_and_update, e Task.model_validate configurados.")

    with patch("app.db.task_crud.datetime") as mock_datetime_module, \
         patch("app.db.task_crud._get_tasks_collection", return_value=mock_mongodb_collection), \
         patch("app.db.task_crud.Task.model_validate", return_value=expected_final_task_object) as mock_pydantic_validate:
        
        mock_datetime_module.now.return_value = fixed_current_time_utc 
        
        # --- Act ---
        print(f"  Atuando: Chamando task_crud.update_task com payload: {update_payload_data}")
        update_result_task = await task_crud.update_task(
            db=MagicMock(),
            task_id=target_task_id,
            owner_id=target_owner_id,
            update_data=update_payload_data.copy() 
        )

    # --- Assert ---
    expected_filter_for_update = {"id": str(target_task_id), "owner_id": str(target_owner_id)}
    expected_data_for_set_operator = {**update_payload_data, "updated_at": fixed_current_time_utc}
    
    mock_mongodb_collection.find_one_and_update.assert_awaited_once_with(
        expected_filter_for_update,
        {"$set": expected_data_for_set_operator},
        return_document=True
    )
    expected_dict_for_validation = db_document_after_update.copy()
    expected_dict_for_validation.pop('_id', None)
    mock_pydantic_validate.assert_called_once_with(expected_dict_for_validation)
    
    assert update_result_task == expected_final_task_object, "A tarefa atualizada retornada não é a esperada."
    print("  Sucesso: Tarefa atualizada e retornada corretamente.")

@pytest.mark.asyncio
async def test_update_task_validation_error_post_db(mocker, sample_task_in_db): 
    """
    Testa falha de validação Pydantic após find_one_and_update retornar dados.
    """
    # ========================
    # --- Arrange ---
    # ========================
    test_task_id = sample_task_in_db.id
    owner_id = sample_task_in_db.owner_id
    update_data = {"title": "Updated Title Valid", "status": TaskStatus.IN_PROGRESS.value}
    fixed_timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    mock_db_object = MagicMock()

    mock_doc_returned_from_db = {
        "_id": "mongo_db_id_valid_err",
        "id": str(test_task_id),
        "owner_id": str(owner_id),
        "title": update_data["title"],
        "status": update_data["status"],
        "created_at": sample_task_in_db.created_at,
        "updated_at": fixed_timestamp,
        "due_date": sample_task_in_db.due_date
    }
    expected_dict_for_validation = mock_doc_returned_from_db.copy()
    expected_dict_for_validation.pop("_id")

    mock_dt_now = mocker.patch("app.db.task_crud.datetime")
    mock_dt_now.now.return_value = fixed_timestamp

    mock_collection = AsyncMock()
    mock_collection.find_one_and_update.return_value = mock_doc_returned_from_db
    mocker.patch("app.db.task_crud._get_tasks_collection", return_value=mock_collection)

    simulated_validation_error = ValidationError.from_exception_data(title='Task', line_errors=[{'loc':('importance',), 'type':'missing'}])
    mock_validate = mocker.patch(
        "app.db.task_crud.Task.model_validate",
        side_effect=simulated_validation_error
    )
    mock_logger_error = mocker.patch("app.db.task_crud.logger.error")

    # ========================
    # --- Act ---
    # ========================
    result = await task_crud.update_task(
        db=mock_db_object,
        task_id=test_task_id,
        owner_id=owner_id,
        update_data=update_data.copy() 
    )

    # ========================
    # --- Assert ---
    # ========================
    assert result is None
    mock_collection.find_one_and_update.assert_awaited_once() 

    find_one_update_args, find_one_update_kwargs = mock_collection.find_one_and_update.await_args
    assert len(find_one_update_args) == 2
    call_filter = find_one_update_args[0]
    call_update_doc = find_one_update_args[1]
    assert call_filter == {"id": str(test_task_id), "owner_id": str(owner_id)}
    expected_update_set = update_data.copy()
    expected_update_set["updated_at"] = fixed_timestamp
    assert call_update_doc == {"$set": expected_update_set}
    assert find_one_update_kwargs.get("return_document") is True

    mock_validate.assert_called_once_with(expected_dict_for_validation)

    mock_logger_error.assert_called_once()
    call_args_log, _ = mock_logger_error.call_args
    log_message = call_args_log[0]
    assert f"DB Validation error update_task {test_task_id} owner {owner_id}" in log_message
    assert str(simulated_validation_error) in log_message

@pytest.mark.asyncio
async def test_update_task_generic_exception(mocker, sample_owner_id): 
    """
    Testa update_task quando find_one_and_update levanta exceção genérica.
    """
    # ========================
    # --- Arrange ---
    # ========================
    test_task_id = uuid.uuid4()
    owner_id = sample_owner_id 
    update_data = {"title": "Tentativa de Update"}
    mock_db_object = MagicMock()
    fixed_timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    mock_dt_now = mocker.patch("app.db.task_crud.datetime")
    mock_dt_now.now.return_value = fixed_timestamp
    simulated_db_error = Exception("Simulated generic DB error on update")
    mock_collection = AsyncMock()
    mock_collection.find_one_and_update.side_effect = simulated_db_error
    mocker.patch("app.db.task_crud._get_tasks_collection", return_value=mock_collection)
    mock_validate = mocker.patch("app.db.task_crud.Task.model_validate")
    mock_logger_exception = mocker.patch("app.db.task_crud.logger.exception")

    # ========================
    # --- Act ---
    # ========================
    result = await task_crud.update_task(
        db=mock_db_object,
        task_id=test_task_id,
        owner_id=owner_id, 
        update_data=update_data.copy()
    )

    # ========================
    # --- Assert ---
    # ========================
    assert result is None
    mock_collection.find_one_and_update.assert_awaited_once()
    find_one_update_args, find_one_update_kwargs = mock_collection.find_one_and_update.await_args
    assert len(find_one_update_args) == 2
    call_filter = find_one_update_args[0]
    call_update_doc = find_one_update_args[1]
    assert call_filter == {"id": str(test_task_id), "owner_id": str(owner_id)}
    expected_update_set = update_data.copy()
    expected_update_set["updated_at"] = fixed_timestamp
    assert call_update_doc == {"$set": expected_update_set}
    assert find_one_update_kwargs.get("return_document") is True
    mock_validate.assert_not_called()
    mock_logger_exception.assert_called_once()
    call_args_log, _ = mock_logger_exception.call_args
    log_message = call_args_log[0]
    assert f"DB Error updating task {test_task_id} owner {owner_id}" in log_message
    assert str(simulated_db_error) in log_message

@pytest.mark.asyncio
async def test_update_task_not_found_logs_warning(mocker, sample_owner_id): 
    """
    Testa se update_task loga um aviso quando find_one_and_update retorna None.
    """
    # ========================
    # --- Arrange ---
    # ========================
    test_task_id = uuid.uuid4()
    owner_id = sample_owner_id
    update_data = {"title": "Nome Nao Sera Atualizado"}
    mock_db_object = MagicMock()
    fixed_timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    mock_dt_now = mocker.patch("app.db.task_crud.datetime")
    mock_dt_now.now.return_value = fixed_timestamp
    mock_collection = AsyncMock()
    mock_collection.find_one_and_update.return_value = None
    mocker.patch("app.db.task_crud._get_tasks_collection", return_value=mock_collection)
    mock_validate = mocker.patch("app.db.task_crud.Task.model_validate")
    mock_logger_warning = mocker.patch("app.db.task_crud.logger.warning")

    # ========================
    # --- Act ---
    # ========================
    result = await task_crud.update_task(
        db=mock_db_object,
        task_id=test_task_id,
        owner_id=owner_id,
        update_data=update_data.copy()
    )

    # ========================
    # --- Assert ---
    # ========================
    assert result is None
    mock_collection.find_one_and_update.assert_awaited_once()
    find_one_update_args, find_one_update_kwargs = mock_collection.find_one_and_update.await_args
    assert len(find_one_update_args) == 2
    call_filter = find_one_update_args[0]
    call_update_doc = find_one_update_args[1]
    assert call_filter == {"id": str(test_task_id), "owner_id": str(owner_id)}
    expected_update_set = update_data.copy()
    expected_update_set["updated_at"] = fixed_timestamp
    assert call_update_doc == {"$set": expected_update_set}
    assert find_one_update_kwargs.get("return_document") is True
    mock_validate.assert_not_called()
    mock_logger_warning.assert_called_once()
    call_args_log, _ = mock_logger_warning.call_args
    assert f"Tentativa de atualizar tarefa não encontrada: ID {test_task_id}, Owner ID {owner_id}" in call_args_log[0]

# ===================================
# --- Testes para `delete_task` ---
# ===================================
@pytest.mark.asyncio
async def test_delete_task_successfully():
    """
    Testa a deleção bem-sucedida de uma tarefa.
    Verifica se `delete_one` é chamado com a query correta e se a função
    retorna `True` quando `deleted_count` é 1.
    """
    target_task_id, target_owner_id = uuid.uuid4(), uuid.uuid4()
    print(f"\nTeste: delete_task - Sucesso (Task ID: {target_task_id})")
    # --- Arrange ---
    mock_mongodb_collection = AsyncMock()
    mock_delete_operation_result = MagicMock()
    mock_delete_operation_result.deleted_count = 1 
    mock_mongodb_collection.delete_one = AsyncMock(return_value=mock_delete_operation_result)
    print("  Mock: delete_one para retornar deleted_count=1.")

    with patch("app.db.task_crud._get_tasks_collection", return_value=mock_mongodb_collection):
        # --- Act ---
        print("  Atuando: Chamando task_crud.delete_task...")
        delete_was_successful = await task_crud.delete_task(
            db=MagicMock(), task_id=target_task_id, owner_id=target_owner_id
        )

    # --- Assert ---
    expected_query_for_delete = {"id": str(target_task_id), "owner_id": str(target_owner_id)}
    mock_mongodb_collection.delete_one.assert_awaited_once_with(expected_query_for_delete)
    assert delete_was_successful is True, "delete_task deveria retornar True para deleção bem-sucedida."
    print("  Sucesso: Tarefa deletada e True retornado.")

@pytest.mark.asyncio
async def test_delete_task_when_not_found_or_not_deleted():
    """
    Testa o comportamento de `delete_task` quando a tarefa não é encontrada
    (ou por algum motivo não é deletada), resultando em `deleted_count = 0`.
    Espera-se que a função retorne `False`.
    """
    target_task_id, target_owner_id = uuid.uuid4(), uuid.uuid4()
    print(f"\nTeste: delete_task - Tarefa não encontrada para deleção (Task ID: {target_task_id})")
    # --- Arrange ---
    mock_mongodb_collection = AsyncMock()
    mock_delete_operation_result = MagicMock()
    mock_delete_operation_result.deleted_count = 0
    mock_mongodb_collection.delete_one = AsyncMock(return_value=mock_delete_operation_result)
    print("  Mock: delete_one para retornar deleted_count=0.")

    with patch("app.db.task_crud._get_tasks_collection", return_value=mock_mongodb_collection):
        # --- Act ---
        print("  Atuando: Chamando task_crud.delete_task...")
        delete_was_successful = await task_crud.delete_task(
            db=MagicMock(), task_id=target_task_id, owner_id=target_owner_id
        )

    # --- Assert ---
    mock_mongodb_collection.delete_one.assert_awaited_once() 
    assert delete_was_successful is False, "delete_task deveria retornar False se nenhum documento for deletado."
    print("  Sucesso: Deleção falhou (tarefa não encontrada) e False retornado.")

@pytest.mark.asyncio
async def test_delete_task_generic_exception(mocker, sample_owner_id): 
    """
    Testa delete_task quando delete_one levanta uma exceção genérica.
    """
    # ========================
    # --- Arrange ---
    # ========================
    test_task_id = uuid.uuid4()
    owner_id = sample_owner_id
    mock_db_object = MagicMock()

    simulated_db_error = Exception("Simulated generic DB error on delete")
    mock_collection = AsyncMock()
    mock_collection.delete_one.side_effect = simulated_db_error
    mocker.patch("app.db.task_crud._get_tasks_collection", return_value=mock_collection)

    mock_logger_exception = mocker.patch("app.db.task_crud.logger.exception")

    # ========================
    # --- Act ---
    # ========================
    result = await task_crud.delete_task(
        db=mock_db_object,
        task_id=test_task_id,
        owner_id=owner_id
    )

    # ========================
    # --- Assert ---
    # ========================
    assert result is False 
    mock_collection.delete_one.assert_awaited_once_with({"id": str(test_task_id), "owner_id": str(owner_id)})

    mock_logger_exception.assert_called_once()
    call_args_log, _ = mock_logger_exception.call_args
    log_message = call_args_log[0]
    assert f"DB Error deleting task {test_task_id} owner {owner_id}" in log_message
    assert str(simulated_db_error) in log_message

# ===========================================
# --- Testes para `_parse_sort_params` ---
# ===========================================

@pytest.mark.parametrize(
    "sort_by_input, sort_order_input, expected_output",
    [
        ("due_date", "asc", [("due_date", ASCENDING)]),
        ("priority_score", "desc", [("priority_score", DESCENDING)]),
        ("created_at", "ASC", [("created_at", ASCENDING)]), 
        ("importance", "DESC", [("importance", DESCENDING)]),
        ("due_date", "ascending_string_literal", [("due_date", DESCENDING)]), 
        ("due_date", "", [("due_date", DESCENDING)]),
        ("invalid_sort_field", "desc", None),
        (None, "desc", None),
    ]
)
def test_parse_sort_params_various_inputs(sort_by_input, sort_order_input, expected_output):
    """
    Testa `_parse_sort_params` com várias combinações de entrada
    para `sort_by` e `sort_order`, verificando se a saída corresponde
    ao formato esperado pelo PyMongo para ordenação.
    """
    
    print(f"\nTeste: _parse_sort_params(sort_by='{sort_by_input}', sort_order='{sort_order_input}')")
    actual_output = task_crud._parse_sort_params(sort_by_input, sort_order_input)
    print(f"  Saída Esperada: {expected_output}, Saída Real: {actual_output}")
    assert actual_output == expected_output, \
        f"Para sort_by='{sort_by_input}', sort_order='{sort_order_input}', " \
        f"esperado {expected_output}, mas obtido {actual_output}."
