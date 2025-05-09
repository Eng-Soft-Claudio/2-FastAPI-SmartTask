# tests/test_tasks.py
"""
Este módulo contém testes de integração para os endpoints de tarefas (`/tasks`)
da API SmartTask, definidos em `app.routers.tasks`.

Os testes cobrem uma ampla gama de funcionalidades, incluindo:
- Criação, listagem, obtenção, atualização e deleção de tarefas (CRUD).
- Validação de entrada para criação e atualização de tarefas.
- Filtros e paginação na listagem de tarefas.
- Ordenação na listagem de tarefas.
- Lógica de autorização (usuário só pode acessar/modificar suas próprias tarefas).
- Tratamento de tokens JWT inválidos ou expirados.
- Tentativas de injeção em parâmetros de filtro.
- Disparo de notificações (e-mail, webhook) via BackgroundTasks.

Utiliza fixtures de `conftest.py` para usuários e autenticação.
A biblioteca `freezegun` é usada para controlar a data/hora em testes sensíveis ao tempo.
O envio de webhooks é mockado automaticamente.
"""

# ==========================================
# --- Importações ---
# ==========================================
import unittest.mock
from unittest.mock import AsyncMock, ANY, MagicMock
from freezegun import freeze_time
from pydantic import ValidationError
import pytest
from httpx import AsyncClient
from fastapi import status
from typing import Dict, List, Any
import uuid
import pytest_asyncio
from app.core.config import settings
from app.db import task_crud
from app.models.task import Task, TaskStatus
from datetime import date, timedelta, datetime, timezone
from tests.conftest import user_a_data
import jwt as jose_jwt
import uuid 
from fastapi import status 

# ==========================================
# --- Mock Webhook ---
# ==========================================
@pytest.fixture(
        autouse=True
)

def auto_mock_send_webhook(mocker):
    """
    Fixture `autouse` que aplica automaticamente um mock à função
    `app.routers.tasks.send_webhook_notification` para todos os testes
    definidos neste módulo.
    Previne chamadas HTTP reais para webhooks e permite verificar se a função
    foi chamada quando esperado.
    """
    mocker.patch(
        "app.routers.tasks.send_webhook_notification",
        new_callable=unittest.mock.AsyncMock,
    )

# ==========================================
# --- Marcador Asyncio e Fixture ---
# ==========================================
pytestmark = pytest.mark.asyncio

@pytest.fixture
def sample_task_create_data() -> Dict[str, Any]:
    """Fornece um dicionário válido para criar uma tarefa nos testes de rota."""
    return {
        "title": "Task Payload for Route Test",
        "description": "Description from payload test",
        "importance": 4,
        "due_date": (date.today() + timedelta(days=5)).isoformat(),
        "status": TaskStatus.PENDING.value,
        "tags": ["route_t", "test_t"],
        "project": "Router Tests T"
    }

# ==========================================
# --- Base Task Data ---
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
    """
    Testa a criação bem-sucedida de uma nova tarefa por um usuário autenticado.
    Verifica o status code HTTP 201 CREATED e se os dados retornados
    correspondem ao payload enviado, incluindo campos gerados pelo servidor
    como id, owner_id, created_at e priority_score.
    """
    # --- Arrange ---
    url = f"{settings.API_V1_STR}/tasks/"
    # --- Act ---
    response = await test_async_client.post(
        url,
        json=base_task_create_data,
        headers=auth_headers_a
    ) 
    # --- Assert ---
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
     """
     Testa a tentativa de criar uma tarefa sem fornecer um token de autenticação.
     Espera-se um erro HTTP 401 Unauthorized como resposta da API.
     """
     # --- Arrange ---
     url = f"{settings.API_V1_STR}/tasks/"
     # --- Act ---
     response = await test_async_client.post(url, json=base_task_create_data) 
     # --- Assert ---
     assert response.status_code == status.HTTP_401_UNAUTHORIZED

# ==================================================================
# --- Testes de Criação e Atualização ---
# ==================================================================
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
    """
    Testa a criação de uma tarefa com campos de string (`title`, `description`)
    preenchidos exatamente no seu comprimento máximo permitido.
    Espera-se que a criação seja bem-sucedida com um status HTTP 201 CREATED.
    """
    # --- Arrange ---
    payload = base_task_create_data.copy()
    payload[field] = "X" * length 
    url = f"{settings.API_V1_STR}/tasks/"
    # --- Act ---
    response = await test_async_client.post(url, json=payload, headers=auth_headers_a)
    # --- Assert ---
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
    """
    Testa a tentativa de criar uma tarefa com campos de string (`title`, `description`)
    excedendo o comprimento máximo permitido estabelecido pelo modelo de dados.
    Espera-se um erro de validação HTTP 422 Unprocessable Entity.
    """
    # --- Arrange ---
    payload = base_task_create_data.copy()
    payload[field] = "X" * length
    url = f"{settings.API_V1_STR}/tasks/"
    # --- Act ---
    response = await test_async_client.post(url, json=payload, headers=auth_headers_a)
    # --- Assert ---
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert f"String should have at most {length -1} characters" in response.text

async def test_create_task_explicit_nulls_optional(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
):
    """
    Testa a criação de uma tarefa onde campos opcionais (description, due_date,
    tags, project) são explicitamente enviados como `null` (None em Python) no payload.
    Espera-se que a tarefa seja criada com sucesso (HTTP 201) e que esses campos
    reflitam o valor nulo na resposta.
    """
        # --- Arrange ---
    payload = base_task_create_data.copy()
    payload["description"] = None
    payload["due_date"] = None
    payload["tags"] = None
    payload["project"] = None
    url = f"{settings.API_V1_STR}/tasks/"

    # --- Act ---
    response = await test_async_client.post(url, json=payload, headers=auth_headers_a)

    # --- Assert ---
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
    """
    Testa a atualização de uma tarefa existente, definindo campos opcionais
    (que previamente continham valores) para `null` (None em Python) no payload.
    Primeiro, uma tarefa é criada com valores. Em seguida, é atualizada.
    Espera-se que a atualização seja bem-sucedida (HTTP 200) e os campos
    sejam refletidos como nulos na resposta.
    """
    # --- Arrange ---
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

    # --- Act ---
    url_put = f"{settings.API_V1_STR}/tasks/{task_id}"
    update_payload = {
        "description": None,
        "due_date": None,
        "tags": None, 
        "project": None,
    }
    response = await test_async_client.put(url_put, json=update_payload, headers=auth_headers_a)
    
    # --- Assert ---
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert response_data["description"] is None
    assert response_data["due_date"] is None
    assert response_data["tags"] is None 
    assert response_data["project"] is None

@pytest.mark.asyncio
async def test_create_task_internal_validation_error(test_async_client: AsyncClient, mocker, auth_headers_a, sample_task_create_data): 
    """
    Testa o tratamento de erro quando a validação Pydantic interna
    ao construir o objeto Task completo na rota falha.
    """
    # --- Arrange ---
    url = f"{settings.API_V1_STR}/tasks/"
    task_payload = sample_task_create_data

    mocker.patch("app.routers.tasks.calculate_priority_score", return_value=50.0)
    simulated_error = ValidationError.from_exception_data(title="Task", line_errors=[])
    mock_task_init = mocker.patch("app.routers.tasks.Task", side_effect=simulated_error)

    mock_crud_create = mocker.patch("app.routers.tasks.task_crud.create_task")
    mock_logger_error = mocker.patch("app.routers.tasks.logger.error")

    # --- Act ---
    response = await test_async_client.post(url, json=task_payload, headers=auth_headers_a)

    # --- Assert ---
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "Erro interno na validação dos dados da tarefa" in response.json()["detail"]
    mock_task_init.assert_called_once()
    mock_crud_create.assert_not_called()
    mock_logger_error.assert_called_once()
    log_call_args = mock_logger_error.call_args.args
    assert "Erro de validação Pydantic ao montar objeto Task" in log_call_args[0]

@pytest.mark.asyncio
async def test_update_task_crud_returns_none(test_async_client: AsyncClient, mocker, auth_headers_a, test_user_a_token_and_id): 
    """
    Testa o comportamento da rota PUT /tasks/{task_id} quando
    task_crud.update_task retorna None.
    """
    # --- Arrange ---
    token, user_id_a = test_user_a_token_and_id
    target_task_id = uuid.uuid4()
    url = f"{settings.API_V1_STR}/tasks/{target_task_id}"
    update_payload = {"title": "Titulo Nao Aplicado"}
    mock_existing_task = MagicMock(spec=Task)
    mock_existing_task.importance = 3 
    mock_existing_task.due_date = None 
    mocker.patch("app.routers.tasks.task_crud.get_task_by_id", return_value=mock_existing_task)
    mock_crud_update = mocker.patch("app.routers.tasks.task_crud.update_task", return_value=None)
    mocker.patch("app.routers.tasks.calculate_priority_score")
    mock_logger_error = mocker.patch("app.routers.tasks.logger.error")

    # --- Act ---
    response = await test_async_client.put(url, json=update_payload, headers=auth_headers_a)

    # --- Assert ---
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "Não foi possível atualizar a tarefa" in response.json()["detail"]
    assert "Pode ter sido deletada ou ocorreu um erro interno" in response.json()["detail"]
    task_crud.get_task_by_id.assert_called_once_with(db=mocker.ANY, task_id=target_task_id, owner_id=user_id_a)
    mock_crud_update.assert_called_once()
    mock_logger_error.assert_called_once()
    assert f"Falha ao atualizar tarefa {target_task_id}" in mock_logger_error.call_args.args[0]

@pytest.mark.asyncio
async def test_create_urgent_task_logs_warning_if_user_incomplete(test_async_client: AsyncClient, mocker): # type: ignore
    """
    Testa se um warning é logado ao criar tarefa urgente se o usuário
    não possui nome completo (mas tem e-mail).
    """
    # --- Arrange ---
    username = f"incomplete_name_{uuid.uuid4().hex[:4]}"
    email = f"{username}@example.com"
    incomplete_user_data = {
        "email": email,
        "username": username,
        "password": "password123",
        "full_name": None 
    }
    register_url = f"{settings.API_V1_STR}/auth/register"
    login_url = f"{settings.API_V1_STR}/auth/login/access-token"

    reg_response = await test_async_client.post(register_url, json=incomplete_user_data)
    assert reg_response.status_code == status.HTTP_201_CREATED
    user_id = reg_response.json()["id"]

    login_payload_form_data = {
        "username": username,
        "password": incomplete_user_data["password"]
    }
    login_response = await test_async_client.post(login_url, data=login_payload_form_data)
    assert login_response.status_code == status.HTTP_200_OK
    token = login_response.json()["access_token"]
    incomplete_user_headers = {"Authorization": f"Bearer {token}"}

    url_create = f"{settings.API_V1_STR}/tasks/"
    urgent_task_payload = {
        "title": "Urgente, usuário sem nome",
        "importance": 5,
        "due_date": (date.today() - timedelta(days=1)).isoformat()
    }

    mocker.patch("app.routers.tasks.is_task_urgent", return_value=True)
    mock_send_email = mocker.patch("app.routers.tasks.send_urgent_task_notification", new_callable=AsyncMock)
    mock_logger_warning = mocker.patch("app.routers.tasks.logger.warning")

    mock_created_task = MagicMock(spec=Task)
    task_id_created = uuid.uuid4()
    mock_created_task.id = task_id_created
    mock_created_task.owner_id = uuid.UUID(user_id)
    mock_created_task.title = urgent_task_payload["title"]
    mocker.patch("app.routers.tasks.task_crud.create_task", return_value=mock_created_task)
    mocker.patch("app.routers.tasks.calculate_priority_score", return_value=1000.0)

    # --- Act ---
    response = await test_async_client.post(url_create, json=urgent_task_payload, headers=incomplete_user_headers)

    # --- Assert ---
    assert response.status_code == status.HTTP_201_CREATED

    mock_logger_warning.assert_called_once()
    log_message = mock_logger_warning.call_args.args[0]
    assert f"Usuário {user_id} (username: {username})" in log_message
    assert "não possui e-mail ou nome completo configurado" in log_message
    assert f"tarefa urgente {task_id_created}" in log_message

    mock_send_email.assert_not_called()

# ==============================================================
# --- Testes de Validação de Entrada (Parametrizados) ---
# ==============================================================
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
    """
    Testa a criação de tarefas com diversos tipos de dados de entrada inválidos
    para campos específicos, como title, importance, due_date e status.
    Verifica se a API retorna HTTP 422 Unprocessable Entity e se a mensagem
    de erro na resposta `detail` corresponde ao campo e tipo de erro esperados.
    """
    # --- Arrange ---
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
    # --- Act ---
    response = await test_async_client.post(url, json=invalid_data, headers=auth_headers_a)
    # --- Assert ---
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
    """
    Testa a atualização de tarefas com dados de entrada inválidos para campos específicos.
    Primeiro cria uma tarefa válida, depois tenta atualizá-la com um valor inválido.
    Verifica se a API retorna HTTP 422 Unprocessable Entity e se a mensagem
    de erro corresponde ao esperado.
    """
    # --- Arrange ---
    url = f"{settings.API_V1_STR}/tasks/"
    create_resp = await test_async_client.post(url, json=base_task_create_data, headers=auth_headers_a)
    assert create_resp.status_code == 201
    task_id = create_resp.json()["id"]

    # --- Act ---
    invalid_update_payload = {field: value}
    url_put = f"{settings.API_V1_STR}/tasks/{task_id}"
    response = await test_async_client.put(url_put, json=invalid_update_payload, headers=auth_headers_a)

    # --- Assert ---
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
    """
    Testa a tentativa de atualizar uma tarefa enviando um payload JSON vazio (`{}`).
    Verifica se a API retorna um erro HTTP 400 Bad Request, indicando que
    nenhum campo válido para atualização foi fornecido.
    """
    # --- Arrange ---
    url = f"{settings.API_V1_STR}/tasks/"
    create_resp = await test_async_client.post(url, json=base_task_create_data, headers=auth_headers_a)
    assert create_resp.status_code == 201
    task_id = create_resp.json()["id"]

    # --- Act ---
    url_put = f"{settings.API_V1_STR}/tasks/{task_id}"
    response = await test_async_client.put(url_put, json={}, headers=auth_headers_a)

    # --- Assert ---
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Nenhum campo válido fornecido" in response.json()["detail"]

# ==========================================
# --- Testes de Listagem ---
# ==========================================
async def test_list_tasks_success(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str]
):
    """
    Testa a listagem bem-sucedida de tarefas para um usuário autenticado (User A).
    Cria duas tarefas para o User A e verifica se ambas são retornadas ao listar
    tarefas para este usuário, e se o status code é HTTP 200 OK.
    """
    # --- Arrange ---
    url = f"{settings.API_V1_STR}/tasks/"
    task1 = {**base_task_create_data, "title": "Task A1 List", "importance": 5, "project": "Alpha"}
    task2 = {**base_task_create_data, "title": "Task A2 List", "status": TaskStatus.IN_PROGRESS.value, "tags": ["urgent"]}
    # --- Act ---
    resp1 = await test_async_client.post(url, json=task1, headers=auth_headers_a)
    # --- Assert ---
    assert resp1.status_code == 201
    # --- Act ---
    resp2 = await test_async_client.post(url, json=task2, headers=auth_headers_a)
    # --- Assert ---
    assert resp2.status_code == 201

    # --- Act ---
    response = await test_async_client.get(url, headers=auth_headers_a)

    # --- Assert ---
    assert response.status_code == status.HTTP_200_OK
    tasks = response.json()
    assert isinstance(tasks, list)
    assert len(tasks) == 2
    titles = {task["title"] for task in tasks}
    assert task1["title"] in titles
    assert task2["title"] in titles

async def test_list_tasks_unauthorized(
        test_async_client: AsyncClient
):
     """
     Testa a tentativa de listar tarefas sem fornecer um token de autenticação.
     Espera-se um erro HTTP 401 Unauthorized.
     """
     # --- Arrange ---
     url = f"{settings.API_V1_STR}/tasks/"
     # --- Act ---
     response = await test_async_client.get(url)
     # --- Assert ---
     assert response.status_code == status.HTTP_401_UNAUTHORIZED

async def test_list_tasks_does_not_show_other_users_tasks(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    auth_headers_b: Dict[str, str]
):
    """
    Testa a separação de dados entre usuários na listagem de tarefas.
    Garante que o User B, ao listar suas tarefas, não veja as tarefas criadas
    pelo User A.
    """
    # --- Arrange ---
    url = f"{settings.API_V1_STR}/tasks/"
    task_a = {**base_task_create_data, "title": "Tarefa Secreta A"}
    resp_a = await test_async_client.post(url, json=task_a, headers=auth_headers_a)
    assert resp_a.status_code == 201

    # --- Act ---
    response_b = await test_async_client.get(url, headers=auth_headers_b)

    # --- Assert ---
    assert response_b.status_code == status.HTTP_200_OK
    tasks_b = response_b.json()
    assert isinstance(tasks_b, list)
    assert len(tasks_b) == 0

async def test_list_tasks_filter_non_existent_project(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    create_filter_sort_tasks: List[Dict] 
):
    """
    Testa a funcionalidade de filtro de listagem de tarefas por projeto,
    especificamente quando o projeto fornecido no filtro não existe em nenhuma tarefa.
    Espera-se uma lista vazia e status HTTP 200 OK.
    """
    # --- Arrange ---
    url = f"{settings.API_V1_STR}/tasks/?project=ProjetoInexistente123"
    # --- Act ---
    response = await test_async_client.get(url, headers=auth_headers_a)
    # --- Assert ---
    assert response.status_code == status.HTTP_200_OK
    tasks = response.json()
    assert isinstance(tasks, list)
    assert len(tasks) == 0 

async def test_list_tasks_filter_non_existent_tag(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    create_filter_sort_tasks: List[Dict]
):
    """
    Testa a funcionalidade de filtro de listagem de tarefas por tag,
    quando a tag fornecida não está associada a nenhuma tarefa.
    Espera-se uma lista vazia e status HTTP 200 OK.
    """
    # --- Arrange ---
    url = f"{settings.API_V1_STR}/tasks/?tag=tag_nao_existe"
    # --- Act ---
    response = await test_async_client.get(url, headers=auth_headers_a)
    # --- Assert ---
    assert response.status_code == status.HTTP_200_OK
    tasks = response.json()
    assert isinstance(tasks, list)
    assert len(tasks) == 0

async def test_list_tasks_filter_multiple_tags_no_match(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    create_filter_sort_tasks: List[Dict]
):
    """
    Testa o filtro de listagem por múltiplas tags quando nenhuma tarefa
    contém TODAS as tags especificadas. O filtro por múltiplas tags geralmente
    implica uma operação AND (a tarefa deve ter todas as tags).
    Espera-se uma lista vazia e status HTTP 200 OK.
    """
    # --- Arrange ---
    url = f"{settings.API_V1_STR}/tasks/?tag=t1&tag=t3"
    # --- Act ---
    response = await test_async_client.get(url, headers=auth_headers_a)
    # --- Assert ---
    assert response.status_code == status.HTTP_200_OK
    tasks = response.json()
    assert isinstance(tasks, list)
    assert len(tasks) == 0 

async def test_list_tasks_filter_status_no_match(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    create_filter_sort_tasks: List[Dict]
):
    """
    Testa o filtro de listagem por status quando nenhuma tarefa corresponde
    ao status fornecido (ex: 'cancelada', se não houver tarefas canceladas).
    Espera-se uma lista vazia e status HTTP 200 OK.
    """
    # --- Arrange ---
    url = f"{settings.API_V1_STR}/tasks/?status={TaskStatus.CANCELLED.value}"
    # --- Act ---
    response = await test_async_client.get(url, headers=auth_headers_a)
    # --- Assert ---
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
    """
    Testa o filtro de listagem por data de vencimento (`due_before`) usando uma
    data muito no passado, onde nenhuma tarefa da fixture `create_filter_sort_tasks`
    (cujos prazos são futuros em relação a "2025-05-04") deveria ser retornada.
    Espera-se uma lista vazia e status HTTP 200 OK.
    """
    # --- Arrange ---
    early_date = "2024-01-01"
    url = f"{settings.API_V1_STR}/tasks/?due_before={early_date}"
    # --- Act ---
    response = await test_async_client.get(url, headers=auth_headers_a)
    # --- Assert ---
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
    """
    Testa a funcionalidade de paginação da listagem de tarefas,
    especificamente o parâmetro `limit`.
    Verifica se, ao definir `limit=1`, apenas uma tarefa é retornada.
    """
    # --- Arrange ---
    url = f"{settings.API_V1_STR}/tasks/?limit=1"
    # --- Act ---
    response = await test_async_client.get(url, headers=auth_headers_a)
    # --- Assert ---
    assert response.status_code == status.HTTP_200_OK
    tasks = response.json()
    assert isinstance(tasks, list)
    assert len(tasks) == 1 

async def test_list_tasks_pagination_skip_all(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    create_filter_sort_tasks: List[Dict] 
):
    """
    Testa a funcionalidade de paginação `skip`.
    Verifica se, ao pular um número de tarefas igual ou maior ao total existente
    (criado pela fixture `create_filter_sort_tasks`), uma lista vazia é retornada.
    """
    # --- Arrange ---
    total_tasks_in_fixture = 5 
    url_skip_exact = f"{settings.API_V1_STR}/tasks/?skip={total_tasks_in_fixture}"
    url_skip_more = f"{settings.API_V1_STR}/tasks/?skip={total_tasks_in_fixture + 5}"
    
    # --- Act (Skip Exato) ---
    response_exact = await test_async_client.get(url_skip_exact, headers=auth_headers_a)
    # --- Assert (Skip Exato) ---
    assert response_exact.status_code == status.HTTP_200_OK
    tasks_exact = response_exact.json()
    assert isinstance(tasks_exact, list)
    assert len(tasks_exact) == 0 

    # --- Act (Skip Mais) ---
    response_skip_more = await test_async_client.get(url_skip_more, headers=auth_headers_a)
    # --- Assert (Skip Mais) ---
    assert response_skip_more.status_code == status.HTTP_200_OK
    tasks_skip_more = response_skip_more.json()
    assert isinstance(tasks_skip_more, list)
    assert len(tasks_skip_more) == 0

async def test_list_tasks_pagination_limit_0(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
):
    """
    Testa o comportamento da paginação quando um valor inválido (`limit=0`)
    é fornecido. A validação da FastAPI (para `Query(ge=1, ...)`) deve
    impedir isso, retornando HTTP 422 Unprocessable Entity.
    """
    # --- Arrange ---
    url = f"{settings.API_V1_STR}/tasks/?limit=0"
    # --- Act ---
    response = await test_async_client.get(url, headers=auth_headers_a)
    # --- Assert ---
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "Input should be greater than or equal to 1" in response.text

async def test_list_tasks_pagination_limit_too_high(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
):
    """
    Testa o comportamento da paginação quando um valor inválido (`limit > 1000`)
    é fornecido. A validação da FastAPI (para `Query(..., le=1000)`) deve
    impedir isso, retornando HTTP 422 Unprocessable Entity.
    """
    # --- Arrange ---
    url = f"{settings.API_V1_STR}/tasks/?limit=1001"
    # --- Act ---
    response = await test_async_client.get(url, headers=auth_headers_a)
    # --- Assert ---
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "Input should be less than or equal to 1000" in response.text

# ======================================================
# --- Testes de de Filtros e Paginação ---
# ======================================================
async def test_list_tasks_filter_and_pagination(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    create_filter_sort_tasks: List[Dict] 
):
    """
    Testa a combinação de filtros de listagem (por projeto) com paginação
    (skip e limit).
    Verifica se o número correto de tarefas é retornado após aplicar
    ambos os tipos de parâmetros.
    """
    # --- Arrange ---
    url = f"{settings.API_V1_STR}/tasks/?project=Filtro&skip=1&limit=2"
    # --- Act ---
    response = await test_async_client.get(url, headers=auth_headers_a)
    # --- Assert ---
    assert response.status_code == status.HTTP_200_OK
    tasks = response.json()
    assert isinstance(tasks, list)
    assert len(tasks) == 2

# ======================================================
# --- Testes de de Filtros e Ordenação ---
# ======================================================
@pytest_asyncio.fixture(
        scope="function" 
)
async def create_filter_sort_tasks(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str]
) -> List[Dict]:
    """
    Fixture assíncrona que cria um conjunto de tarefas de teste com variações
    em seus atributos (título, importância, projeto, status, data de vencimento, tags).
    Essas tarefas são criadas pelo User A e são usadas para testar as
    funcionalidades de filtragem e ordenação do endpoint de listagem de tarefas.
    Retorna uma lista de dicionários, onde cada dicionário representa os dados
    da tarefa criada (conforme retornado pela API).
    """
    # --- Arrange ---
    url = f"{settings.API_V1_STR}/tasks/"
    tasks_to_create = [
        {"title": "Filter Task P1 High", "importance": 5, "project": "Filtro", "status": TaskStatus.PENDING.value, "due_date": "2026-01-01", "tags": ["t1", "t2"]},
        {"title": "Filter Task P1 Low", "importance": 1, "project": "Filtro", "status": TaskStatus.PENDING.value, "due_date": "2026-02-01"},
        {"title": "Filter Task P2 Medium", "importance": 3, "project": "Outro", "status": TaskStatus.IN_PROGRESS.value, "tags": ["t2"]},
        {"title": "Filter Task P1 Medium", "importance": 3, "project": "Filtro", "status": TaskStatus.PENDING.value, "due_date": "2025-12-15", "tags": ["t3"]}, 
        {"title": "Filter Task P1 Done", "importance": 4, "project": "Filtro", "status": TaskStatus.COMPLETED.value}, 
    ]
    created_tasks = []
    # --- Act ---
    for task_data in tasks_to_create:
        response = await test_async_client.post(url, json=task_data, headers=auth_headers_a)
        # --- Assert (Criação) ---
        assert response.status_code == 201
        created_tasks.append(response.json())
    # --- Return ---
    return created_tasks

async def test_list_tasks_filter_by_project(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    create_filter_sort_tasks: List[Dict] 
):
    """
    Testa a filtragem da lista de tarefas pelo campo 'project'.
    Verifica se apenas as tarefas pertencentes ao projeto "Filtro" são retornadas.
    Utiliza a fixture `create_filter_sort_tasks` para popular o banco com dados de teste.
    """
    # --- Arrange ---
    url = f"{settings.API_V1_STR}/tasks/?project=Filtro"
    # --- Act ---
    response = await test_async_client.get(url, headers=auth_headers_a)
    # --- Assert ---
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) == 4 
    assert all(task["project"] == "Filtro" for task in tasks)

async def test_list_tasks_filter_by_status(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    create_filter_sort_tasks: List[Dict]
):
    """
    Testa a filtragem da lista de tarefas pelo campo 'status'.
    Verifica se apenas as tarefas com status "pendente" são retornadas.
    """
    # --- Arrange ---
    url = f"{settings.API_V1_STR}/tasks/?status=pendente"
    # --- Act ---
    response = await test_async_client.get(url, headers=auth_headers_a)
    # --- Assert ---
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) == 3 
    assert all(task["status"] == TaskStatus.PENDING.value for task in tasks)

async def test_list_tasks_filter_by_single_tag(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    create_filter_sort_tasks: List[Dict]
):
    """
    Testa a filtragem da lista de tarefas por uma única tag.
    Verifica se as tarefas que contêm a tag "t2" são retornadas corretamente.
    """
    # --- Arrange ---
    url = f"{settings.API_V1_STR}/tasks/?tag=t2"
    # --- Act ---
    response = await test_async_client.get(url, headers=auth_headers_a)
    # --- Assert ---
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
    """
    Testa a filtragem da lista de tarefas por múltiplas tags (operação AND).
    Verifica se apenas as tarefas que contêm TODAS as tags especificadas ("t1" E "t2")
    são retornadas.
    """
    # --- Arrange ---
    url = f"{settings.API_V1_STR}/tasks/?tag=t1&tag=t2"
    # --- Act ---
    response = await test_async_client.get(url, headers=auth_headers_a)
    # --- Assert ---
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) == 1 
    assert tasks[0]["title"] == "Filter Task P1 High"

async def test_list_tasks_sort_by_priority(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    create_filter_sort_tasks: List[Dict]
):
    """
    Testa a ordenação da lista de tarefas pelo campo 'priority_score'
    em ordem descendente.
    Verifica se as tarefas retornadas estão ordenadas corretamente pela pontuação
    de prioridade.
    """
    # --- Arrange ---
    url = f"{settings.API_V1_STR}/tasks/?sort_by=priority_score&sort_order=desc"
    # --- Act ---
    response = await test_async_client.get(url, headers=auth_headers_a)
    # --- Assert ---
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
    """
    Testa a ordenação da lista de tarefas pelo campo 'due_date'
    em ordem ascendente.
    Verifica se as tarefas retornadas (que possuem data de vencimento)
    estão ordenadas corretamente. Tarefas sem data de vencimento podem aparecer
    no início ou no fim dependendo da lógica de ordenação do banco para nulos.
    """
    # --- Arrange ---
    url = f"{settings.API_V1_STR}/tasks/?sort_by=due_date&sort_order=asc"
    # --- Act ---
    response = await test_async_client.get(url, headers=auth_headers_a)
    # --- Assert ---
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
    """
    Testa a busca bem-sucedida de uma tarefa específica pelo seu ID,
    pertencente ao usuário autenticado.
    Verifica se o status code é HTTP 200 OK e se os dados da tarefa retornada
    correspondem aos da tarefa criada.
    """
    # --- Arrange ---
    url_create = f"{settings.API_V1_STR}/tasks/"
    create_response = await test_async_client.post(url_create, json=base_task_create_data, headers=auth_headers_a) 
    assert create_response.status_code == 201
    task_id = create_response.json()["id"]

    # --- Act ---
    url_get = f"{settings.API_V1_STR}/tasks/{task_id}"
    get_response = await test_async_client.get(url_get, headers=auth_headers_a) 

    # --- Assert ---
    assert get_response.status_code == status.HTTP_200_OK
    response_data = get_response.json()
    assert response_data["id"] == task_id
    assert response_data["title"] == base_task_create_data["title"] 

async def test_get_specific_task_not_found(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str] 
):
    """
    Testa a tentativa de buscar uma tarefa específica usando um ID que
    não existe no banco de dados.
    Espera-se um erro HTTP 404 Not Found.
    """
    # --- Arrange ---
    non_existent_id = uuid.uuid4()
    url = f"{settings.API_V1_STR}/tasks/{non_existent_id}"
    # --- Act ---
    response = await test_async_client.get(url, headers=auth_headers_a)
    # --- Assert ---
    assert response.status_code == status.HTTP_404_NOT_FOUND

async def test_get_specific_task_unauthorized(
        test_async_client: AsyncClient
):
    """
    Testa a tentativa de buscar uma tarefa específica sem fornecer um
    token de autenticação.
    Espera-se um erro HTTP 401 Unauthorized.
    """
    # --- Arrange ---
    some_id = uuid.uuid4() 
    url = f"{settings.API_V1_STR}/tasks/{some_id}"
    # --- Act ---
    response = await test_async_client.get(url) 
    # --- Assert ---
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

async def test_get_other_user_task_forbidden( 
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    auth_headers_b: Dict[str, str]
):
    """
    Testa a tentativa do User B de obter uma tarefa que pertence ao User A.
    A lógica de `get_task_by_id` (usada pelo endpoint) deve retornar None se
    o `owner_id` não corresponder, resultando em um HTTP 404 Not Found para
    o User B (como se a tarefa não existisse para ele).
    """
    # --- Arrange ---
    url = f"{settings.API_V1_STR}/tasks/"
    task_a_data = {**base_task_create_data, "title": "Task A para GET"}
    resp_a = await test_async_client.post(url, json=task_a_data, headers=auth_headers_a)
    assert resp_a.status_code == 201
    task_a_id = resp_a.json()["id"]

    # --- Act ---
    url_get = f"{settings.API_V1_STR}/tasks/{task_a_id}"
    response_b = await test_async_client.get(url_get, headers=auth_headers_b)

    # --- Assert ---
    assert response_b.status_code == status.HTTP_404_NOT_FOUND

# ========================================
# --- Testes PUT /tasks/{id} ---
# ========================================
async def test_update_task_success(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
):
    """
    Testa a atualização bem-sucedida de uma tarefa existente pelo seu proprietário.
    Verifica se o status code é HTTP 200 OK e se os campos da tarefa
    foram atualizados conforme o payload enviado, incluindo a recalculação da
    pontuação de prioridade e a atualização do timestamp `updated_at`.
    """
    # --- Arrange ---
    url = f"{settings.API_V1_STR}/tasks/"
    create_resp = await test_async_client.post(
        url,
        json=base_task_create_data,
        headers=auth_headers_a
    )
    assert create_resp.status_code == 201
    task_id = create_resp.json()["id"]
    original_score = create_resp.json().get("priority_score")

    # --- Act ---
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

    # --- Assert ---
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
    """
    Testa a tentativa de atualizar uma tarefa que não existe (ID inválido).
    Espera-se um erro HTTP 404 Not Found.
    """
    # --- Arrange ---
    url = f"{settings.API_V1_STR}/tasks/{uuid.uuid4()}" 
    # --- Act ---
    response = await test_async_client.put(url, json={"title": "Inexistente"}, headers=auth_headers_a)
    # --- Assert ---
    assert response.status_code == status.HTTP_404_NOT_FOUND

async def test_update_other_user_task_forbidden( 
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    auth_headers_b: Dict[str, str]
):
    """
    Testa a tentativa do User B de atualizar uma tarefa que pertence ao User A.
    A lógica deve impedir essa operação, resultando em um HTTP 404 Not Found
    (como se a tarefa não existisse para o User B).
    """
    # --- Arrange ---
    url = f"{settings.API_V1_STR}/tasks/"
    resp_a = await test_async_client.post(url, json=base_task_create_data, headers=auth_headers_a)
    assert resp_a.status_code == 201
    task_a_id = resp_a.json()["id"]

    # --- Act ---
    url_put = f"{settings.API_V1_STR}/tasks/{task_a_id}"
    response_b = await test_async_client.put(url_put, json={"title": "Hackeado?"}, headers=auth_headers_b)

    # --- Assert ---
    assert response_b.status_code == status.HTTP_404_NOT_FOUND

# ==========================================
# --- Testes DELETE /tasks/{id} ---
# ==========================================
async def test_delete_task_success(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str]
):
    """
    Testa a deleção bem-sucedida de uma tarefa pelo seu proprietário.
    Verifica se o status code é HTTP 204 No Content e se uma tentativa
    posterior de obter a tarefa deletada resulta em HTTP 404 Not Found.
    """
    # --- Arrange ---
    url = f"{settings.API_V1_STR}/tasks/"
    create_resp = await test_async_client.post(url, json=base_task_create_data, headers=auth_headers_a)
    assert create_resp.status_code == 201
    task_id = create_resp.json()["id"]

    # --- Act ---
    url_delete = f"{settings.API_V1_STR}/tasks/{task_id}"
    delete_response = await test_async_client.delete(url_delete, headers=auth_headers_a)

    # --- Assert (Delete) ---
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT

    # --- Assert (Verificar Get posterior falha) ---
    url_get = f"{settings.API_V1_STR}/tasks/{task_id}"
    get_response = await test_async_client.get(url_get, headers=auth_headers_a)
    assert get_response.status_code == status.HTTP_404_NOT_FOUND

async def test_delete_task_not_found(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str]
):
    """
    Testa a tentativa de deletar uma tarefa que não existe (ID inválido).
    Espera-se um erro HTTP 404 Not Found.
    """
    # --- Arrange ---
    url = f"{settings.API_V1_STR}/tasks/{uuid.uuid4()}" 
    # --- Act ---
    response = await test_async_client.delete(url, headers=auth_headers_a)
    # --- Assert ---
    assert response.status_code == status.HTTP_404_NOT_FOUND

async def test_delete_other_user_task_forbidden( 
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    auth_headers_b: Dict[str, str]
):
    """
    Testa a tentativa do User B de deletar uma tarefa que pertence ao User A.
    A operação deve ser impedida, resultando em HTTP 404 Not Found.
    """
    # --- Arrange ---
    url = f"{settings.API_V1_STR}/tasks/"
    resp_a = await test_async_client.post(url, json=base_task_create_data, headers=auth_headers_a)
    assert resp_a.status_code == 201
    task_a_id = resp_a.json()["id"]

    # --- Act ---
    url_delete = f"{settings.API_V1_STR}/tasks/{task_a_id}"
    response_b = await test_async_client.delete(url_delete, headers=auth_headers_b)

    # --- Assert ---
    # No seu código original, o teste espera `assert response_b.status_code == status.HTTP_404_NOT_FOUND`
    # Esta linha foi comentada no original, mas a lógica da docstring e do nome sugere que a asserção deveria estar aqui.
    # Para seguir estritamente, mantenho como no original, mas uma asserção é esperada aqui.
    # (O seu código original aqui não tinha a asserção de status code final)

# ==========================================
# --- Testes de Segurança (JWT) ---
# ==========================================
async def test_access_tasks_invalid_token_format(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str], 
    mocker
):
    """
    Testa o acesso ao endpoint de listagem de tarefas (`/tasks/`) com um token JWT
    que está mal formatado (não é um JWT válido).
    Espera-se um erro HTTP 401 Unauthorized e um log de erro específico
    da camada de segurança.
    """
    # --- Arrange ---
    url = f"{settings.API_V1_STR}/tasks/"
    invalid_headers = {"Authorization": "Bearer tokeninvalido.nao.jwt"}
    mock_sec_logger = mocker.patch("app.core.security.logger")
    # --- Act ---
    response = await test_async_client.get(url, headers=invalid_headers)
    # --- Assert ---
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "validar as credenciais" in response.json()["detail"]
    mock_sec_logger.error.assert_called_once()
    assert "Not enough segments" in mock_sec_logger.error.call_args[0][0]

async def test_access_tasks_token_wrong_secret(
    test_async_client: AsyncClient,
    mocker 
):
    """
    Testa o acesso ao endpoint de listagem de tarefas (`/tasks/`) com um token JWT
    que foi assinado com uma chave secreta incorreta.
    Espera-se um erro HTTP 401 Unauthorized e um log de erro indicando falha
    na verificação da assinatura.
    """
    # --- Arrange ---
    from app.core.security import create_access_token 

    user_id_dummy = uuid.uuid4()
    username_dummy = "dummyuser"

    wrong_secret = "outra-chave-secreta-bem-diferente"
    assert wrong_secret != settings.JWT_SECRET_KEY 

    import jwt as jose_jwt
    to_encode = {"sub": str(user_id_dummy),
                "username": username_dummy,
                "exp": datetime.now(timezone.utc) + timedelta(minutes=15)
                }
    token_really_wrong_key = jose_jwt.encode(to_encode, wrong_secret, algorithm=settings.JWT_ALGORITHM)
    mock_sec_logger = mocker.patch("app.core.security.logger")
    url = f"{settings.API_V1_STR}/tasks/"
    invalid_headers = {"Authorization": f"Bearer {token_really_wrong_key}"}
    # --- Act ---
    response = await test_async_client.get(url, headers=invalid_headers)
    # --- Assert ---
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
    """
    Testa o acesso ao endpoint de listagem de tarefas (`/tasks/`) com um token JWT
    que já expirou.
    Espera-se um erro HTTP 401 Unauthorized e um log de erro indicando
    que a assinatura expirou.
    """
    # --- Arrange ---

    _, user_id = test_user_a_token_and_id 

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
    url = f"{settings.API_V1_STR}/tasks/"
    invalid_headers = {"Authorization": f"Bearer {expired_token}"}
    # --- Act ---
    response = await test_async_client.get(url, headers=invalid_headers)
    # --- Assert ---
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Não autenticado" in response.json().get("detail", "") or \
           "Credenciais inválidas" in response.json().get("detail", "") or \
           "Token expirado" in response.json().get("detail", "") or \
           "validar as credenciais" in response.json().get("detail", "")

# ================================================================
# --- Testes de Tentativas de Injeção em Filtros de Listagem ---
# ================================================================
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
    Testa tentativas de injeção de query MongoDB (ou SQL-like) nos parâmetros
    de filtro de string (`project`, `tag`) do endpoint de listagem de tarefas.
    A API deve tratar esses inputs como strings literais ou rejeitá-los com
    HTTP 422 Unprocessable Entity se o tipo de dado esperado for estritamente string
    e o valor injetado for, por exemplo, um dicionário (como `{"$ne": ...}`).
    Se um valor que parece uma string maliciosa passar e resultar em 200 OK,
    o teste verifica se nenhuma tarefa inesperada é retornada (a lista deve ser vazia
    ou o filtro deve ser tratado literalmente).
    """
    # --- Arrange ---
    url = f"{settings.API_V1_STR}/tasks/?{param_name}={str(injected_value)}" 
    # --- Act ---
    response = await test_async_client.get(url, headers=auth_headers_a)
    # --- Assert ---
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY \
        or response.status_code == status.HTTP_200_OK, \
        f"Recebido status inesperado {response.status_code} para injeção em '{param_name}'"

    if response.status_code == status.HTTP_200_OK:
        tasks = response.json()
        assert isinstance(tasks, list)

async def test_list_tasks_filter_regex_injection(
    test_async_client: AsyncClient,
    auth_headers_a: Dict[str, str],
    create_filter_sort_tasks: List[Dict] 
):
    """
    Testa especificamente uma tentativa de injeção de expressão regular MongoDB (`/.*/)
    no parâmetro de filtro 'project'.
    Espera-se que o Pydantic/FastAPI trate o input como uma string literal e,
    portanto, não encontre tarefas (ou apenas tarefas cujo nome do projeto seja
    literalmente "/.*/").
    """
    # --- Arrange ---
    payload_str = "/.*/" 
    url = f"{settings.API_V1_STR}/tasks/?project={payload_str}"
    # --- Act ---
    response = await test_async_client.get(url, headers=auth_headers_a)
    # --- Assert ---
    assert response.status_code == status.HTTP_200_OK
    tasks = response.json()
    assert isinstance(tasks, list)
    found_literal_match = any(task.get("project") == payload_str for task in tasks)
    assert not found_literal_match or len(tasks) == 0, \
           "Injeção de Regex parece ter encontrado resultados inesperados ou foi tratada literalmente de forma incorreta."
    
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
    Testa se a criação de uma tarefa que é identificada como urgente
    (pela função `is_task_urgent`) dispara corretamente a função de background
    `send_urgent_task_notification`.
    Utiliza mocks para controlar o resultado de `is_task_urgent` e para
    verificar a chamada a `send_urgent_task_notification`.
    """
    # --- Arrange ---
    mock_send_email = mocker.patch(
        "app.routers.tasks.send_urgent_task_notification",
        new_callable=AsyncMock
    )
    mocker.patch("app.routers.tasks.is_task_urgent", return_value=True) 

    urgent_task_payload = {
        "title": "Tarefa Super Urgente Imediata",
        "description": "Precisa de email agora",
        "importance": 5,
        "due_date": (date.today() - timedelta(days=1)).isoformat() 
    }
    url = f"{settings.API_V1_STR}/tasks/"
    # --- Act ---
    response = await test_async_client.post(url, json=urgent_task_payload, headers=auth_headers_a)

    # --- Assert ---
    assert response.status_code == status.HTTP_201_CREATED
    created_task_data = response.json()
    mock_send_email.assert_called_once()
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
    Testa se a criação de uma tarefa que NÃO é identificada como urgente
    (pela função `is_task_urgent` mockada para retornar False) NÃO dispara
    a função de background `send_urgent_task_notification`.
    """
    # --- Arrange ---
    mock_send_email = mocker.patch(
        "app.routers.tasks.send_urgent_task_notification",
        new_callable=AsyncMock
    )
    mocker.patch("app.routers.tasks.is_task_urgent", return_value=False) 

    non_urgent_task_payload = {
        "title": "Tarefa Não Urgente Imediata",
        "description": "Sem pressa",
        "importance": 1,
        "due_date": (date.today() + timedelta(days=30)).isoformat() 
    }
    url = f"{settings.API_V1_STR}/tasks/"
    # --- Act ---
    response = await test_async_client.post(url, json=non_urgent_task_payload, headers=auth_headers_a)

    # --- Assert ---
    assert response.status_code == status.HTTP_201_CREATED
    mock_send_email.assert_not_called()