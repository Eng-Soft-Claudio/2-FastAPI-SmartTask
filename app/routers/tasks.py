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
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorCollection
from pymongo import DESCENDING, ASCENDING
from pymongo.errors import DuplicateKeyError
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

# --- Dependências Tipadas para Melhor Legibilidade ---
DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_database)]

# Função auxiliar para obter a coleção de tarefas (simplifica injeção)
async def get_task_collection(db: DbDep) -> AsyncIOMotorCollection:
    """Retorna a coleção MongoDB 'tasks'."""
    return db[task_crud.TASKS_COLLECTION]
TaskCollectionDep = Annotated[AsyncIOMotorCollection, Depends(get_task_collection)]


# ==============================================================================
# --- ROTAS CRUD PROTEGIDAS PARA TAREFAS ---
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
    collection: TaskCollectionDep, 
    current_user: CurrentUser, 
    background_tasks: BackgroundTasks 
):
    """
    Endpoint para criar uma nova tarefa.

    - Recebe dados validados pelo modelo `TaskCreate`.
    - Calcula a `priority_score`.
    - Associa a tarefa ao `owner_id` do usuário logado.
    - Salva no MongoDB.
    - Envia notificações (e-mail, webhook) em background se necessário.
    - Retorna a tarefa criada.
    """
    # Converte dados de entrada Pydantic para dicionário, excluindo campos não enviados
    task_data = task_in.model_dump(exclude_unset=True)

    # --- Calcular Prioridade ---
    # Usa a função utilitária com os dados recebidos
    priority = calculate_priority_score(
        importance=task_in.importance,
        due_date=task_in.due_date
    )

    # --- Criar o objeto Tarefa completo para o DB ---
    task_db = Task(
        id=uuid.uuid4(),                  
        owner_id=current_user.id,          
        created_at=datetime.now(timezone.utc), 
        priority_score=priority,           
        **task_data                        
    )

    # Converte o objeto Pydantic para dicionário antes de inserir no MongoDB
    task_db_dict = task_db.model_dump(mode="json")

    try:
        # --- Inserir no Banco de Dados ---
        insert_result = await collection.insert_one(task_db_dict)
        if not insert_result.acknowledged:
             logger.error("Falha no ACK ao inserir tarefa no MongoDB.")
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="Falha ao salvar a tarefa no banco de dados.")

        # --- Disparar Tarefas em Background (Após Sucesso no DB) ---

        # 1. Webhook 
        task_dict_for_webhook = task_db.model_dump(mode="json") 
        background_tasks.add_task( 
             send_webhook_notification, 
             event_type="task.created",
             task_data=task_dict_for_webhook 
        )
        logger.info(f"Tarefa de webhook 'task.created' para {task_db.id} adicionada ao background.")

        # 2. Notificação por E-mail (se urgente e usuário configurado)
        # A lógica de envio de email em si não está implementada aqui, assumindo
        # que o worker ARQ cuida disso periodicamente.
        # Se quiséssemos enviar email *imediatamente* na criação/update:
        # if is_task_urgent(task_db):
        #     if current_user.email and current_user.full_name:
        #          background_tasks.add_task( # Também rodaria em background
        #              send_urgent_task_notification,
        #              user_email=current_user.email,
        #              # ... outros args ...
        #          )
        #          logger.info(f"Tarefa de email urgente para {task_db.id} adicionada ao background.")
        #     else:
        #          logger.warning(f"Usuário {current_user.id} sem e-mail/nome para notificação IMEDIATA da tarefa urgente {task_db.id}.")


    except DuplicateKeyError:
        logger.warning(f"Tentativa de criar tarefa duplicada para user {current_user.id}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Uma tarefa com identificador semelhante já existe para este usuário.")
    except Exception as e: 
        logger.exception(f"Erro inesperado ao criar tarefa ou agendar background tasks para user {current_user.id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Ocorreu um erro interno ao processar a criação da tarefa.")

    return task_db


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
    collection: TaskCollectionDep,
    current_user: CurrentUser, 
    # --- Parâmetros de Filtro ---
    status_filter: Annotated[Optional[TaskStatus], Query(
        alias="status", title="Filtro por Status",
        description="Filtrar tarefas por um status específico."
    )] = None,
    due_before: Annotated[Optional[date], Query(
        title="Vencimento Antes De",
        description="Filtrar tarefas com prazo de vencimento até esta data (inclusive)."
    )] = None,
    project_filter: Annotated[Optional[str], Query(
        alias="project", title="Filtro por Projeto",
        description="Filtrar tarefas por nome exato do projeto.", min_length=1
    )] = None,
    tags_filter: Annotated[Optional[List[str]], Query(
        alias="tag", title="Filtro por Tags (AND)",
        description="Filtrar tarefas que contenham TODAS as tags especificadas (usar ?tag=t1&tag=t2).", min_length=1
    )] = None,
    # --- Parâmetros de Ordenação ---
    sort_by: Annotated[Optional[str], Query(
        title="Ordenar Por",
        description="Campo para ordenar: 'priority_score', 'due_date', 'created_at', 'importance'.",
        enum=["priority_score", "due_date", "created_at", "importance"] 
    )] = None,
    sort_order: Annotated[Optional[str], Query(
        title="Ordem",
        description="Ordem da ordenação: 'asc' ou 'desc'.",
        enum=["asc", "desc"] 
    )] = "desc", 
    # --- Parâmetros de Paginação ---
    limit: Annotated[int, Query(ge=1, le=1000, title="Limite de Resultados", description="Número máximo de tarefas a retornar.")] = 100,
    skip: Annotated[int, Query(ge=0, title="Pular Resultados", description="Número de tarefas a pular (para paginação).")] = 0,
):
    """
    Endpoint para listar tarefas do usuário autenticado com filtros, ordenação e paginação.
    """
    query = {"owner_id": str(current_user.id)}

    # --- Adicionar Filtros Opcionais à Query MongoDB ---
    if status_filter:
        query["status"] = status_filter.value 
    if due_before:
        query["due_date"] = {"$lte": datetime.combine(due_before, datetime.min.time(), tzinfo=timezone.utc)} 
    if project_filter:
        query["project"] = project_filter 
    if tags_filter:
        query["tags"] = {"$all": tags_filter}

    # --- Determinar Campo e Ordem de Ordenação ---
    sort_tuple = None
    if sort_by in ["priority_score", "due_date", "created_at", "importance"]:
        mongo_order = DESCENDING if sort_order.lower() == "desc" else ASCENDING
        sort_tuple = (sort_by, mongo_order)

    # --- Executar Query com Paginação e Ordenação ---
    try:
        tasks_cursor = collection.find(query).skip(skip).limit(limit)
        if sort_tuple:
            tasks_cursor = tasks_cursor.sort([sort_tuple]) 

        # --- Processar e Validar Resultados ---
        validated_tasks = []
        async for task_dict in tasks_cursor:
            task_dict.pop('_id', None) 
            try:
                # Valida cada dicionário retornado com o modelo Pydantic Task
                validated_tasks.append(Task.model_validate(task_dict))
            except (ValidationError, Exception) as e:
                logger.error(f"Erro ao validar tarefa do DB (list {current_user.id}): {task_dict} - Erro: {e}")
                # Em produção, decidir se continua ou retorna erro parcial
                continue # Pula tarefa inválida por enquanto

        return validated_tasks

    except Exception as e: 
        logger.exception(f"Erro ao buscar/processar tarefas para user {current_user.id} com query {query}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Ocorreu um erro interno ao buscar as tarefas.")


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
    collection: TaskCollectionDep,
    current_user: CurrentUser 
):
    """
    Endpoint para buscar uma única tarefa pelo seu ID (UUID).
    Apenas retorna a tarefa se o ID for encontrado E pertencer ao usuário logado.
    """
    # Busca no MongoDB usando o ID da tarefa e o ID do usuário logado
    task_dict = await collection.find_one({
        "id": str(task_id),          
        "owner_id": str(current_user.id) 
    })

    if task_dict:
        task_dict.pop('_id', None) 
        try:
            # Valida os dados do DB com o modelo Pydantic Task
            return Task.model_validate(task_dict)
        except (ValidationError, Exception) as e:
            logger.error(f"Erro ao validar tarefa {task_id} do DB para user {current_user.id}: {e}")
            # Pode indicar inconsistência de dados no DB
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="Erro ao processar dados da tarefa encontrada.")
    else:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Tarefa com ID {task_id} não encontrada.")


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
    collection: TaskCollectionDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks 
):
    """
    Endpoint para atualizar campos específicos de uma tarefa.

    - Verifica se a tarefa pertence ao usuário.
    - Recebe dados validados pelo modelo `TaskUpdate`.
    - Recalcula `priority_score` se `importance` ou `due_date` mudarem.
    - Atualiza o campo `updated_at`.
    - Salva as alterações no MongoDB.
    - Envia webhook em background.
    - Retorna a tarefa completa e atualizada.
    """
    # --- Garantir que a tarefa existe e pertence ao usuário antes de prosseguir ---
    existing_task_dict = await collection.find_one({
        "id": str(task_id),
        "owner_id": str(current_user.id)
    })
    if not existing_task_dict:
        # Levanta 404 (ou 403 se preferíssemos verificar a existência geral)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                             detail=f"Tarefa {task_id} não encontrada ou não pertence a você.")

    # Validar tarefa existente para fácil acesso aos campos com tipos corretos
    try:
         existing_task = Task.model_validate(existing_task_dict)
    except Exception:
        logger.exception(f"Erro ao validar dados da tarefa existente {task_id} antes do update.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="Erro interno ao processar dados da tarefa existente.")

    # --- Preparar Dados para Atualização ---
    # Pega apenas os campos que foram explicitamente enviados no request 
    update_data = task_update.model_dump(exclude_unset=True, exclude={"owner_id"}) 

    # Se nenhum campo válido foi enviado para atualização
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Nenhum campo válido fornecido para atualização.")

    # --- Recalcular Prioridade (se necessário) ---
    should_recalculate_priority = False
    current_importance = existing_task.importance
    current_due_date = existing_task.due_date

    # Verifica se os campos relevantes para prioridade foram enviados na atualização
    if "importance" in update_data and update_data["importance"] != current_importance:
        current_importance = update_data["importance"] 
        should_recalculate_priority = True
    if "due_date" in update_data:
        new_due_date_obj = update_data["due_date"] 
        if new_due_date_obj != current_due_date:
            current_due_date = new_due_date_obj 
            should_recalculate_priority = True

    # Recalcula se algum dos campos chave mudou
    if should_recalculate_priority:
         priority = calculate_priority_score(
            importance=current_importance,
            due_date=current_due_date     
         )
         update_data["priority_score"] = priority 
         logger.info(f"Recalculada prioridade para tarefa {task_id} para: {priority}")

    # --- Definir Timestamp de Atualização ---
    update_data["updated_at"] = datetime.now(timezone.utc)

    # --- Executar Atualização Atômica no Banco de Dados ---
    try:
        updated_task_dict_raw = await collection.find_one_and_update(
            {"id": str(task_id), "owner_id": str(current_user.id)}, 
            {"$set": update_data}, 
            return_document=True 
        )

        if not updated_task_dict_raw:
             logger.error(f"Falha ao encontrar a tarefa {task_id} durante find_one_and_update, após verificação inicial.")
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tarefa {task_id} não encontrada durante a atualização.")

        # --- Processar Resultado e Enviar Webhook ---
        updated_task_dict_raw.pop('_id', None)
        try:
            updated_task = Task.model_validate(updated_task_dict_raw) 

            # Enviar Webhook em Background
            task_dict_for_webhook = updated_task.model_dump(mode="json")
            background_tasks.add_task(
                send_webhook_notification,
                event_type="task.updated",
                task_data=task_dict_for_webhook
            )
            logger.info(f"Tarefa de webhook 'task.updated' para {updated_task.id} adicionada ao background.")

            # Notificação por e-mail imediata poderia ser adicionada aqui também (via background_tasks) se necessário

            return updated_task 

        except (ValidationError, Exception) as e:
             logger.error(f"Erro ao validar tarefa atualizada do DB (ID: {task_id}) para user {current_user.id}: {e}")
             # Se a validação falhar após o update, indica um problema sério
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                 detail="Erro ao processar dados da tarefa após atualização.")

    except Exception as e: 
         logger.exception(f"Erro ao atualizar tarefa {task_id} ou agendar background tasks: {e}")
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                             detail="Erro interno ao processar atualização da tarefa.")



@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT, 
    summary="Deleta uma tarefa",
    description="Remove permanentemente uma tarefa do banco de dados, **se** ela pertencer ao usuário autenticado.",
    # Documenta explicitamente os erros além dos globais
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Tarefa não encontrada ou não pertence a você"},
        status.HTTP_403_FORBIDDEN: {"description": "Acesso negado a esta tarefa"},
        status.HTTP_204_NO_CONTENT: {"description": "Tarefa deletada com sucesso (sem corpo de resposta)"},
    }
)
async def delete_task(
    task_id: uuid.UUID,
    collection: TaskCollectionDep,
    current_user: CurrentUser 
    # Nota: Não precisamos de BackgroundTasks aqui, mas poderia ter para um evento 'task.deleted'
):
    """
    Endpoint para deletar uma tarefa.
    Só permite deletar tarefas que pertencem ao usuário logado.
    """
    # Tenta deletar o documento que combina ID da tarefa E ID do usuário
    delete_result = await collection.delete_one({
        "id": str(task_id),
        "owner_id": str(current_user.id) 
    })

    # Verifica se algum documento foi realmente deletado
    if delete_result.deleted_count == 0:
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Tarefa com ID {task_id} não encontrada ou não pertence a você.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)