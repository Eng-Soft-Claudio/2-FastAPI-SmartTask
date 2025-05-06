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

# Logger específico para o worker ARQ, usando o logger padrão do ARQ para consistência.
# O ARQ usa "arq.worker" como um de seus loggers.
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
    # Obtém a conexão com o banco de dados do contexto do worker.
    db: Optional[AsyncIOMotorDatabase] = ctx.get("db")

    if db is None:
        logger.error("Conexão com o banco de dados não disponível no contexto ARQ.")
        return

    # Obtém as coleções do MongoDB.
    # É mais seguro referenciar os nomes das coleções a partir dos módulos CRUD,
    # embora também possam ser constantes definidas aqui.
    # Embora user_crud.get_user_by_id seja usado, a coleção é referenciada indiretamente.
    tasks_collection = db[task_crud.TASKS_COLLECTION]
    users_collection = db[user_crud.USERS_COLLECTION] 

    # --- Define os Critérios de Busca no MongoDB para Tarefas Urgentes ---
    # A data de "hoje" no início do dia, para comparações com due_date.
    today_start_utc = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)

    # Query MongoDB para encontrar tarefas urgentes.
    # 1. Status: não deve ser 'concluída' nem 'cancelada'.
    # 2. Urgência:
    #    - Ou a pontuação de prioridade é alta (acima do threshold configurado).
    #    - Ou a data de entrega (due_date) é hoje ou anterior.
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

    # Itera sobre as tarefas urgentes encontradas.
    async for task_dict in urgent_tasks_cursor:
        task_dict.pop('_id', None) 
        try:
            # Valida os dados da tarefa com o modelo Pydantic Task.
            task = Task.model_validate(task_dict)
            logger.debug(f"Processando tarefa urgente ID: {task.id}, Título: {task.title}")

            # Busca os dados do usuário proprietário da tarefa.
            user = await user_crud.get_user_by_id(db, task.owner_id)

            if user and user.email and user.full_name and not user.disabled:
                # Se o usuário existe, tem e-mail, nome e não está desabilitado, envia a notificação.
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
                # Caso onde o usuário existe e não está desabilitado, mas falta e-mail ou nome completo.
                logger.warning(f"Usuário '{user.username}' (ID: {task.owner_id}) associado à tarefa urgente '{task.id}' "
                               "não possui e-mail ou nome completo configurado. Notificação não enviada.")

        except Exception as e:
            # Captura qualquer erro durante o processamento de uma tarefa específica
            # para que o job continue processando as demais tarefas urgentes.
            logger.exception(f"Erro ao processar tarefa urgente (ID no dict: {task_dict.get('id', 'N/A')}): {e}")
            continue # Continua para a próxima tarefa.

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
        # Armazena a instância da conexão com o banco de dados no contexto do worker.
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
# O ARQ procurará por uma classe chamada `WorkerSettings` neste arquivo
# quando o comando `arq app.worker.WorkerSettings` (ou similar) for executado.
class WorkerSettings:
    """
    Define as configurações para o worker ARQ.
    Isso inclui funções de ciclo de vida (startup/shutdown),
    tarefas agendadas (`cron_jobs`) e configurações de conexão com o Redis.
    """
    # Funções a serem executadas no início e no fim do ciclo de vida do worker.
    on_startup = startup
    on_shutdown = shutdown

    # --- Definição dos Cron Jobs (Tarefas Agendadas) ---
    # `arq.cron` é usado para definir tarefas que rodam em intervalos específicos.
    cron_jobs = [
        arq.cron(check_and_notify_urgent_tasks, minute={*range(0, 60, 15)}, run_at_startup=False), 
        # Verifica tarefas urgentes uma vez ao dia, às 08:00.
        # run_at_startup=False para não rodar duas vezes se já rodou o acima.
        arq.cron(check_and_notify_urgent_tasks, hour=8, minute=0, run_at_startup=False) 
    ]
    logger.info(f"Cron jobs configurados: {len(cron_jobs)} jobs definidos.")


    # --- Configurações do Redis (Broker do ARQ) ---
    # ARQ usa Redis para enfileirar e gerenciar tarefas.
    if settings.REDIS_URL:
        try:
            # Parse da Pydantic `RedisDsn` para os parâmetros de `RedisSettings` do ARQ.
            # Nota: As versões mais recentes do ARQ podem ter simplificado isso,
            # permitindo passar diretamente a URL string ou um objeto `redis.asyncio.Redis`.
            # Esta forma é explícita e compatível com versões mais antigas.
            host = settings.REDIS_URL.host or 'localhost'
            port = int(settings.REDIS_URL.port) if settings.REDIS_URL.port else 6379
            # O caminho na URL do Redis (ex: /0) é usado para o número do banco de dados.
            db_num_from_path = int(settings.REDIS_URL.path.strip('/')) if settings.REDIS_URL.path and settings.REDIS_URL.path != '/' else 0
            password = settings.REDIS_URL.password

            redis_settings: RedisSettings = RedisSettings(
                host=host,
                port=port,
                database=db_num_from_path,
                password=password,
                # Timeouts e retries podem ser configurados aqui para maior robustez, se necessário.
                # Ex: conn_timeout=10, conn_retries=5, conn_retry_delay=1,
            )
            logger.info(f"RedisSettings configuradas para ARQ: host={host}, port={port}, db={db_num_from_path}")
        except Exception as e:
            # Captura qualquer erro durante o parsing da URL do Redis ou configuração.
            logger.exception(f"Erro crítico ao configurar RedisSettings a partir da URL: '{settings.REDIS_URL}'. Erro: {e}")
            # Levanta um erro para impedir que o worker inicie com uma configuração de Redis inválida.
            raise ValueError(f"Erro ao processar REDIS_URL para ARQ: {e}")
    else:
        # Se REDIS_URL não estiver definida, o ARQ não pode funcionar.
        logger.error("Configuração crítica ausente: REDIS_URL não está definida. Worker ARQ não pode iniciar.")
        raise ValueError("REDIS_URL não está definida nas configurações. O worker ARQ requer uma URL do Redis para operar.")