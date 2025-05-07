# tests/test_core_email.py
"""
Este módulo contém testes unitários para as funções de envio de e-mail
definidas em `app.core.email`.

Os testes verificam:
- Comportamento quando o envio de e-mail está desabilitado (`MAIL_ENABLED=False`).
- Comportamento quando faltam credenciais de e-mail obrigatórias.
- Chamada correta à biblioteca `fastapi-mail` (mockada) para envio de e-mails
  com templates HTML e em texto puro.
- Tratamento de exceções durante o envio de e-mails.
- A lógica específica da função `send_urgent_task_notification`, verificando
  os argumentos passados para a função de envio genérica `send_email_async`.

Todos os envios reais de e-mail são mockados para evitar efeitos colaterais
e dependências externas durante os testes.
"""

# ========================
# --- Importações ---
# ========================
import uuid
import logging
from unittest.mock import AsyncMock, patch, ANY 

import pytest
from fastapi_mail import MessageSchema, MessageType 

# --- Módulos da Aplicação ---
from app.core.config import settings
from app.core.email import (conf, send_email_async, send_urgent_task_notification)
from app.core import email as email_module 

# ====================================
# --- Marcador Global de Teste ---
# ====================================
pytestmark = pytest.mark.asyncio

# ===========================================================
# --- Testes de Condições de Guarda para `send_email_async` ---
# ===========================================================
# Testes que verificam se `send_email_async` se comporta corretamente
# sob diferentes condições de configuração (e-mail desabilitado, credenciais ausentes).

async def test_send_email_async_when_mail_is_disabled(mocker, caplog):
    """
    Testa se `send_email_async` NÃO tenta enviar um e-mail e loga uma mensagem informativa
    quando a configuração `settings.MAIL_ENABLED` é `False`.
    """
    print("\nTeste: send_email_async com MAIL_ENABLED=False.")
    # Arrange: Mockar `fm.send_message` para garantir que não seja chamado.
    #          Mockar `settings.MAIL_ENABLED` para ser False.
    mock_fastapi_mail_send_message = mocker.patch("app.core.email.fm.send_message", new_callable=AsyncMock)
    mocker.patch.object(settings, 'MAIL_ENABLED', False)
    print("  Mock: fm.send_message e settings.MAIL_ENABLED=False.")

    # Act: Chamar a função de envio de e-mail.
    print("  Atuando: Chamando send_email_async...")
    await send_email_async(
        subject="E-mail de Teste (Desabilitado)",
        recipient_to=["test_disabled@example.com"],
        body={"info": "Este e-mail não deve ser enviado."},
        template_name="dummy_template_desabilitado.html"
    )

    # Assert: Verificar que `fm.send_message` não foi chamado e que um log apropriado foi gerado.
    mock_fastapi_mail_send_message.assert_not_called()
    found_log = False
    expected_message = "Envio de e-mail desabilitado nas configurações" 
    for record in caplog.records:
        if expected_message in record.message:
            assert record.levelname == "WARNING" 
            found_log = True
            break
    assert found_log, f"Log esperado contendo '{expected_message}' não encontrado. Logs: {caplog.text}"
    print("  Sucesso: E-mail não enviado e log de desativação presente.")


async def test_send_email_async_when_essential_credentials_are_missing(mocker):
    """
    Testa se `send_email_async` NÃO tenta enviar um e-mail e loga um erro
    quando `settings.MAIL_ENABLED` é `True`, mas faltam credenciais essenciais
    (como MAIL_USERNAME, MAIL_PASSWORD, etc.).

    O teste é parametrizado implicitamente por um loop para verificar a ausência
    de cada credencial essencial individualmente.
    """
    print("\nTeste: send_email_async com MAIL_ENABLED=True, mas faltando credenciais.")
    mock_fastapi_mail_send_message = mocker.patch("app.core.email.fm.send_message", new_callable=AsyncMock)
    mocker.patch.object(settings, 'MAIL_ENABLED', True)
    mock_email_module_logger = mocker.patch("app.core.email.logger")
    essential_mail_fields = ['MAIL_USERNAME', 'MAIL_PASSWORD', 'MAIL_FROM', 'MAIL_SERVER']

    for missing_field in essential_mail_fields:
        print(f"  Testando cenário: Faltando '{missing_field}'...")
        # Define todas as credenciais, depois remove uma
        mocker.patch.object(settings, 'MAIL_USERNAME', 'test_user')
        mocker.patch.object(settings, 'MAIL_PASSWORD', 'test_password')
        mocker.patch.object(settings, 'MAIL_FROM', 'test_from@example.com') 
        mocker.patch.object(settings, 'MAIL_SERVER', 'smtp.example.com')
        mocker.patch.object(settings, 'MAIL_PORT', 587)
        mocker.patch.object(settings, 'MAIL_STARTTLS', True)
        mocker.patch.object(settings, 'MAIL_SSL_TLS', False)
        
        mocker.patch.object(settings, missing_field, None) 
        print(f"    Mock: {missing_field}=None, outras credenciais definidas.")

        mock_fastapi_mail_send_message.reset_mock()
        mock_email_module_logger.reset_mock()

        await send_email_async(
            subject=f"Teste de Credenciais (Falta {missing_field})",
            recipient_to=["test_cred_missing@example.com"], 
            body={"info": f"Teste com {missing_field} ausente."}
        )

        mock_fastapi_mail_send_message.assert_not_called()
        mock_email_module_logger.error.assert_called_once()
        log_call_args = mock_email_module_logger.error.call_args[0]
        assert "Configurações essenciais de e-mail ausentes" in log_call_args[0], \
            f"Log de erro para '{missing_field}' ausente não correspondeu. Log: {log_call_args[0]}"
        print(f"    Sucesso para '{missing_field}' ausente: E-mail não enviado e erro logado.")
    print("  Todos os cenários de credenciais ausentes verificados.")

# =========================================================
# --- Testes de Funcionalidade para `send_email_async` ---
# =========================================================
# Testes que verificam se `send_email_async` chama `fastapi-mail` corretamente
# quando as configurações estão válidas.

async def test_send_email_async_with_html_template_calls_fastapi_mail_correctly(mocker):
    """
    Testa se `send_email_async` chama `fm.send_message` (de `fastapi-mail`)
    corretamente quando um template HTML é especificado.

    Verifica:
    - Se `fm.send_message` é chamado uma vez.
    - Se o objeto `MessageSchema` passado para `fm.send_message` tem os atributos corretos
      (assunto, destinatários, corpo do template, tipo HTML).
    - Se `template_name` é passado corretamente como kwarg.
    - Se logs informativos são gerados.
    """
    print("\nTeste: send_email_async com template HTML.")
    mock_fastapi_mail_send_message = mocker.patch("app.core.email.fm.send_message", new_callable=AsyncMock)
    mocker.patch.object(settings, 'MAIL_ENABLED', True)
    mocker.patch.object(settings, 'MAIL_USERNAME', 'test_user_template')
    mocker.patch.object(settings, 'MAIL_PASSWORD', 'test_pass_template')
    mocker.patch.object(settings, 'MAIL_FROM', 'sender_template@example.com') 
    mocker.patch.object(settings, 'MAIL_SERVER', 'smtp.template.example.com')
    mocker.patch.object(settings, 'MAIL_PORT', 587)
    mock_email_module_logger_info = mocker.patch("app.core.email.logger.info")
    print("  Mock: fm.send_message, settings de e-mail (habilitado), logger.info.")

    test_subject = "Assunto do E-mail com Template HTML"
    test_recipient = "recipient_html@example.com"
    test_body_dict_for_template = {"user_name": "Claudio", "item_name": "SmartTask"}
    test_template_file_name = "meu_template_email.html"

    print(f"  Atuando: Chamando send_email_async com template '{test_template_file_name}'...")
    await send_email_async(
        subject=test_subject,
        recipient_to=[test_recipient],
        body=test_body_dict_for_template,
        template_name=test_template_file_name
    )

    mock_fastapi_mail_send_message.assert_called_once()
    message_arg_schema: MessageSchema = mock_fastapi_mail_send_message.call_args[0][0]
    template_arg_name_from_kwargs = mock_fastapi_mail_send_message.call_args.kwargs.get('template_name')

    assert isinstance(message_arg_schema, MessageSchema)
    assert message_arg_schema.subject == test_subject
    assert message_arg_schema.recipients == [test_recipient]
    assert message_arg_schema.template_body == test_body_dict_for_template
    assert message_arg_schema.body is None
    assert message_arg_schema.subtype == MessageType.html
    assert template_arg_name_from_kwargs == test_template_file_name
    assert mock_email_module_logger_info.call_count >= 2
    print(f"  Sucesso: fm.send_message chamado corretamente para template HTML.")


async def test_send_email_async_with_plain_text_calls_fastapi_mail_correctly(mocker):
    """
    Testa se `send_email_async` chama `fm.send_message` (de `fastapi-mail`)
    corretamente quando um corpo de e-mail em texto puro é especificado.

    Verifica:
    - Se `fm.send_message` é chamado uma vez.
    - Se o objeto `MessageSchema` passado tem os atributos corretos
      (assunto, destinatários, corpo de texto puro, tipo PLAIN).
    - Se `template_name` NÃO é passado.
    - Se logs informativos são gerados.
    """
    print("\nTeste: send_email_async com texto puro.")
    # Arrange: Configurar mocks e settings.
    mock_fastapi_mail_send_message = mocker.patch("app.core.email.fm.send_message", new_callable=AsyncMock)
    mocker.patch.object(settings, 'MAIL_ENABLED', True)
    # Reutilizando settings dos testes anteriores para simplicidade, ajuste se necessário.
    mocker.patch.object(settings, 'MAIL_USERNAME', 'test_user_plain')
    mocker.patch.object(settings, 'MAIL_PASSWORD', 'test_pass_plain')
    mocker.patch.object(settings, 'MAIL_FROM', 'sender_plain@example.com')
    mocker.patch.object(settings, 'MAIL_SERVER', 'smtp.plain.example.com')
    mocker.patch.object(settings, 'MAIL_PORT', 587)
    mock_email_module_logger_info = mocker.patch("app.core.email.logger.info")
    print("  Mock: fm.send_message, settings de e-mail (habilitado), logger.info.")

    # Dados de teste.
    test_subject = "Assunto do E-mail em Texto Puro"
    test_recipient = "recipient_plain@example.com"
    test_plain_body_content = "Este é o corpo do e-mail em texto puro.\nCom múltiplas linhas."

    # Act: Chamar a função de envio.
    print(f"  Atuando: Chamando send_email_async com texto puro...")
    await send_email_async(
        subject=test_subject,
        recipient_to=[test_recipient],
        body=None, # `body` (para template) deve ser None.
        plain_text_body=test_plain_body_content 
    )

    # Assert: Verificar a chamada e seus argumentos.
    mock_fastapi_mail_send_message.assert_called_once()
    message_arg_schema: MessageSchema = mock_fastapi_mail_send_message.call_args[0][0]
    template_arg_name_from_kwargs = mock_fastapi_mail_send_message.call_args.kwargs.get('template_name')

    assert isinstance(message_arg_schema, MessageSchema), "Argumento não é MessageSchema."
    assert message_arg_schema.subject == test_subject, "Assunto não corresponde."
    assert message_arg_schema.recipients == [test_recipient], "Destinatários não correspondem."
    assert message_arg_schema.template_body is None, "Corpo do template deveria ser None."
    assert message_arg_schema.body == test_plain_body_content, "Corpo de texto puro não corresponde."
    assert message_arg_schema.subtype == MessageType.plain, "Subtipo não é PLAIN."
    assert template_arg_name_from_kwargs is None, "Nome do template deveria ser None para e-mail de texto puro."
    assert mock_email_module_logger_info.call_count >= 2, "Logs informativos não foram chamados."
    print(f"  Sucesso: fm.send_message chamado corretamente para texto puro.")


async def test_send_email_async_handles_exception_from_fastapi_mail(mocker):
    """
    Testa o tratamento de erro em `send_email_async` quando a chamada
    a `fm.send_message` (de `fastapi-mail`) levanta uma exceção (ex: erro SMTP).

    Verifica:
    - Se `fm.send_message` é chamado.
    - Se `logger.exception` é chamado para logar o erro.
    - Se a mensagem de log de exceção contém informações úteis.
    """
    print("\nTeste: send_email_async tratando exceção do fm.send_message.")
    # Arrange: Configurar settings para permitir envio e mockar fm.send_message para levantar erro.
    simulated_smtp_error_message = "Simulated SMTP Connection Error (535 Authentication credentials invalid)"
    mock_fastapi_mail_send_message = mocker.patch(
        "app.core.email.fm.send_message",
        new_callable=AsyncMock,
        side_effect=Exception(simulated_smtp_error_message) 
    )
    mocker.patch.object(settings, 'MAIL_ENABLED', True)
    mocker.patch.object(settings, 'MAIL_USERNAME', 'user_excp')
    mocker.patch.object(settings, 'MAIL_PASSWORD', 'pass_excp')
    mocker.patch.object(settings, 'MAIL_FROM', 'sender_excp@example.com')
    mocker.patch.object(settings, 'MAIL_SERVER', 'smtp.excp.example.com')
    mocker.patch.object(settings, 'MAIL_PORT', 587)
    mock_email_module_logger_exception = mocker.patch("app.core.email.logger.exception")
    print("  Mock: fm.send_message (para levantar erro), settings, logger.exception.")

    test_recipient_list = ["recipient_error@example.com"]
    # Act: Chamar a função de envio.
    print(f"  Atuando: Chamando send_email_async (esperando que fm.send_message falhe)...")
    await send_email_async(
        subject="E-mail de Teste de Erro de Envio",
        recipient_to=test_recipient_list,
        body={"info": "Este envio deve falhar e ser logado."}
    )

    # Assert: Verificar mocks.
    mock_fastapi_mail_send_message.assert_called_once()
    mock_email_module_logger_exception.assert_called_once()
    
    # Verifica a mensagem logada por logger.exception.
    log_message_args = mock_email_module_logger_exception.call_args[0] # (args, kwargs)
    logged_error_message_str = log_message_args[0]
    
    assert f"Erro ao enviar e-mail para {test_recipient_list}" in logged_error_message_str, \
        "Mensagem de log de exceção não contém os destinatários."
    # A exceção original (`side_effect`) deve estar na mensagem de log também (via f-string ou %s).
    assert simulated_smtp_error_message in logged_error_message_str or \
           simulated_smtp_error_message in str(mock_email_module_logger_exception.call_args.kwargs.get('exc_info')), \
        "A mensagem de erro original do SMTP não foi incluída no log de exceção."
    print("  Sucesso: Exceção do fm.send_message tratada e logada corretamente.")


# ================================================================
# --- Testes Unitários para `send_urgent_task_notification` ---
# ================================================================
# Estes testes focam na lógica específica de `send_urgent_task_notification`,
# mockando a função genérica `send_email_async` que ela chama.

@pytest.fixture(autouse=True) # `autouse=True` aplica este mock a todos os testes *neste escopo/módulo* (se não estiver em uma classe).
                              # Para maior controle, poderia ser passado explicitamente para cada teste.
def auto_mock_send_email_async_for_urgent_tests(mocker) -> AsyncMock:
    """
    Fixture que mocka automaticamente `app.core.email.send_email_async`
    para todos os testes de `send_urgent_task_notification` neste arquivo.
    Retorna o mock para que possa ser usado nas asserções.
    """
    print("  Fixture (autouse): Mockando app.core.email.send_email_async.")
    mocked_function = mocker.patch("app.core.email.send_email_async", new_callable=AsyncMock)
    return mocked_function


async def test_send_urgent_task_notification_constructs_correct_arguments(
    auto_mock_send_email_async_for_urgent_tests: AsyncMock, 
    mocker
):
    """
    Verifica se `send_urgent_task_notification` chama `send_email_async`
    com os argumentos corretos (assunto, destinatário, nome do template, e corpo do template)
    quando todos os dados de entrada são fornecidos.
    """
    print("\nTeste: send_urgent_task_notification com todos os dados e FRONTEND_URL.")
    # Arrange: Definir dados de teste e mockar settings.FRONTEND_URL.
    test_frontend_base_url = "http://smarttask.dev"
    mocker.patch.object(settings, 'FRONTEND_URL', test_frontend_base_url)
    print(f"  Mock: settings.FRONTEND_URL='{test_frontend_base_url}'.")

    user_email_addr = "urgent_user@example.com"
    user_full_name = "Urgent User Name"
    task_display_title = "URGENT: Resolver bug crítico na API!"
    task_unique_id = str(uuid.uuid4())
    task_due_date_str = "2025-01-01"
    task_priority_score_float = 123.456

    # Act: Chamar a função a ser testada.
    print("  Atuando: Chamando send_urgent_task_notification...")
    await email_module.send_urgent_task_notification(
        user_email=user_email_addr,
        user_name=user_full_name,
        task_title=task_display_title,
        task_id=task_unique_id,
        task_due_date=task_due_date_str,
        priority_score=task_priority_score_float
    )

    # Assert: Verificar se `send_email_async` foi chamado uma vez com os argumentos corretos.
    auto_mock_send_email_async_for_urgent_tests.assert_awaited_once() 
    
    # `call_args.kwargs` contém os argumentos nomeados passados para o mock.
    called_with_kwargs = auto_mock_send_email_async_for_urgent_tests.call_args.kwargs
    print(f"  Argumentos passados para send_email_async (mock): {called_with_kwargs}")

    assert called_with_kwargs.get("subject") == f"🚨 Tarefa Urgente no SmartTask: {task_display_title}", "Assunto do e-mail incorreto."
    assert called_with_kwargs.get("recipient_to") == [user_email_addr], "Destinatário incorreto."
    assert called_with_kwargs.get("template_name") == "urgent_task.html", "Nome do template incorreto."
    assert called_with_kwargs.get("plain_text_body") is not None, "Corpo de texto puro alternativo deveria ser gerado."

    # Verifica o conteúdo do dicionário `body` passado para o template.
    template_body_dict = called_with_kwargs.get("body")
    assert isinstance(template_body_dict, dict), "Corpo do template não é um dicionário."
    assert template_body_dict.get("task_title") == task_display_title
    assert template_body_dict.get("user_name") == user_full_name
    assert template_body_dict.get("due_date") == task_due_date_str
    # Verifica se a pontuação de prioridade foi formatada para duas casas decimais.
    assert template_body_dict.get("priority_score") == f"{task_priority_score_float:.2f}"
    assert template_body_dict.get("task_link") == f"{test_frontend_base_url}/tasks/{task_unique_id}"
    assert template_body_dict.get("project_name") == settings.PROJECT_NAME
    print("  Sucesso: send_urgent_task_notification passou os argumentos corretos para send_email_async.")


async def test_send_urgent_task_notification_handles_no_due_date_and_no_frontend_url(
    auto_mock_send_email_async_for_urgent_tests: AsyncMock,
    mocker
):
    """
    Verifica se `send_urgent_task_notification` lida corretamente com cenários
    onde `task_due_date` é None e `settings.FRONTEND_URL` não está definida.
    O `due_date` no corpo do template deve ser "N/A" e `task_link` deve ser None.
    """
    print("\nTeste: send_urgent_task_notification sem due_date e sem FRONTEND_URL.")
    # Arrange: Mockar settings.FRONTEND_URL para ser None.
    mocker.patch.object(settings, 'FRONTEND_URL', None)
    print("  Mock: settings.FRONTEND_URL=None.")

    user_email_addr = "nodate_nolink_user@example.com"
    user_full_name = "User Without Due Date"
    task_display_title = "Tarefa Opcional Sem Prazo ou Link"
    task_unique_id = str(uuid.uuid4())
    task_priority_score_float = 500.0

    # Act: Chamar a função.
    print("  Atuando: Chamando send_urgent_task_notification com task_due_date=None...")
    await email_module.send_urgent_task_notification(
        user_email=user_email_addr,
        user_name=user_full_name,
        task_title=task_display_title,
        task_id=task_unique_id,
        task_due_date=None, 
        priority_score=task_priority_score_float
    )

    # Assert: Verificar argumentos, focando em `due_date` e `task_link`.
    auto_mock_send_email_async_for_urgent_tests.assert_awaited_once()
    called_with_kwargs = auto_mock_send_email_async_for_urgent_tests.call_args.kwargs
    print(f"  Argumentos passados (body): {called_with_kwargs.get('body')}")

    assert called_with_kwargs.get("recipient_to") == [user_email_addr]
    template_body_dict = called_with_kwargs.get("body")
    assert isinstance(template_body_dict, dict)
    assert template_body_dict.get("due_date") == "N/A", "due_date no template deveria ser 'N/A'."
    assert template_body_dict.get("task_link") is None, "task_link no template deveria ser None."
    print("  Sucesso: Cenário sem due_date e FRONTEND_URL tratado corretamente.")