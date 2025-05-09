# app/routers/tasks.py
"""
Este módulo define as rotas da API para o gerenciamento de Tarefas (Tasks).
Inclui operações CRUD (Criar, Ler, Atualizar, Deletar) para tarefas,
além de listagem com filtros, ordenação e paginação.
As rotas são protegidas e associadas ao usuário autenticado.
Utiliza BackgroundTasks para operações que não precisam bloquear a resposta,
como o envio de webhooks e notificações por e-mail.
"""

# ========================
# --- Importações ---
# ========================
import logging
import uuid
from datetime import date, datetime, timezone
from typing import Annotated, List, Optional

from fastapi import (APIRouter, BackgroundTasks, Body, Depends, HTTPException, Path,
                   Query, Response, status)
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import ValidationError

# --- Módulos da Aplicação ---
from app.core.dependencies import CurrentUser, DbDep
from app.core.email import send_urgent_task_notification
from app.core.utils import (calculate_priority_score, is_task_urgent,
                            send_webhook_notification)
from app.db import task_crud
from app.models.task import Task, TaskCreate, TaskStatus, TaskUpdate
from app.core.config import settings

# ========================
# --- Configurações e Constantes ---
# ========================
logger = logging.getLogger(__name__)

# ========================
# --- Configuração do Router ---
# ========================
router = APIRouter(
    prefix="/tasks",
    tags=["Tasks"],
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Recurso (tarefa) não encontrado."},
        status.HTTP_401_UNAUTHORIZED: {"description": "Não autorizado (Token JWT inválido, ausente ou expirado)."},
        status.HTTP_403_FORBIDDEN: {"description": "Proibido (Usuário autenticado não tem permissão para acessar/modificar este recurso específico)."}
    },
)

# ========================
# --- Endpoint: Criar Tarefa ---
# ========================
@router.post(
    "/",
    response_model=Task,
    status_code=status.HTTP_201_CREATED,
    summary="Cria uma nova tarefa para o usuário autenticado",
    description=(
        "Cria uma nova tarefa associada ao usuário atualmente autenticado. "
        "A pontuação de prioridade é calculada automaticamente com base na importância e data de entrega. "
        "O ID do proprietário (`owner_id`) e os timestamps (`created_at`) são definidos pelo servidor."
    ),
    response_description="A tarefa recém-criada, incluindo todos os seus detalhes e campos gerados.",
)
async def create_task(
    task_in: Annotated[TaskCreate, Body(description="Dados da nova tarefa a ser criada.")],
    db: DbDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks
):
    """
    Endpoint para criar uma nova tarefa.

    Fluxo de execução:
    1. Extrai os dados da tarefa do corpo da requisição (`task_in`).
    2. Calcula a `priority_score` com base na importância e data de entrega.
    3. Constrói o objeto completo da tarefa (`Task`), incluindo ID, `owner_id` (do `current_user`),
       `created_at` e a `priority_score` calculada. Valida este objeto com Pydantic.
    4. Persiste a tarefa no banco de dados usando `task_crud.create_task`.
    5. Se a criação for bem-sucedida, agenda tarefas em segundo plano para:
        - Enviar uma notificação de webhook (evento `task.created`).
        - Se a tarefa for urgente, enviar uma notificação por e-mail para o usuário.
    6. Retorna a tarefa criada.

    Levanta `HTTPException` em caso de erro de validação, falha na persistência ou outros problemas.
    """
    task_data_from_request = task_in.model_dump(exclude_unset=True)

    priority_score_calculated = calculate_priority_score(
        importance=task_in.importance,
        due_date=task_in.due_date
    )
    logger.info(f"Prioridade calculada para nova tarefa (Título: '{task_in.title}'): {priority_score_calculated}")

    try:
        task_db_obj_to_create = Task(
            id=uuid.uuid4(),
            owner_id=current_user.id,
            created_at=datetime.now(timezone.utc),
            priority_score=priority_score_calculated,
            **task_data_from_request
        )
    except ValidationError as e:
        logger.error(f"Erro de validação Pydantic ao montar objeto Task para usuário {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Erro interno na validação dos dados da tarefa: {e.errors()}"
        )

    created_task_from_db = await task_crud.create_task(db=db, task_db=task_db_obj_to_create)
    if created_task_from_db is None: # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao salvar a tarefa no banco de dados."
        )
    logger.info(f"Tarefa {created_task_from_db.id} criada com sucesso para usuário {current_user.id}.")

    task_dict_for_webhook = created_task_from_db.model_dump(mode="json")
    background_tasks.add_task(
         send_webhook_notification,
         event_type="task.created",
         task_data=task_dict_for_webhook
    )
    logger.debug(f"Tarefa de webhook 'task.created' para {created_task_from_db.id} adicionada ao background.")

    if is_task_urgent(created_task_from_db):
        if current_user.email and current_user.full_name:
            logger.info(f"Tarefa {created_task_from_db.id} é urgente. Agendando e-mail de notificação para {current_user.email}.")
            background_tasks.add_task(
                send_urgent_task_notification,
                user_email=current_user.email,
                user_name=current_user.full_name,
                task_title=created_task_from_db.title,
                task_id=str(created_task_from_db.id),
                task_due_date=str(created_task_from_db.due_date) if created_task_from_db.due_date else None,
                priority_score=created_task_from_db.priority_score or 0.0
            )
        else:
             logger.warning(f"Usuário {current_user.id} (username: {current_user.username}) não possui e-mail ou nome completo configurado. "
                            f"Notificação por e-mail para tarefa urgente {created_task_from_db.id} não será enviada.")

    return created_task_from_db

# ========================
# --- Endpoint: Listar Tarefas ---
# ========================
@router.get(
    "/",
    response_model=List[Task],
    summary="Lista as tarefas do usuário autenticado com filtros e ordenação",
    description=(
        "Recupera uma lista de tarefas pertencentes exclusivamente ao usuário autenticado.\n"
        "Suporta múltiplos filtros combinados (status, data de entrega até, projeto, tags).\n"
        "Permite ordenação por: `priority_score`, `due_date`, `created_at`, `importance`.\n"
        "A paginação é controlada por `limit` e `skip`."
    ),
    response_description="Uma lista (potencialmente vazia) das tarefas do usuário, filtradas e ordenadas conforme os parâmetros.",
)
async def list_tasks(
    db: DbDep,
    current_user: CurrentUser,
    status_filter: Annotated[Optional[TaskStatus], Query(alias="status", description="Filtrar tarefas por status específico.")] = None,
    due_before: Annotated[Optional[date], Query(description="Filtrar tarefas com data de entrega até (inclusive) esta data.")] = None,
    project_filter: Annotated[Optional[str], Query(alias="project", min_length=1, description="Filtrar tarefas por nome exato do projeto.")] = None,
    tags_filter: Annotated[Optional[List[str]], Query(alias="tag", min_length=1, description="Filtrar tarefas que contenham TODAS as tags fornecidas.")] = None,
    sort_by: Annotated[Optional[str], Query(enum=["priority_score", "due_date", "created_at", "importance"], description="Campo para ordenação das tarefas.")] = None,
    sort_order: Annotated[str, Query(enum=["asc", "desc"], description="Ordem da ordenação (ascendente ou descendente).")] = "desc",
    limit: Annotated[int, Query(ge=1, le=1000, description="Número máximo de tarefas a retornar.")] = 100,
    skip: Annotated[int, Query(ge=0, description="Número de tarefas a pular (para paginação).")] = 0,
):
    """
    Endpoint para listar tarefas do usuário autenticado.

    A busca é delegada para a função `task_crud.get_tasks_by_owner`, que lida com a
    construção da query no banco de dados com base nos filtros, ordenação e paginação fornecidos.
    Todos os filtros e parâmetros são opcionais.
    """
    logger.info(f"Listando tarefas para usuário {current_user.id} com filtros: status='{status_filter}', "
                f"due_before='{due_before}', project='{project_filter}', tags='{tags_filter}', "
                f"sort_by='{sort_by}', sort_order='{sort_order}', limit={limit}, skip={skip}")

    tasks = await task_crud.get_tasks_by_owner(
        db=db,
        owner_id=current_user.id,
        status_filter=status_filter,
        due_before=due_before,
        project_filter=project_filter,
        tags_filter=tags_filter,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        skip=skip
    )
    logger.debug(f"Encontradas {len(tasks)} tarefas para usuário {current_user.id} com os filtros aplicados.")
    return tasks

# ========================
# --- Endpoint: Obter Tarefa Específica ---
# ========================
@router.get(
    "/{task_id}",
    response_model=Task,
    summary="Busca uma tarefa específica pelo seu ID",
    description="Recupera os detalhes completos de uma tarefa específica, desde que ela pertença ao usuário autenticado.",
    response_description="Os detalhes completos da tarefa encontrada.",
    responses={status.HTTP_403_FORBIDDEN: {"description": "Acesso negado: esta tarefa não pertence a você ou não existe para você."}}
)
async def get_task(
    task_id: Annotated[uuid.UUID, Path(description="ID da tarefa a ser recuperada.")],
    db: DbDep,
    current_user: CurrentUser
):
    """
    Endpoint para buscar uma única tarefa pelo seu ID (UUID).

    A função `task_crud.get_task_by_id` é responsável por verificar se a tarefa
    com o `task_id` fornecido pertence ao `current_user.id`.
    Se a tarefa não for encontrada ou não pertencer ao usuário, retorna HTTP 404.
    """
    logger.info(f"Buscando tarefa {task_id} para usuário {current_user.id}.")
    task = await task_crud.get_task_by_id(db=db, task_id=task_id, owner_id=current_user.id)

    if task is None:
        logger.warning(f"Tarefa {task_id} não encontrada ou acesso negado para usuário {current_user.id}.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tarefa com ID '{task_id}' não encontrada ou você não tem permissão para acessá-la."
        )
    logger.debug(f"Tarefa {task_id} encontrada para usuário {current_user.id}: {task.title}")
    return task

# ========================
# --- Endpoint: Atualizar Tarefa ---
# ========================
@router.put(
    "/{task_id}",
    response_model=Task,
    summary="Atualiza uma tarefa existente do usuário autenticado",
    description=(
        "Atualiza campos de uma tarefa existente, desde que ela pertença ao usuário autenticado.\n"
        "A pontuação de prioridade (`priority_score`) é recalculada automaticamente se `importance` ou `due_date` forem modificados.\n"
        "O campo `updated_at` é atualizado automaticamente."
    ),
    response_description="Os detalhes completos da tarefa após a atualização.",
    responses={status.HTTP_403_FORBIDDEN: {"description": "Acesso negado: esta tarefa não pertence a você."}}
)
async def update_task(
    task_id: Annotated[uuid.UUID, Path(description="ID da tarefa a ser atualizada.")],
    task_update_payload: Annotated[TaskUpdate, Body(description="Campos da tarefa a serem atualizados.")],
    db: DbDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks
):
    """
    Endpoint para atualizar campos específicos de uma tarefa existente.

    Fluxo de execução:
    1. Busca a tarefa existente para garantir que ela pertence ao usuário e para obter valores atuais.
    2. Recebe os dados de atualização validados pelo modelo `TaskUpdate`.
    3. Se nenhum dado for fornecido para atualização, retorna um erro HTTP 400.
    4. Prepara o dicionário `update_data_for_db` apenas com os campos enviados.
    5. Verifica se `importance` ou `due_date` foram alterados para recalcular `priority_score`.
    6. Chama `task_crud.update_task` para persistir as alterações.
    7. Agenda notificação de webhook para `task.updated`.
    8. Retorna a tarefa atualizada.
    """
    logger.info(f"Iniciando atualização da tarefa {task_id} para usuário {current_user.id} com payload: {task_update_payload.model_dump(exclude_unset=True)}")
    existing_task = await task_crud.get_task_by_id(db=db, task_id=task_id, owner_id=current_user.id)
    if not existing_task:
        logger.warning(f"Tentativa de atualizar tarefa {task_id} que não foi encontrada para usuário {current_user.id}.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tarefa com ID '{task_id}' não encontrada ou você não tem permissão para modificá-la."
        )

    update_data_from_request = task_update_payload.model_dump(exclude_unset=True)

    if not update_data_from_request:
        logger.info(f"Nenhum campo fornecido para atualização da tarefa {task_id}.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nenhum campo válido fornecido para atualização."
        )

    new_importance = update_data_from_request.get("importance", existing_task.importance)
    if "due_date" in update_data_from_request:
        new_due_date = update_data_from_request.get("due_date")
    else:
        new_due_date = existing_task.due_date

    should_recalculate_priority = False
    if "importance" in update_data_from_request and update_data_from_request["importance"] != existing_task.importance:
        should_recalculate_priority = True
    if "due_date" in update_data_from_request and new_due_date != existing_task.due_date:
        should_recalculate_priority = True
    if "priority_score" in update_data_from_request: # pragma: no cover
        should_recalculate_priority = False

    update_data_for_db = update_data_from_request.copy()

    if should_recalculate_priority:
        new_priority_score = calculate_priority_score(
            importance=new_importance,
            due_date=new_due_date
        )
        update_data_for_db["priority_score"] = new_priority_score
        logger.info(f"Prioridade para tarefa {task_id} recalculada para: {new_priority_score}.")

    updated_task_from_db = await task_crud.update_task(
        db=db,
        task_id=task_id,
        owner_id=current_user.id,
        update_data=update_data_for_db
    )

    if updated_task_from_db is None:
        logger.error(f"Falha ao atualizar tarefa {task_id} no DB para usuário {current_user.id}. CRUD retornou None.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Não foi possível atualizar a tarefa com ID '{task_id}'. " # String de detalhe original
                   "Pode ter sido deletada ou ocorreu um erro interno." # Mantido para consistência com teste.
        )
    logger.info(f"Tarefa {updated_task_from_db.id} atualizada com sucesso para usuário {current_user.id}.")

    task_dict_for_webhook = updated_task_from_db.model_dump(mode="json")
    background_tasks.add_task(
        send_webhook_notification,
        event_type="task.updated",
        task_data=task_dict_for_webhook
    )
    logger.debug(f"Tarefa de webhook 'task.updated' para {updated_task_from_db.id} adicionada ao background.")

    return updated_task_from_db

# ========================
# --- Endpoint: Deletar Tarefa ---
# ========================
@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deleta uma tarefa do usuário autenticado",
    description="Remove permanentemente uma tarefa específica do banco de dados, desde que ela pertença ao usuário autenticado.",
    responses={
        status.HTTP_204_NO_CONTENT: {"description": "Tarefa deletada com sucesso (sem corpo de resposta)."}
    }
)
async def delete_task(
    task_id: Annotated[uuid.UUID, Path(description="ID da tarefa a ser deletada.")],
    db: DbDep,
    current_user: CurrentUser
):
    """
    Endpoint para deletar uma tarefa específica.

    Verifica se a tarefa pertence ao usuário autenticado e, se sim, a remove
    permanentemente do banco de dados usando `task_crud.delete_task`.
    Retorna HTTP 204 (No Content) em caso de sucesso.

    Levanta `HTTPException` com status 404 se a tarefa não for encontrada ou
    não pertencer ao usuário.
    """
    logger.info(f"Iniciando deleção da tarefa {task_id} para usuário {current_user.id}.")
    deleted_successfully = await task_crud.delete_task(
        db=db,
        task_id=task_id,
        owner_id=current_user.id
    )

    if not deleted_successfully:
        logger.warning(f"Falha ao deletar tarefa {task_id}. Não encontrada ou não pertence ao usuário {current_user.id}.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tarefa com ID '{task_id}' não encontrada ou você não tem permissão para deletá-la."
        )

    logger.info(f"Tarefa {task_id} deletada com sucesso para usuário {current_user.id}.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)