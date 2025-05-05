# tests/test_core_utils_webhooks.py

import pytest
import logging
import httpx
import respx 
import hmac
import hashlib
import json
from unittest.mock import AsyncMock, patch # Usaremos patch do unittest

from app.core.utils import send_webhook_notification
from app.core.config import settings

pytestmark = pytest.mark.asyncio

# Dados de teste para a tarefa
test_task_data = {
    "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "owner_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
    "title": "Webhook Test Task",
    "importance": 4,
    "status": "pendente",
}
test_event_type = "task.test_event"
test_webhook_url = "http://test-webhook.site/hook" 

@pytest.fixture(autouse=True)
def override_settings_for_webhook(monkeypatch):
    """Sobrescreve configurações de webhook APENAS para estes testes."""
    monkeypatch.setattr(settings, 'WEBHOOK_URL', test_webhook_url)
    monkeypatch.setattr(settings, 'WEBHOOK_SECRET', None)

# Usar respx para mockar as chamadas httpx
@respx.mock
async def test_send_webhook_no_secret(override_settings_for_webhook):
    """Testa o envio de webhook quando não há segredo configurado."""
    respx.post(test_webhook_url).mock(return_value=httpx.Response(200, json={"status": "ok"}))

    await send_webhook_notification(
        event_type=test_event_type,
        task_data=test_task_data
    )

    # Verifica se a chamada HTTP foi feita para a URL correta
    assert respx.calls.call_count == 1
    request = respx.calls.last.request
    assert str(request.url) == test_webhook_url

    # Verifica o payload JSON
    payload = json.loads(request.content)
    assert payload["event"] == test_event_type
    assert payload["task"] == test_task_data
    assert "timestamp" in payload

    # Verifica que o header de assinatura NÃO foi enviado
    assert "X-SmartTask-Signature" not in request.headers

# Usar respx e monkeypatch para setar o segredo
@respx.mock
async def test_send_webhook_with_secret(monkeypatch):
    """Testa o envio de webhook com um segredo e verifica a assinatura HMAC."""
    test_secret = "my-super-secret-webhook-key"
    monkeypatch.setattr(settings, 'WEBHOOK_SECRET', test_secret) 
    monkeypatch.setattr(settings, 'WEBHOOK_URL', test_webhook_url) 

    # Mocka a rota httpx
    route = respx.post(test_webhook_url).mock(return_value=httpx.Response(200))

    await send_webhook_notification(
        event_type=test_event_type,
        task_data=test_task_data
    )

    # Verifica a chamada HTTP
    assert route.called
    request = respx.calls.last.request

    # Verifica que o header de assinatura FOI enviado
    assert "X-SmartTask-Signature" in request.headers
    signature_header = request.headers["X-SmartTask-Signature"]
    assert signature_header.startswith("sha256=")

    # Verifica se a assinatura está correta
    # Recria o payload exato e calcula a assinatura esperada
    payload_dict = {
        "event": test_event_type,
        "task": test_task_data,
    }
    sent_payload_bytes = request.content 
    sent_payload_dict = json.loads(sent_payload_bytes) 
    # Agora pega o timestamp que foi realmente enviado
    payload_dict["timestamp"] = sent_payload_dict["timestamp"]

    # Gera o payload JSON ordenado e encodado como a função faz
    expected_payload_bytes = json.dumps(payload_dict, separators=(',', ':'), sort_keys=True).encode('utf-8')
    secret_bytes = test_secret.encode('utf-8')
    expected_signature = hmac.new(secret_bytes, expected_payload_bytes, hashlib.sha256).hexdigest()

    # Compara a assinatura esperada com a que está no header
    assert signature_header == f"sha256={expected_signature}"


@respx.mock
async def test_send_webhook_http_error(override_settings_for_webhook, mocker):
    """Testa o tratamento de erro HTTP (ex: 404, 500) do servidor do webhook."""
    respx.post(test_webhook_url).mock(return_value=httpx.Response(500, text="Internal Server Error"))

    mock_logger = mocker.patch("app.core.utils.logger")

    await send_webhook_notification(test_event_type, test_task_data)

    mock_logger.error.assert_called_once()
    call_args, _ = mock_logger.error.call_args 
    assert "Erro no servidor do webhook" in call_args[0]
    assert "Status: 500" in call_args[0]
    assert "Internal Server Error" in call_args[0]

@respx.mock
async def test_send_webhook_request_error(override_settings_for_webhook, mocker):
    """Testa o tratamento de erro de rede/conexão ao enviar webhook."""
    respx.post(test_webhook_url).mock(side_effect=httpx.RequestError("Connection failed"))

    mock_logger = mocker.patch("app.core.utils.logger")

    await send_webhook_notification(test_event_type, test_task_data)

    mock_logger.error.assert_called_once()
    call_args, _ = mock_logger.error.call_args
    assert "Erro na requisição ao enviar webhook" in call_args[0]
    assert "Connection failed" in call_args[0]

async def test_send_webhook_url_not_configured(mocker):
    """Testa que nada acontece se WEBHOOK_URL não estiver configurada."""
    with patch('app.core.utils.settings.WEBHOOK_URL', None):
         # Mock para garantir que httpx não seja instanciado ou chamado
        mock_post = mocker.patch("httpx.AsyncClient.post", new_callable=AsyncMock)
        # Mock do logger para garantir que nenhuma tentativa de envio foi logada (exceto o debug)
        mock_logger = mocker.patch("app.core.utils.logger")

        await send_webhook_notification(test_event_type, test_task_data)

        mock_post.assert_not_called()
        assert not mock_logger.info.called
        assert not mock_logger.error.called
        mock_logger.debug.assert_called_once_with(
             "Webhook URL não configurada, pulando envio."
        )