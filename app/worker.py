# app/worker.py
"""
Este módulo define um worker ARQ (Asynchronous Runtimes for Queueing) para executar
tarefas em segundo plano e agendadas.

Ele inclui:
- Uma tarefa periódica (`check_and_notify_urgent_tasks`) para verificar tarefas
  que se tornaram urgentes e notificar os usuários correspondentes por e-mail.
- Funções de ciclo de vida (`startup` e `shutdown`) para gerenciar a conexão
  com o banco de dados MongoDB para o worker.
- A classe `WorkerSettings` que configura o comportamento do worker ARQ, incluindo
  os `cron_jobs` e as configurações de conexão com o Redis (usado pelo ARQ como broker).
"""

# ========================
# --- Importações ---
# ========================

# --- Bibliotecas Padrão/Terceiros ---
import asyncio
import logging
from datetime import date, datetime, timezone 
from typing import Any, Dict, Optional

import arq.cron
from arq.connections import RedisSettings
from motor.motor_asyncio import AsyncIOMotorDatabase

# --- Módulos da Aplicação ---
from app.core.config import settings
from app.core.email import send_urgent_task_notification
from app.db import task_crud, user_crud
from app.db.mongodb_utils import (close_mongo_connection, connect_to_mongo) 
from app.models.task import Task, TaskStatus 

# =====================================
# --- Configurações e Constantes ---
# =====================================
logger = logging.getLogger("arq.worker") 

# ==================================
# --- Função de Tarefa Periódica ---
# ==================================
async def check_and_notify_urgent_tasks(ctx: Dict[str, Any]):
    """
    Tarefa periódica ARQ que varre o banco de dados em busca de tarefas
    consideradas urgentes e notifica os respectivos usuários por e-mail.

    Critérios de Urgência:
    - Tarefas não concluídas ou canceladas.
    - E que atendam a pelo menos um dos seguintes:
        - `priority_score` acima de um limiar definido (`EMAIL_URGENCY_THRESHOLD`).
        - `due_date` é hoje ou já passou.

    Args:
        ctx: Dicionário de contexto fornecido pelo worker ARQ. Espera-se que contenha
             uma instância de conexão com o banco de dados (`db`) injetada pela função `startup`.
    """
    logger.info("Executando job: Verificação e notificação de tarefas urgentes...")
    db: Optional[AsyncIOMotorDatabase] = ctx.get("db")

    if db is None:
        logger.error("Conexão com o banco de dados não disponível no contexto ARQ.")
        return
    tasks_collection = db[task_crud.TASKS_COLLECTION]
    users_collection = db[user_crud.USERS_COLLECTION] 
    today_start_utc = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)
    query_urgent_tasks = {
        "status": {"$nin": [TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value]},
        "$or": [
            {"priority_score": {"$gt": settings.EMAIL_URGENCY_THRESHOLD}},
            {"due_date": {"$lte": today_start_utc}} 
        ]
    }
    logger.debug(f"Query MongoDB para tarefas urgentes: {query_urgent_tasks}")

    urgent_tasks_cursor = tasks_collection.find(query_urgent_tasks)
    notifications_sent_count = 0
    async for task_dict in urgent_tasks_cursor:
        task_dict.pop('_id', None) 
        try:
            task = Task.model_validate(task_dict)
            logger.debug(f"Processando tarefa urgente ID: {task.id}, Título: {task.title}")
            user = await user_crud.get_user_by_id(db, task.owner_id)
            if user and user.email and user.full_name and not user.disabled:
                logger.info(f"Tarefa urgente ID '{task.id}' (Título: '{task.title}') encontrada. "
                            f"Notificando usuário: {user.username} (E-mail: {user.email}).")
                await send_urgent_task_notification(
                    user_email=user.email,
                    user_name=user.full_name,
                    task_title=task.title,
                    task_id=str(task.id),
                    task_due_date=str(task.due_date) if task.due_date else None, 
                    priority_score=task.priority_score or 0.0 
                )
                notifications_sent_count += 1
            elif not user:
                logger.warning(f"Usuário com ID '{task.owner_id}' associado à tarefa urgente '{task.id}' não foi encontrado no banco de dados.")
            elif user and user.disabled:
                logger.info(f"Usuário '{user.username}' (ID: {task.owner_id}) associado à tarefa urgente '{task.id}' está desabilitado. "
                            "Notificação não enviada.")
            else:
                logger.warning(f"Usuário '{user.username}' (ID: {task.owner_id}) associado à tarefa urgente '{task.id}' "
                               "não possui e-mail ou nome completo configurado. Notificação não enviada.")
        except Exception as e:
            logger.exception(f"Erro ao processar tarefa urgente (ID no dict: {task_dict.get('id', 'N/A')}): {e}")
            continue 
    logger.info(f"Verificação de tarefas urgentes concluída. Total de {notifications_sent_count} notificações enviadas.")

# ==========================================
# --- Funções de Ciclo de Vida do Worker ---
# ==========================================
async def startup(ctx: Dict[str, Any]):
    """
    Função executada quando o worker ARQ é iniciado.
    Responsável por estabelecer conexões com recursos externos, como o banco de dados.

    Args:
        ctx: Dicionário de contexto do ARQ, onde podemos armazenar recursos
             (como a conexão DB) para serem usados pelas tarefas do worker.
    """
    logger.info("Worker ARQ: Iniciando rotinas de startup...")
    db_connection_instance = await connect_to_mongo()
    if db_connection_instance is not None:
        ctx["db"] = db_connection_instance
        logger.info("Worker ARQ: Conexão com MongoDB estabelecida e armazenada no contexto.")
    else:
        logger.error("Worker ARQ: Falha crítica ao conectar ao MongoDB durante o startup. "
                     "A conexão não estará disponível para as tarefas.")
        ctx["db"] = None

async def shutdown(ctx: Dict[str, Any]):
    """
    Função executada quando o worker ARQ está sendo encerrado.
    Responsável por liberar recursos, como fechar a conexão com o banco de dados.

    Args:
        ctx: Dicionário de contexto do ARQ.
    """
    logger.info("Worker ARQ: Iniciando rotinas de shutdown...")
    if ctx.get("db") is not None: 
        await close_mongo_connection()
        logger.info("Worker ARQ: Conexão com MongoDB fechada.")
    else:
        logger.info("Worker ARQ: Nenhuma conexão com MongoDB para fechar (não estava disponível ou já fechada).")

# =======================================
# --- Configurações do Worker ARQ ---
# =======================================
class WorkerSettings:
    """
    Define as configurações para o worker ARQ.
    Isso inclui funções de ciclo de vida (startup/shutdown),
    tarefas agendadas (`cron_jobs`) e configurações de conexão com o Redis.
    """
    on_startup = startup
    on_shutdown = shutdown
    cron_jobs = [
        arq.cron(check_and_notify_urgent_tasks, minute={*range(0, 60, 15)}, run_at_startup=False), 
        arq.cron(check_and_notify_urgent_tasks, hour=8, minute=0, run_at_startup=False) 
    ]
    logger.info(f"Cron jobs configurados: {len(cron_jobs)} jobs definidos.")
    if settings.REDIS_URL:
        try:
            host = settings.REDIS_URL.host or 'localhost'
            port = int(settings.REDIS_URL.port) if settings.REDIS_URL.port else 6379
            db_num_from_path = int(settings.REDIS_URL.path.strip('/')) if settings.REDIS_URL.path and settings.REDIS_URL.path != '/' else 0
            password = settings.REDIS_URL.password

            redis_settings: RedisSettings = RedisSettings(
                host=host,
                port=port,
                database=db_num_from_path,
                password=password,
            )
            logger.info(f"RedisSettings configuradas para ARQ: host={host}, port={port}, db={db_num_from_path}")
        except Exception as e:# pragma: no cover
            logger.exception(f"Erro crítico ao configurar RedisSettings a partir da URL: '{settings.REDIS_URL}'. Erro: {e}")
            raise ValueError(f"Erro ao processar REDIS_URL para ARQ: {e}")# pragma: no cover
    else:
        logger.error("Configuração crítica ausente: REDIS_URL não está definida. Worker ARQ não pode iniciar.")
        raise ValueError("REDIS_URL não está definida nas configurações. O worker ARQ requer uma URL do Redis para operar.")