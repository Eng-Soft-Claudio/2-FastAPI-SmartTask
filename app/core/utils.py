# app/core/utils.py
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional, TYPE_CHECKING
import math
from app.core.config import settings 
from app.models.task import Task
import httpx 
import json  
import logging 
import hmac   
import hashlib 

logger = logging.getLogger(__name__)

# --- Função de cálculo de prioridade ---
def calculate_priority_score(
    importance: int,
    due_date: Optional[date]
    ) -> Optional[float]:
    """
    Calcula a pontuação de prioridade de uma tarefa.

    Args:
        importance: Nível de importância da tarefa (ex: 1-5).
        due_date: Data de vencimento da tarefa (opcional).

    Returns:
        A pontuação de prioridade calculada, ou None se não aplicável.
        Retornaremos float para permitir scores não inteiros.
    """
    if not 1 <= importance <= 5:
         return None 

    # --- Importância
    importance_score = importance * settings.PRIORITY_WEIGHT_IMPORTANCE

    # --- Prazo
    due_date_score = 0.0 
    if due_date:
        today = date.today() 

        days_remaining = (due_date - today).days

        if days_remaining < 0: 
            due_date_score = settings.PRIORITY_SCORE_IF_OVERDUE

        elif days_remaining == 0: 
             due_date_score = settings.PRIORITY_WEIGHT_DUE_DATE / 1.0 

        elif days_remaining > 0:
            effective_days = max(1, days_remaining) 
            due_date_score = settings.PRIORITY_WEIGHT_DUE_DATE / effective_days
            importance_score = importance * settings.PRIORITY_WEIGHT_IMPORTANCE 

        else:
             due_date_score = 0.0

    elif settings.PRIORITY_DEFAULT_SCORE_NO_DUE_DATE is not None:
         due_date_score = settings.PRIORITY_DEFAULT_SCORE_NO_DUE_DATE

    # --- Combinar Scores
    total_score = round(due_date_score + importance_score, 2) 

    return total_score

# --- Função de tarefa urgente ---
def is_task_urgent(task: Task) -> bool:
    """Verifica se uma tarefa atende aos critérios de urgência para notificação."""
    # --- Critério 0: Tarefa deve ter um score ou prazo
    if task.priority_score is None and task.due_date is None:
         return False 

    # --- Critério 1: Score acima do limiar (e não None)
    if task.priority_score is not None and task.priority_score > settings.EMAIL_URGENCY_THRESHOLD:
        return True

    # --- Critério 2: Vence hoje ou está atrasada
    if task.due_date:
        today = date.today()
        days_remaining = (task.due_date - today).days
        if days_remaining <= 0:
            return True

    return False

# --- Função de Webhook ---
async def send_webhook_notification(
    event_type: str,
    task_data: Dict[str, Any] 
    ):
    """
    Envia uma notificação via webhook para a URL configurada (se houver).
    Executada em background.

    Args:
        event_type: Tipo do evento (ex: 'task.created', 'task.updated').
        task_data: Dados da tarefa como um dicionário Python.
    """
    if not settings.WEBHOOK_URL:
        logger.debug("Webhook URL não configurada, pulando envio.") 
        return 

    # Converter URL Pydantic para string
    webhook_url_str = str(settings.WEBHOOK_URL)

    payload = {
        "event": event_type,
        "task": task_data,
        "timestamp": datetime.now(timezone.utc).isoformat() 
    }

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "SmartTask-Webhook-Client/1.0" 
    }

    # --- Segurança de Assinatura ---
    if settings.WEBHOOK_SECRET:
        try:
            payload_bytes = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode('utf-8')
            secret_bytes = settings.WEBHOOK_SECRET.encode('utf-8')

            signature = hmac.new(secret_bytes, payload_bytes, hashlib.sha256).hexdigest()
            headers["X-SmartTask-Signature"] = f"sha256={signature}"
        except Exception as e:
             logger.error(f"Erro ao gerar assinatura HMAC para webhook: {e}")
             return 

    # --- Envio da Requisição HTTP ---
    try:
         async with httpx.AsyncClient() as client:
            logger.info(f"Enviando webhook evento '{event_type}' para {webhook_url_str}")
            response = await client.post(
                webhook_url_str,
                json=payload, 
                headers=headers,
                timeout=10.0 
            )

            response.raise_for_status()

            logger.info(f"Webhook enviado com sucesso para {webhook_url_str}. Status: {response.status_code}")

    except httpx.TimeoutException:
         logger.error(f"Timeout ao enviar webhook para {webhook_url_str}")
    except httpx.RequestError as exc:
         logger.error(f"Erro na requisição ao enviar webhook para {webhook_url_str}: {exc}")
    except httpx.HTTPStatusError as exc:
         logger.error(
             f"Erro no servidor do webhook ({webhook_url_str}). "
             f"Status: {exc.response.status_code}. Resposta: {exc.response.text[:200]}..." 
         )
    except Exception as e:
         logger.exception(f"Erro inesperado ao enviar webhook para {webhook_url_str}: {e}")