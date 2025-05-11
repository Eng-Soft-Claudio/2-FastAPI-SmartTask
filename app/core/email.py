# app/core/email.py
"""
Este módulo lida com o envio de e-mails, utilizando a biblioteca FastAPI-Mail.
Inclui a configuração da conexão SMTP e funções para enviar e-mails
de forma assíncrona, tanto com templates HTML quanto com texto puro.
"""

# ========================
# --- Importações ---
# ========================
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from pydantic import EmailStr

# --- Módulos da Aplicação ---
from app.core.config import settings

# ========================
# --- Configuração do Logger ---
# ========================
logger = logging.getLogger(__name__)

# ========================
# --- Configuração FastMail ---
# ========================
# Cria a configuração de conexão para o FastMail com base nas settings.
conf = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME or "",
    MAIL_PASSWORD=settings.MAIL_PASSWORD or "",
    MAIL_FROM=settings.MAIL_FROM or "default@example.com",
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER or "",
    MAIL_FROM_NAME=settings.MAIL_FROM_NAME or "Default Sender",
    MAIL_STARTTLS=settings.MAIL_STARTTLS,
    MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
    USE_CREDENTIALS=settings.USE_CREDENTIALS,
    VALIDATE_CERTS=settings.VALIDATE_CERTS,
    TEMPLATE_FOLDER=Path(settings.EMAIL_TEMPLATES_DIR) if settings.EMAIL_TEMPLATES_DIR else None,
)

# ========================
# --- Instância do FastMail ---
# ========================
fm = FastMail(conf)

# ========================
# --- Função Principal de Envio ---
# ========================
async def send_email_async(
    subject: str,
    recipient_to: List[EmailStr],
    body: Dict[str, Any],
    template_name: Optional[str] = None,
    plain_text_body: Optional[str] = None
):
    """
    Envia um e-mail de forma assíncrona.

    Verifica se o envio de e-mail está habilitado e se as credenciais
    necessárias estão configuradas antes de tentar o envio.

    Args:
        subject: Assunto do e-mail.
        recipient_to: Lista de e-mails dos destinatários.
        body: Dicionário com variáveis para o template HTML (se usado).
        template_name: Nome do arquivo do template HTML.
        plain_text_body: Conteúdo em texto puro (usado se template_name não for fornecido).
    """
    if not settings.MAIL_ENABLED:
        logger.warning("Envio de e-mail desabilitado nas configurações (MAIL_ENABLED=false).")
        return

    if not all([settings.MAIL_USERNAME, settings.MAIL_PASSWORD, settings.MAIL_FROM, settings.MAIL_SERVER]):
        logger.error("Configurações essenciais de e-mail ausentes. Não foi possível enviar.")
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

# ========================
# --- Funções Utilitárias Específicas ---
# ========================
async def send_urgent_task_notification(
    user_email: EmailStr,
    user_name: str,
    task_title: str,
    task_id: str,
    task_due_date: Optional[str],
    priority_score: float
):
    """
    Prepara e envia uma notificação específica para tarefas urgentes.

    Args:
        user_email: Email do destinatário.
        user_name: Nome do destinatário.
        task_title: Título da tarefa urgente.
        task_id: ID da tarefa (para link).
        task_due_date: Data de vencimento formatada (ou None).
        priority_score: Pontuação de prioridade da tarefa.
    """
    subject = f"🚨 Tarefa Urgente no SmartTask: {task_title}"
    task_link = f"{settings.FRONTEND_URL}/tasks/{task_id}" if settings.FRONTEND_URL else None

    email_body_data = {
        "task_title": task_title,
        "user_name": user_name,
        "due_date": task_due_date or "N/A",
        "priority_score": f"{priority_score:.2f}",
        "task_link": task_link,
        "project_name": settings.PROJECT_NAME
    }
    template_name = "urgent_task.html"
    plain_text_body = (
        f"Olá {user_name},\n"
        f"A tarefa '{task_title}' no {settings.PROJECT_NAME} é considerada urgente.\n"
        f"Prioridade: {priority_score:.2f}, Vencimento: {task_due_date or 'N/A'}.\n"
    )
    if task_link:
        plain_text_body += f"Acesse a tarefa aqui: {task_link}"

    await send_email_async(
        subject=subject,
        recipient_to=[user_email],
        body=email_body_data,
        template_name=template_name,
        plain_text_body=plain_text_body
    )