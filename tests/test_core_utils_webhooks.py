# tests/test_core_utils_webhooks.py
"""
Este módulo contém testes unitários para a função `send_webhook_notification`
localizada em `app.core.utils`.

Os testes utilizam `respx` para mockar as requisições HTTP externas,
permitindo testar o comportamento da função sob diversas condições:
- Envio de webhook sem segredo (sem header de assinatura).
- Envio de webhook com segredo (com verificação da assinatura HMAC-SHA256).
- Tratamento de erros HTTP retornados pelo servidor do webhook (ex: 4xx, 5xx).
- Tratamento de erros de rede/conexão durante a tentativa de envio.
- Comportamento quando a URL do webhook não está configurada nas settings.
"""

# ========================
# --- Importações ---
# ========================
import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

# --- Módulos da Aplicação ---
from app.core.config import settings
from app.core.utils import send_webhook_notification

# ========================
# --- Marcador Global de Teste ---
# ========================
pytestmark = pytest.mark.asyncio

# ========================
# --- Constantes e Dados de Teste ---
# ========================
TEST_TASK_DATA_FOR_WEBHOOK = {
    "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "owner_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
    "title": "Tarefa de Teste para Webhook",
    "importance": 4,
    "status": "pendente_webhook_test",
}
TEST_EVENT_TYPE_WEBHOOK = "task.webhook_test_event"
TEST_WEBHOOK_TARGET_URL = "http://mocked-webhook-receiver.test/api/hook"

# ========================
# --- Fixtures de Teste ---
# ========================
@pytest.fixture(autouse=True)
def override_webhook_settings_for_tests(monkeypatch):
    """
    Fixture `autouse` que sobrescreve as configurações globais de webhook
    (`settings.WEBHOOK_URL` e `settings.WEBHOOK_SECRET`) para cada teste neste módulo.
    """
    print("  Fixture (autouse): Configurando settings de webhook para testes...")
    monkeypatch.setattr(settings, 'WEBHOOK_URL', TEST_WEBHOOK_TARGET_URL)
    monkeypatch.setattr(settings, 'WEBHOOK_SECRET', None)
    print(f"    settings.WEBHOOK_URL mockado para: {TEST_WEBHOOK_TARGET_URL}")
    print(f"    settings.WEBHOOK_SECRET mockado para: None (inicialmente)")

# ========================
# --- Testes da Função `send_webhook_notification` ---
# ========================
@respx.mock
async def test_send_webhook_successfully_without_secret():
    """
    Testa o envio bem-sucedido de uma notificação de webhook quando
    `settings.WEBHOOK_SECRET` NÃO está configurado.
    """
    print("\nTeste: send_webhook_notification - Envio bem-sucedido sem segredo.")
    # --- Arrange ---
    mocked_route = respx.post(TEST_WEBHOOK_TARGET_URL).mock(
        return_value=httpx.Response(200, json={"status": "webhook_received_ok"})
    )
    print(f"  Mock respx: Rota POST para '{TEST_WEBHOOK_TARGET_URL}' mockada para retornar 200.")

    # --- Act ---
    print("  Atuando: Chamando send_webhook_notification...")
    await send_webhook_notification(
        event_type=TEST_EVENT_TYPE_WEBHOOK,
        task_data=TEST_TASK_DATA_FOR_WEBHOOK
    )

    # --- Assert ---
    assert mocked_route.called, "A rota do webhook mockada não foi chamada."
    assert respx.calls.call_count == 1, "Número de chamadas HTTP incorreto."

    last_request_made = respx.calls.last.request
    print(f"  Requisição enviada: URL='{last_request_made.url}', Headers='{last_request_made.headers}'")
    assert str(last_request_made.url) == TEST_WEBHOOK_TARGET_URL, "URL da requisição incorreta."

    sent_payload = json.loads(last_request_made.content)
    print(f"  Payload enviado: {sent_payload}")
    assert sent_payload.get("event") == TEST_EVENT_TYPE_WEBHOOK
    assert sent_payload.get("task") == TEST_TASK_DATA_FOR_WEBHOOK
    assert "timestamp" in sent_payload

    assert "X-SmartTask-Signature" not in last_request_made.headers
    print("  Sucesso: Webhook enviado corretamente sem header de assinatura.")

@respx.mock
async def test_send_webhook_successfully_with_secret_and_valid_signature(
    monkeypatch
):
    """
    Testa o envio bem-sucedido de notificação de webhook com `WEBHOOK_SECRET` configurado.
    """
    print("\nTeste: send_webhook_notification - Envio bem-sucedido com segredo e assinatura válida.")
    # --- Arrange ---
    test_webhook_secret_key = "este-e-um-segredo-muito-secreto-para-hmac"
    monkeypatch.setattr(settings, 'WEBHOOK_SECRET', test_webhook_secret_key)
    print(f"  Mock monkeypatch: settings.WEBHOOK_SECRET definido para '{test_webhook_secret_key}'.")
    mocked_route = respx.post(TEST_WEBHOOK_TARGET_URL).mock(return_value=httpx.Response(200))
    print(f"  Mock respx: Rota POST para '{TEST_WEBHOOK_TARGET_URL}' mockada.")

    # --- Act ---
    print("  Atuando: Chamando send_webhook_notification...")
    await send_webhook_notification(
        event_type=TEST_EVENT_TYPE_WEBHOOK,
        task_data=TEST_TASK_DATA_FOR_WEBHOOK
    )

    # --- Assert ---
    assert mocked_route.called
    last_request_made = respx.calls.last.request
    assert "X-SmartTask-Signature" in last_request_made.headers
    signature_from_header = last_request_made.headers["X-SmartTask-Signature"]
    assert signature_from_header.startswith("sha256=")
    print(f"  Header de assinatura recebido: {signature_from_header}")

    sent_payload_bytes = last_request_made.content
    sent_payload_dict_actual = json.loads(sent_payload_bytes)
    actual_timestamp_sent = sent_payload_dict_actual["timestamp"]
    expected_payload_base = {"event": TEST_EVENT_TYPE_WEBHOOK, "task": TEST_TASK_DATA_FOR_WEBHOOK}
    payload_for_signature_calculation = expected_payload_base.copy()
    payload_for_signature_calculation["timestamp"] = actual_timestamp_sent
    payload_bytes_for_hmac = json.dumps(
        payload_for_signature_calculation, separators=(',', ':'), sort_keys=True
    ).encode('utf-8')
    secret_bytes_for_hmac = test_webhook_secret_key.encode('utf-8')
    expected_hmac_signature_hex = hmac.new(
        secret_bytes_for_hmac, payload_bytes_for_hmac, hashlib.sha256
    ).hexdigest()
    print(f"  Assinatura HMAC calculada esperada: {expected_hmac_signature_hex}")
    assert signature_from_header == f"sha256={expected_hmac_signature_hex}"
    print("  Sucesso: Webhook enviado com segredo e assinatura HMAC válida.")

@respx.mock
async def test_send_webhook_handles_http_error_from_server(mocker):
    """
    Testa o tratamento de erro quando o servidor do webhook retorna um erro HTTP.
    """
    print("\nTeste: send_webhook_notification - Tratamento de erro HTTP do servidor.")
    # --- Arrange ---
    http_error_status_code = 500
    http_error_response_text = "Ocorreu um Erro Interno no Servidor do Webhook"
    respx.post(TEST_WEBHOOK_TARGET_URL).mock(
        return_value=httpx.Response(http_error_status_code, text=http_error_response_text)
    )
    print(f"  Mock respx: Rota POST para '{TEST_WEBHOOK_TARGET_URL}' mockada para retornar {http_error_status_code}.")
    mock_utils_logger = mocker.patch("app.core.utils.logger")
    print("  Mock: app.core.utils.logger.")

    # --- Act ---
    print("  Atuando: Chamando send_webhook_notification (esperando erro HTTP)...")
    await send_webhook_notification(TEST_EVENT_TYPE_WEBHOOK, TEST_TASK_DATA_FOR_WEBHOOK)

    # --- Assert ---
    mock_utils_logger.error.assert_called_once()
    error_log_args, _ = mock_utils_logger.error.call_args
    error_log_message = error_log_args[0]
    print(f"  Log de erro capturado: {error_log_message}")
    assert "Erro no servidor do webhook" in error_log_message
    assert f"({TEST_WEBHOOK_TARGET_URL})" in error_log_message
    assert f"Status: {http_error_status_code}" in error_log_message
    assert http_error_response_text in error_log_message
    print("  Sucesso: Erro HTTP do servidor tratado e logado corretamente.")

@respx.mock
async def test_send_webhook_handles_network_request_error(mocker):
    """
    Testa o tratamento de erro quando ocorre um problema de rede ou conexão.
    """
    print("\nTeste: send_webhook_notification - Tratamento de erro de rede/conexão.")
    # --- Arrange ---
    simulated_network_error_message = "Falha de conexão simulada (DNS lookup failed)"
    respx.post(TEST_WEBHOOK_TARGET_URL).mock(side_effect=httpx.RequestError(simulated_network_error_message))
    print(f"  Mock respx: Rota POST para '{TEST_WEBHOOK_TARGET_URL}' mockada para levantar httpx.RequestError.")
    mock_utils_logger = mocker.patch("app.core.utils.logger")
    print("  Mock: app.core.utils.logger.")

    # --- Act ---
    print("  Atuando: Chamando send_webhook_notification (esperando erro de rede)...")
    await send_webhook_notification(TEST_EVENT_TYPE_WEBHOOK, TEST_TASK_DATA_FOR_WEBHOOK)

    # --- Assert ---
    mock_utils_logger.error.assert_called_once()
    error_log_args, _ = mock_utils_logger.error.call_args
    error_log_message = error_log_args[0]
    print(f"  Log de erro capturado: {error_log_message}")
    assert "Erro na requisição ao enviar webhook para" in error_log_message
    assert TEST_WEBHOOK_TARGET_URL in error_log_message
    assert simulated_network_error_message in error_log_message
    print("  Sucesso: Erro de rede/conexão tratado e logado corretamente.")

async def test_send_webhook_does_nothing_if_url_not_configured(mocker):
    """
    Testa se `send_webhook_notification` não faz nada se `settings.WEBHOOK_URL` não estiver configurada.
    """
    print("\nTeste: send_webhook_notification - WEBHOOK_URL não configurada.")
    # --- Arrange ---
    with patch('app.core.utils.settings.WEBHOOK_URL', None):
        print(f"  Mock patch: settings.WEBHOOK_URL definido como None para este teste.")
        mock_httpx_client_post = mocker.patch("httpx.AsyncClient.post", new_callable=AsyncMock)
        mock_utils_logger = mocker.patch("app.core.utils.logger")
        print("  Mock: httpx.AsyncClient.post e app.core.utils.logger.")

        # --- Act ---
        print("  Atuando: Chamando send_webhook_notification...")
        await send_webhook_notification(TEST_EVENT_TYPE_WEBHOOK, TEST_TASK_DATA_FOR_WEBHOOK)

        # --- Assert ---
        mock_httpx_client_post.assert_not_called()
        assert not mock_utils_logger.info.called
        assert not mock_utils_logger.error.called
        expected_debug_message = "Webhook URL não configurada, pulando envio."
        mock_utils_logger.debug.assert_called_once_with(expected_debug_message)
        print("  Sucesso: Nenhuma tentativa de envio de webhook e log de debug correto quando URL não configurada.")

@respx.mock
async def test_send_webhook_signature_generation_failure(mocker):
    """
    Testa o tratamento de erro quando a geração da assinatura HMAC falha.
    """
    print("\nTeste: send_webhook_notification - Falha na geração da assinatura HMAC.")
    # --- Arrange ---
    test_secret = "super_secret"
    mocker.patch.object(settings, 'WEBHOOK_SECRET', test_secret)
    mock_utils_logger = mocker.patch("app.core.utils.logger")
    mocker.patch("app.core.utils.hmac.new", side_effect=Exception("HMAC generation error"))

    # --- Act ---
    await send_webhook_notification(TEST_EVENT_TYPE_WEBHOOK, TEST_TASK_DATA_FOR_WEBHOOK)

    # --- Assert ---
    mock_utils_logger.error.assert_called_once()
    error_log_message = mock_utils_logger.error.call_args[0][0]
    assert "Erro ao gerar assinatura HMAC para webhook" in error_log_message
    assert "HMAC generation error" in error_log_message
    assert respx.calls.call_count == 0
    print("  Sucesso: Falha na geração de assinatura HMAC tratada e logada.")

@respx.mock
async def test_send_webhook_unexpected_generic_exception_during_send(mocker):
    """
    Testa o tratamento de uma exceção genérica inesperada durante o envio do webhook.
    """
    print("\nTeste: send_webhook_notification - Exceção genérica inesperada no envio.")
    # --- Arrange ---
    mock_utils_logger = mocker.patch("app.core.utils.logger")
    mock_post_method = AsyncMock(side_effect=Exception("Erro genérico simulado no post"))
    mock_client_operations = AsyncMock()
    mock_client_operations.post = mock_post_method
    mock_client_context = AsyncMock()
    mock_client_context.__aenter__ = AsyncMock(return_value=mock_client_operations)
    mock_client_context.__aexit__ = AsyncMock(return_value=None)
    mocker.patch("httpx.AsyncClient", return_value=mock_client_context)

    # --- Act ---
    await send_webhook_notification(TEST_EVENT_TYPE_WEBHOOK, TEST_TASK_DATA_FOR_WEBHOOK)

    # --- Assert ---
    mock_utils_logger.exception.assert_called_once()
    exception_log_message = mock_utils_logger.exception.call_args[0][0]
    assert "Erro inesperado ao enviar webhook para" in exception_log_message
    assert "Erro genérico simulado no post" in exception_log_message
    print("  Sucesso: Exceção genérica inesperada durante o envio tratada e logada com logger.exception.")

@respx.mock
async def test_send_webhook_handles_timeout_exception(mocker):
    """
    Testa o tratamento de erro quando ocorre um httpx.TimeoutException
    ao tentar enviar a notificação de webhook.
    """
    print("\nTeste: send_webhook_notification - Tratamento de httpx.TimeoutException.")
    # --- Arrange ---
    simulated_timeout_message = "Simulated timeout durante o envio do webhook"
    dummy_request_for_exception = httpx.Request(method="POST", url=TEST_WEBHOOK_TARGET_URL)
    respx.post(TEST_WEBHOOK_TARGET_URL).mock(
        side_effect=httpx.TimeoutException(simulated_timeout_message, request=dummy_request_for_exception)
    )
    print(f"  Mock respx: Rota POST para '{TEST_WEBHOOK_TARGET_URL}' mockada para levantar httpx.TimeoutException.")
    mock_utils_logger = mocker.patch("app.core.utils.logger")
    print("  Mock: app.core.utils.logger.")

    # --- Act ---
    print("  Atuando: Chamando send_webhook_notification (esperando timeout)...")
    await send_webhook_notification(TEST_EVENT_TYPE_WEBHOOK, TEST_TASK_DATA_FOR_WEBHOOK)

    # --- Assert ---
    mock_utils_logger.error.assert_called_once()
    error_log_args, _ = mock_utils_logger.error.call_args
    error_log_message = error_log_args[0]
    print(f"  Log de erro capturado: {error_log_message}")
    assert "Timeout ao enviar webhook para" in error_log_message
    assert TEST_WEBHOOK_TARGET_URL in error_log_message
    print("  Sucesso: httpx.TimeoutException tratado e logado corretamente.")