# tests/test_core_email.py

import uuid
import pytest
import logging 
from unittest.mock import AsyncMock, patch, ANY 
from pydantic import EmailStr
from fastapi_mail import MessageType, MessageSchema
from app.core.email import send_email_async, send_urgent_task_notification, conf
from app.core.config import settings

pytestmark = pytest.mark.asyncio

#  =================================================
# --- Testes de Guarda ---
#  =================================================

async def test_send_email_async_mail_disabled(mocker, caplog):
    """Testa que nenhum email é enviado se MAIL_ENABLED=False."""
    mock_fm_send = mocker.patch("app.core.email.fm.send_message", new_callable=AsyncMock)
    mocker.patch.object(settings, 'MAIL_ENABLED', False)

    await send_email_async(
        subject="Teste Desabilitado",
        recipient_to=["test@example.com"],
        body={"info": "Teste"},
        template_name="dummy_template.html"
    )

    mock_fm_send.assert_not_called()
    assert "Envio de e-mail desabilitado" in caplog.text

async def test_send_email_async_missing_credentials(mocker):
    """Testa que nenhum email é enviado e erro é logado se faltarem credenciais."""
    mock_fm_send = mocker.patch("app.core.email.fm.send_message", new_callable=AsyncMock)
    mocker.patch.object(settings, 'MAIL_ENABLED', True)
    for missing_field in ['MAIL_USERNAME', 'MAIL_PASSWORD', 'MAIL_FROM', 'MAIL_SERVER']:
        mocker.patch.object(settings, 'MAIL_USERNAME', 'user')
        mocker.patch.object(settings, 'MAIL_PASSWORD', 'pass')
        mocker.patch.object(settings, 'MAIL_FROM', 'from@example.com')
        mocker.patch.object(settings, 'MAIL_SERVER', 'server')
        mocker.patch.object(settings, missing_field, None)

        mock_logger = mocker.patch("app.core.email.logger")
        mock_fm_send.reset_mock()
        mock_logger.reset_mock() 

        await send_email_async(
            subject="Teste Credenciais",
            recipient_to=["test@example.com"],
            body={"info": "Teste"}
        )

        mock_fm_send.assert_not_called()
        mock_logger.error.assert_called_once()
        assert "Configurações essenciais de e-mail ausentes" in mock_logger.error.call_args[0][0]

#  =================================================
# --- Testes de Funcionalidade ---
#  =================================================

async def test_send_email_async_with_template_calls_fm(mocker):
    """Testa se send_email_async chama fm.send_message corretamente com template."""
    mock_fm_send = mocker.patch("app.core.email.fm.send_message", new_callable=AsyncMock)
    mocker.patch.object(settings, 'MAIL_ENABLED', True)
    mocker.patch.object(settings, 'MAIL_USERNAME', 'user')
    mocker.patch.object(settings, 'MAIL_PASSWORD', 'pass')
    mocker.patch.object(settings, 'MAIL_FROM', 'sender@example.com')
    mocker.patch.object(settings, 'MAIL_SERVER', 'smtp.example.com')
    mock_logger_info = mocker.patch("app.core.email.logger.info")

    test_subject = "Assunto Template"
    test_recipient = "recipient@example.com"
    test_body_dict = {"key": "value"}
    test_template = "template.html"

    await send_email_async(
        subject=test_subject,
        recipient_to=[test_recipient],
        body=test_body_dict,
        template_name=test_template
    )

    mock_fm_send.assert_called_once()
    message_arg: MessageSchema = mock_fm_send.call_args[0][0] 
    template_arg = mock_fm_send.call_args.kwargs.get('template_name')

    assert isinstance(message_arg, MessageSchema)
    assert message_arg.subject == test_subject
    assert message_arg.recipients == [test_recipient]
    assert message_arg.template_body == test_body_dict
    assert message_arg.body is None
    assert message_arg.subtype == MessageType.html
    assert template_arg == test_template
    assert mock_logger_info.call_count >= 2 

async def test_send_email_async_plain_text_calls_fm(mocker):
    """Testa se send_email_async chama fm.send_message corretamente com texto puro."""
    mock_fm_send = mocker.patch("app.core.email.fm.send_message", new_callable=AsyncMock)
    mocker.patch.object(settings, 'MAIL_ENABLED', True)
    mocker.patch.object(settings, 'MAIL_USERNAME', 'user')
    mocker.patch.object(settings, 'MAIL_PASSWORD', 'pass')
    mocker.patch.object(settings, 'MAIL_FROM', 'sender@example.com')
    mocker.patch.object(settings, 'MAIL_SERVER', 'smtp.example.com')
    mock_logger_info = mocker.patch("app.core.email.logger.info")

    test_subject = "Assunto Plain"
    test_recipient = "plain@example.com"
    test_plain_body = "Corpo simples."

    await send_email_async(
        subject=test_subject,
        recipient_to=[test_recipient],
        body=None,
        plain_text_body=test_plain_body
    )

    mock_fm_send.assert_called_once()
    message_arg: MessageSchema = mock_fm_send.call_args[0][0]
    template_arg = mock_fm_send.call_args.kwargs.get('template_name')

    assert isinstance(message_arg, MessageSchema)
    assert message_arg.subject == test_subject
    assert message_arg.recipients == [test_recipient]
    assert message_arg.template_body is None
    assert message_arg.body == test_plain_body
    assert message_arg.subtype == MessageType.plain
    assert template_arg is None
    assert mock_logger_info.call_count >= 2

async def test_send_email_async_handles_send_exception(mocker):
    """Testa o tratamento de erro se fm.send_message levantar exceção."""
    error_message = "SMTP Error"
    mock_fm_send = mocker.patch(
        "app.core.email.fm.send_message",
        new_callable=AsyncMock,
        side_effect=Exception(error_message)
    )

    mocker.patch.object(settings, 'MAIL_ENABLED', True)
    mocker.patch.object(settings, 'MAIL_USERNAME', 'user')
    mocker.patch.object(settings, 'MAIL_PASSWORD', 'pass')
    mocker.patch.object(settings, 'MAIL_FROM', 'sender@example.com')
    mocker.patch.object(settings, 'MAIL_SERVER', 'smtp.example.com')

    mock_logger_exception = mocker.patch("app.core.email.logger.exception")

    test_recipient = ["fail@example.com"]
    await send_email_async(
        subject="Teste de Erro",
        recipient_to=test_recipient,
        body={"info": "teste"}
    )

    mock_fm_send.assert_called_once() 
    mock_logger_exception.assert_called_once() 
    log_message = mock_logger_exception.call_args[0][0] 
    assert f"Erro ao enviar e-mail para {test_recipient}" in log_message
    assert error_message in log_message

#  =================================================
# --- Testes Unitários ---
#  =================================================

from app.core import email as email_module

@pytest.fixture(autouse=True)
def patch_send_email_async(mocker):
    """Mocka automaticamente send_email_async para todos os testes desta seção."""
    return mocker.patch("app.core.email.send_email_async", new_callable=AsyncMock)


async def test_send_urgent_task_call_args(patch_send_email_async, mocker):
    """Verifica argumentos passados para send_email_async por send_urgent..."""
    test_frontend_url = "http://test.dev"
    mocker.patch.object(settings, 'FRONTEND_URL', test_frontend_url)

    email = "urgent@test.co"
    name = "Urgent Joe"
    title = "Fix Now!"
    task_id = str(uuid.uuid4())
    due_date = "2025-01-01"
    score = 123.456

    await email_module.send_urgent_task_notification(
        user_email=email,
        user_name=name,
        task_title=title,
        task_id=task_id,
        task_due_date=due_date,
        priority_score=score
    )

    patch_send_email_async.assert_called_once()
    call_args = patch_send_email_async.call_args.kwargs

    assert call_args["subject"] == f"🚨 Tarefa Urgente no SmartTask: {title}"
    assert call_args["recipient_to"] == [email]
    assert call_args["template_name"] == "urgent_task.html"
    assert call_args["plain_text_body"] is not None

    body = call_args["body"]
    assert body["task_title"] == title
    assert body["user_name"] == name
    assert body["due_date"] == due_date
    assert body["priority_score"] == f"{score:.2f}" 
    assert body["task_link"] == f"{test_frontend_url}/tasks/{task_id}"
    assert body["project_name"] == settings.PROJECT_NAME

async def test_send_urgent_task_call_args_no_due_no_link(patch_send_email_async, mocker):
    """Verifica argumentos quando não há due_date e FRONTEND_URL."""
    mocker.patch.object(settings, 'FRONTEND_URL', None) 

    email = "nodate@test.co"
    name = "No Date User"
    title = "No Link Task"
    task_id = str(uuid.uuid4())
    score = 500.0

    await email_module.send_urgent_task_notification(
        user_email=email,
        user_name=name,
        task_title=title,
        task_id=task_id,
        task_due_date=None, 
        priority_score=score
    )

    patch_send_email_async.assert_called_once()
    call_args = patch_send_email_async.call_args.kwargs
    assert call_args["recipient_to"] == [email]

    body = call_args["body"]
    assert body["due_date"] == "N/A" 
    assert body["task_link"] is None
