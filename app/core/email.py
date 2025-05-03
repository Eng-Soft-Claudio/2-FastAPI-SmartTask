# app/core/email.py
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from pydantic import EmailStr, BaseModel
from app.core.config import settings 

logger = logging.getLogger(__name__)

# --- Configuração da conexão ---
conf = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME or "", 
    MAIL_PASSWORD=settings.MAIL_PASSWORD or "",
    MAIL_FROM=settings.MAIL_FROM or EmailStr("default@example.com"), 
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER or "",
    MAIL_FROM_NAME=settings.MAIL_FROM_NAME or "Default Sender",
    MAIL_STARTTLS=settings.MAIL_STARTTLS,
    MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
    USE_CREDENTIALS=settings.USE_CREDENTIALS,
    VALIDATE_CERTS=settings.VALIDATE_CERTS,
    TEMPLATE_FOLDER=Path(settings.EMAIL_TEMPLATES_DIR) if settings.EMAIL_TEMPLATES_DIR else None, 
)

# Instância principal do FastMail
fm = FastMail(conf)

async def send_email_async(
    subject: str,
    recipient_to: List[EmailStr],
    body: Dict[str, Any], 
    template_name: Optional[str] = None, 
    plain_text_body: Optional[str] = None 
):
    """
    Envia um e-mail de forma assíncrona.

    Args:
        subject: Assunto do e-mail.
        recipient_to: Lista de destinatários.
        body: Dicionário com variáveis para preencher o template HTML.
        template_name: Nome do arquivo do template HTML (sem extensão, deve estar em EMAIL_TEMPLATES_DIR).
        plain_text_body: Conteúdo alternativo em texto puro.
    """
    if not settings.MAIL_ENABLED:
        logger.warning("Envio de e-mail desabilitado nas configurações (MAIL_ENABLED=false).")
        return

    if not all([settings.MAIL_USERNAME, settings.MAIL_PASSWORD, settings.MAIL_FROM, settings.MAIL_SERVER]):
        logger.error("Configurações essenciais de e-mail ausentes (USERNAME, PASSWORD, FROM, SERVER). Não foi possível enviar.")
        return

    message = MessageSchema(
        subject=subject,
        recipients=recipient_to,
        template_body=body if template_name else None, 
        body=plain_text_body if not template_name else None, 
        subtype=MessageType.html if template_name else MessageType.plain, 
    )

    try:
        logger.info(f"Tentando enviar e-mail para {recipient_to} com assunto '{subject}'...")
        await fm.send_message(message, template_name=template_name)
        logger.info(f"E-mail enviado com sucesso para {recipient_to}.")
    except Exception as e:
        logger.exception(f"Erro ao enviar e-mail para {recipient_to}: {e}")

# --- Funções utilitárias ---

async def send_urgent_task_notification(
    user_email: EmailStr,
    user_name: str,
    task_title: str,
    task_id: str,
    task_due_date: Optional[str],
    priority_score: float
):
    """Envia notificação de tarefa urgente."""

    subject = f"🚨 Tarefa Urgente no SmartTask: {task_title}"

    # Link para a tarefa
    task_link = f"{settings.FRONTEND_URL}/tasks/{task_id}" if settings.FRONTEND_URL else None

    # Corpo/Contexto para o template
    email_body_data = {
        "task_title": task_title,
        "user_name": user_name,
        "due_date": task_due_date or "N/A",
        "priority_score": f"{priority_score:.2f}", 
        "task_link": task_link,
        "project_name": settings.PROJECT_NAME
    }

    # Nome do template HTML (criaremos abaixo)
    template_name = "urgent_task.html"

    await send_email_async(
        subject=subject,
        recipient_to=[user_email],
        body=email_body_data,
        template_name=template_name,
        plain_text_body=f"Olá {user_name},\nA tarefa '{task_title}' no {settings.PROJECT_NAME} é considerada urgente.\n"
                       f"Prioridade: {priority_score:.2f}, Vencimento: {task_due_date or 'N/A'}.\n"
                       f"{'Acesse a tarefa aqui: ' + task_link if task_link else ''}"
    )