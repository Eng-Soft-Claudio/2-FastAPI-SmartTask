# tests/test_core_config.py
import pytest
import os
from pydantic import ValidationError
import importlib
from app.core.config import Settings

# =====================================================
#  --- Teste Principal ---
# =====================================================

def test_settings_mail_enabled_missing_credentials(monkeypatch):
    """Testa se a validação falha quando MAIL_ENABLED=True e faltam credenciais."""
    # 1. Limpar variáveis de email pré-existentes
    monkeypatch.delenv("MAIL_ENABLED", raising=False)
    monkeypatch.delenv("MAIL_USERNAME", raising=False)
    monkeypatch.delenv("MAIL_PASSWORD", raising=False)
    monkeypatch.delenv("MAIL_FROM", raising=False)
    monkeypatch.delenv("MAIL_SERVER", raising=False)

    # 2. Definir variáveis obrigatórias não relacionadas a email
    monkeypatch.setenv("JWT_SECRET_KEY", "testsecret")
    monkeypatch.setenv("MONGODB_URL", "mongodb://test")

    # 3. Definir cenário: MAIL_ENABLED=True, mas falta USERNAME
    monkeypatch.setenv("MAIL_ENABLED", "True")
    # NÃO define MAIL_USERNAME
    monkeypatch.setenv("MAIL_PASSWORD", "password")
    monkeypatch.setenv("MAIL_FROM", "sender@example.com")
    monkeypatch.setenv("MAIL_SERVER", "smtp.test.com")

    # 4. Instanciar Settings e verificar a exceção
    with pytest.raises((ValueError, ValidationError)) as exc_info:
        Settings(_env_file=None)

    assert "MAIL_USERNAME, MAIL_PASSWORD, MAIL_FROM e MAIL_SERVER devem ser definidos" in str(exc_info.value)

def test_settings_mail_disabled_credentials_not_needed(monkeypatch):
    """Testa se a validação PASSA quando MAIL_ENABLED=False, mesmo sem credenciais."""
    # 1. Limpar variáveis de email
    monkeypatch.delenv("MAIL_ENABLED", raising=False)
    monkeypatch.delenv("MAIL_USERNAME", raising=False)
    monkeypatch.delenv("MAIL_PASSWORD", raising=False)
    monkeypatch.delenv("MAIL_FROM", raising=False)
    monkeypatch.delenv("MAIL_SERVER", raising=False)

    # 2. Definir variáveis obrigatórias não relacionadas a email
    monkeypatch.setenv("JWT_SECRET_KEY", "testsecret")
    monkeypatch.setenv("MONGODB_URL", "mongodb://test")
    # Defina outras se necessário

    # 3. Definir cenário: MAIL_ENABLED=False, outras ausentes
    monkeypatch.setenv("MAIL_ENABLED", "False")

    # 4. Instanciar Settings e verificar se NÃO levanta exceção
    try:
        settings_instance = Settings(_env_file=None)
        assert not settings_instance.MAIL_ENABLED
        # Verifica se os outros campos são None como esperado
        assert settings_instance.MAIL_USERNAME is None
        assert settings_instance.MAIL_PASSWORD is None
        assert settings_instance.MAIL_FROM is None
        assert settings_instance.MAIL_SERVER is None
    except (ValueError, ValidationError) as e:
        pytest.fail(f"Validação de Settings falhou inesperadamente com MAIL_ENABLED=False: {e}")

# =====================================================
#  --- Teste Secundário ---
# =====================================================

def test_settings_mail_enabled_all_credentials_ok(monkeypatch):
    """Testa se a validação PASSA quando MAIL_ENABLED=True e TUDO está definido."""
    # 1. Limpar
    monkeypatch.delenv("MAIL_ENABLED", raising=False)
    monkeypatch.delenv("MAIL_USERNAME", raising=False)
    monkeypatch.delenv("MAIL_PASSWORD", raising=False)
    monkeypatch.delenv("MAIL_FROM", raising=False)
    monkeypatch.delenv("MAIL_SERVER", raising=False)

    # 2. Definir obrigatórias
    monkeypatch.setenv("JWT_SECRET_KEY", "testsecret")
    monkeypatch.setenv("MONGODB_URL", "mongodb://test")

    # 3. Definir tudo para email
    monkeypatch.setenv("MAIL_ENABLED", "True")
    monkeypatch.setenv("MAIL_USERNAME", "testuser")
    monkeypatch.setenv("MAIL_PASSWORD", "testpass")
    monkeypatch.setenv("MAIL_FROM", "test@example.com")
    monkeypatch.setenv("MAIL_SERVER", "mail.example.com")

    # 4. Verificar se NÃO levanta exceção
    try:
        settings_instance = Settings(_env_file=None)
        assert settings_instance.MAIL_ENABLED
        assert settings_instance.MAIL_USERNAME == "testuser"
    except (ValueError, ValidationError) as e:
        pytest.fail(f"Validação de Settings falhou inesperadamente com todas as credenciais: {e}")