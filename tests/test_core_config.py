# tests/test_core_config.py
"""
Este módulo contém testes para a classe de configurações da aplicação (`app.core.config.Settings`).
O foco principal é validar a lógica condicional relacionada às configurações de e-mail,
garantindo que as credenciais de e-mail sejam obrigatórias apenas quando
a funcionalidade de e-mail está explicitamente habilitada (`MAIL_ENABLED=True`).
"""

# ========================
# --- Importações ---
# ========================
from logging import config
import os 
from unittest.mock import patch 
import pytest
from pydantic import ValidationError
import importlib

# --- Módulo da Aplicação ---
from app.core.config import Settings
import app.core.config as config_module

# ================================================
# --- Testes de Validação de Configurações de E-mail ---
# ================================================

def test_settings_mail_enabled_and_missing_credentials_fails_validation(monkeypatch):
    """
    Testa se a instanciação de `Settings` falha com `ValidationError` (ou `ValueError`)
    quando `MAIL_ENABLED` é True, mas uma ou mais credenciais de e-mail
    (MAIL_USERNAME, MAIL_PASSWORD, MAIL_FROM, MAIL_SERVER) estão ausentes.

    Cenário: MAIL_ENABLED=True, MAIL_USERNAME não definido.
    """
    print("\nTeste: MAIL_ENABLED=True e falta MAIL_USERNAME -> Deve falhar a validação.")

    # --- Arrange: Configurar variáveis de ambiente ---
    # 1. Limpar quaisquer variáveis de ambiente de e-mail preexistentes para isolamento do teste.
    print("  Limpando variáveis de ambiente de e-mail...")
    monkeypatch.delenv("MAIL_ENABLED", raising=False)
    monkeypatch.delenv("MAIL_USERNAME", raising=False)
    monkeypatch.delenv("MAIL_PASSWORD", raising=False)
    monkeypatch.delenv("MAIL_FROM", raising=False)
    monkeypatch.delenv("MAIL_PORT", raising=False) 
    monkeypatch.delenv("MAIL_SERVER", raising=False)
    monkeypatch.delenv("MAIL_TLS", raising=False) 
    monkeypatch.delenv("MAIL_SSL", raising=False) 
    # Adicione outras variáveis de e-mail que seu Settings possa ter.

    # 2. Definir variáveis de ambiente obrigatórias não relacionadas a e-mail.
    #    (ex: JWT_SECRET_KEY, MONGODB_URL) para que Settings possa ser instanciado.
    print("  Definindo variáveis de ambiente obrigatórias (não-email)...")
    monkeypatch.setenv("PROJECT_NAME", "Test Project")
    monkeypatch.setenv("API_V1_STR", "/api/v1")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("JWT_SECRET_KEY", "test_jwt_secret_key_for_config_test")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
    monkeypatch.setenv("REFRESH_TOKEN_EXPIRE_DAYS", "7") 
    monkeypatch.setenv("MONGODB_URL", "mongodb://localhost:27017/test_config_db")
    monkeypatch.setenv("DATABASE_NAME", "test_config_db")
    # Adicione quaisquer outras variáveis que `Settings` sempre espera.

    # 3. Definir o cenário de teste específico: E-mail habilitado, mas falta MAIL_USERNAME.
    print("  Definindo cenário de teste: MAIL_ENABLED=True, MAIL_USERNAME ausente.")
    monkeypatch.setenv("MAIL_ENABLED", "True")
    # monkeypatch.setenv("MAIL_USERNAME", "user") # MAIL_USERNAME é omitido intencionalmente
    monkeypatch.setenv("MAIL_PASSWORD", "secretpassword")
    monkeypatch.setenv("MAIL_FROM", "tests@example.com")
    monkeypatch.setenv("MAIL_SERVER", "smtp.example.com")
    monkeypatch.setenv("MAIL_PORT", "587")
    monkeypatch.setenv("MAIL_TLS", "True")


    # --- Act & Assert: Tentar instanciar Settings e verificar a exceção ---
    # Pydantic v2 levanta ValidationError. ValueError pode ser de validadores customizados.
    print("  Tentando instanciar Settings, esperando exceção...")
    with pytest.raises((ValueError, ValidationError)) as exc_info:
        # `_env_file=None` garante que Pydantic não tente carregar um arquivo .env real.
        Settings(_env_file=None) 

    # Verifica se a mensagem de erro da exceção contém o texto esperado.
    expected_error_message_part = "MAIL_USERNAME, MAIL_PASSWORD, MAIL_FROM e MAIL_SERVER devem ser definidos"
    print(f"  Exceção recebida: {exc_info.value}")
    assert expected_error_message_part in str(exc_info.value), \
        f"A mensagem de erro não contém '{expected_error_message_part}'. Erro: {str(exc_info.value)}"
    print("  Validação falhou como esperado.")

def test_settings_mail_disabled_and_credentials_not_needed_passes_validation(monkeypatch):
    """
    Testa se a instanciação de `Settings` é bem-sucedida quando `MAIL_ENABLED`
    é False, mesmo que as credenciais de e-mail estejam ausentes.

    Neste cenário, os campos de credenciais de e-mail devem ser opcionais
    e podem ser None.
    """
    print("\nTeste: MAIL_ENABLED=False, credenciais ausentes -> Deve passar a validação.")

    # --- Arrange: Configurar variáveis de ambiente ---
    # 1. Limpar variáveis de e-mail.
    print("  Limpando variáveis de ambiente de e-mail...")
    monkeypatch.delenv("MAIL_ENABLED", raising=False)
    monkeypatch.delenv("MAIL_USERNAME", raising=False)
    monkeypatch.delenv("MAIL_PASSWORD", raising=False)
    monkeypatch.delenv("MAIL_FROM", raising=False)
    monkeypatch.delenv("MAIL_PORT", raising=False)
    monkeypatch.delenv("MAIL_SERVER", raising=False)
    monkeypatch.delenv("MAIL_TLS", raising=False)
    monkeypatch.delenv("MAIL_SSL", raising=False)

    # 2. Definir variáveis obrigatórias não relacionadas a e-mail.
    print("  Definindo variáveis de ambiente obrigatórias (não-email)...")
    monkeypatch.setenv("PROJECT_NAME", "Test Project Disabled Mail")
    monkeypatch.setenv("API_V1_STR", "/api/v1")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("JWT_SECRET_KEY", "test_jwt_secret_for_disabled_mail")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
    monkeypatch.setenv("REFRESH_TOKEN_EXPIRE_DAYS", "14")
    monkeypatch.setenv("MONGODB_URL", "mongodb://localhost:27017/test_disabled_mail_db")
    monkeypatch.setenv("DATABASE_NAME", "test_disabled_mail_db")


    # 3. Definir o cenário: MAIL_ENABLED=False, outras credenciais de e-mail ausentes.
    print("  Definindo cenário de teste: MAIL_ENABLED=False.")
    monkeypatch.setenv("MAIL_ENABLED", "False")

    # --- Act & Assert: Tentar instanciar Settings e verificar se NÃO levanta exceção ---
    print("  Tentando instanciar Settings, esperando sucesso...")
    try:
        
        settings_instance = Settings(_env_file=None) 
        
        print(f"  Settings instanciado com sucesso: MAIL_ENABLED={settings_instance.MAIL_ENABLED}")
        assert not settings_instance.MAIL_ENABLED, "MAIL_ENABLED deveria ser False."
        assert settings_instance.MAIL_USERNAME is None, "MAIL_USERNAME deveria ser None."
        assert settings_instance.MAIL_PASSWORD is None, "MAIL_PASSWORD deveria ser None."
        assert settings_instance.MAIL_FROM is None, "MAIL_FROM deveria ser None."
        assert settings_instance.MAIL_SERVER is None, "MAIL_SERVER deveria ser None."
        assert settings_instance.MAIL_PORT == 587, "MAIL_PORT deveria ter seu valor default (e.g., 587)." 

    except (ValueError, ValidationError) as e:
        pytest.fail(
            f"A validação de Settings falhou inesperadamente quando MAIL_ENABLED=False. Erro: {e}\n"
            f"Variáveis de ambiente configuradas: {dict(os.environ)}"
        )
    print("  Validação passou como esperado com MAIL_ENABLED=False.")

def test_settings_mail_enabled_and_all_credentials_provided_passes_validation(monkeypatch):
    """
    Testa se a instanciação de `Settings` é bem-sucedida quando `MAIL_ENABLED`
    é True e TODAS as credenciais de e-mail necessárias estão definidas.
    """
    print("\nTeste: MAIL_ENABLED=True e todas credenciais de e-mail fornecidas -> Deve passar a validação.")

    # --- Arrange: Configurar variáveis de ambiente ---
    # 1. Limpar variáveis de e-mail.
    print("  Limpando variáveis de ambiente de e-mail...")
    monkeypatch.delenv("MAIL_ENABLED", raising=False)
    monkeypatch.delenv("MAIL_USERNAME", raising=False)
    monkeypatch.delenv("MAIL_PASSWORD", raising=False)
    monkeypatch.delenv("MAIL_FROM", raising=False)
    monkeypatch.delenv("MAIL_PORT", raising=False)
    monkeypatch.delenv("MAIL_SERVER", raising=False)
    monkeypatch.delenv("MAIL_TLS", raising=False)
    monkeypatch.delenv("MAIL_SSL", raising=False)

    # 2. Definir variáveis obrigatórias não relacionadas a e-mail.
    print("  Definindo variáveis de ambiente obrigatórias (não-email)...")
    monkeypatch.setenv("PROJECT_NAME", "Test Project All Mail")
    monkeypatch.setenv("API_V1_STR", "/api/v1")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("JWT_SECRET_KEY", "test_jwt_secret_for_all_mail")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
    monkeypatch.setenv("REFRESH_TOKEN_EXPIRE_DAYS", "3")
    monkeypatch.setenv("MONGODB_URL", "mongodb://localhost:27017/test_all_mail_db")
    monkeypatch.setenv("DATABASE_NAME", "test_all_mail_db")


    # 3. Definir o cenário: MAIL_ENABLED=True e todas as credenciais de e-mail fornecidas.
    print("  Definindo cenário de teste: MAIL_ENABLED=True e todas credenciais de e-mail presentes.")
    monkeypatch.setenv("MAIL_ENABLED", "True")
    monkeypatch.setenv("MAIL_USERNAME", "test_mailer_user")
    monkeypatch.setenv("MAIL_PASSWORD", "supersecretmailerpassword")
    monkeypatch.setenv("MAIL_FROM", "noreply_tests@example.com")
    monkeypatch.setenv("MAIL_SERVER", "smtp.mailservice.example.com")
    monkeypatch.setenv("MAIL_PORT", "465") # Exemplo para SSL
    monkeypatch.setenv("MAIL_SSL", "True") # Exemplo com SSL
    monkeypatch.setenv("MAIL_TLS", "False")# Exemplo com SSL


    # --- Act & Assert: Tentar instanciar Settings e verificar se NÃO levanta exceção ---
    print("  Tentando instanciar Settings, esperando sucesso...")
    try:
        settings_instance = Settings(_env_file=None)

        print(f"  Settings instanciado com sucesso: MAIL_ENABLED={settings_instance.MAIL_ENABLED}, MAIL_USERNAME='{settings_instance.MAIL_USERNAME}'")
        assert settings_instance.MAIL_ENABLED, "MAIL_ENABLED deveria ser True."
        assert settings_instance.MAIL_USERNAME == "test_mailer_user", "MAIL_USERNAME não corresponde."
        assert settings_instance.MAIL_PASSWORD == "supersecretmailerpassword"
        assert settings_instance.MAIL_FROM == "noreply_tests@example.com"
        assert settings_instance.MAIL_SERVER == "smtp.mailservice.example.com"
        assert settings_instance.MAIL_PORT == 465

    except (ValueError, ValidationError) as e:
        pytest.fail(
            "A validação de Settings falhou inesperadamente quando MAIL_ENABLED=True e todas as credenciais "
            f"de e-mail foram fornecidas. Erro: {e}\n"
            f"Variáveis de ambiente configuradas: {dict(os.environ)}"
        )
    print("  Validação passou como esperado com MAIL_ENABLED=True e todas credenciais de e-mail presentes.")

def test_settings_missing_required_pydantic_field_fails(monkeypatch):
    print("\nTeste: Campo Pydantic obrigatório ausente -> Deve falhar a validação.")
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False) # Ou MONGODB_URL
    # Certifique-se que MONGODB_URL está definido se você está testando a falta de JWT_SECRET_KEY, etc.
    monkeypatch.setenv("MONGODB_URL", "mongodb://localhost:27017/test_config_db")

    # Definir MAIL_ENABLED como False para que check_mail_config não interfira
    monkeypatch.setenv("MAIL_ENABLED", "False")

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    
    assert "JWT_SECRET_KEY" in str(exc_info.value).upper() or "FIELD REQUIRED" in str(exc_info.value).upper()
    print(f"  Pydantic ValidationError capturada como esperado: {exc_info.value}")