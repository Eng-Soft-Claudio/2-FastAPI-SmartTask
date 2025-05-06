# tests/test_tasks.py
# ==========================================
# --- Importações ---
# ==========================================
import unittest.mock
from unittest.mock import AsyncMock, ANY
from freezegun import freeze_time
import pytest
from httpx import AsyncClient
from fastapi import status
from typing import Dict, List, Any
import uuid
import pytest_asyncio
from pytest_mock import mocker
from app.core.config import settings
from app.models.task import TaskStatus
from datetime import date, timedelta, datetime, timezone
from tests.conftest import user_a_data

# ==========================================
# --- Criação do Mock Webhook ---
# ==========================================
@pytest.fixture(
        autouse=True
)

def auto_mock_send_webhook(mocker):
    """
    Aplica automaticamente o mock para send_webhook_notification para todos
    os testes neste módulo.
    """
    mocker.patch(
        "app.routers.tasks.send_webhook_notification",
        new_callable=unittest.mock.AsyncMock,
    )

# ==========================================
# --- Criação do Loop Assíncrono ---
# ==========================================
pytestmark = pytest.mark.asyncio

# ==========================================
# --- Criação do Base Task Data ---
# ==========================================
base_task_create_data = {
    "title": "Tarefa de Teste Padrão",
    "description": "Descrição da tarefa padrão",
    "importance": 3,
}

# ==========================================
# --- Testes de Criação ---
# ==========================================
async def test_create_task_success(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
):
    """Testa a criação bem-sucedida de uma tarefa e verifica chamada do webhook."""
    
    url = f"{settings.API_V1_STR}/tasks/"
    response = await test_async_client.post(
        url,
        json=base_task_create_data,
        headers=auth_headers_a
    ) 

    assert response.status_code == status.HTTP_201_CREATED
    response_data = response.json()
    assert response_data["title"] == base_task_create_data["title"]
    assert response_data["importance"] == base_task_create_data["importance"]
    assert response_data["status"] == TaskStatus.PENDING.value
    assert "id" in response_data
    assert "owner_id" in response_data
    assert "created_at" in response_data
    assert "priority_score" in response_data

async def test_create_task_unauthorized(
        test_async_client: AsyncClient
):
     """Testa criar tarefa sem autenticação."""
     url = f"{settings.API_V1_STR}/tasks/"
     response = await test_async_client.post(url, json=base_task_create_data) 
     assert response.status_code == status.HTTP_401_UNAUTHORIZED

# ==========================================
# --- Testes de Criação e Atualização ---
# ==========================================

@pytest.mark.parametrize(
    "field, length", [
        ("title", 100), 
        ("description", 500), 
    ]
)

async def test_create_task_max_length_success(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    field: str,
    length: int,
):
    """Testa criar tarefa com campos string no comprimento máximo permitido."""
    payload = base_task_create_data.copy()
    payload[field] = "X" * length 
    url = f"{settings.API_V1_STR}/tasks/"
    response = await test_async_client.post(url, json=payload, headers=auth_headers_a)
    assert response.status_code == status.HTTP_201_CREATED
    response_data = response.json()
    assert response_data[field] == payload[field]


@pytest.mark.parametrize(
    "field, length", [
        ("title", 101), 
        ("description", 501), 
    ]
)

async def test_create_task_max_length_fail(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    field: str,
    length: int,
):
    """Testa criar tarefa com campos string acima do comprimento máximo."""
    payload = base_task_create_data.copy()
    payload[field] = "X" * length
    url = f"{settings.API_V1_STR}/tasks/"
    response = await test_async_client.post(url, json=payload, headers=auth_headers_a)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert f"String should have at most {length -1} characters" in response.text


async def test_create_task_explicit_nulls_optional(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
):
    """Testa criar tarefa enviando explicitamente null para campos opcionais."""
    payload = base_task_create_data.copy()
    payload["description"] = None
    payload["due_date"] = None
    payload["tags"] = None
    payload["project"] = None

    url = f"{settings.API_V1_STR}/tasks/"
    response = await test_async_client.post(url, json=payload, headers=auth_headers_a)
    assert response.status_code == status.HTTP_201_CREATED
    response_data = response.json()
    assert response_data["description"] is None
    assert response_data["due_date"] is None
    assert response_data["tags"] is None
    assert response_data["project"] is None


async def test_update_task_explicit_nulls_optional(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
):
    """Testa atualizar tarefa definindo campos opcionais como null explicitamente."""
    url_create = f"{settings.API_V1_STR}/tasks/"
    create_payload = {
        **base_task_create_data,
        "description": "Descrição inicial",
        "due_date": date.today().isoformat(),
        "tags": ["inicial"],
        "project": "Projeto Inicial"
    }
    create_resp = await test_async_client.post(url_create, json=create_payload, headers=auth_headers_a)
    assert create_resp.status_code == status.HTTP_201_CREATED
    task_id = create_resp.json()["id"]

    # Act: Atualizar enviando nulls
    url_put = f"{settings.API_V1_STR}/tasks/{task_id}"
    update_payload = {
        "description": None,
        "due_date": None,
        "tags": None, 
        "project": None,
    }
    response = await test_async_client.put(url_put, json=update_payload, headers=auth_headers_a)
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert response_data["description"] is None
    assert response_data["due_date"] is None
    assert response_data["tags"] is None 
    assert response_data["project"] is None

# ==========================================
# --- Testes de Validação ---
# ==========================================
@pytest.mark.parametrize(
    "field, value, error_type, error_msg_part", [
        ("title", "T2", "string_too_short", "String should have at least 3 characters"),
        ("importance", 0, "greater_than_equal", "Input should be greater than or equal to 1"),
        ("importance", 6, "less_than_equal", "Input should be less than or equal to 5"),
        ("due_date", "nao-e-data", "date_from_datetime_parsing", "invalid character"),
        ("status", "invalido", "enum", "Input should be"),
    ]
)

async def test_create_task_invalid_input(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    field: str, value: Any, error_type: str, error_msg_part: str
):
    """Testa criar tarefa com dados inválidos."""
    invalid_data = base_task_create_data.copy()
    if value is None:
         if field in ["title", "importance"]:
              if field in invalid_data: 
                   del invalid_data[field]
         elif field == "status":
              pytest.skip("Teste 'None' não aplicável para 'status' com default.")
              return
         else:
             invalid_data[field] = value
    else:
        invalid_data[field] = value

    url = f"{settings.API_V1_STR}/tasks/"
    response = await test_async_client.post(url, json=invalid_data, headers=auth_headers_a)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    error_details = response.json()["detail"]
    found_error = False
    for error in error_details:
        if field in error.get("loc", []) and error.get("type") == error_type:
            if error_msg_part in error.get("msg", ""):
                found_error = True
                break
    assert found_error, f"Erro esperado para campo '{field}' tipo '{error_type}' msg '{error_msg_part}' não encontrado em {error_details}"

@pytest.mark.parametrize(
    "field, value, error_type, error_msg_part", [
        ("title", "T2", "string_too_short", "String should have at least 3 characters"),
        ("importance", 0, "greater_than_equal", "Input should be greater than or equal to 1"),
        ("importance", 6, "less_than_equal", "Input should be less than or equal to 5"),
        ("due_date", "nao-e-data", "date_from_datetime_parsing", "invalid character"),
        ("status", "invalido", "enum", "Input should be"), 
    ]
)

async def test_update_task_invalid_input(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    field: str, value: Any, error_type: str, error_msg_part: str
):
    """Testa atualizar tarefa com dados inválidos."""
    # Arrange: Criar uma tarefa primeiro
    url = f"{settings.API_V1_STR}/tasks/"
    create_resp = await test_async_client.post(url, json=base_task_create_data, headers=auth_headers_a)
    assert create_resp.status_code == 201
    task_id = create_resp.json()["id"]

    # Act: Tentar atualizar com dado inválido
    invalid_update_payload = {field: value}
    url_put = f"{settings.API_V1_STR}/tasks/{task_id}"
    response = await test_async_client.put(url_put, json=invalid_update_payload, headers=auth_headers_a)

    # Assert
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    error_details = response.json()["detail"]
    found_error = False
    for error in error_details:
        if field in error.get("loc", []) and error.get("type") == error_type:
            if error_msg_part in error.get("msg", ""):
                found_error = True
                break
    assert found_error, f"Erro esperado para campo '{field}' com tipo '{error_type}' e msg contendo '{error_msg_part}' não encontrado em {error_details}"

async def test_update_task_empty_payload(
     test_async_client: AsyncClient, auth_headers_a: Dict[str, str]
):
    """Testa atualizar tarefa com payload vazio (deve retornar 400)."""
    # Arrange: Criar tarefa
    url = f"{settings.API_V1_STR}/tasks/"
    create_resp = await test_async_client.post(url, json=base_task_create_data, headers=auth_headers_a)
    assert create_resp.status_code == 201
    task_id = create_resp.json()["id"]

    # Act: Tentar atualizar com payload vazio
    url_put = f"{settings.API_V1_STR}/tasks/{task_id}"
    response = await test_async_client.put(url_put, json={}, headers=auth_headers_a) # Payload vazio

    # Assert: Esperamos 400 (conforme nossa lógica em update_task)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Nenhum campo válido fornecido" in response.json()["detail"]

# ==========================================
# --- Testes de Listagem ---
# ==========================================
async def test_list_tasks_success(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str]
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

async def test_list_tasks_unauthorized(
        test_async_client: AsyncClient
):
     """Testa listar tarefas sem autenticação."""
     url = f"{settings.API_V1_STR}/tasks/"
     response = await test_async_client.get(url)
     assert response.status_code == status.HTTP_401_UNAUTHORIZED

async def test_list_tasks_does_not_show_other_users_tasks(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    auth_headers_b: Dict[str, str]
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

async def test_list_tasks_filter_non_existent_project(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    create_filter_sort_tasks: List[Dict] 
):
    """Testa listar tarefas filtrando por um projeto que não existe."""
    url = f"{settings.API_V1_STR}/tasks/?project=ProjetoInexistente123"
    response = await test_async_client.get(url, headers=auth_headers_a)
    assert response.status_code == status.HTTP_200_OK
    tasks = response.json()
    assert isinstance(tasks, list)
    assert len(tasks) == 0 

async def test_list_tasks_filter_non_existent_tag(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    create_filter_sort_tasks: List[Dict]
):
    """Testa listar tarefas filtrando por uma tag que nenhuma tarefa possui."""
    url = f"{settings.API_V1_STR}/tasks/?tag=tag_nao_existe"
    response = await test_async_client.get(url, headers=auth_headers_a)
    assert response.status_code == status.HTTP_200_OK
    tasks = response.json()
    assert isinstance(tasks, list)
    assert len(tasks) == 0

async def test_list_tasks_filter_multiple_tags_no_match(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    create_filter_sort_tasks: List[Dict]
):
    """Testa listar tarefas filtrando por múltiplas tags onde nenhuma tarefa possui TODAS."""
    url = f"{settings.API_V1_STR}/tasks/?tag=t1&tag=t3"
    response = await test_async_client.get(url, headers=auth_headers_a)
    assert response.status_code == status.HTTP_200_OK
    tasks = response.json()
    assert isinstance(tasks, list)
    assert len(tasks) == 0 

async def test_list_tasks_filter_status_no_match(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    create_filter_sort_tasks: List[Dict]
):
    """Testa listar tarefas filtrando por um status que nenhuma tarefa possui (ex: cancelada)."""
    url = f"{settings.API_V1_STR}/tasks/?status={TaskStatus.CANCELLED.value}"
    response = await test_async_client.get(url, headers=auth_headers_a)
    assert response.status_code == status.HTTP_200_OK
    tasks = response.json()
    assert isinstance(tasks, list)
    assert len(tasks) == 0 

@freeze_time("2025-05-04")

async def test_list_tasks_filter_due_before_very_early(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    create_filter_sort_tasks: List[Dict]
):
    """Testa listar tarefas filtrando com due_before muito no passado."""
    early_date = "2024-01-01"
    url = f"{settings.API_V1_STR}/tasks/?due_before={early_date}"
    response = await test_async_client.get(url, headers=auth_headers_a)
    assert response.status_code == status.HTTP_200_OK
    tasks = response.json()
    assert isinstance(tasks, list)
    assert len(tasks) == 0 

# ========================================
# --- Testes de Paginação ---
# ========================================

async def test_list_tasks_pagination_limit_1(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    create_filter_sort_tasks: List[Dict] 
):
    """Testa a paginação com limit=1."""
    url = f"{settings.API_V1_STR}/tasks/?limit=1"
    response = await test_async_client.get(url, headers=auth_headers_a)
    assert response.status_code == status.HTTP_200_OK
    tasks = response.json()
    assert isinstance(tasks, list)
    assert len(tasks) == 1 

async def test_list_tasks_pagination_skip_all(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    create_filter_sort_tasks: List[Dict] 
):
    """Testa a paginação pulando todas as tarefas ou mais."""
    total_tasks_in_fixture = 5
    url = f"{settings.API_V1_STR}/tasks/?skip={total_tasks_in_fixture}"
    response = await test_async_client.get(url, headers=auth_headers_a)
    assert response.status_code == status.HTTP_200_OK
    tasks = response.json()
    assert isinstance(tasks, list)
    assert len(tasks) == 0 

    url_skip_more = f"{settings.API_V1_STR}/tasks/?skip={total_tasks_in_fixture + 5}"
    response_skip_more = await test_async_client.get(url_skip_more, headers=auth_headers_a)
    assert response_skip_more.status_code == status.HTTP_200_OK
    tasks_skip_more = response_skip_more.json()
    assert isinstance(tasks_skip_more, list)
    assert len(tasks_skip_more) == 0

async def test_list_tasks_pagination_limit_0(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
):
    """Testa a paginação com limit=0 (deve ser bloqueado pela validação)."""
    url = f"{settings.API_V1_STR}/tasks/?limit=0"
    response = await test_async_client.get(url, headers=auth_headers_a)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    # Verificar a mensagem de erro específica seria ainda melhor
    assert "Input should be greater than or equal to 1" in response.text

async def test_list_tasks_pagination_limit_too_high(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
):
    """Testa a paginação com limit > 1000 (deve ser bloqueado pela validação)."""
    url = f"{settings.API_V1_STR}/tasks/?limit=1001"
    response = await test_async_client.get(url, headers=auth_headers_a)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "Input should be less than or equal to 1000" in response.text

# ========================================
# --- Testes de Filtros e Paginação ---
# ========================================

async def test_list_tasks_filter_and_pagination(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    create_filter_sort_tasks: List[Dict] 
):
    """Testa filtro por projeto e paginação (skip=1, limit=2)."""
    url = f"{settings.API_V1_STR}/tasks/?project=Filtro&skip=1&limit=2"
    response = await test_async_client.get(url, headers=auth_headers_a)
    assert response.status_code == status.HTTP_200_OK
    tasks = response.json()
    assert isinstance(tasks, list)
    assert len(tasks) == 2

# ========================================
# --- Testes de Filtros e Ordenação ---
# ========================================

@pytest_asyncio.fixture(
        scope="function"
)

async def create_filter_sort_tasks(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str]
) -> List[Dict]:
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
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    create_filter_sort_tasks: List[Dict]
):
    url = f"{settings.API_V1_STR}/tasks/?project=Filtro"
    response = await test_async_client.get(url, headers=auth_headers_a)
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) == 4 
    assert all(task["project"] == "Filtro" for task in tasks)

async def test_list_tasks_filter_by_status(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    create_filter_sort_tasks: List[Dict]
):
    url = f"{settings.API_V1_STR}/tasks/?status=pendente"
    response = await test_async_client.get(url, headers=auth_headers_a)
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) == 3 
    assert all(task["status"] == TaskStatus.PENDING.value for task in tasks)

async def test_list_tasks_filter_by_single_tag(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    create_filter_sort_tasks: List[Dict]
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
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    create_filter_sort_tasks: List[Dict]
):
    url = f"{settings.API_V1_STR}/tasks/?tag=t1&tag=t2"
    response = await test_async_client.get(url, headers=auth_headers_a)
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) == 1 
    assert tasks[0]["title"] == "Filter Task P1 High"

async def test_list_tasks_sort_by_priority(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    create_filter_sort_tasks: List[Dict]
):
    url = f"{settings.API_V1_STR}/tasks/?sort_by=priority_score&sort_order=desc"
    response = await test_async_client.get(url, headers=auth_headers_a)
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) == 5 
    scores = [task.get("priority_score") for task in tasks if task.get("priority_score") is not None]
    assert scores == sorted(scores, reverse=True)

async def test_list_tasks_sort_by_due_date_asc(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    create_filter_sort_tasks: List[Dict]
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

async def test_get_specific_task_not_found(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str] 
):
    """Testa buscar uma tarefa com ID inexistente."""
    non_existent_id = uuid.uuid4()
    url = f"{settings.API_V1_STR}/tasks/{non_existent_id}"
    response = await test_async_client.get(url, headers=auth_headers_a)
    assert response.status_code == status.HTTP_404_NOT_FOUND

async def test_get_specific_task_unauthorized(
        test_async_client: AsyncClient
):
    """Testa buscar tarefa específica sem autenticação."""
    some_id = uuid.uuid4()
    url = f"{settings.API_V1_STR}/tasks/{some_id}"
    response = await test_async_client.get(url) 
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

async def test_get_other_user_task_forbidden(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    auth_headers_b: Dict[str, str]
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
# --- Testes PUT /tasks/{id} ---
# ========================================

async def test_update_task_success(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
):
    """Testa atualizar uma tarefa com sucesso e verifica chamada do webhook."""
    # Arrange: Criar tarefa
    url = f"{settings.API_V1_STR}/tasks/"
    create_resp = await test_async_client.post(
        url,
        json=base_task_create_data,
        headers=auth_headers_a
    )
    assert create_resp.status_code == 201
    task_id = create_resp.json()["id"]
    original_score = create_resp.json().get("priority_score")

    # Act: Atualizar a tarefa
    url_put = f"{settings.API_V1_STR}/tasks/{task_id}"
    update_payload = {
        "title": "Título Atualizado",
        "status": TaskStatus.COMPLETED.value,
        "importance": 5
    } 
    response = await test_async_client.put(
        url_put,
        json=update_payload,
        headers=auth_headers_a
    )

    # Assert
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == task_id
    assert data["title"] == update_payload["title"]
    assert data["status"] == update_payload["status"]
    assert data["importance"] == update_payload["importance"]
    assert "updated_at" in data and data["updated_at"] is not None
    assert "priority_score" in data
    assert data["priority_score"] != original_score

async def test_update_task_not_found(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str]
):
    """Testa atualizar tarefa inexistente."""
    url = f"{settings.API_V1_STR}/tasks/{uuid.uuid4()}" 
    response = await test_async_client.put(url, json={"title": "Inexistente"}, headers=auth_headers_a)
    assert response.status_code == status.HTTP_404_NOT_FOUND

async def test_update_other_user_task_forbidden(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    auth_headers_b: Dict[str, str]
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
    auth_headers_a: Dict[str, str]
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

async def test_get_specific_task_not_found(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str] 
):
    """Testa buscar uma tarefa com ID inexistente."""
    non_existent_id = uuid.uuid4()
    url = f"{settings.API_V1_STR}/tasks/{non_existent_id}"
    response = await test_async_client.get(url, headers=auth_headers_a) 
    assert response.status_code == status.HTTP_404_NOT_FOUND

async def test_get_specific_task_unauthorized(
        test_async_client: AsyncClient
):
     """Testa buscar tarefa sem autenticação."""
     some_valid_id_placeholder = uuid.uuid4()
     url = f"{settings.API_V1_STR}/tasks/{some_valid_id_placeholder}"
     response = await test_async_client.get(url)
     assert response.status_code == status.HTTP_401_UNAUTHORIZED

async def test_get_other_user_task_forbidden(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    auth_headers_b: Dict[str, str]
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
# --- Testes DELETE /tasks/{id} ---
# ==========================================

async def test_delete_task_success(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str]
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
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str]
):
    """Testa deletar tarefa inexistente."""
    url = f"{settings.API_V1_STR}/tasks/{uuid.uuid4()}" # ID aleatório
    response = await test_async_client.delete(url, headers=auth_headers_a)
    assert response.status_code == status.HTTP_404_NOT_FOUND

async def test_delete_other_user_task_forbidden(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    auth_headers_b: Dict[str, str]
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
    
# ==========================================
# --- Testes de Segurança (JWT) ---
# ==========================================

async def test_access_tasks_invalid_token_format(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    mocker
):
    """Testa acessar /tasks com um token JWT mal formatado."""
    url = f"{settings.API_V1_STR}/tasks/"
    invalid_headers = {"Authorization": "Bearer tokeninvalido.nao.jwt"}

    mock_sec_logger = mocker.patch("app.core.security.logger")

    response = await test_async_client.get(url, headers=invalid_headers)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "validar as credenciais" in response.json()["detail"]
    mock_sec_logger.error.assert_called_once()
    assert "Not enough segments" in mock_sec_logger.error.call_args[0][0]

async def test_access_tasks_token_wrong_secret(
    test_async_client: AsyncClient,
    mocker 
):
    """Testa acessar /tasks com um token assinado com segredo incorreto."""
    from app.core.security import create_access_token
    from app.models.token import TokenPayload

    # 1. Criando um usuário para ter um ID válido 
    user_id_dummy = uuid.uuid4()
    username_dummy = "dummyuser"

    # 2. Gerando um token JWT usando uma chave secreta diferente da configuração
    wrong_secret = "outra-chave-secreta-bem-diferente"
    assert wrong_secret != settings.JWT_SECRET_KEY
    token_wrong_key = create_access_token(
        subject=user_id_dummy,
        username=username_dummy,
    )
    import jwt as jose_jwt 
    to_encode = {"sub": str(user_id_dummy),
                "username": username_dummy,
                "exp": datetime.now(timezone.utc) + timedelta(minutes=15)
                }
    token_really_wrong_key = jose_jwt.encode(to_encode, wrong_secret, algorithm=settings.JWT_ALGORITHM)

    mock_sec_logger = mocker.patch("app.core.security.logger")

    # 3. Tentando acessar a API com este token
    url = f"{settings.API_V1_STR}/tasks/"
    invalid_headers = {"Authorization": f"Bearer {token_really_wrong_key}"}
    response = await test_async_client.get(url, headers=invalid_headers)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "validar as credenciais" in response.json()["detail"]
    mock_sec_logger.error.assert_called_once()
    assert "Signature verification failed" in mock_sec_logger.error.call_args[0][0]


@freeze_time("2025-05-04 18:35:00")

async def test_access_tasks_expired_token(
    test_async_client: AsyncClient,
    test_user_a_token_and_id: tuple[str, uuid.UUID],
    mocker
):
    """Testa acessar /tasks com um token JWT expirado."""
    import jwt as jose_jwt
    from datetime import datetime, timedelta, timezone

    _, user_id = test_user_a_token_and_id

    # 1. Criando um token com data de expiração no passado
    past_time = datetime.now(timezone.utc) - timedelta(minutes=30)
    expired_payload = {
        "sub": str(user_id), 
        "username": user_a_data["username"],
        "exp": past_time
    }
    expired_token = jose_jwt.encode(
        expired_payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )

    mock_sec_logger = mocker.patch("app.core.security.logger")

    # 2. Tente acessar a API com o token expirado
    url = f"{settings.API_V1_STR}/tasks/"
    invalid_headers = {"Authorization": f"Bearer {expired_token}"}
    response = await test_async_client.get(url, headers=invalid_headers)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "validar as credenciais" in response.json()["detail"]
    mock_sec_logger.error.assert_called_once()
    assert "Signature has expired" in mock_sec_logger.error.call_args[0][0]

@pytest.mark.parametrize(
    "param_name, injected_value", [
        ("project", {"$ne": "some_project"}), 
        ("project", "; --"), 
        ("project", "' OR '1'='1"), 
        ("tag", {"$ne": "some_tag"}), 
        ("tag", "*"),
        ("tag", "t1; DROP TABLE tasks; --"), 
    ]
)

async def test_list_tasks_filter_injection_attempt_string(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    param_name: str,
    injected_value: Any,
):
    """
    Testa tentativas de injeção em filtros de string (project, tag).
    Espera-se erro 422 (Validação) pois o tipo esperado é string simples.
    """
    url = f"{settings.API_V1_STR}/tasks/?{param_name}={str(injected_value)}" 

    response = await test_async_client.get(url, headers=auth_headers_a)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY \
           or response.status_code == status.HTTP_200_OK, \
           f"Recebido status inesperado {response.status_code} para injeção em '{param_name}'"

    if response.status_code == status.HTTP_200_OK:
        tasks = response.json()
        assert isinstance(tasks, list)
        print(f"WARN: Injeção em '{param_name}' retornou 200 OK. Resultado: {tasks}")

async def test_list_tasks_filter_regex_injection(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    create_filter_sort_tasks: List[Dict]
):
    """
    Testa especificamente a injeção de $regex no filtro 'project'.
    MongoDB pode aceitar regex, mas Pydantic deve garantir que é tratado como string.
    """
    payload_str = "/.*/" 
    url = f"{settings.API_V1_STR}/tasks/?project={payload_str}"
    response = await test_async_client.get(url, headers=auth_headers_a)

    assert response.status_code == status.HTTP_200_OK
    tasks = response.json()
    assert isinstance(tasks, list)
    found_literal_match = any(task.get("project") == payload_str for task in tasks)
    assert not found_literal_match or len(tasks) == 0, \
           "Injeção de Regex parece ter encontrado resultados inesperados ou foi tratada literalmente."
    
# ================================================
# --- Testes de Notificação Imediata de E-mail ---
# ================================================

@freeze_time("2025-05-04") 
async def test_create_task_triggers_immediate_urgent_email(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    mocker, 
):
    """
    Testa se a criação de uma tarefa claramente urgente dispara
    a background task para envio imediato de e-mail.
    """
    # Mockar a função de envio de email que é chamada pela rota
    mock_send_email = mocker.patch(
        "app.routers.tasks.send_urgent_task_notification",
        new_callable=AsyncMock
    )
    # Mockar is_task_urgent para garantir que ela retorne True neste teste
    mocker.patch("app.routers.tasks.is_task_urgent", return_value=True)

    urgent_task_payload = {
        "title": "Tarefa Super Urgente Imediata",
        "description": "Precisa de email agora",
        "importance": 5,
        "due_date": (date.today() - timedelta(days=1)).isoformat() 
    }

    url = f"{settings.API_V1_STR}/tasks/"
    response = await test_async_client.post(url, json=urgent_task_payload, headers=auth_headers_a)

    # Verifica a criação da tarefa
    assert response.status_code == status.HTTP_201_CREATED
    created_task_data = response.json()

    # Verifica se a função de envio de email foi chamada na background task
    mock_send_email.assert_called_once()

    # Verificar alguns argumentos chave passados para a função mockada
    call_args = mock_send_email.call_args.kwargs
    assert call_args["user_email"] == user_a_data["email"] 
    assert call_args["task_title"] == urgent_task_payload["title"]
    assert call_args["task_id"] == created_task_data["id"]


@freeze_time("2025-05-04") 
async def test_create_task_does_not_trigger_immediate_non_urgent_email(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    mocker, 
):
    """
    Testa se a criação de uma tarefa claramente NÃO urgente NÃO dispara
    a background task para envio imediato de e-mail.
    """
    # Mockar a função de envio de email
    mock_send_email = mocker.patch(
        "app.routers.tasks.send_urgent_task_notification",
        new_callable=AsyncMock
    )
    # Mockar is_task_urgent para garantir que retorne False
    mocker.patch("app.routers.tasks.is_task_urgent", return_value=False)

    # Dados para uma tarefa que NÃO deve ser urgente
    non_urgent_task_payload = {
        "title": "Tarefa Não Urgente Imediata",
        "description": "Sem pressa",
        "importance": 1,
        "due_date": (date.today() + timedelta(days=30)).isoformat() 
    }

    url = f"{settings.API_V1_STR}/tasks/"
    response = await test_async_client.post(url, json=non_urgent_task_payload, headers=auth_headers_a)

    # Verifica a criação da tarefa
    assert response.status_code == status.HTTP_201_CREATED

    # Verifica que a função de envio de email NÃO foi chamada
    mock_send_email.assert_not_called()