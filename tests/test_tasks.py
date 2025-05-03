# tests/test_tasks.py
import pytest
from httpx import AsyncClient
from fastapi import status
from typing import Dict, List, Any # Para type hints
import uuid # Para IDs

from app.core.config import settings
from app.models.task import TaskStatus # Para comparar status

# Marca todos os testes neste módulo para usar asyncio
pytestmark = pytest.mark.asyncio

# Dados de teste comuns
task_data_1 = {
    "title": "Tarefa Teste 1 (Tasks)",
    "description": "Descrição da tarefa 1",
    "importance": 3,
    "due_date": "2025-12-01",
    "tags": ["testing", "backend"],
    "project": "Projeto Teste"
}

task_data_2 = {
    "title": "Tarefa Teste 2 (Tasks)",
    "importance": 5,
    "status": TaskStatus.IN_PROGRESS.value # Usar valor do enum
}


async def test_create_task_success(
    test_async_client: AsyncClient,
    auth_headers: Dict[str, str] # Usa a fixture de headers
):
    """Testa a criação bem-sucedida de uma tarefa."""
    url = f"{settings.API_V1_STR}/tasks/"
    response = await test_async_client.post(url, json=task_data_1, headers=auth_headers)

    assert response.status_code == status.HTTP_201_CREATED
    response_data = response.json()
    assert response_data["title"] == task_data_1["title"]
    assert response_data["importance"] == task_data_1["importance"]
    assert response_data["due_date"] == task_data_1["due_date"]
    assert "id" in response_data
    assert "owner_id" in response_data # Garante que owner foi adicionado
    assert "priority_score" in response_data # Garante que foi calculado

async def test_create_task_unauthorized(test_async_client: AsyncClient):
     """Testa criar tarefa sem autenticação."""
     url = f"{settings.API_V1_STR}/tasks/"
     response = await test_async_client.post(url, json=task_data_1) # Sem headers
     assert response.status_code == status.HTTP_401_UNAUTHORIZED

async def test_list_tasks_success(
    test_async_client: AsyncClient,
    auth_headers: Dict[str, str]
):
    """Testa listar tarefas do usuário autenticado."""
    # Criar algumas tarefas primeiro para ter o que listar
    url_create = f"{settings.API_V1_STR}/tasks/"
    await test_async_client.post(url_create, json=task_data_1, headers=auth_headers)
    await test_async_client.post(url_create, json=task_data_2, headers=auth_headers)

    url_list = f"{settings.API_V1_STR}/tasks/"
    response = await test_async_client.get(url_list, headers=auth_headers)

    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert isinstance(response_data, list)
    # Verificar se pelo menos as tarefas criadas estão lá (pode haver outras dos testes de módulo)
    titles = [task["title"] for task in response_data]
    assert task_data_1["title"] in titles
    assert task_data_2["title"] in titles
    # Verificar que todas as tarefas listadas pertencem ao usuário logado (opcional mas bom)
    # Precisaríamos do ID do usuário da fixture test_user_token, talvez passando o user ID?

async def test_list_tasks_unauthorized(test_async_client: AsyncClient):
     """Testa listar tarefas sem autenticação."""
     url = f"{settings.API_V1_STR}/tasks/"
     response = await test_async_client.get(url) # Sem headers
     assert response.status_code == status.HTTP_401_UNAUTHORIZED

async def test_get_specific_task_success(
    test_async_client: AsyncClient,
    auth_headers: Dict[str, str]
):
    """Testa buscar uma tarefa específica do usuário."""
    # Criar uma tarefa
    url_create = f"{settings.API_V1_STR}/tasks/"
    create_response = await test_async_client.post(url_create, json=task_data_1, headers=auth_headers)
    assert create_response.status_code == 201
    task_id = create_response.json()["id"]

    # Buscar a tarefa criada
    url_get = f"{settings.API_V1_STR}/tasks/{task_id}"
    get_response = await test_async_client.get(url_get, headers=auth_headers)

    assert get_response.status_code == status.HTTP_200_OK
    response_data = get_response.json()
    assert response_data["id"] == task_id
    assert response_data["title"] == task_data_1["title"]

async def test_get_specific_task_not_found(
    test_async_client: AsyncClient,
    auth_headers: Dict[str, str]
):
    """Testa buscar uma tarefa com ID inexistente."""
    non_existent_id = uuid.uuid4() # Gera um UUID aleatório
    url = f"{settings.API_V1_STR}/tasks/{non_existent_id}"
    response = await test_async_client.get(url, headers=auth_headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND

async def test_get_specific_task_unauthorized(test_async_client: AsyncClient):
     """Testa buscar tarefa sem autenticação."""
     # Assumindo que alguma tarefa existe de outros testes
     some_valid_id_placeholder = uuid.uuid4() # Apenas para formar a URL
     url = f"{settings.API_V1_STR}/tasks/{some_valid_id_placeholder}"
     response = await test_async_client.get(url)
     assert response.status_code == status.HTTP_401_UNAUTHORIZED

# TODO: Adicionar testes para PUT e DELETE, incluindo casos de sucesso,
#       não encontrado, e tentativa de modificar/deletar tarefa de outro usuário (requer criar um segundo usuário/token).
# TODO: Adicionar testes para filtros e ordenação na listagem.