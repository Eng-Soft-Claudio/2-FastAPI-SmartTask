# app/worker.py
import asyncio
import logging
from datetime import date, datetime
from typing import Dict, Any, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase 
from arq import cron
from arq.connections import RedisSettings
from redis.asyncio import Redis
from app.core.config import settings
from app.db.mongodb_utils import connect_to_mongo, close_mongo_connection, get_database 
from app.db import user_crud, task_crud 
from app.core.email import send_urgent_task_notification
from app.core.utils import is_task_urgent
from app.models.task import Task, TaskStatus 

logger = logging.getLogger("arq.worker")

# === FUNÇÃO DA TAREFA PERIÓDICA ===
# Será chamada pelo scheduler do ARQ
async def check_and_notify_urgent_tasks(ctx: Dict[str, Any]):
    """
    Tarefa periódica que busca tarefas urgentes e notifica os usuários.
    'ctx' é um dicionário passado pelo worker ARQ, contém recursos como conexão DB.
    """
    logger.info("Executando verificação de tarefas urgentes...")
    db: Optional[AsyncIOMotorDatabase] = ctx.get("db")

    if db is None:
         logger.error("Conexão com o banco de dados não disponível no contexto ARQ.")
         return

    tasks_collection = db[task_crud.TASKS_COLLECTION] 
    users_collection = db[user_crud.USERS_COLLECTION] 

    # --- Critérios de Busca no MongoDB ---
    # 1. Tarefas não concluídas ou canceladas
    # 2. Com priority_score > threshold OU com due_date <= hoje
    today_start = datetime.combine(date.today(), datetime.min.time()) 

    query = {
        "status": {"$nin": [TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value]},
        "$or": [
            {"priority_score": {"$gt": settings.EMAIL_URGENCY_THRESHOLD}},
            {"due_date": {"$lte": today_start}} 
        ]
    }

    urgent_tasks_cursor = tasks_collection.find(query)
    count = 0

    async for task_dict in urgent_tasks_cursor:
        task_dict.pop('_id', None)
        try:
             task = Task.model_validate(task_dict) 

             user = await user_crud.get_user_by_id(db, task.owner_id)

             if user and user.email and user.full_name and not user.disabled:
                logger.info(f"Tarefa urgente encontrada ({task.id}), notificando usuário {user.email}...")

                await send_urgent_task_notification(
                     user_email=user.email,
                     user_name=user.full_name,
                     task_title=task.title,
                     task_id=str(task.id),
                     task_due_date=str(task.due_date) if task.due_date else None,
                     priority_score=task.priority_score or 0.0
                 )
                count += 1
             elif not user:
                logger.warning(f"Usuário {task.owner_id} da tarefa urgente {task.id} não encontrado.")
             elif user and user.disabled:
                 logger.info(f"Usuário {user.username} da tarefa urgente {task.id} está desabilitado. Notificação não enviada.")
             else: 
                 logger.warning(f"Usuário {user.username} da tarefa urgente {task.id} sem e-mail ou nome completo. Notificação não enviada.")

        except Exception as e:
            logger.exception(f"Erro ao processar tarefa urgente {task_dict.get('id')}: {e}")
            continue 

    logger.info(f"Verificação de tarefas urgentes concluída. {count} notificações enviadas.")


# === CONFIGURAÇÕES DO WORKER ARQ ===
async def startup(ctx: Dict[str, Any]):
    """Função executada quando o worker ARQ inicia."""
    logger.info("Iniciando worker ARQ...")
    db_instance = await connect_to_mongo()
    if db_instance is not None:
         ctx["db"] = db_instance 
         logger.info("Conexão MongoDB estabelecida para o worker ARQ.")
    else:
         logger.error("Falha ao conectar ao MongoDB no startup do worker ARQ.")
         ctx["db"] = None


async def shutdown(ctx: Dict[str, Any]):
    """Função executada quando o worker ARQ termina."""
    logger.info("Encerrando worker ARQ...")
    if ctx.get("db")is not None:
        await close_mongo_connection() 
        logger.info("Conexão MongoDB fechada pelo worker ARQ.")

# Classe de configurações do worker para ARQ
# ARQ procurará por esta classe quando executarmos o worker
class WorkerSettings:
    on_startup = startup
    on_shutdown = shutdown

    # --- Consulta à lista de tarefas agendadas ---
    cron_jobs = [
        cron(check_and_notify_urgent_tasks, minute={*range(0, 60, 1)}, run_at_startup=True),
        cron(check_and_notify_urgent_tasks, hour=8, minute=0),
    ]

    # --- Configurações do Redis ---
    if settings.REDIS_URL:
        try:
             redis_settings: RedisSettings = RedisSettings(
                 host=settings.REDIS_URL.host or 'localhost', 
                 port=int(settings.REDIS_URL.port) if settings.REDIS_URL.port else 6379,
                 database=int(settings.REDIS_URL.path[1:]) if settings.REDIS_URL.path and settings.REDIS_URL.path != '/' else 0, 
                 password=settings.REDIS_URL.password, 
                 # conn_timeout=10,
                 # conn_retries=5,
                 # conn_retry_delay=1,
            )
        except Exception as e:
             logger.exception(f"Erro ao configurar RedisSettings a partir da URL: {settings.REDIS_URL} - Erro: {e}")
             raise ValueError(f"Erro ao processar REDIS_URL: {e}")
    else:
         raise ValueError("REDIS_URL não está definida nas configurações, worker ARQ não pode iniciar.")