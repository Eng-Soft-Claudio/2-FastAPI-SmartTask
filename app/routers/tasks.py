# app/routers/tasks.py

# --- Importações Essenciais ---
import logging
from typing import List, Optional, Annotated
import uuid
from datetime import date, datetime, timezone

# --- Imports do FastAPI ---
from fastapi import (
    APIRouter, HTTPException, Body, status, Depends, Response, Query,
    BackgroundTasks
)

# --- Imports do MongoDB/Motor ---
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import ValidationError 

# --- Imports da Nossa Aplicação ---
from app.models.task import Task, TaskCreate, TaskUpdate, TaskStatus
from app.db import task_crud
from app.db.mongodb_utils import get_database
from app.core.dependencies import CurrentUser
from app.models.user import UserInDB
from app.core.utils import calculate_priority_score, is_task_urgent, send_webhook_notification

# --- Instanciar Logger ---
logger = logging.getLogger(__name__)

# --- Configuração do Roteador ---
router = APIRouter(
    prefix="/tasks",
    tags=["Tasks"],
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Tarefa não encontrada"},
        status.HTTP_401_UNAUTHORIZED: {"description": "Não autorizado (Token inválido ou ausente)"},
        status.HTTP_403_FORBIDDEN: {"description": "Proibido (Usuário não tem permissão para este recurso)"}
    },
)

# --- Dependência de Banco de Dados (Simplificada) ---
DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_database)]

# ==============================================================================
# --- ROTAS CRUD PROTEGIDAS PARA TAREFAS ---
# (Agora utilizando app.db.task_crud)
# ==============================================================================

@router.post(
    "/",
    response_model=Task,
    status_code=status.HTTP_201_CREATED,
    summary="Cria uma nova tarefa",
    description="Cria uma nova tarefa associada ao usuário autenticado. A prioridade e owner_id são definidos automaticamente.",
    response_description="A tarefa recém-criada com todos os seus detalhes.",
)
async def create_task(
    task_in: Annotated[TaskCreate, Body(description="Dados da nova tarefa a ser criada")],
    db: DbDep, 
    current_user: CurrentUser,
    background_tasks: BackgroundTasks
):
    """
    Endpoint para criar uma nova tarefa.

    - Recebe dados validados pelo modelo `TaskCreate`.
    - Calcula a `priority_score`.
    - Associa a tarefa ao `owner_id` do usuário logado.
    - Chama `task_crud.create_task` para salvar no MongoDB.
    - Envia notificações (webhook) em background se necessário.
    - Retorna a tarefa criada.
    """
    task_data = task_in.model_dump(exclude_unset=True)

    # --- Calcular Prioridade ---
    priority = calculate_priority_score(
        importance=task_in.importance,
        due_date=task_in.due_date
    )

    # --- Criar o objeto Tarefa completo ---
    try:
        task_db_obj = Task(
            id=uuid.uuid4(),
            owner_id=current_user.id,
            created_at=datetime.now(timezone.utc),
            priority_score=priority,
            **task_data
        )
    except ValidationError as e:
         logger.error(f"Erro de validação Pydantic ao montar Task para criação: {e}")
         raise HTTPException(
             status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
             detail=f"Erro interno na validação dos dados da tarefa: {e}"
         )

    # --- Inserir no Banco de Dados via CRUD ---
    created_task = await task_crud.create_task(db=db, task_db=task_db_obj)

    if created_task is None:
         logger.error(f"Falha ao criar tarefa no banco de dados para usuário {current_user.id}.")
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Falha ao salvar a tarefa no banco de dados.")

    # --- Disparar Tarefas em Background ---
    task_dict_for_webhook = created_task.model_dump(mode="json")
    background_tasks.add_task(
         send_webhook_notification,
         event_type="task.created",
         task_data=task_dict_for_webhook
    )
    logger.info(f"Tarefa de webhook 'task.created' para {created_task.id} adicionada ao background.")


    return created_task


@router.get(
    "/",
    response_model=List[Task],
    summary="Lista as tarefas do usuário autenticado",
    description="""Recupera uma lista de tarefas pertencentes ao usuário autenticado.
    Permite filtros por status, prazo (até uma data), projeto e tags (contendo todas).
    Permite ordenação por 'priority_score', 'due_date', 'created_at' ou 'importance'.""",
    response_description="Uma lista (possivelmente vazia) contendo as tarefas filtradas e ordenadas do usuário.",
)
async def list_tasks(
    db: DbDep, 
    current_user: CurrentUser,
    # --- Parâmetros de Filtro ---
    status_filter: Annotated[Optional[TaskStatus], Query(alias="status")] = None,
    due_before: Annotated[Optional[date], Query()] = None,
    project_filter: Annotated[Optional[str], Query(alias="project", min_length=1)] = None,
    tags_filter: Annotated[Optional[List[str]], Query(alias="tag", min_length=1)] = None,
    # --- Parâmetros de Ordenação ---
    sort_by: Annotated[Optional[str], Query(enum=["priority_score", "due_date", "created_at", "importance"])] = None,
    sort_order: Annotated[Optional[str], Query(enum=["asc", "desc"])] = "desc",
    # --- Parâmetros de Paginação ---
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    skip: Annotated[int, Query(ge=0)] = 0,
):
    """
    Endpoint para listar tarefas do usuário autenticado com filtros, ordenação e paginação.
    Delega a busca para `task_crud.get_tasks_by_owner`.
    """
    # --- Chamar a função CRUD para buscar as tarefas ---
    tasks = await task_crud.get_tasks_by_owner(
        db=db,
        owner_id=current_user.id,
        status_filter=status_filter,
        due_before=due_before,
        project_filter=project_filter,
        tags_filter=tags_filter,
        sort_by=sort_by,
        sort_order=sort_order or "desc", 
        limit=limit,
        skip=skip
    )

    return tasks


@router.get(
    "/{task_id}",
    response_model=Task,
    summary="Busca uma tarefa específica por ID",
    description="Recupera os detalhes de uma tarefa específica, **se** ela pertencer ao usuário autenticado.",
    response_description="Os detalhes completos da tarefa encontrada.",
    responses={status.HTTP_403_FORBIDDEN: {"description": "Acesso negado a esta tarefa"}}
)
async def get_task(
    task_id: uuid.UUID,
    db: DbDep, 
    current_user: CurrentUser
):
    """
    Endpoint para buscar uma única tarefa pelo seu ID (UUID).
    Delega a busca para `task_crud.get_task_by_id`, que já inclui a verificação do owner.
    """
    # --- Buscar a tarefa via CRUD ---
    task = await task_crud.get_task_by_id(db=db, task_id=task_id, owner_id=current_user.id)

    if task is None:
        logger.warning(f"Tentativa de acesso à tarefa {task_id} falhou ou tarefa não encontrada para usuário {current_user.id}.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Tarefa com ID {task_id} não encontrada.")

    return task


@router.put(
    "/{task_id}",
    response_model=Task,
    summary="Atualiza uma tarefa existente",
    description="Atualiza os campos de uma tarefa existente, **se** ela pertencer ao usuário autenticado. A prioridade é recalculada se necessário.",
    response_description="Os detalhes completos da tarefa atualizada.",
    responses={status.HTTP_403_FORBIDDEN: {"description": "Acesso negado a esta tarefa"}}
)
async def update_task(
    task_id: uuid.UUID,
    task_update: Annotated[TaskUpdate, Body(description="Campos da tarefa a serem atualizados")],
    db: DbDep, 
    current_user: CurrentUser,
    background_tasks: BackgroundTasks
):
    """
    Endpoint para atualizar campos específicos de uma tarefa.

    - Busca a tarefa existente para obter os valores atuais (necessário para recalcular prioridade).
    - Recebe dados validados pelo modelo `TaskUpdate`.
    - Prepara dicionário `update_data` apenas com campos enviados.
    - Recalcula `priority_score` se `importance` ou `due_date` mudarem.
    - Adiciona `updated_at`.
    - Chama `task_crud.update_task` para salvar no MongoDB.
    - Envia webhook em background.
    - Retorna a tarefa completa e atualizada.
    """
    # --- Obter Tarefa Existente ---
    existing_task = await task_crud.get_task_by_id(db=db, task_id=task_id, owner_id=current_user.id)
    if not existing_task:
        logger.warning(f"Tentativa de atualizar tarefa {task_id} não encontrada para usuário {current_user.id}.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Tarefa {task_id} não encontrada ou não pertence a você.")

    # --- Preparar Dados para Atualização ---
    update_data_from_request = task_update.model_dump(exclude_unset=True)

    if not update_data_from_request:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Nenhum campo válido fornecido para atualização.")

    # --- Recalcular Prioridade (se necessário) ---
    should_recalculate_priority = False
    new_importance = update_data_from_request.get("importance", existing_task.importance)
    new_due_date = update_data_from_request.get("due_date", existing_task.due_date) \
                    if "due_date" in update_data_from_request else existing_task.due_date

    # Verifica se os campos relevantes foram alterados
    if "importance" in update_data_from_request and update_data_from_request["importance"] != existing_task.importance:
        should_recalculate_priority = True
    if "due_date" in update_data_from_request and new_due_date != existing_task.due_date:
        should_recalculate_priority = True

    # Dicionário final a ser passado para o $set no CRUD
    update_data_for_db = update_data_from_request.copy()

    if should_recalculate_priority:
         new_priority = calculate_priority_score(
            importance=new_importance,
            due_date=new_due_date
         )
         update_data_for_db["priority_score"] = new_priority
         logger.info(f"Recalculada prioridade para tarefa {task_id} para: {new_priority}")

    # --- Executar Atualização via CRUD ---
    updated_task = await task_crud.update_task(
        db=db,
        task_id=task_id,
        owner_id=current_user.id,
        update_data=update_data_for_db 
    )

    if updated_task is None:
         logger.error(f"Falha ao atualizar tarefa {task_id} no banco de dados para usuário {current_user.id}.")
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Não foi possível atualizar a tarefa {task_id} (pode ter sido deletada).")

    # --- Disparar Tarefas em Background ---
    task_dict_for_webhook = updated_task.model_dump(mode="json")
    background_tasks.add_task(
        send_webhook_notification,
        event_type="task.updated",
        task_data=task_dict_for_webhook
    )
    logger.info(f"Tarefa de webhook 'task.updated' para {updated_task.id} adicionada ao background.")

    return updated_task


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deleta uma tarefa",
    description="Remove permanentemente uma tarefa do banco de dados, **se** ela pertencer ao usuário autenticado.",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Tarefa não encontrada ou não pertence a você"},
        status.HTTP_403_FORBIDDEN: {"description": "Acesso negado a esta tarefa"},
        status.HTTP_204_NO_CONTENT: {"description": "Tarefa deletada com sucesso (sem corpo de resposta)"},
    }
)
async def delete_task(
    task_id: uuid.UUID,
    db: DbDep, 
    current_user: CurrentUser
):
    """
    Endpoint para deletar uma tarefa.
    Delega a deleção para `task_crud.delete_task`.
    """
    # --- Tentar deletar via CRUD ---
    deleted = await task_crud.delete_task(db=db, task_id=task_id, owner_id=current_user.id)

    if not deleted:
         # Função CRUD retorna False se delete_one não deletou nada (count 0)
         logger.warning(f"Tentativa de deletar tarefa {task_id} não encontrada para usuário {current_user.id}.")
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Tarefa com ID {task_id} não encontrada ou não pertence a você.")

    return Response(status_code=status.HTTP_204_NO_CONTENT)