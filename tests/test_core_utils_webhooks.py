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

# ====================================
# --- Marcador Global de Teste ---
# ====================================
pytestmark = pytest.mark.asyncio

# =====================================
# --- Constantes e Dados de Teste ---
# =====================================

# Dados de teste para a tarefa que será enviada no payload do webhook.
TEST_TASK_DATA_FOR_WEBHOOK = {
    "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "owner_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
    "title": "Tarefa de Teste para Webhook",
    "importance": 4,
    "status": "pendente_webhook_test",
}
TEST_EVENT_TYPE_WEBHOOK = "task.webhook_test_event"
# URL mockada para os webhooks; `respx` interceptará chamadas para esta URL.
TEST_WEBHOOK_TARGET_URL = "http://mocked-webhook-receiver.test/api/hook"

# =================================
# --- Fixtures de Teste ---
# =================================

@pytest.fixture(autouse=True) # Aplicado automaticamente a todos os testes neste arquivo.
def override_webhook_settings_for_tests(monkeypatch):
    """
    Fixture `autouse` que sobrescreve as configurações globais de webhook
    (`settings.WEBHOOK_URL` e `settings.WEBHOOK_SECRET`) para cada teste neste módulo.
    Isso garante um estado limpo e controlado para as configurações de webhook,
    prevenindo que valores de um teste afetem outro ou que o sistema dependa
    de variáveis de ambiente reais durante os testes.

    - Define `WEBHOOK_URL` para uma URL de teste padrão.
    - Inicialmente define `WEBHOOK_SECRET` como `None` (pode ser alterado por testes específicos).
    """
    print("  Fixture (autouse): Configurando settings de webhook para testes...")
    monkeypatch.setattr(settings, 'WEBHOOK_URL', TEST_WEBHOOK_TARGET_URL)
    # WEBHOOK_SECRET é None por padrão; testes que precisam dele o definirão.
    monkeypatch.setattr(settings, 'WEBHOOK_SECRET', None)
    print(f"    settings.WEBHOOK_URL mockado para: {TEST_WEBHOOK_TARGET_URL}")
    print(f"    settings.WEBHOOK_SECRET mockado para: None (inicialmente)")

# ===========================================================
# --- Testes da Função `send_webhook_notification` ---
# ===========================================================

@respx.mock # Ativa o mock de `respx` para este teste.
async def test_send_webhook_successfully_without_secret(
    # `override_webhook_settings_for_tests` já foi aplicada (autouse).
):
    """
    Testa o envio bem-sucedido de uma notificação de webhook quando
    `settings.WEBHOOK_SECRET` NÃO está configurado.

    Verifica:
    - Se uma requisição POST HTTP é feita para a `WEBHOOK_URL` configurada.
    - Se o payload JSON enviado contém os dados corretos (evento, dados da tarefa, timestamp).
    - Se o header de assinatura `X-SmartTask-Signature` NÃO está presente na requisição.
    """
    print("\nTeste: send_webhook_notification - Envio bem-sucedido sem segredo.")
    # Arrange: Mockar a rota HTTP para retornar uma resposta de sucesso (200 OK).
    # `respx` interceptará a chamada para TEST_WEBHOOK_TARGET_URL.
    mocked_route = respx.post(TEST_WEBHOOK_TARGET_URL).mock(
        return_value=httpx.Response(200, json={"status": "webhook_received_ok"})
    )
    print(f"  Mock respx: Rota POST para '{TEST_WEBHOOK_TARGET_URL}' mockada para retornar 200.")

    # Act: Chamar a função de envio de webhook.
    print("  Atuando: Chamando send_webhook_notification...")
    await send_webhook_notification(
        event_type=TEST_EVENT_TYPE_WEBHOOK,
        task_data=TEST_TASK_DATA_FOR_WEBHOOK
    )

    # Assert: Verificar a chamada HTTP e seus detalhes.
    assert mocked_route.called, "A rota do webhook mockada não foi chamada."
    assert respx.calls.call_count == 1, "Número de chamadas HTTP incorreto."
    
    last_request_made = respx.calls.last.request
    print(f"  Requisição enviada: URL='{last_request_made.url}', Headers='{last_request_made.headers}'")
    assert str(last_request_made.url) == TEST_WEBHOOK_TARGET_URL, "URL da requisição incorreta."

    # Verificar o payload JSON enviado.
    sent_payload = json.loads(last_request_made.content)
    print(f"  Payload enviado: {sent_payload}")
    assert sent_payload.get("event") == TEST_EVENT_TYPE_WEBHOOK, "Campo 'event' no payload incorreto."
    assert sent_payload.get("task") == TEST_TASK_DATA_FOR_WEBHOOK, "Campo 'task' no payload incorreto."
    assert "timestamp" in sent_payload, "Campo 'timestamp' ausente no payload."

    # Verificar a ausência do header de assinatura.
    assert "X-SmartTask-Signature" not in last_request_made.headers, \
        "Header 'X-SmartTask-Signature' presente indevidamente (deveria estar ausente sem segredo)."
    print("  Sucesso: Webhook enviado corretamente sem header de assinatura.")

@respx.mock
async def test_send_webhook_successfully_with_secret_and_valid_signature(
    monkeypatch
    # Para modificar settings.WEBHOOK_SECRET especificamente para este teste.
):
    """
    Testa o envio bem-sucedido de uma notificação de webhook quando
    `settings.WEBHOOK_SECRET` ESTÁ configurado.

    Verifica:
    - Se a requisição POST HTTP é feita.
    - Se o header de assinatura `X-SmartTask-Signature` ESTÁ presente.
    - Se a assinatura HMAC-SHA256 no header corresponde à assinatura calculada
      do payload enviado, usando o segredo configurado.
    """
    print("\nTeste: send_webhook_notification - Envio bem-sucedido com segredo e assinatura válida.")
    # Arrange: Definir um segredo para o webhook e mockar a rota HTTP.
    test_webhook_secret_key = "este-e-um-segredo-muito-secreto-para-hmac"
    monkeypatch.setattr(settings, 'WEBHOOK_SECRET', test_webhook_secret_key)
    # WEBHOOK_URL já está setada pela fixture autouse.
    print(f"  Mock monkeypatch: settings.WEBHOOK_SECRET definido para '{test_webhook_secret_key}'.")

    mocked_route = respx.post(TEST_WEBHOOK_TARGET_URL).mock(return_value=httpx.Response(200))
    print(f"  Mock respx: Rota POST para '{TEST_WEBHOOK_TARGET_URL}' mockada.")

    # Act: Chamar a função de envio.
    print("  Atuando: Chamando send_webhook_notification...")
    await send_webhook_notification(
        event_type=TEST_EVENT_TYPE_WEBHOOK,
        task_data=TEST_TASK_DATA_FOR_WEBHOOK
    )

    # Assert: Verificar a chamada HTTP e a assinatura.
    assert mocked_route.called, "Rota do webhook não foi chamada."
    last_request_made = respx.calls.last.request

    # Verificar presença do header de assinatura.
    assert "X-SmartTask-Signature" in last_request_made.headers, "Header 'X-SmartTask-Signature' ausente."
    
    signature_from_header = last_request_made.headers["X-SmartTask-Signature"]
    assert signature_from_header.startswith("sha256="), "Formato do header de assinatura inválido."
    print(f"  Header de assinatura recebido: {signature_from_header}")

    # Verificar se a assinatura está correta.
    # Para isso, precisamos recriar o payload *exatamente como foi enviado*
    # (incluindo o timestamp que foi gerado pela função `send_webhook_notification`).
    
    # 1. Obter o payload que foi realmente enviado na requisição mockada.
    sent_payload_bytes = last_request_made.content
    sent_payload_dict_actual = json.loads(sent_payload_bytes)
    actual_timestamp_sent = sent_payload_dict_actual["timestamp"] # Extrai o timestamp real.

    # 2. Construir o payload base esperado (sem o timestamp, que é dinâmico).
    expected_payload_base = {
        "event": TEST_EVENT_TYPE_WEBHOOK,
        "task": TEST_TASK_DATA_FOR_WEBHOOK,
    }
    # 3. Adicionar o timestamp real enviado ao nosso payload esperado para cálculo.
    payload_for_signature_calculation = expected_payload_base.copy()
    payload_for_signature_calculation["timestamp"] = actual_timestamp_sent

    # 4. Gerar a representação JSON ordenada e encodada (como a função de webhook faz internamente).
    #    É crucial que a serialização (ordem das chaves, espaçamento) seja idêntica.
    payload_bytes_for_hmac = json.dumps(
        payload_for_signature_calculation,
        separators=(',', ':'), # Compacta o JSON, sem espaços extras.
        sort_keys=True        # Ordena as chaves alfabeticamente.
    ).encode('utf-8')
    
    secret_bytes_for_hmac = test_webhook_secret_key.encode('utf-8')
    
    # 5. Calcular a assinatura HMAC-SHA256 esperada.
    expected_hmac_signature_hex = hmac.new(
        secret_bytes_for_hmac,
        payload_bytes_for_hmac,
        hashlib.sha256
    ).hexdigest()
    print(f"  Assinatura HMAC calculada esperada: {expected_hmac_signature_hex}")

    # 6. Comparar com a assinatura do header.
    assert signature_from_header == f"sha256={expected_hmac_signature_hex}", "Assinatura HMAC no header não corresponde à esperada."
    print("  Sucesso: Webhook enviado com segredo e assinatura HMAC válida.")

@respx.mock
async def test_send_webhook_handles_http_error_from_server(
    # `override_webhook_settings_for_tests` já aplicada.
    mocker # Para mockar o logger.
):
    """
    Testa o tratamento de erro quando o servidor do webhook retorna um erro HTTP
    (ex: status code 404 Not Found, 500 Internal Server Error).

    Verifica se um erro é logado pela função `send_webhook_notification`.
    """
    print("\nTeste: send_webhook_notification - Tratamento de erro HTTP do servidor.")
    # Arrange: Mockar a rota HTTP para retornar um erro 500.
    http_error_status_code = 500
    http_error_response_text = "Ocorreu um Erro Interno no Servidor do Webhook"
    respx.post(TEST_WEBHOOK_TARGET_URL).mock(
        return_value=httpx.Response(http_error_status_code, text=http_error_response_text)
    )
    print(f"  Mock respx: Rota POST para '{TEST_WEBHOOK_TARGET_URL}' mockada para retornar {http_error_status_code}.")

    # Mockar o logger de `app.core.utils` para verificar se `logger.error` é chamado.
    mock_utils_logger = mocker.patch("app.core.utils.logger")
    print("  Mock: app.core.utils.logger.")

    # Act: Chamar a função.
    print("  Atuando: Chamando send_webhook_notification (esperando erro HTTP)...")
    await send_webhook_notification(TEST_EVENT_TYPE_WEBHOOK, TEST_TASK_DATA_FOR_WEBHOOK)

    # Assert: Verificar se o logger.error foi chamado com a mensagem apropriada.
    mock_utils_logger.error.assert_called_once()
    # Extrai os argumentos da chamada ao logger.error.
    error_log_args, _ = mock_utils_logger.error.call_args
    error_log_message = error_log_args[0] 
    print(f"  Log de erro capturado: {error_log_message}")
    
    assert "Erro no servidor do webhook" in error_log_message, "Log não indica erro no servidor do webhook."
    assert f"({TEST_WEBHOOK_TARGET_URL})" in error_log_message, "URL (entre parênteses) não encontrada na mensagem de erro."
    assert f"Status: {http_error_status_code}" in error_log_message, "Status code do erro não encontrado na mensagem."
    assert http_error_response_text in error_log_message, "Texto da resposta do erro não encontrado na mensagem."
    print("  Sucesso: Erro HTTP do servidor tratado e logado corretamente.")

@respx.mock
async def test_send_webhook_handles_network_request_error(
    # `override_webhook_settings_for_tests` já aplicada.
    mocker
):
    """
    Testa o tratamento de erro quando ocorre um problema de rede ou conexão
    ao tentar enviar a notificação de webhook (ex: `httpx.RequestError`).

    Verifica se um erro é logado.
    """
    print("\nTeste: send_webhook_notification - Tratamento de erro de rede/conexão.")
    # Arrange: Mockar a rota HTTP para levantar uma exceção de rede.
    simulated_network_error_message = "Falha de conexão simulada (DNS lookup failed)"
    respx.post(TEST_WEBHOOK_TARGET_URL).mock(side_effect=httpx.RequestError(simulated_network_error_message))
    print(f"  Mock respx: Rota POST para '{TEST_WEBHOOK_TARGET_URL}' mockada para levantar httpx.RequestError.")
    
    mock_utils_logger = mocker.patch("app.core.utils.logger")
    print("  Mock: app.core.utils.logger.")

    # Act: Chamar a função.
    print("  Atuando: Chamando send_webhook_notification (esperando erro de rede)...")
    await send_webhook_notification(TEST_EVENT_TYPE_WEBHOOK, TEST_TASK_DATA_FOR_WEBHOOK)

    # Assert: Verificar se logger.error foi chamado.
    mock_utils_logger.error.assert_called_once()
    error_log_args, _ = mock_utils_logger.error.call_args
    error_log_message = error_log_args[0]
    print(f"  Log de erro capturado: {error_log_message}")

    assert "Erro na requisição ao enviar webhook para" in error_log_message, "Parte inicial da mensagem de erro de rede não encontrada."
    assert TEST_WEBHOOK_TARGET_URL in error_log_message, "URL não encontrada na mensagem de erro de rede."
    assert simulated_network_error_message in error_log_message, "Mensagem da exceção de rede não encontrada no log."
    print("  Sucesso: Erro de rede/conexão tratado e logado corretamente.")

async def test_send_webhook_does_nothing_if_url_not_configured(mocker):
    """
    Testa se `send_webhook_notification` não realiza nenhuma ação (nem tenta enviar)
    e loga uma mensagem de debug se `settings.WEBHOOK_URL` não estiver configurada (for None).

    Verifica:
    - Se `httpx.AsyncClient.post` (ou qualquer chamada HTTP) NÃO é feito.
    - Se nenhum log de info ou erro é gerado (além de um possível debug).
    - Se um log de debug específico é gerado indicando que o envio foi pulado.
    """
    print("\nTeste: send_webhook_notification - WEBHOOK_URL não configurada.")
    # Arrange: Garantir que WEBHOOK_URL é None.
    # A fixture `override_webhook_settings_for_tests` já define WEBHOOK_URL,
    # então precisamos sobrescrevê-la novamente para None aqui.
    with patch('app.core.utils.settings.WEBHOOK_URL', None): 
        print(f"  Mock patch: settings.WEBHOOK_URL definido como None para este teste.")
        # Mock para garantir que nenhuma chamada HTTP real seja feita.
        # Mockamos o método `post` da classe `AsyncClient` no módulo `httpx`.
        mock_httpx_client_post = mocker.patch("httpx.AsyncClient.post", new_callable=AsyncMock)
        
        # Mockar o logger de `app.core.utils` para verificar suas chamadas.
        mock_utils_logger = mocker.patch("app.core.utils.logger")
        print("  Mock: httpx.AsyncClient.post e app.core.utils.logger.")

        # Act: Chamar a função.
        print("  Atuando: Chamando send_webhook_notification...")
        await send_webhook_notification(TEST_EVENT_TYPE_WEBHOOK, TEST_TASK_DATA_FOR_WEBHOOK)

        # Assert:
        mock_httpx_client_post.assert_not_called(), "httpx.AsyncClient.post foi chamado indevidamente."
        # Verifica se não houve logs de info ou error (o que indicaria uma tentativa de envio ou falha).
        assert not mock_utils_logger.info.called, "logger.info foi chamado indevidamente."
        assert not mock_utils_logger.error.called, "logger.error foi chamado indevidamente."
        
        # Verifica se a mensagem de debug esperada foi logada.
        expected_debug_message = "Webhook URL não configurada, pulando envio."
        mock_utils_logger.debug.assert_called_once_with(expected_debug_message)
        print("  Sucesso: Nenhuma tentativa de envio de webhook e log de debug correto quando URL não configurada.")

# =======================================================
@respx.mock # Necessário para que httpx não seja realmente chamado, pois retornaremos antes
async def test_send_webhook_signature_generation_failure(mocker):
    """
    Testa o tratamento de erro quando a geração da assinatura HMAC falha.
    """
    print("\nTeste: send_webhook_notification - Falha na geração da assinatura HMAC.")
    # Arrange: Configurar WEBHOOK_SECRET e mokar hmac.new para falhar
    test_secret = "super_secret"
    mocker.patch.object(settings, 'WEBHOOK_SECRET', test_secret) # Usar mocker.patch.object
    
    mock_utils_logger = mocker.patch("app.core.utils.logger")
    # Mokar hmac.new para levantar uma exceção
    mocker.patch("app.core.utils.hmac.new", side_effect=Exception("HMAC generation error"))

    # Act: Chamar a função
    await send_webhook_notification(TEST_EVENT_TYPE_WEBHOOK, TEST_TASK_DATA_FOR_WEBHOOK)

    # Assert: Verificar se o logger.error foi chamado e se não houve tentativa de envio HTTP
    mock_utils_logger.error.assert_called_once()
    error_log_message = mock_utils_logger.error.call_args[0][0]
    assert "Erro ao gerar assinatura HMAC para webhook" in error_log_message
    assert "HMAC generation error" in error_log_message # Verificar se a msg da exceção está no log
    
    # Verificar que o httpx.post não foi chamado (pois deve retornar antes)
    # Se a rota de respx não for definida e chamada, respx.calls estará vazio.
    assert respx.calls.call_count == 0, "Chamada HTTP foi feita indevidamente após falha na assinatura."
    print("  Sucesso: Falha na geração de assinatura HMAC tratada e logada.")

@respx.mock
async def test_send_webhook_unexpected_generic_exception_during_send(mocker):
    print("\nTeste: send_webhook_notification - Exceção genérica inesperada no envio.")
    mock_utils_logger = mocker.patch("app.core.utils.logger")

    # Precisamos que `client.post` levante uma exceção quando awaited.
    # Mokar a classe AsyncClient para que sua instância retornada
    # tenha um método post que é um AsyncMock que levanta uma exceção.

    mock_post_method = AsyncMock(side_effect=Exception("Erro genérico simulado no post"))

    # Moka o construtor da classe httpx.AsyncClient
    # O construtor retorna um objeto (mock_client_context)
    # que, quando usado em `async with` (via __aenter__), retorna
    # outro objeto (mock_client_operations) que tem o método 'post'.
    
    mock_client_operations = AsyncMock()
    mock_client_operations.post = mock_post_method # O método post levanta a exceção

    mock_client_context = AsyncMock()
    # __aenter__ deve ser um método assíncrono que retorna o objeto com 'post'
    mock_client_context.__aenter__ = AsyncMock(return_value=mock_client_operations)
    # __aexit__ também precisa ser um método assíncrono
    mock_client_context.__aexit__ = AsyncMock(return_value=None)

    mocker.patch("httpx.AsyncClient", return_value=mock_client_context)

    # Act
    await send_webhook_notification(TEST_EVENT_TYPE_WEBHOOK, TEST_TASK_DATA_FOR_WEBHOOK)

    # Assert
    mock_utils_logger.exception.assert_called_once()
    # (O resto das suas asserções)
    exception_log_message = mock_utils_logger.exception.call_args[0][0]
    assert "Erro inesperado ao enviar webhook para" in exception_log_message
    assert "Erro genérico simulado no post" in exception_log_message # Verifique a mensagem do side_effect
    print("  Sucesso: Exceção genérica inesperada durante o envio tratada e logada com logger.exception.")

@respx.mock
async def test_send_webhook_handles_timeout_exception(mocker):
    """
    Testa o tratamento de erro quando ocorre um httpx.TimeoutException
    ao tentar enviar a notificação de webhook.

    Verifica se um erro apropriado é logado.
    """
    print("\nTeste: send_webhook_notification - Tratamento de httpx.TimeoutException.")
    # Arrange: Mockar a rota HTTP para levantar uma TimeoutException.
    # A TimeoutException geralmente precisa de um contexto de request para ser construída,
    # mas o respx pode simular o efeito.
    # Uma forma simples é fazer o side_effect levantar TimeoutException.
    # O construtor de TimeoutException aceita uma mensagem e um request.
    # Para simplificar no mock, podemos apenas levantar a exceção com uma mensagem.
    simulated_timeout_message = "Simulated timeout durante o envio do webhook"
    # Precisamos da instância do request para o construtor do TimeoutException.
    # Como não temos uma instância real do request aqui antes do mock, podemos criar um dummy.
    dummy_request_for_exception = httpx.Request(method="POST", url=TEST_WEBHOOK_TARGET_URL)
    
    respx.post(TEST_WEBHOOK_TARGET_URL).mock(
        side_effect=httpx.TimeoutException(simulated_timeout_message, request=dummy_request_for_exception)
    )
    print(f"  Mock respx: Rota POST para '{TEST_WEBHOOK_TARGET_URL}' mockada para levantar httpx.TimeoutException.")
    
    mock_utils_logger = mocker.patch("app.core.utils.logger")
    print("  Mock: app.core.utils.logger.")

    # Act: Chamar a função.
    print("  Atuando: Chamando send_webhook_notification (esperando timeout)...")
    await send_webhook_notification(TEST_EVENT_TYPE_WEBHOOK, TEST_TASK_DATA_FOR_WEBHOOK)

    # Assert: Verificar se logger.error foi chamado com a mensagem correta.
    mock_utils_logger.error.assert_called_once()
    error_log_args, _ = mock_utils_logger.error.call_args
    error_log_message = error_log_args[0] 
    print(f"  Log de erro capturado: {error_log_message}")

    assert "Timeout ao enviar webhook para" in error_log_message, \
        "Mensagem de log para TimeoutException não encontrada ou incorreta."
    assert TEST_WEBHOOK_TARGET_URL in error_log_message, \
        "URL não encontrada na mensagem de log de timeout."
    # A mensagem da TimeoutException original (simulated_timeout_message) NÃO é incluída
    # na f-string do logger.error, então não precisamos verificá-la lá.

    print("  Sucesso: httpx.TimeoutException tratado e logado corretamente.")