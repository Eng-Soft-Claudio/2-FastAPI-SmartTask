# tests/test_tasks.py
import pytest
from httpx import AsyncClient
from fastapi import status
from typing import Dict, List, Any
import uuid
import pytest_asyncio
from app.core.config import settings
from app.models.task import TaskStatus
from tests.conftest import auth_headers_a, auth_headers_b

pytestmark = pytest.mark.asyncio

base_task_create_data = {
    "title": "Tarefa de Teste Padrão",
    "description": "Descrição da tarefa padrão",
    "importance": 3,
}

# ==========================================
# --- Testes de Criação ---
# ==========================================
# Pede a fixture correta: auth_headers_a
async def test_create_task_success(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str] # << CORRIGIDO para User A
):
    """Testa a criação bem-sucedida de uma tarefa."""
    url = f"{settings.API_V1_STR}/tasks/"
    response = await test_async_client.post(url, json=base_task_create_data, headers=auth_headers_a) # << CORRIGIDO

    assert response.status_code == status.HTTP_201_CREATED
    response_data = response.json()
    assert response_data["title"] == base_task_create_data["title"]
    assert response_data["importance"] == base_task_create_data["importance"]
    assert "id" in response_data
    assert "owner_id" in response_data
    assert "created_at" in response_data
    assert "priority_score" in response_data

async def test_create_task_unauthorized(test_async_client: AsyncClient):
     """Testa criar tarefa sem autenticação."""
     url = f"{settings.API_V1_STR}/tasks/"
     response = await test_async_client.post(url, json=base_task_create_data) # Não envia headers
     assert response.status_code == status.HTTP_401_UNAUTHORIZED

# ========================================
# --- Testes de Listagem ---
# ========================================
async def test_list_tasks_success(
    test_async_client: AsyncClient, auth_headers_a: Dict[str, str]
):
    """Testa se User A lista apenas suas tarefas criadas neste teste."""
    url = f"{settings.API_V1_STR}/tasks/"
    task1 = {**base_task_create_data, "title": "Task A1 List", "importance": 5, "project": "Alpha"}
    task2 = {**base_task_create_data, "title": "Task A2 List", "status": TaskStatus.IN_PROGRESS.value, "tags": ["urgent"]}
    resp1 = await test_async_client.post(url, json=task1, headers=auth_headers_a)
    assert resp1.status_code == 201
    resp2 = await test_async_client.post(url, json=task2, headers=auth_headers_a)
    assert resp2.status_code == 201

    response = await test_async_client.get(url, headers=auth_headers_a)

    assert response.status_code == status.HTTP_200_OK
    tasks = response.json()
    assert isinstance(tasks, list)
    # Com scope='function', o DB é limpo, então só essas 2 devem existir
    assert len(tasks) == 2
    titles = {task["title"] for task in tasks}
    assert task1["title"] in titles
    assert task2["title"] in titles

async def test_list_tasks_unauthorized(test_async_client: AsyncClient):
     """Testa listar tarefas sem autenticação."""
     url = f"{settings.API_V1_STR}/tasks/"
     response = await test_async_client.get(url)
     assert response.status_code == status.HTTP_401_UNAUTHORIZED

async def test_list_tasks_does_not_show_other_users_tasks(
    test_async_client: AsyncClient, auth_headers_a: Dict[str, str], auth_headers_b: Dict[str, str]
):
    """Garante que User B não vê as tarefas do User A."""
    url = f"{settings.API_V1_STR}/tasks/"
    task_a = {**base_task_create_data, "title": "Tarefa Secreta A"}
    resp_a = await test_async_client.post(url, json=task_a, headers=auth_headers_a)
    assert resp_a.status_code == 201

    response_b = await test_async_client.get(url, headers=auth_headers_b)

    assert response_b.status_code == status.HTTP_200_OK
    tasks_b = response_b.json()
    assert isinstance(tasks_b, list)
    assert len(tasks_b) == 0 # Lista de B deve estar vazia

# ========================================
# --- Testes de Filtros e Ordenação ---
# ========================================

# Criar uma fixture de dados para facilitar testes de filtro/sort
@pytest_asyncio.fixture(scope="function")
async def create_filter_sort_tasks(test_async_client: AsyncClient, auth_headers_a: Dict[str, str]) -> List[Dict]:
    """Cria um conjunto de tarefas com variações para testes."""
    url = f"{settings.API_V1_STR}/tasks/"
    tasks_to_create = [
        {"title": "Filter Task P1 High", "importance": 5, "project": "Filtro", "status": TaskStatus.PENDING.value, "due_date": "2026-01-01", "tags": ["t1", "t2"]},
        {"title": "Filter Task P1 Low", "importance": 1, "project": "Filtro", "status": TaskStatus.PENDING.value, "due_date": "2026-02-01"},
        {"title": "Filter Task P2 Medium", "importance": 3, "project": "Outro", "status": TaskStatus.IN_PROGRESS.value, "tags": ["t2"]},
        {"title": "Filter Task P1 Medium", "importance": 3, "project": "Filtro", "status": TaskStatus.PENDING.value, "due_date": "2025-12-15", "tags": ["t3"]}, 
        {"title": "Filter Task P1 Done", "importance": 4, "project": "Filtro", "status": TaskStatus.COMPLETED.value}, 
    ]
    created_tasks = []
    for task_data in tasks_to_create:
        response = await test_async_client.post(url, json=task_data, headers=auth_headers_a)
        assert response.status_code == 201
        created_tasks.append(response.json())
    return created_tasks

async def test_list_tasks_filter_by_project(
    test_async_client: AsyncClient, auth_headers_a: Dict[str, str], create_filter_sort_tasks: List[Dict]
):
    url = f"{settings.API_V1_STR}/tasks/?project=Filtro"
    response = await test_async_client.get(url, headers=auth_headers_a)
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) == 4 
    assert all(task["project"] == "Filtro" for task in tasks)

async def test_list_tasks_filter_by_status(
    test_async_client: AsyncClient, auth_headers_a: Dict[str, str], create_filter_sort_tasks: List[Dict]
):
    url = f"{settings.API_V1_STR}/tasks/?status=pendente"
    response = await test_async_client.get(url, headers=auth_headers_a)
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) == 3 
    assert all(task["status"] == TaskStatus.PENDING.value for task in tasks)

async def test_list_tasks_filter_by_single_tag(
    test_async_client: AsyncClient, auth_headers_a: Dict[str, str], create_filter_sort_tasks: List[Dict]
):
    url = f"{settings.API_V1_STR}/tasks/?tag=t2"
    response = await test_async_client.get(url, headers=auth_headers_a)
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) == 2 
    titles = {task["title"] for task in tasks}
    assert "Filter Task P1 High" in titles
    assert "Filter Task P2 Medium" in titles

async def test_list_tasks_filter_by_multiple_tags(
    test_async_client: AsyncClient, auth_headers_a: Dict[str, str], create_filter_sort_tasks: List[Dict]
):
    url = f"{settings.API_V1_STR}/tasks/?tag=t1&tag=t2"
    response = await test_async_client.get(url, headers=auth_headers_a)
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) == 1 
    assert tasks[0]["title"] == "Filter Task P1 High"

async def test_list_tasks_sort_by_priority(
    test_async_client: AsyncClient, auth_headers_a: Dict[str, str], create_filter_sort_tasks: List[Dict]
):
    url = f"{settings.API_V1_STR}/tasks/?sort_by=priority_score&sort_order=desc"
    response = await test_async_client.get(url, headers=auth_headers_a)
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) == 5 
    scores = [task.get("priority_score") for task in tasks if task.get("priority_score") is not None]
    assert scores == sorted(scores, reverse=True)

async def test_list_tasks_sort_by_due_date_asc(
    test_async_client: AsyncClient, auth_headers_a: Dict[str, str], create_filter_sort_tasks: List[Dict]
):
    url = f"{settings.API_V1_STR}/tasks/?sort_by=due_date&sort_order=asc"
    response = await test_async_client.get(url, headers=auth_headers_a)
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) == 5
    due_dates = [task.get("due_date") for task in tasks if task.get("due_date")]
    assert due_dates == sorted(due_dates)
    assert tasks[0]["due_date"] is None or tasks[0]["due_date"] == "2025-12-15"

# ========================================
# --- Testes GET /tasks/{id} ---
# ========================================
###################################################
# test_get_specific_task_unauthorized <<<<<FALTANDO
###################################################
async def test_get_specific_task_success(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str] 
):
    """Testa buscar uma tarefa específica do usuário."""
    # Criar uma tarefa usando User A
    url_create = f"{settings.API_V1_STR}/tasks/"
    create_response = await test_async_client.post(url_create, json=base_task_create_data, headers=auth_headers_a) 
    assert create_response.status_code == 201
    task_id = create_response.json()["id"]

    # Buscar a tarefa criada usando User A
    url_get = f"{settings.API_V1_STR}/tasks/{task_id}"
    get_response = await test_async_client.get(url_get, headers=auth_headers_a) 

    assert get_response.status_code == status.HTTP_200_OK
    response_data = get_response.json()
    assert response_data["id"] == task_id
    assert response_data["title"] == base_task_create_data["title"] 


# Usa a fixture correta: auth_headers_a
async def test_get_specific_task_not_found(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str] 
):
    """Testa buscar uma tarefa com ID inexistente."""
    non_existent_id = uuid.uuid4()
    url = f"{settings.API_V1_STR}/tasks/{non_existent_id}"
    response = await test_async_client.get(url, headers=auth_headers_a)
    assert response.status_code == status.HTTP_404_NOT_FOUND

async def test_get_other_user_task_forbidden(
    test_async_client: AsyncClient, auth_headers_a: Dict[str, str], auth_headers_b: Dict[str, str]
):
    """Garante que User B não consegue obter a tarefa do User A por ID."""
    # Arrange: User A cria tarefa
    url = f"{settings.API_V1_STR}/tasks/"
    task_a_data = {**base_task_create_data, "title": "Task A para GET"}
    resp_a = await test_async_client.post(url, json=task_a_data, headers=auth_headers_a)
    assert resp_a.status_code == 201
    task_a_id = resp_a.json()["id"]

    # Act: User B tenta obter a tarefa de User A
    url_get = f"{settings.API_V1_STR}/tasks/{task_a_id}"
    response_b = await test_async_client.get(url_get, headers=auth_headers_b)

    # Assert: Deve falhar com 404 (pois o findOne combina id E owner_id)
    assert response_b.status_code == status.HTTP_404_NOT_FOUND

# ========================================
# --- Testes PUT /tasks/{id} (NOVOS) ---
# ========================================
async def test_update_task_success(
    test_async_client: AsyncClient, auth_headers_a: Dict[str, str]
):
    """Testa atualizar uma tarefa com sucesso."""
    # Arrange: Criar tarefa
    url = f"{settings.API_V1_STR}/tasks/"
    create_resp = await test_async_client.post(url, json=base_task_create_data, headers=auth_headers_a)
    assert create_resp.status_code == 201
    task_id = create_resp.json()["id"]
    original_score = create_resp.json()["priority_score"]

    # Act: Atualizar a tarefa
    url_put = f"{settings.API_V1_STR}/tasks/{task_id}"
    update_payload = {"title": "Título Atualizado", "status": TaskStatus.COMPLETED.value, "importance": 5} 
    response = await test_async_client.put(url_put, json=update_payload, headers=auth_headers_a)

    # Assert
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == task_id
    assert data["title"] == update_payload["title"]
    assert data["status"] == update_payload["status"]
    assert data["importance"] == update_payload["importance"]
    assert "updated_at" in data and data["updated_at"] is not None
    assert "priority_score" in data
    # Verificar se score mudou (importância 3 -> 5)
    assert data["priority_score"] != original_score

async def test_update_task_not_found(
    test_async_client: AsyncClient, auth_headers_a: Dict[str, str]
):
    """Testa atualizar tarefa inexistente."""
    url = f"{settings.API_V1_STR}/tasks/{uuid.uuid4()}" 
    response = await test_async_client.put(url, json={"title": "Inexistente"}, headers=auth_headers_a)
    assert response.status_code == status.HTTP_404_NOT_FOUND

async def test_update_other_user_task_forbidden(
    test_async_client: AsyncClient, auth_headers_a: Dict[str, str], auth_headers_b: Dict[str, str]
):
    """Testa se User B não pode atualizar tarefa do User A."""
    # Arrange: User A cria tarefa
    url = f"{settings.API_V1_STR}/tasks/"
    resp_a = await test_async_client.post(url, json=base_task_create_data, headers=auth_headers_a)
    assert resp_a.status_code == 201
    task_a_id = resp_a.json()["id"]

    # Act: User B tenta atualizar
    url_put = f"{settings.API_V1_STR}/tasks/{task_a_id}"
    response_b = await test_async_client.put(url_put, json={"title": "Hackeado?"}, headers=auth_headers_b)

    # Assert: Falha com 404
    assert response_b.status_code == status.HTTP_404_NOT_FOUND

async def test_get_specific_task_success(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str] # << CORRIGIDO para User A
):
    """Testa buscar uma tarefa específica do usuário A."""
    url_create = f"{settings.API_V1_STR}/tasks/"
    create_response = await test_async_client.post(url_create, json=base_task_create_data, headers=auth_headers_a) # << CORRIGIDO
    assert create_response.status_code == 201
    task_id = create_response.json()["id"]

    url_get = f"{settings.API_V1_STR}/tasks/{task_id}"
    get_response = await test_async_client.get(url_get, headers=auth_headers_a) # << CORRIGIDO

    assert get_response.status_code == status.HTTP_200_OK
    response_data = get_response.json()
    assert response_data["id"] == task_id
    assert response_data["title"] == base_task_create_data["title"]


# Pede a fixture correta: auth_headers_a
async def test_get_specific_task_not_found(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str] # << CORRIGIDO para User A
):
    """Testa buscar uma tarefa com ID inexistente."""
    non_existent_id = uuid.uuid4()
    url = f"{settings.API_V1_STR}/tasks/{non_existent_id}"
    response = await test_async_client.get(url, headers=auth_headers_a) # << CORRIGIDO
    assert response.status_code == status.HTTP_404_NOT_FOUND

# Nenhuma mudança necessária
async def test_get_specific_task_unauthorized(test_async_client: AsyncClient):
     """Testa buscar tarefa sem autenticação."""
     some_valid_id_placeholder = uuid.uuid4()
     url = f"{settings.API_V1_STR}/tasks/{some_valid_id_placeholder}"
     response = await test_async_client.get(url)
     assert response.status_code == status.HTTP_401_UNAUTHORIZED

# Nenhuma mudança necessária
async def test_get_other_user_task_forbidden(
    test_async_client: AsyncClient, auth_headers_a: Dict[str, str], auth_headers_b: Dict[str, str]
):
    """Garante que User B não consegue obter a tarefa do User A por ID."""
    url = f"{settings.API_V1_STR}/tasks/"
    task_a_data = {**base_task_create_data, "title": "Task A para GET"}
    resp_a = await test_async_client.post(url, json=task_a_data, headers=auth_headers_a)
    assert resp_a.status_code == 201
    task_a_id = resp_a.json()["id"]

    url_get = f"{settings.API_V1_STR}/tasks/{task_a_id}"
    response_b = await test_async_client.get(url_get, headers=auth_headers_b)

    assert response_b.status_code == status.HTTP_404_NOT_FOUND

# ==========================================
# --- Testes DELETE /tasks/{id} (NOVOS) ---
# ==========================================
async def test_delete_task_success(
    test_async_client: AsyncClient, auth_headers_a: Dict[str, str]
):
    """Testa deletar uma tarefa com sucesso."""
    # Arrange: Criar tarefa
    url = f"{settings.API_V1_STR}/tasks/"
    create_resp = await test_async_client.post(url, json=base_task_create_data, headers=auth_headers_a)
    assert create_resp.status_code == 201
    task_id = create_resp.json()["id"]

    # Act: Deletar a tarefa
    url_delete = f"{settings.API_V1_STR}/tasks/{task_id}"
    delete_response = await test_async_client.delete(url_delete, headers=auth_headers_a)

    # Assert (Delete)
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT

    # Assert (Verificar Get posterior falha)
    url_get = f"{settings.API_V1_STR}/tasks/{task_id}"
    get_response = await test_async_client.get(url_get, headers=auth_headers_a)
    assert get_response.status_code == status.HTTP_404_NOT_FOUND


async def test_delete_task_not_found(
    test_async_client: AsyncClient, auth_headers_a: Dict[str, str]
):
    """Testa deletar tarefa inexistente."""
    url = f"{settings.API_V1_STR}/tasks/{uuid.uuid4()}" # ID aleatório
    response = await test_async_client.delete(url, headers=auth_headers_a)
    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_delete_other_user_task_forbidden(
    test_async_client: AsyncClient, auth_headers_a: Dict[str, str], auth_headers_b: Dict[str, str]
):
    """Testa se User B não pode deletar tarefa do User A."""
    # Arrange: User A cria tarefa
    url = f"{settings.API_V1_STR}/tasks/"
    resp_a = await test_async_client.post(url, json=base_task_create_data, headers=auth_headers_a)
    assert resp_a.status_code == 201
    task_a_id = resp_a.json()["id"]

    # Act: User B tenta deletar
    url_delete = f"{settings.API_V1_STR}/tasks/{task_a_id}"
    response_b = await test_async_client.delete(url_delete, headers=auth_headers_b)

    # Assert: Falha com 404
    assert response_b.status_code == status.HTTP_404_NOT_FOUND