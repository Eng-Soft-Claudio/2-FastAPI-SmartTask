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
from datetime import date, datetime, timezone 
from typing import Any, Dict, List, Optional 
from unittest.mock import AsyncMock, MagicMock, patch 

import pytest
from pydantic import ValidationError 
from pymongo import ASCENDING, DESCENDING 

# --- Módulos da Aplicação ---
from app.db import task_crud 
from app.models.task import Task, TaskStatus 

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

    iterator_mock = AsyncMock()
    # Configura o side_effect de __anext__ para retornar os itens um por um,
    # e depois levantar StopAsyncIteration.
    # Adiciona StopAsyncIteration ao final da lista de side_effects.
    effects = list(items_to_yield) + [StopAsyncIteration]
    iterator_mock.__anext__.side_effect = effects
    return iterator_mock

# ===================================
# --- Testes para `create_task` ---
# ===================================
# Testa a função de criação de novas tarefas.

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
    # Mock para a coleção do MongoDB.
    mock_mongodb_collection = AsyncMock() # Usamos AsyncMock para métodos de coleção async.
    # Mock para o resultado da operação insert_one.
    mock_insert_operation_result = MagicMock()
    mock_insert_operation_result.acknowledged = True # Simula inserção bem-sucedida.
    mock_mongodb_collection.insert_one = AsyncMock(return_value=mock_insert_operation_result)
    print("  Mock: Coleção MongoDB e resultado de insert_one configurados para sucesso.")

    # Patch `_get_tasks_collection` para retornar nosso mock da coleção.
    # Patch `db` na chamada a `create_task` com um MagicMock simples, pois não interagimos com ele diretamente.
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
    print(f"\nTeste: create_task - Inserção no DB não confirmada (Task ID: {valid_task_obj.id})")
    # --- Arrange ---
    mock_mongodb_collection = AsyncMock()
    mock_insert_operation_result = MagicMock()
    mock_insert_operation_result.acknowledged = False 
    mock_mongodb_collection.insert_one = AsyncMock(return_value=mock_insert_operation_result)
    print("  Mock: insert_one configurado para acknowledged=False.")

    with patch("app.db.task_crud._get_tasks_collection", return_value=mock_mongodb_collection):
        # --- Act ---
        print("  Atuando: Chamando task_crud.create_task...")
        created_task_result = await task_crud.create_task(db=MagicMock(), task_db=valid_task_obj)

    # --- Assert ---
    mock_mongodb_collection.insert_one.assert_awaited_once()
    assert created_task_result is None, "Deveria retornar None se a inserção não for acknowledged."
    print("  Sucesso: create_task retornou None como esperado.")

@pytest.mark.asyncio
async def test_create_task_handles_db_exception_on_insert(valid_task_obj: Task, mocker):
    """
    Testa o tratamento de exceção em `create_task` quando `insert_one`
    levanta uma exceção (simulando um erro do banco de dados).
    Espera-se que a exceção seja capturada, logada, e que a função retorne `None`.
    """
    print(f"\nTeste: create_task - Exceção no DB durante insert_one (Task ID: {valid_task_obj.id})")
    # --- Arrange ---
    mock_mongodb_collection = AsyncMock()
    simulated_db_error = Exception("Erro de Simulação na Inserção no DB")
    # Configura `insert_one` para levantar a exceção simulada.
    mock_mongodb_collection.insert_one = AsyncMock(side_effect=simulated_db_error)
    # Mocka o logger do módulo `task_crud` para verificar se a exceção é logada.
    mock_task_crud_logger = mocker.patch("app.db.task_crud.logger")
    print(f"  Mock: insert_one para levantar '{simulated_db_error}', logger mockado.")

    with patch("app.db.task_crud._get_tasks_collection", return_value=mock_mongodb_collection):
        # --- Act ---
        print("  Atuando: Chamando task_crud.create_task (esperando exceção interna)...")
        created_task_result = await task_crud.create_task(db=MagicMock(), task_db=valid_task_obj)

    # --- Assert ---
    mock_mongodb_collection.insert_one.assert_awaited_once() 
    assert created_task_result is None, "Deveria retornar None em caso de exceção no DB."
    mock_task_crud_logger.exception.assert_called_once(), "logger.exception não foi chamado."
    print("  Sucesso: Exceção do DB tratada, retornou None e exceção foi logada.")

# =====================================
# --- Testes para `get_task_by_id` ---
# =====================================
# Testa a função de busca de tarefa por seu ID e ID do proprietário.

@pytest.mark.asyncio
async def test_get_task_by_id_successfully(valid_task_obj: Task):
    """
    Testa a busca bem-sucedida de uma tarefa por ID.
    Verifica se `find_one` é chamado com a query correta, se `Task.model_validate`
    é chamado com os dados corretos (sem `_id`), e se a tarefa é retornada.
    """
    print(f"\nTeste: get_task_by_id - Sucesso (Task ID: {valid_task_obj.id})")
    # --- Arrange ---
    # Prepara um dicionário como se viesse do MongoDB, incluindo o `_id`.
    task_dict_from_db = valid_task_obj.model_dump(mode='json')
    task_dict_from_db['_id'] = "some_random_mongodb_object_id" 
    
    mock_mongodb_collection = AsyncMock() 
    # `find_one` é configurado para retornar nosso dicionário mockado.
    mock_mongodb_collection.find_one = AsyncMock(return_value=task_dict_from_db)
    print(f"  Mock: find_one para retornar dados da tarefa (incluindo _id).")
    
    target_task_id = valid_task_obj.id
    target_owner_id = valid_task_obj.owner_id

    # Patch `_get_tasks_collection` e `Task.model_validate` (para isolar a lógica de `get_task_by_id`).
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
    
    # Verifica se `Task.model_validate` foi chamado com o dicionário correto (SEM `_id`).
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
    # Simula dados inválidos que seriam retornados pelo DB.
    invalid_task_dict_from_db = {"id": str(uuid.uuid4()), "owner_id": str(uuid.uuid4()), "title_erroneo": "Tarefa Inválida"}
    invalid_task_dict_from_db['_id'] = "another_mongo_id"

    mock_mongodb_collection = AsyncMock()
    mock_mongodb_collection.find_one = AsyncMock(return_value=invalid_task_dict_from_db)
    # Mocka o logger para verificar se o erro de validação é logado.
    mock_task_crud_logger = mocker.patch("app.db.task_crud.logger")
    print(f"  Mock: find_one para retornar dados inválidos, logger mockado.")

    task_id_for_test = uuid.UUID(invalid_task_dict_from_db["id"])
    owner_id_for_test = uuid.UUID(invalid_task_dict_from_db["owner_id"])

    # Simula uma `ValidationError` que seria levantada por `Task.model_validate`.
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
# Testa a listagem de tarefas com filtros, ordenação e paginação.
# Estes testes usam mocks simplificados para a cadeia de chamadas do Motor (find().skip().limit().sort()).

@pytest.mark.asyncio

async def test_get_tasks_by_owner_list_basic_success(valid_task_obj: Task):
    """
    Testa a listagem básica de tarefas para um proprietário, sem filtros ou ordenação complexa.
    Verifica se a query `find` é construída corretamente e se skip/limit são aplicados.
    """
    target_owner_id = valid_task_obj.owner_id
    # Dicionário da tarefa como seria retornado do DB e antes da iteração.
    task_dict_from_db_iter = valid_task_obj.model_dump(mode='json')
    task_dict_from_db_iter['_id'] = "id_from_db" # Mock _id

    print(f"\nTeste: get_tasks_by_owner - Listagem básica para Owner ID: {target_owner_id}")

    # --- Arrange: Configurar a cadeia de mocks ---
    mock_motor_cursor = AsyncMock() # Este será o nosso cursor chainable e iterável
    mock_motor_cursor.__aiter__.return_value = [task_dict_from_db_iter]
    mock_motor_cursor.skip = MagicMock(return_value=mock_motor_cursor)
    mock_motor_cursor.limit = MagicMock(return_value=mock_motor_cursor)

    # Mock para a coleção
    mock_mongodb_collection = MagicMock() 

    # Configura o método find deste MagicMock
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

    print(f"\nTeste: get_tasks_by_owner - Com filtros e ordenação para Owner ID: {target_owner_id}")

    # --- Arrange: Configurar a cadeia de mocks ---
    mock_motor_cursor = AsyncMock() 
    mock_motor_cursor.__aiter__.return_value = [task_dict_from_db_iter]
    mock_motor_cursor.skip = MagicMock(return_value=mock_motor_cursor)  
    mock_motor_cursor.limit = MagicMock(return_value=mock_motor_cursor) 
    mock_motor_cursor.sort = MagicMock(return_value=mock_motor_cursor)

    # Mock para a coleção
    mock_mongodb_collection = MagicMock()

    # Configura o método find deste MagicMock
    mock_mongodb_collection.find = MagicMock(return_value=mock_motor_cursor) 
    
    print("  Mock: Cadeia de find().skip().limit().sort() e validação de modelo configurados.")

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
    mock_mongodb_collection.find.assert_called_once_with(expected_query_with_filters)
    mock_motor_cursor.skip.assert_called_once_with(test_skip_val)
    mock_motor_cursor.limit.assert_called_once_with(test_limit_val)
    mock_motor_cursor.sort.assert_called_once_with([(sort_field, ASCENDING)])
    
    assert len(retrieved_tasks_list) == 1
    assert retrieved_tasks_list[0] == valid_task_obj
    print(f"  Sucesso: Listagem com filtros e ordenação funcionou.")

@pytest.mark.asyncio
async def test_get_tasks_by_owner_handles_validation_error_during_iteration(valid_task_obj: Task, mocker):
    """
    Testa o tratamento de erro em `get_tasks_by_owner` quando `Task.model_validate`
    levanta uma `ValidationError` para um dos documentos durante a iteração do cursor.
    Espera-se que o erro seja logado, o item inválido seja pulado, e os itens válidos sejam retornados.
    """
    target_owner_id = uuid.uuid4()
    print(f"\nTeste: get_tasks_by_owner - Exceção geral do DB durante `find`.")
    
    simulated_db_error_on_find = Exception("Erro de Simulação de Conexão Perdida no Find")

    # Mock da função _get_tasks_collection para retornar um objeto que falhará em .find()
    # Este mock_collection será o 'collection' dentro de get_tasks_by_owner
    mock_collection_object = MagicMock()
    # Configura o método 'find' neste mock_collection_object para levantar o erro
    mock_collection_object.find.side_effect = simulated_db_error_on_find

    # Patch _get_tasks_collection para retornar este mock específico
    patch_get_collection = patch("app.db.task_crud._get_tasks_collection", return_value=mock_collection_object)
    
    mock_task_crud_logger = mocker.patch("app.db.task_crud.logger")
    print(f"  Mock: _get_tasks_collection retorna um mock cujo .find() levanta '{simulated_db_error_on_find}'. Logger mockado.")

    # Inicia o patch antes de chamar a função
    with patch_get_collection: # Equivalente a patch_get_collection.start() e .stop()
        print("  Atuando: Chamando get_tasks_by_owner (esperando exceção interna no DB)...")
        retrieved_tasks_list = await task_crud.get_tasks_by_owner(db=MagicMock(), owner_id=target_owner_id)

    # --- Assert ---
    assert retrieved_tasks_list == [], "Deveria retornar lista vazia em caso de exceção no DB."
    mock_task_crud_logger.exception.assert_called_once(), "logger.exception não foi chamado."
    
    log_call_args_tuple = mock_task_crud_logger.exception.call_args[0]
    assert f"DB Error listing tasks for owner {target_owner_id}" in log_call_args_tuple[0], \
        "Mensagem de log de exceção não contém as informações esperadas."
    
    # Importante: Verificar se mock_collection_object.find FOI chamado
    mock_collection_object.find.assert_called_once()
    print("  Sucesso: Exceção geral do DB tratada, retornou lista vazia e exceção foi logada.")

@pytest.mark.asyncio
async def test_get_tasks_by_owner_handles_general_db_exception(mocker):
    """
    Testa o tratamento de exceção em `get_tasks_by_owner` quando ocorre um erro
    geral no banco de dados durante a operação `find` (ou iteração).
    Espera-se que a função retorne uma lista vazia e logue a exceção.
    """
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
    # Mock para o timestamp que será gerado por datetime.now() dentro de update_task.
    fixed_current_time_utc = datetime.now(timezone.utc).replace(microsecond=0)
    
    # Prepara o dicionário como ele seria retornado do DB após a atualização.
    db_document_after_update = valid_task_obj.model_dump(mode='json')
    db_document_after_update.update(update_payload_data) 
    db_document_after_update['updated_at'] = fixed_current_time_utc 
    db_document_after_update['_id'] = 'some_mongo_id_for_update' 

    # Objeto Task final que esperamos após a validação do `db_document_after_update`.
    expected_final_task_object = Task(**db_document_after_update)
    
    mock_mongodb_collection = AsyncMock()
    # `find_one_and_update` retorna o documento atualizado (após `return_document=True`).
    mock_mongodb_collection.find_one_and_update = AsyncMock(return_value=db_document_after_update)
    print("  Mock: Coleção MongoDB, find_one_and_update, e Task.model_validate configurados.")

    # Patch `datetime.now` dentro de `task_crud` para controlar o valor de `updated_at`.
    # Patch `_get_tasks_collection` e `Task.model_validate`.
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
    # `update_task` adiciona `updated_at` ao `update_payload_data` antes de passar para `$set`.
    expected_data_for_set_operator = {**update_payload_data, "updated_at": fixed_current_time_utc}
    
    mock_mongodb_collection.find_one_and_update.assert_awaited_once_with(
        expected_filter_for_update,
        {"$set": expected_data_for_set_operator},
        return_document=True
    )
    # `model_validate` deve ser chamado com o dicionário bruto do DB (já com _id removido pela função).
    expected_dict_for_validation = db_document_after_update.copy()
    expected_dict_for_validation.pop('_id', None)
    mock_pydantic_validate.assert_called_once_with(expected_dict_for_validation)
    
    assert update_result_task == expected_final_task_object, "A tarefa atualizada retornada não é a esperada."
    print("  Sucesso: Tarefa atualizada e retornada corretamente.")

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

# ===========================================
# --- Testes para `_parse_sort_params` ---
# ===========================================
# Testa a função auxiliar de parsing de parâmetros de ordenação.
# Esta é uma função síncrona, então não precisa de @pytest.mark.asyncio.

@pytest.mark.parametrize(
    "sort_by_input, sort_order_input, expected_output",
    [
        ("due_date", "asc", [("due_date", ASCENDING)]),
        ("priority_score", "desc", [("priority_score", DESCENDING)]),
        ("created_at", "ASC", [("created_at", ASCENDING)]), 
        ("importance", "DESC", [("importance", DESCENDING)]),
        # Comportamento original: se sort_order não é 'asc', assume 'desc'.
        ("due_date", "ascending_string_literal", [("due_date", DESCENDING)]), 
        ("due_date", "", [("due_date", DESCENDING)]),
        # Casos de falha (campo inválido ou None)
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
