# app/core/utils.py

# ========================
# --- Importações ---
# ========================
import json
import hmac
import hashlib
import math
import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional, TYPE_CHECKING
from app.models.task import Task
import httpx 

# --- Módulos da Aplicação ---
from app.core.config import settings

# ===============================
# --- Configuração do Logger ---
# ===============================
logger = logging.getLogger(__name__)

# =============================================
# --- Função de Cálculo de Prioridade ---
# =============================================
def calculate_priority_score(
    importance: int,
    due_date: Optional[date]
    ) -> Optional[float]:
    """
    Calcula a pontuação de prioridade de uma tarefa com base na importância
    e na data de vencimento, utilizando pesos definidos nas configurações.

    Args:
        importance: Nível de importância da tarefa (inteiro, esperado 1-5).
        due_date: Data de vencimento da tarefa (objeto date ou None).

    Returns:
        A pontuação de prioridade calculada (float) ou None se a importância for inválida.
    """
    # Validação básica da importância
    if not 1 <= importance <= 5:
         logger.warning(f"Cálculo de prioridade recebido com importância inválida: {importance}")
         return None

    # =======================
    # --- Score Importância ---
    # =======================
    # Calcula a parte do score referente à importância
    importance_score = importance * settings.PRIORITY_WEIGHT_IMPORTANCE

    # ==================
    # --- Score Prazo ---
    # ==================
    # Inicializa o score de prazo
    due_date_score = 0.0
    if due_date:
        # Se há data de vencimento, calcula dias restantes
        today = date.today()
        days_remaining = (due_date - today).days

        if days_remaining < 0:
            # Tarefa atrasada recebe score máximo definido
            due_date_score = settings.PRIORITY_SCORE_IF_OVERDUE
            logger.debug(f"Tarefa atrasada ({days_remaining} dias), aplicando score de overdue: {due_date_score}")
        elif days_remaining == 0:
            # Tarefa vence hoje, score alto (inverso de 1 dia)
             due_date_score = settings.PRIORITY_WEIGHT_DUE_DATE / 1.0
             logger.debug(f"Tarefa vence hoje, aplicando score de prazo: {due_date_score}")
        elif days_remaining > 0:
            # Tarefa vence no futuro, score inversamente proporcional aos dias
            effective_days = max(1, days_remaining)
            due_date_score = settings.PRIORITY_WEIGHT_DUE_DATE / effective_days
            logger.debug(f"Tarefa vence em {days_remaining} dias, aplicando score de prazo: {due_date_score}")

    elif settings.PRIORITY_DEFAULT_SCORE_NO_DUE_DATE is not None:
         # Tarefa sem data de vencimento, usa score padrão (se definido)
         due_date_score = settings.PRIORITY_DEFAULT_SCORE_NO_DUE_DATE
         logger.debug(f"Tarefa sem prazo, aplicando score default de prazo: {due_date_score}")

    # =========================
    # --- Combinar Scores ---
    # =========================
    # Soma os scores de importância e prazo e arredonda
    total_score = round(due_date_score + importance_score, 2)
    logger.debug(f"Score final calculado: {total_score} (prazo={due_date_score}, importancia={importance_score})")

    return total_score

# ===================================
# --- Função de Tarefa Urgente ---
# ===================================
def is_task_urgent(task: Task) -> bool:
    """
    Verifica se uma tarefa é considerada urgente para fins de notificação.

    Critérios de Urgência:
    1. A pontuação de prioridade (`priority_score`) é maior que o limiar
       `EMAIL_URGENCY_THRESHOLD` definido nas configurações.
    OU
    2. A tarefa tem uma `due_date` definida e essa data é hoje ou já passou.

    Args:
        task: O objeto Task a ser verificado.

    Returns:
        True se a tarefa for considerada urgente, False caso contrário.
    """
    # Condição inicial: tarefa precisa ter score ou prazo para ser potencialmente urgente
    if task.priority_score is None and task.due_date is None:
         return False

    # Critério 1: Score acima do limiar
    if task.priority_score is not None and task.priority_score > settings.EMAIL_URGENCY_THRESHOLD:
        return True

    # Critério 2: Vence hoje ou está atrasada
    if task.due_date:
        today = date.today()
        days_remaining = (task.due_date - today).days
        if days_remaining <= 0: 
            return True

    # Se nenhum critério foi atendido
    return False

# =====================================
# --- Função de Envio de Webhook ---
# =====================================
async def send_webhook_notification(
    event_type: str,
    task_data: Dict[str, Any]
    ):
    """
    Envia uma notificação via webhook para a URL configurada (se houver).

    Constrói o payload JSON com tipo de evento, dados da tarefa e timestamp.
    Se um `WEBHOOK_SECRET` estiver configurado, calcula e adiciona uma assinatura
    HMAC-SHA256 ao cabeçalho `X-SmartTask-Signature`.
    Realiza a requisição POST usando `httpx` e trata exceções comuns.

    Args:
        event_type: String identificando o tipo do evento (ex: 'task.created').
        task_data: Dicionário contendo os dados da tarefa a serem enviados.
    """
    # Retorna cedo se a URL do webhook não estiver configurada
    if not settings.WEBHOOK_URL:
        logger.debug("Webhook URL não configurada, pulando envio.")
        return

    # Converte a URL (que pode ser um objeto HttpUrl Pydantic) para string
    webhook_url_str = str(settings.WEBHOOK_URL)

    # Monta o payload da notificação
    payload = {
        "event": event_type,
        "task": task_data,
        "timestamp": datetime.now(timezone.utc).isoformat() # Timestamp UTC em ISO format
    }

    # Cabeçalhos padrão da requisição
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "SmartTask-Webhook-Client/1.0" # Identifica nosso cliente
    }

    # =============================
    # --- Segurança: Assinatura ---
    # =============================
    # Adiciona assinatura HMAC se um segredo estiver configurado
    if settings.WEBHOOK_SECRET:
        try:
            # Serializa o payload JSON de forma consistente (ordenado, sem espaços)
            payload_bytes = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode('utf-8')
            secret_bytes = settings.WEBHOOK_SECRET.encode('utf-8')

            # Calcula o HMAC-SHA256
            signature = hmac.new(secret_bytes, payload_bytes, hashlib.sha256).hexdigest()
            # Adiciona ao header no formato padrão 'schema=signature'
            headers["X-SmartTask-Signature"] = f"sha256={signature}"
        except Exception as e:
             # Loga erro e não envia se a assinatura falhar
             logger.error(f"Erro ao gerar assinatura HMAC para webhook: {e}", exc_info=True)
             return

    # =================================
    # --- Envio da Requisição HTTP ---
    # =================================
    try:
         # Usa um cliente HTTP assíncrono para enviar a requisição
         async with httpx.AsyncClient() as client:
            logger.info(f"Enviando webhook evento '{event_type}' para {webhook_url_str}")
            response = await client.post(
                webhook_url_str,
                json=payload, 
                headers=headers,
                timeout=10.0 
            )

            # Levanta uma exceção para respostas com status de erro (4xx ou 5xx)
            response.raise_for_status()

            logger.info(f"Webhook enviado com sucesso para {webhook_url_str}. Status: {response.status_code}")

    # --- Tratamento de Erros Específicos ---
    except httpx.TimeoutException:
         logger.error(f"Timeout ao enviar webhook para {webhook_url_str}")
    except httpx.RequestError as exc:
         # Erros relacionados à conexão ou requisição (DNS, conexão recusada, etc.)
         logger.error(f"Erro na requisição ao enviar webhook para {webhook_url_str}: {exc}")
    except httpx.HTTPStatusError as exc:
         # Erros retornados pelo servidor do webhook (4xx, 5xx)
         logger.error(
             f"Erro no servidor do webhook ({webhook_url_str}). "
             f"Status: {exc.response.status_code}. Resposta: {exc.response.text[:200]}..."
         )
    # --- Tratamento de Erro Genérico ---
    except Exception as e:
         # Captura qualquer outra exceção inesperada
         logger.exception(f"Erro inesperado ao enviar webhook para {webhook_url_str}: {e}")