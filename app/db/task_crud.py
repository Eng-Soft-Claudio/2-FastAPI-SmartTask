# app/db/task_crud.py
"""
Módulo contendo as funções CRUD (Create, Read, Update, Delete)
para interagir com a coleção de tarefas no MongoDB.
Inclui também funções auxiliares e para criação de índices.
"""

# ========================
# --- Importações ---
# ========================
import logging
import uuid
from datetime import date, datetime, timezone
from typing import List, Optional, Dict, Any, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorCollection
from pymongo import ASCENDING, DESCENDING
from pydantic import ValidationError

# --- Módulos da Aplicação ---
from app.models.task import Task, TaskCreate, TaskUpdate, TaskStatus

# ========================
# --- Configurações e Constantes ---
# ========================
logger = logging.getLogger(__name__)
TASKS_COLLECTION = "tasks"

# ========================
# --- Funções Auxiliares (Internas) ---
# ========================
def _get_tasks_collection(db: AsyncIOMotorDatabase) -> AsyncIOMotorCollection:
    """Retorna a coleção de tarefas do banco de dados."""
    return db[TASKS_COLLECTION]

def _parse_sort_params(sort_by: Optional[str], sort_order: str) -> Optional[List[Tuple[str, int]]]:
    """
    Converte os parâmetros de ordenação de string para o formato do PyMongo.

    Args:
        sort_by: Campo pelo qual ordenar.
        sort_order: Ordem da ordenação ("asc" ou "desc").

    Returns:
        Lista de tuplas para ordenação do PyMongo ou None se o campo não for válido.
    """
    if sort_order.lower() == "asc":
        mongo_order = ASCENDING
    else:
        mongo_order = DESCENDING

    if sort_by in ["priority_score", "due_date", "created_at", "importance"]:
        return [(sort_by, mongo_order)]
    return None

# ========================
# --- Operações CRUD para Tarefas ---
# ========================
async def create_task(db: AsyncIOMotorDatabase, task_db: Task) -> Optional[Task]:
    """
    Cria uma nova tarefa no banco de dados.

    A tarefa já deve chegar validada e com campos como ID e owner_id preenchidos.

    Args:
        db: Instância da conexão com o banco de dados.
        task_db: Objeto Task contendo os dados da tarefa a ser criada.

    Returns:
        O objeto Task criado se sucesso, None caso contrário.
    """
    collection = _get_tasks_collection(db)
    task_db_dict = task_db.model_dump(mode="json")
    try:
        insert_result = await collection.insert_one(task_db_dict)
        if insert_result.acknowledged:
            return task_db
        else: # pragma: no cover
            logger.warning(f"Criação da tarefa para owner {task_db.owner_id} não foi reconhecida pelo DB (acknowledged=False).")
            return None
    except Exception as e:
        logger.exception(f"DB Error creating task for owner {task_db.owner_id}: {e}")
        return None

async def get_task_by_id(db: AsyncIOMotorDatabase, task_id: uuid.UUID, owner_id: uuid.UUID) -> Optional[Task]:
    """
    Busca uma tarefa específica pelo seu ID e pelo ID do proprietário.

    Args:
        db: Instância da conexão com o banco de dados.
        task_id: ID da tarefa a ser buscada.
        owner_id: ID do proprietário da tarefa.

    Returns:
        O objeto Task encontrado ou None se a tarefa não existir ou erro de validação.
    """
    collection = _get_tasks_collection(db)
    task_dict = await collection.find_one({"id": str(task_id), "owner_id": str(owner_id)})
    if task_dict:
        task_dict.pop('_id', None)
        try:
            return Task.model_validate(task_dict)
        except (ValidationError, Exception) as e:
            logger.error(f"DB Validation error get_task_by_id {task_id} for owner {owner_id}: {e}")
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

    Args:
        db: Instância da conexão com o banco de dados.
        owner_id: ID do proprietário das tarefas.
        status_filter: Filtra tarefas pelo status.
        due_before: Filtra tarefas com data de entrega anterior ou igual à data fornecida.
        project_filter: Filtra tarefas por nome do projeto.
        tags_filter: Filtra tarefas que contenham todas as tags listadas.
        sort_by: Campo para ordenação.
        sort_order: Ordem da ordenação ("asc" ou "desc").
        limit: Número máximo de tarefas a retornar.
        skip: Número de tarefas a pular (para paginação).

    Returns:
        Uma lista de objetos Task. Retorna lista vazia em caso de erro ou nenhuma tarefa encontrada.
    """
    collection = _get_tasks_collection(db)
    query: Dict[str, Any] = {"owner_id": str(owner_id)}

    if status_filter:
        query["status"] = status_filter.value
    if due_before:
        due_before_dt = datetime.combine(due_before, datetime.max.time(), tzinfo=timezone.utc) # Use max.time()
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
                logger.error(f"DB Validation error list_tasks owner {owner_id} task {task_dict.get('id', 'N/A')}: {e}")
                continue
        return validated_tasks
    except Exception as e:
        logger.exception(f"DB Error listing tasks for owner {owner_id}: {e}")
        return []

async def update_task(
    db: AsyncIOMotorDatabase,
    task_id: uuid.UUID,
    owner_id: uuid.UUID,
    update_data: Dict[str, Any]
) -> Optional[Task]:
    """
    Atualiza uma tarefa existente de um proprietário específico.

    Os dados de atualização devem ser fornecidos em um dicionário pronto para o
    operador '$set' do MongoDB. O campo 'updated_at' é automaticamente atualizado.

    Args:
        db: Instância da conexão com o banco de dados.
        task_id: ID da tarefa a ser atualizada.
        owner_id: ID do proprietário da tarefa.
        update_data: Dicionário com os campos a serem atualizados.

    Returns:
        O objeto Task atualizado ou None se a tarefa não for encontrada ou ocorrer um erro.
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
                logger.error(f"DB Validation error update_task {task_id} owner {owner_id}: {e}")
                return None
        else:
            logger.warning(f"Tentativa de atualizar tarefa não encontrada: ID {task_id}, Owner ID {owner_id}")
            return None
    except Exception as e:
        logger.exception(f"DB Error updating task {task_id} owner {owner_id}: {e}")
        return None

async def delete_task(db: AsyncIOMotorDatabase, task_id: uuid.UUID, owner_id: uuid.UUID) -> bool:
    """
    Deleta uma tarefa específica pelo seu ID e pelo ID do proprietário.

    Args:
        db: Instância da conexão com o banco de dados.
        task_id: ID da tarefa a ser deletada.
        owner_id: ID do proprietário da tarefa.

    Returns:
        True se a tarefa foi deletada com sucesso (1 documento afetado), False caso contrário.
    """
    collection = _get_tasks_collection(db)
    try:
        delete_result = await collection.delete_one({"id": str(task_id), "owner_id": str(owner_id)})
        return delete_result.deleted_count == 1
    except Exception as e:
        logger.exception(f"DB Error deleting task {task_id} owner {owner_id}: {e}")
        return False

# ========================
# --- Criação de Índices do Banco de Dados ---
# ========================
async def create_task_indexes(db: AsyncIOMotorDatabase):
    """
    Cria os índices necessários na coleção de tarefas para otimizar consultas.

    Os índices são criados apenas se ainda não existirem.
    Esta função é tipicamente chamada durante a inicialização da aplicação.

    Args:
        db: Instância da conexão com o banco de dados.
    """
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
        logging.error(f"Erro ao criar índices da coleção 'tasks': {e}", exc_info=True)