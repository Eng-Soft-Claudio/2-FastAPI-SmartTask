# tests/test_core_email.py

import uuid
import pytest
from unittest.mock import AsyncMock, patch, ANY # Usar ANY para argumentos variáveis como 'body'
from pydantic import EmailStr
from fastapi_mail import MessageType
from app.core.email import send_email_async, send_urgent_task_notification, conf # Importa conf para referência
from app.core.config import settings

pytestmark = pytest.mark.asyncio

# --- Testes para send_email_async ---

# Mock global para fm.send_message, assumindo que fm é a instância de FastMail no módulo email.py
# Vamos aplicar o patch em cada teste para controlar melhor o mock.

async def test_send_email_async_mail_disabled(mocker, caplog):
    """Testa que nenhum email é enviado se MAIL_ENABLED=False."""
    mock_fm_send = mocker.patch("app.core.email.fm.send_message", new_callable=AsyncMock)
    # Garante que MAIL_ENABLED seja False para este teste
    mocker.patch.object(settings, 'MAIL_ENABLED', False)

    await send_email_async(
        subject="Teste Desabilitado",
        recipient_to=["test@example.com"],
        body={"info": "Teste"},
        template_name="dummy_template.html"
    )

    mock_fm_send.assert_not_called()
    assert "Envio de e-mail desabilitado" in caplog.text # Verifica o log de warning

async def test_send_email_async_missing_credentials(mocker):
    """Testa que nenhum email é enviado se faltarem credenciais SMTP."""
    mock_fm_send = mocker.patch("app.core.email.fm.send_message", new_callable=AsyncMock)
    # Garante que MAIL_ENABLED=True, mas falta uma credencial
    mocker.patch.object(settings, 'MAIL_ENABLED', True)
    mocker.patch.object(settings, 'MAIL_USERNAME', None) 

    # Mockar o logger para evitar que o erro apareça no console
    mock_logger = mocker.patch("app.core.email.logger")

    await send_email_async(
        subject="Teste Credenciais",
        recipient_to=["test@example.com"],
        body={"info": "Teste"}
    )

    # Verifica que o envio real não foi chamado
    mock_fm_send.assert_not_called()
    mock_logger.error.assert_called_once()
    assert "Configurações essenciais de e-mail ausentes" in mock_logger.error.call_args[0][0]

async def test_send_email_async_with_template(mocker):
    """Testa envio com template HTML."""
    mock_fm_send = mocker.patch("app.core.email.fm.send_message", new_callable=AsyncMock)
    # Configurações mínimas para passar nas verificações iniciais
    mocker.patch.object(settings, 'MAIL_ENABLED', True)
    mocker.patch.object(settings, 'MAIL_USERNAME', 'user')
    mocker.patch.object(settings, 'MAIL_PASSWORD', 'pass')
    mocker.patch.object(settings, 'MAIL_FROM', 'sender@example.com')
    mocker.patch.object(settings, 'MAIL_SERVER', 'smtp.example.com')

    test_subject = "Assunto Template"
    test_recipient =  "recipient@example.com"
    test_body_dict = {"key": "value", "name": "Tester"}
    test_template_name = "my_template.html"

    await send_email_async(
        subject=test_subject,
        recipient_to=[test_recipient],
        body=test_body_dict,
        template_name=test_template_name
    )

    # Verifica se fm.send_message foi chamado uma vez
    mock_fm_send.assert_called_once()

    # Verifica os argumentos passados para fm.send_message
    # Acessa o primeiro argumento posicional (MessageSchema)
    message_schema_arg = mock_fm_send.call_args[0][0]
    # Acessa argumentos nomeados (template_name)
    template_name_arg = mock_fm_send.call_args[1].get('template_name')

    assert message_schema_arg.subject == test_subject
    assert message_schema_arg.recipients == [test_recipient]
    assert message_schema_arg.template_body == test_body_dict
    assert message_schema_arg.body is None # Body deve ser None quando template_body é usado
    assert message_schema_arg.subtype == MessageType.html
    assert template_name_arg == test_template_name

async def test_send_email_async_plain_text(mocker):
    """Testa envio com texto puro."""
    mock_fm_send = mocker.patch("app.core.email.fm.send_message", new_callable=AsyncMock)
    # Configurações mínimas
    mocker.patch.object(settings, 'MAIL_ENABLED', True)
    mocker.patch.object(settings, 'MAIL_USERNAME', 'user')
    mocker.patch.object(settings, 'MAIL_PASSWORD', 'pass')
    mocker.patch.object(settings, 'MAIL_FROM', 'sender@example.com')
    mocker.patch.object(settings, 'MAIL_SERVER', 'smtp.example.com')

    test_subject = "Assunto Texto Puro"
    test_recipient = "another@example.com"
    test_plain_body = "Este é o corpo em texto.\nCom quebra de linha."
    # Não passamos body dict nem template_name

    await send_email_async(
        subject=test_subject,
        recipient_to=[test_recipient],
        body=None, # Explicitamente None
        template_name=None, # Explicitamente None
        plain_text_body=test_plain_body
    )

    # Verifica chamada
    mock_fm_send.assert_called_once()

    # Verifica argumentos
    message_schema_arg = mock_fm_send.call_args[0][0]
    template_name_arg = mock_fm_send.call_args[1].get('template_name')

    assert message_schema_arg.subject == test_subject
    assert message_schema_arg.recipients == [test_recipient]
    assert message_schema_arg.template_body is None # template_body deve ser None
    assert message_schema_arg.body == test_plain_body # body deve ter o texto puro
    assert message_schema_arg.subtype == MessageType.plain
    assert template_name_arg is None # template_name não foi passado

# --- Testes para send_urgent_task_notification ---

@patch("app.core.email.send_email_async", new_callable=AsyncMock)
async def test_send_urgent_task_notification_call(mock_send_email_async, mocker):
    """Verifica se send_urgent_task_notification chama send_email_async corretamente."""
    # Configura URL do frontend para testar o link
    test_frontend_url = "http://frontend.test"
    mocker.patch.object(settings, 'FRONTEND_URL', test_frontend_url)
    # Garante que o e-mail esteja habilitado para este teste
    mocker.patch.object(settings, 'MAIL_ENABLED', True)

    user_email = "urgent@example.com"
    user_name = "Urgent User"
    task_title = "Tarefa Muito Urgente"
    task_id = str(uuid.uuid4())
    task_due_date_str = "2025-05-10"
    priority_score = 150.55

    await send_urgent_task_notification(
        user_email=user_email,
        user_name=user_name,
        task_title=task_title,
        task_id=task_id,
        task_due_date=task_due_date_str,
        priority_score=priority_score
    )

    # Verifica se send_email_async foi chamado uma vez
    mock_send_email_async.assert_called_once()

    # Verifica os argumentos passados para send_email_async
    call_args = mock_send_email_async.call_args.kwargs

    assert call_args["subject"] == f"🚨 Tarefa Urgente no SmartTask: {task_title}"
    assert call_args["recipient_to"] == [user_email]
    assert call_args["template_name"] == "urgent_task.html"
    assert call_args["plain_text_body"] is not None # Verifica se texto alternativo foi gerado
    # Verifica o conteúdo do 'body' (dicionário para o template)
    body_dict = call_args["body"]
    assert body_dict["user_name"] == user_name
    assert body_dict["task_title"] == task_title
    assert body_dict["due_date"] == task_due_date_str
    assert body_dict["priority_score"] == f"{priority_score:.2f}" # Verifica formatação
    assert body_dict["task_link"] == f"{test_frontend_url}/tasks/{task_id}"
    assert body_dict["project_name"] == settings.PROJECT_NAME


@patch("app.core.email.send_email_async", new_callable=AsyncMock)
async def test_send_urgent_task_no_due_date_no_link(mock_send_email_async, mocker):
    """Verifica envio sem data de vencimento e sem link de frontend."""
    # Garante que FRONTEND_URL é None
    mocker.patch.object(settings, 'FRONTEND_URL', None)
    mocker.patch.object(settings, 'MAIL_ENABLED', True)

    await send_urgent_task_notification(
        user_email="user@example.com",
        user_name="No Link User",
        task_title="Task No Link",
        task_id=str(uuid.uuid4()),
        task_due_date=None, # Sem data
        priority_score=200.0
    )

    mock_send_email_async.assert_called_once()
    body_dict = mock_send_email_async.call_args.kwargs["body"]
    assert body_dict["due_date"] == "N/A" # Verifica tratamento de None para data
    assert body_dict["task_link"] is None # Verifica link ausente