# app/core/utils.py
"""
Módulo contendo funções utilitárias diversas para a aplicação SmartTask.
Inclui cálculos de prioridade para tarefas, verificação de urgência de tarefas,
e envio de notificações via webhook.
"""

# ========================
# --- Importações ---
# ========================
import json
import hmac
import hashlib
import math # Embora math não seja usado explicitamente, é uma importação comum em utils.
import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional
# TYPE_CHECKING removido se não usado para imports condicionais de tipo.
import httpx

# --- Módulos da Aplicação ---
from models.task import Task # Importação direta do modelo Task
from core.config import settings

# ========================
# --- Configuração do Logger ---
# ========================
logger = logging.getLogger(__name__)

# ========================
# --- Função de Cálculo de Prioridade ---
# ========================
def calculate_priority_score(
    importance: int,
    due_date: Optional[date]
) -> Optional[float]:
    """
    Calcula a pontuação de prioridade de uma tarefa.

    A pontuação é baseada na importância fornecida e na data de vencimento,
    utilizando pesos configuráveis através das settings da aplicação.

    Args:
        importance: Nível de importância da tarefa (inteiro, 1-5).
        due_date: Data de vencimento da tarefa (objeto date ou None).

    Returns:
        A pontuação de prioridade calculada (float), ou None se a importância for inválida.
    """
    if not 1 <= importance <= 5:
        logger.warning(f"Cálculo de prioridade recebido com importância inválida: {importance}")
        return None

    # --- Score de Importância ---
    importance_score = importance * settings.PRIORITY_WEIGHT_IMPORTANCE

    # --- Score de Prazo ---
    due_date_score = 0.0
    if due_date:
        today = date.today()
        days_remaining = (due_date - today).days

        if days_remaining < 0:
            due_date_score = settings.PRIORITY_SCORE_IF_OVERDUE
            logger.debug(f"Tarefa atrasada ({days_remaining} dias), score de overdue: {due_date_score}")
        elif days_remaining == 0:
            due_date_score = settings.PRIORITY_WEIGHT_DUE_DATE / 1.0
            logger.debug(f"Tarefa vence hoje, score de prazo: {due_date_score}")
        elif days_remaining > 0:
            effective_days = max(1, days_remaining) # Evita divisão por zero ou por dias < 1
            due_date_score = settings.PRIORITY_WEIGHT_DUE_DATE / effective_days
            logger.debug(f"Tarefa vence em {days_remaining} dias, score de prazo: {due_date_score}")

    elif settings.PRIORITY_DEFAULT_SCORE_NO_DUE_DATE is not None:
        due_date_score = settings.PRIORITY_DEFAULT_SCORE_NO_DUE_DATE
        logger.debug(f"Tarefa sem prazo, score default de prazo: {due_date_score}")

    # --- Combinar Scores ---
    total_score = round(due_date_score + importance_score, 2)
    logger.debug(f"Score final calculado: {total_score} (prazo={due_date_score}, importancia={importance_score})")
    return total_score

# ========================
# --- Função de Tarefa Urgente ---
# ========================
def is_task_urgent(task: Task) -> bool:
    """
    Verifica se uma tarefa é considerada urgente para fins de notificação.

    Args:
        task: O objeto Task a ser verificado.

    Returns:
        True se a tarefa for considerada urgente, False caso contrário.
    """
    if task.priority_score is None and task.due_date is None:
        return False # Tarefa sem score nem prazo não pode ser urgente pelos critérios atuais

    if task.priority_score is not None and task.priority_score > settings.EMAIL_URGENCY_THRESHOLD:
        return True

    if task.due_date:
        today = date.today()
        if (task.due_date - today).days <= 0: # Vence hoje ou está atrasada
            return True
    return False

# ========================
# --- Função de Envio de Webhook ---
# ========================
async def send_webhook_notification(
    event_type: str,
    task_data: Dict[str, Any]
):
    """
    Envia uma notificação via webhook para a URL configurada.

    Inclui assinatura HMAC-SHA256 se WEBHOOK_SECRET estiver definido.

    Args:
        event_type: String identificando o tipo do evento (ex: 'task.created').
        task_data: Dicionário com os dados da tarefa.
    """
    if not settings.WEBHOOK_URL:
        logger.debug("Webhook URL não configurada, pulando envio.")
        return

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

    # --- Segurança: Assinatura ---
    if settings.WEBHOOK_SECRET:
        try:
            payload_bytes = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode('utf-8')
            secret_bytes = settings.WEBHOOK_SECRET.encode('utf-8')
            signature = hmac.new(secret_bytes, payload_bytes, hashlib.sha256).hexdigest()
            headers["X-SmartTask-Signature"] = f"sha256={signature}"
        except Exception as e:
            logger.error(f"Erro ao gerar assinatura HMAC para webhook: {e}", exc_info=True)
            return # Não envia se a assinatura falhar

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
            response.raise_for_status() # Levanta exceção para status de erro HTTP (4xx, 5xx)
            logger.info(f"Webhook enviado com sucesso para {webhook_url_str}. Status: {response.status_code}")

    except httpx.TimeoutException:
        logger.error(f"Timeout ao enviar webhook para {webhook_url_str}") # pragma: no cover
    except httpx.RequestError as exc:
        logger.error(f"Erro na requisição ao enviar webhook para {webhook_url_str}: {exc}")
    except httpx.HTTPStatusError as exc:
        logger.error(
            f"Erro no servidor do webhook ({webhook_url_str}). "
            f"Status: {exc.response.status_code}. Resposta: {exc.response.text[:200]}..."
        )
    except Exception as e:
        logger.exception(f"Erro inesperado ao enviar webhook para {webhook_url_str}: {e}")