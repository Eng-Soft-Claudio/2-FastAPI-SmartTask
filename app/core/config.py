# app/core/config.py

# ========================
# --- Importações ---
# ========================
import os
import logging
from typing import Optional, List 
from pydantic_settings import BaseSettings
from pydantic import EmailStr, Field, RedisDsn, ValidationError, model_validator, HttpUrl
from dotenv import load_dotenv

# ===============================
# --- Configuração do Logger ---
# ===============================
logger = logging.getLogger(__name__)

# ===============================
# --- Carregamento do .env ---
# ===============================
# Define o caminho para o arquivo .env na raiz do projeto
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
# Carrega as variáveis do arquivo .env para o ambiente, se o arquivo existir
loaded = load_dotenv(dotenv_path=dotenv_path)

# ======================================
# --- Definição das Configurações ---
# ======================================
class Settings(BaseSettings):
    """
    Configurações da aplicação lidas do ambiente usando Pydantic BaseSettings.
    Procura variáveis de ambiente ou variáveis em um arquivo .env.
    Docs Pydantic Settings: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
    """
    # =========================
    # --- Config Gerais ---
    # =========================
    PROJECT_NAME: str = Field("SmartTask API", description="Nome do Projeto")
    API_V1_STR: str = Field("/api/v1", description="Prefixo para a versão 1 da API")

    # =============================
    # --- Configurações MongoDB ---
    # =============================
    MONGODB_URL: str = Field(..., description="URL de conexão completa do MongoDB (obrigatória)")
    DATABASE_NAME: str = Field("smarttask_db", description="Nome do banco de dados MongoDB")

    # ===========================
    # --- Configurações JWT ---
    # ===========================
    JWT_SECRET_KEY: str = Field(..., description="Chave secreta forte para assinar tokens JWT (obrigatória)")
    JWT_ALGORITHM: str = Field("HS256", description="Algoritmo de assinatura JWT")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(60 * 24 * 7, description="Validade do token de acesso em minutos (padrão: 7 dias)")

    # =======================================
    # --- Configurações de Prioridade ---
    # =======================================
    PRIORITY_WEIGHT_DUE_DATE: float = Field(
        100.0,
        description="Peso para o componente de prazo no cálculo de prioridade."
    )
    PRIORITY_WEIGHT_IMPORTANCE: float = Field(
        10.0,
        description="Peso (multiplicador) para o componente de importância no cálculo de prioridade."
    )
    PRIORITY_DEFAULT_SCORE_NO_DUE_DATE: Optional[float] = Field(
        0.0,
        description="Pontuação base de prazo para tarefas sem data de vencimento (pode ser None ou 0.0)."
    )
    PRIORITY_SCORE_IF_OVERDUE: float = Field(
        1000.0,
        description="Pontuação (ou fator aditivo/multiplicativo) especial para tarefas atrasadas."
    )

    # ==============================
    # --- Configuração Webhook ---
    # ==============================
    WEBHOOK_URL: Optional[HttpUrl] = Field(
        default=None,
        description="URL opcional para enviar notificações de eventos de tarefas (webhooks)."
    )
    WEBHOOK_SECRET: Optional[str] = Field(
        default=None,
        description="Segredo opcional usado para assinar payloads de webhook para verificação (HMAC-SHA256)."
    )

    # ================================
    # --- Configurações de E-mail ---
    # ================================
    MAIL_ENABLED: bool = Field(
            default=False, 
            description="Flag para habilitar/desabilitar envio de e-mails globalmente."
    )
    MAIL_USERNAME: Optional[str] = Field(default=None, description="Usuário do servidor SMTP.")
    MAIL_PASSWORD: Optional[str] = Field(default=None, description="Senha do servidor SMTP.")
    MAIL_FROM: Optional[EmailStr] = Field(
        default=None,
        description="Endereço de e-mail remetente."
    )
    MAIL_FROM_NAME: Optional[str] = Field(
        default="SmartTask Notificações",
        description="Nome do remetente exibido no e-mail."
    )
    MAIL_PORT: int = Field(
        default=587,
        description="Porta do servidor SMTP."
    )
    MAIL_SERVER: Optional[str] = Field(
        default=None,
        description="Endereço do servidor SMTP."
    )
    MAIL_STARTTLS: bool = Field(default=True, description="Usar STARTTLS para conexão SMTP.")
    MAIL_SSL_TLS: bool = Field(default=False, description="Usar SSL/TLS direto para conexão SMTP.")
    USE_CREDENTIALS: bool = Field(default=True, description="Usar credenciais (username/password) para SMTP.")
    VALIDATE_CERTS: bool = Field(default=True, description="Validar certificados SSL/TLS do servidor SMTP.")

    # ==============================================
    # --- Configurações Adicionais Específicas ---
    # ==============================================
    EMAIL_TEMPLATES_DIR: str = Field(default="app/email-templates/build", description="Diretório de templates de e-mail compilados.")
    EMAIL_URGENCY_THRESHOLD: float = Field(
        default=100.0,
        description="Limiar de priority_score para considerar uma tarefa urgente para notificação por e-mail."
    )
    FRONTEND_URL: Optional[str] = Field(default=None, description="URL base do frontend para links no e-mail (se houver).")

    # ==============================
    # --- Configuração Redis ---
    # ==============================
    REDIS_URL: Optional[RedisDsn] = Field(
        default=None,
        description="URL de conexão do Redis para filas de tarefas (ARQ)."
    )

    # ===============================
    # --- Configuração de Logging ---
    # ===============================
    LOG_LEVEL: str = Field(default="INFO", description="Nível de log (DEBUG, INFO, WARNING, ERROR, CRITICAL)")

    # ===================================
    # --- Configurações CORS ---
    # ===================================
    # A conversão de string separada por vírgula para List[str] é feita automaticamente pelo Pydantic v2
    CORS_ALLOWED_ORIGINS: List[str] = Field(default=[], description="Lista de origens CORS permitidas (separadas por vírgula no .env)")


    # ====================================================
    # --- Configuração do Modelo Pydantic BaseSettings ---
    # ====================================================
    model_config = {
        "case_sensitive": False, 
    }

    # ===============================
    # --- Validadores ---
    # ===============================
    @model_validator(mode='after')
    def check_mail_config(self) -> 'Settings':
        """Valida se as credenciais de e-mail estão presentes quando habilitado."""
        if self.MAIL_ENABLED and not all([self.MAIL_USERNAME, self.MAIL_PASSWORD, self.MAIL_FROM, self.MAIL_SERVER]):
            raise ValueError(
                "Se MAIL_ENABLED for True, MAIL_USERNAME, MAIL_PASSWORD, MAIL_FROM e MAIL_SERVER devem ser definidos."
            )
        return self

    @model_validator(mode='after')
    def check_webhook_config(self) -> 'Settings':
        """Valida a configuração do webhook se URL for fornecida."""
        # Este validador já estava implícito na linha final do arquivo original.
        # Vamos torná-lo explícito.
        if self.WEBHOOK_URL and not isinstance(self.WEBHOOK_URL, HttpUrl):
             # Pydantic já deve ter validado HttpUrl, mas como dupla checagem.
             # Usar warning em vez de raise para não impedir start da app por URL inválida.
             logger.warning(f"WEBHOOK_URL '{self.WEBHOOK_URL}' não parece ser uma URL válida.")
             # Opcionalmente, poderia limpar a URL:
             # self.WEBHOOK_URL = None
        return self

# ================================
# --- Criação da Instância ---
# ================================
try:
    # Pydantic BaseSettings lê do ambiente ou .env na instanciação
    settings = Settings()
except ValidationError as e:
    # Captura erros de validação do Pydantic (campos obrigatórios faltando, tipos inválidos)
    logger.critical(f"Erro fatal de validação ao carregar configurações: {e}")
    raise e
except ValueError as e:
     # Captura erros do nosso validador customizado
    logger.critical(f"Erro fatal de validação na configuração (check_mail_config?): {e}")
    raise e
except Exception as e:
     # Captura outros erros inesperados
    logger.critical(f"Erro inesperado ao carregar configurações: {e}", exc_info=True)
    raise e