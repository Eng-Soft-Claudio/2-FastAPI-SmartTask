# app/core/email.py

# ========================
# --- Importações ---
# ========================
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from pydantic import EmailStr, BaseModel
from app.core.config import settings

# ===============================
# --- Configuração do Logger ---
# ===============================
logger = logging.getLogger(__name__)

# ==================================
# --- Configuração FastMail ---
# ==================================
# Cria a configuração de conexão para o FastMail, lendo das settings.
# Utiliza valores padrão seguros ou "" caso as settings não definam alguns campos opcionais.
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

# ================================
# --- Instância do FastMail ---
# ================================
# Instância principal usada para enviar e-mails.
fm = FastMail(conf)

# ===============================
# --- Função Principal Envio ---
# ===============================
async def send_email_async(
    subject: str,
    recipient_to: List[EmailStr], # A validação Pydantic ocorre na assinatura
    body: Dict[str, Any],
    template_name: Optional[str] = None,
    plain_text_body: Optional[str] = None
):
    """
    Envia um e-mail de forma assíncrona usando FastMail.

    Verifica se o envio de e-mail está habilitado e se as credenciais
    necessárias estão configuradas antes de tentar enviar.

    Args:
        subject: Assunto do e-mail.
        recipient_to: Lista de endereços de e-mail dos destinatários.
        body: Dicionário com variáveis para preencher o template HTML.
              Usado se 'template_name' for fornecido.
        template_name: Nome do arquivo do template HTML (sem extensão).
                       Define o modo de envio como HTML.
        plain_text_body: Conteúdo alternativo em texto puro. Usado se
                         'template_name' não for fornecido. Define o modo
                         de envio como texto plano.
    """
    # Verifica se o envio global de emails está habilitado
    if not settings.MAIL_ENABLED:
        logger.warning("Envio de e-mail desabilitado nas configurações (MAIL_ENABLED=false).")
        return

    # Verifica se todas as configurações essenciais de SMTP estão presentes
    if not all([settings.MAIL_USERNAME, settings.MAIL_PASSWORD, settings.MAIL_FROM, settings.MAIL_SERVER]):
        logger.error("Configurações essenciais de e-mail ausentes (USERNAME, PASSWORD, FROM, SERVER). Não foi possível enviar.")
        return

    # Cria o objeto de mensagem do FastMail
    message = MessageSchema(
        subject=subject,
        recipients=recipient_to,
        # Usa o body dict se template for fornecido, senão espera texto puro
        template_body=body if template_name else None,
        body=plain_text_body if not template_name else None,
        # Define o subtipo (HTML ou Plain) com base na presença do template
        subtype=MessageType.html if template_name else MessageType.plain,
    )

    # Tenta enviar a mensagem e trata exceções
    try:
        logger.info(f"Tentando enviar e-mail para {recipient_to} com assunto '{subject}'...")
        # Chama o método de envio do FastMail
        await fm.send_message(message, template_name=template_name)
        logger.info(f"E-mail enviado com sucesso para {recipient_to}.")
    except Exception as e:
        # Loga a exceção completa em caso de falha no envio
        logger.exception(f"Erro ao enviar e-mail para {recipient_to}: {e}")


# =========================================
# --- Funções Utilitárias Específicas ---
# =========================================

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

    Reúne os dados necessários, formata o assunto, corpo e link,
    e chama a função genérica `send_email_async` para realizar o envio
    usando um template HTML específico ('urgent_task.html').

    Args:
        user_email: Email do destinatário.
        user_name: Nome do destinatário.
        task_title: Título da tarefa urgente.
        task_id: ID da tarefa urgente (para link).
        task_due_date: Data de vencimento formatada como string (ou None).
        priority_score: Pontuação de prioridade calculada.
    """
    # Define o assunto do e-mail
    subject = f"🚨 Tarefa Urgente no SmartTask: {task_title}"

    # Monta o link para a tarefa, se FRONTEND_URL estiver configurado
    task_link = f"{settings.FRONTEND_URL}/tasks/{task_id}" if settings.FRONTEND_URL else None

    # Prepara o dicionário 'body' com os dados para o template HTML
    email_body_data = {
        "task_title": task_title,
        "user_name": user_name,
        "due_date": task_due_date or "N/A", 
        "priority_score": f"{priority_score:.2f}", 
        "task_link": task_link,
        "project_name": settings.PROJECT_NAME
    }

    # Define o nome do template HTML a ser usado
    template_name = "urgent_task.html"

    # Monta o corpo em texto puro como fallback
    plain_text_body = (
        f"Olá {user_name},\n"
        f"A tarefa '{task_title}' no {settings.PROJECT_NAME} é considerada urgente.\n"
        f"Prioridade: {priority_score:.2f}, Vencimento: {task_due_date or 'N/A'}.\n"
    )
    if task_link:
        plain_text_body += f"Acesse a tarefa aqui: {task_link}"

    # Chama a função genérica de envio
    await send_email_async(
        subject=subject,
        recipient_to=[user_email], 
        body=email_body_data,
        template_name=template_name,
        plain_text_body=plain_text_body
    )