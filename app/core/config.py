# app/core/config.py
import os
from pydantic_settings import BaseSettings
from pydantic import EmailStr, Field, RedisDsn, model_validator, HttpUrl
from typing import Optional
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

# --- Carrega variáveis do .env ---
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
loaded = load_dotenv(dotenv_path=dotenv_path)

class Settings(BaseSettings):
    """
    Configurações da aplicação lidas do ambiente.
    Docs Pydantic Settings: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
    """
    PROJECT_NAME: str = Field("SmartTask API", description="Nome do Projeto")
    API_V1_STR: str = Field("/api/v1", description="Prefixo para a versão 1 da API")

    # --- Configurações MongoDB ---
    MONGODB_URL: str = Field(..., env="MONGODB_URL", description="URL de conexão do MongoDB")
    DATABASE_NAME: str = Field("smarttask_db", description="Nome do banco de dados MongoDB")

     # --- Configurações JWT ---
    JWT_SECRET_KEY: str = Field(..., env="JWT_SECRET_KEY", description="Chave secreta para assinar tokens JWT")
    JWT_ALGORITHM: str = Field("HS256", env="JWT_ALGORITHM", description="Algoritmo de assinatura JWT")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(60 * 24 * 7, env="ACCESS_TOKEN_EXPIRE_MINUTES", description="Validade do token de acesso (minutos)") # Ex: 7 dias

    # --- Configurações de Prioridade ---
    PRIORITY_WEIGHT_DUE_DATE: float = Field(
        100.0, 
        env="PRIORITY_WEIGHT_DUE_DATE",
        description="Peso para o componente de prazo no cálculo de prioridade."
    )
    PRIORITY_WEIGHT_IMPORTANCE: float = Field(
        10.0, 
        env="PRIORITY_WEIGHT_IMPORTANCE",
        description="Peso (multiplicador) para o componente de importância no cálculo de prioridade."
    )
    PRIORITY_DEFAULT_SCORE_NO_DUE_DATE: Optional[float] = Field(
        0.0, 
        env="PRIORITY_DEFAULT_SCORE_NO_DUE_DATE",
        description="Pontuação base de prazo para tarefas sem data de vencimento (pode ser None ou 0)."
    )
    PRIORITY_SCORE_IF_OVERDUE: float = Field(
        1000.0, 
        env="PRIORITY_SCORE_IF_OVERDUE",
        description="Pontuação (ou fator aditivo/multiplicativo) especial para tarefas atrasadas."
    )

    # --- Configuração Webhook ---
    WEBHOOK_URL: Optional[HttpUrl] = Field(
        None,
        env="WEBHOOK_URL",
        description="URL opcional para enviar notificações de eventos de tarefas (webhooks)."
    )
    # Segredo para assinar requests de webhook (HMAC)
    WEBHOOK_SECRET: Optional[str] = Field(
        None,
        env="WEBHOOK_SECRET",
        description="Segredo opcional usado para assinar payloads de webhook para verificação."
    )

    # --- Configurações de E-mail ---
    MAIL_ENABLED: bool = Field(
            default=True,
            env="MAIL_ENABLED",
            description="Flag para habilitar/desabilitar envio de e-mails globalmente."
        )
    MAIL_USERNAME: Optional[str] = Field(None, env="MAIL_USERNAME", description="Usuário do servidor SMTP.")
    MAIL_PASSWORD: Optional[str] = Field(None, env="MAIL_PASSWORD", description="Senha do servidor SMTP.")
    MAIL_FROM: Optional[EmailStr] = Field(
        None,
        env="MAIL_FROM",
        description="Endereço de e-mail remetente."
        )
    MAIL_FROM_NAME: Optional[str] = Field(
        "SmartTask Notificações", 
        env="MAIL_FROM_NAME",
        description="Nome do remetente exibido no e-mail."
        )
    MAIL_PORT: int = Field(
        587,
        env="MAIL_PORT",
        description="Porta do servidor SMTP."
        )
    MAIL_SERVER: Optional[str] = Field(
        None,
        env="MAIL_SERVER",
        description="Endereço do servidor SMTP."
        )
    # Configurações para fastapi-mail
    MAIL_STARTTLS: bool = Field(True, env="MAIL_STARTTLS") 
    MAIL_SSL_TLS: bool = Field(False, env="MAIL_SSL_TLS") 
    USE_CREDENTIALS: bool = Field(True, env="USE_CREDENTIALS")
    VALIDATE_CERTS: bool = Field(True, env="VALIDATE_CERTS") 

    # --- Configurações Adicionais (Templates, Limiar) ---
    EMAIL_TEMPLATES_DIR: str = Field("app/email-templates/build", description="Diretório de templates de e-mail compilados.") # Definiremos isso
    EMAIL_URGENCY_THRESHOLD: float = Field(
        100.0, 
        env="EMAIL_URGENCY_THRESHOLD",
        description="Limiar de priority_score para considerar uma tarefa urgente para notificação."
        )
    FRONTEND_URL: Optional[str] = Field(None, env="FRONTEND_URL", description="URL base do frontend para links no e-mail (se houver).") # Ex: http://localhost:3000

     # --- Configuração Redis ---
    REDIS_URL: Optional[RedisDsn] = Field(
        None, 
        env="REDIS_URL",
        description="URL de conexão do Redis para filas de tarefas (ARQ)."
    )

    # --- Configurações CORS ---

    # --- Configuração Pydantic (case-insensitive)---
    model_config = {
        "case_sensitive": False,
    }

# --- Validação ---
    @model_validator(mode='after')
    def check_mail_config(self) -> 'Settings':
        if self.MAIL_ENABLED and not all([self.MAIL_USERNAME, self.MAIL_PASSWORD, self.MAIL_FROM, self.MAIL_SERVER]):
            raise ValueError(
                "Se MAIL_ENABLED for True, MAIL_USERNAME, MAIL_PASSWORD, MAIL_FROM e MAIL_SERVER devem ser definidos."
            )
        return self

# --- Cria a instância ---
try:
    settings = Settings()
except ValueError as e:
     raise e 
# Validação extra da instância
if settings.WEBHOOK_URL and not isinstance(settings.WEBHOOK_URL, HttpUrl):
     logger.warning(f"WEBHOOK_URL '{settings.WEBHOOK_URL}' não parece ser uma URL válida.")
