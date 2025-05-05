# app/db/task_crud.py
import logging
import uuid
from datetime import date, datetime, timezone
from typing import List, Optional, Dict, Any, Tuple

from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorCollection
from pymongo import ASCENDING, DESCENDING
from pydantic import ValidationError

from app.models.task import Task, TaskCreate, TaskUpdate, TaskStatus 

# Nome da coleção no MongoDB para tarefas
TASKS_COLLECTION = "tasks"

# --- Funções Auxiliares (internas ao CRUD) ---

def _get_tasks_collection(db: AsyncIOMotorDatabase) -> AsyncIOMotorCollection:
    """Retorna a coleção de tarefas."""
    return db[TASKS_COLLECTION]

def _parse_sort_params(sort_by: Optional[str], sort_order: str) -> Optional[List[Tuple[str, int]]]:
    """Converte parâmetros de sort em formato para pymongo."""
    if sort_by in ["priority_score", "due_date", "created_at", "importance"]:
        mongo_order = DESCENDING if sort_order.lower() == "desc" else ASCENDING
        return [(sort_by, mongo_order)]
    return None

# --- Funções CRUD para Tarefas ---

async def create_task(db: AsyncIOMotorDatabase, task_db: Task) -> Optional[Task]:
    """
    Cria uma nova tarefa no banco de dados.
    Recebe um objeto Task já validado e com campos calculados (id, owner_id, etc.).
    Retorna o objeto Task criado ou None em caso de erro.
    """
    collection = _get_tasks_collection(db)
    task_db_dict = task_db.model_dump(mode="json") 
    try:
        insert_result = await collection.insert_one(task_db_dict)
        if insert_result.acknowledged:
            return task_db 
        else:
            return None
    except Exception as e:
        print(f"DB Error creating task: {e}") 
        return None

async def get_task_by_id(db: AsyncIOMotorDatabase, task_id: uuid.UUID, owner_id: uuid.UUID) -> Optional[Task]:
    """Busca uma tarefa pelo seu ID e ID do proprietário."""
    collection = _get_tasks_collection(db)
    task_dict = await collection.find_one({"id": str(task_id), "owner_id": str(owner_id)})
    if task_dict:
        task_dict.pop('_id', None)
        try:
            return Task.model_validate(task_dict)
        except (ValidationError, Exception) as e:
            print(f"DB Validation error get_task_by_id {task_id}: {e}") 
            return None 
    return None

async def get_tasks_by_owner(
    db: AsyncIOMotorDatabase,
    owner_id: uuid.UUID,
    *, 
    status_filter: Optional[TaskStatus] = None,
    due_before: Optional[date] = None,
    project_filter: Optional[str] = None,
    tags_filter: Optional[List[str]] = None,
    sort_by: Optional[str] = None,
    sort_order: str = "desc",
    limit: int = 100,
    skip: int = 0
) -> List[Task]:
    """
    Busca tarefas de um proprietário com filtros, ordenação e paginação.
    Retorna uma lista de objetos Task.
    """
    collection = _get_tasks_collection(db)
    query: Dict[str, Any] = {"owner_id": str(owner_id)}

    # Adiciona filtros opcionais
    if status_filter:
        query["status"] = status_filter.value
    if due_before:
        due_before_dt = datetime.combine(due_before, datetime.min.time(), tzinfo=timezone.utc)
        query["due_date"] = {"$lte": due_before_dt}
    if project_filter:
        query["project"] = project_filter
    if tags_filter:
        query["tags"] = {"$all": tags_filter} 

    sort_list = _parse_sort_params(sort_by, sort_order)

    validated_tasks = []
    try:
        tasks_cursor = collection.find(query).skip(skip).limit(limit)
        if sort_list:
            tasks_cursor = tasks_cursor.sort(sort_list)

        async for task_dict in tasks_cursor:
            task_dict.pop('_id', None)
            try:
                validated_tasks.append(Task.model_validate(task_dict))
            except (ValidationError, Exception) as e:
                 print(f"DB Validation error list_tasks {task_dict.get('id')}: {e}") 
                 continue 
        return validated_tasks
    except Exception as e:
        print(f"DB Error listing tasks for owner {owner_id}: {e}") 
        return []


async def update_task(
    db: AsyncIOMotorDatabase,
    task_id: uuid.UUID,
    owner_id: uuid.UUID,
    update_data: Dict[str, Any] 
) -> Optional[Task]:
    """
    Atualiza uma tarefa existente.
    Recebe um dicionário com os campos $set do MongoDB.
    Retorna o objeto Task atualizado ou None se não encontrada/erro.
    """
    collection = _get_tasks_collection(db)
    update_data["updated_at"] = datetime.now(timezone.utc)

    try:
        updated_task_dict_raw = await collection.find_one_and_update(
            {"id": str(task_id), "owner_id": str(owner_id)},
            {"$set": update_data},
            return_document=True 
        )

        if updated_task_dict_raw:
            updated_task_dict_raw.pop('_id', None)
            try:
                return Task.model_validate(updated_task_dict_raw)
            except (ValidationError, Exception) as e:
                 print(f"DB Validation error update_task {task_id}: {e}") 
                 return None
        else:
            return None 
    except Exception as e:
        print(f"DB Error updating task {task_id}: {e}") 
        return None


async def delete_task(db: AsyncIOMotorDatabase, task_id: uuid.UUID, owner_id: uuid.UUID) -> bool:
    """
    Deleta uma tarefa pelo ID e ID do proprietário.
    Retorna True se a deleção foi bem-sucedida (1 documento deletado), False caso contrário.
    """
    collection = _get_tasks_collection(db)
    try:
        delete_result = await collection.delete_one({"id": str(task_id), "owner_id": str(owner_id)})
        return delete_result.deleted_count == 1
    except Exception as e:
        print(f"DB Error deleting task {task_id}: {e}") 
        return False
    
async def create_task_indexes(db: AsyncIOMotorDatabase):
    """Cria índices importantes para a coleção de tarefas se não existirem."""
    collection = _get_tasks_collection(db) 
    try:
        await collection.create_index("id", unique=True, name="task_id_unique_idx")
        await collection.create_index("owner_id", name="task_owner_idx")
        await collection.create_index(
            [("owner_id", ASCENDING), ("due_date", DESCENDING)], 
            name="task_owner_due_date_idx"
        )
        await collection.create_index(
            [("owner_id", ASCENDING), ("priority_score", DESCENDING)], 
            name="task_owner_priority_idx"
        )
        await collection.create_index("tags", name="task_tags_idx")

        logging.info("Índices da coleção 'tasks' verificados/criados.")
    except Exception as e:
        logging.error(f"Erro ao criar índices da coleção 'tasks': {e}")