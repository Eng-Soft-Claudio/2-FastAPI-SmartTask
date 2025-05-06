# app/db/mongodb_utils.py

# ========================
# --- Importações ---
# ========================
import logging
from typing import Optional
import motor.motor_asyncio 
from motor.motor_asyncio import AsyncIOMotorDatabase 

# --- Módulos da Aplicação ---
from app.core.config import settings 

# ===============================
# --- Configuração do Logger ---
# ===============================
logger = logging.getLogger(__name__)

# ====================================
# --- Variáveis Globais de Conexão ---
# ====================================
# Armazenam a instância do cliente e do banco de dados para reutilização.
# Inicializadas como None e populadas por connect_to_mongo.
db_client: Optional[motor.motor_asyncio.AsyncIOMotorClient] = None
db_instance: Optional[AsyncIOMotorDatabase] = None

# ==============================
# --- Função de Conexão ---
# ==============================
async def connect_to_mongo() -> Optional[AsyncIOMotorDatabase]:
    """
    Estabelece a conexão com o MongoDB na inicialização da aplicação.

    - Cria um cliente AsyncIOMotorClient usando a MONGODB_URL das configurações.
    - Define um timeout para seleção do servidor.
    - Envia um comando 'ping' para verificar a conexão.
    - Define as variáveis globais `db_client` e `db_instance`.
    - Trata exceções de conexão e loga erros.

    Returns:
        A instância do banco de dados (AsyncIOMotorDatabase) se a conexão for bem-sucedida,
        ou None em caso de falha.
    """
    global db_client, db_instance
    logger.info("Tentando conectar ao MongoDB...")
    try:
        # Cria o cliente de conexão assíncrono
        db_client = motor.motor_asyncio.AsyncIOMotorClient(
            settings.MONGODB_URL,
            # Timeout para o servidor ser encontrado/eleito
            serverSelectionTimeoutMS=5000 
        )
        # Verifica a conexão enviando um comando ping
        await db_client.admin.command('ping')
        logger.info("Comando ping para MongoDB bem-sucedido.")

        # Obtém a instância do banco de dados especificado nas configurações
        db_instance = db_client[settings.DATABASE_NAME]
        logger.info(f"Conectado com sucesso ao banco de dados: {settings.DATABASE_NAME}")
        return db_instance

    except Exception as e:
        # Loga erro detalhado em caso de falha na conexão
        logger.error(f"Não foi possível conectar ao MongoDB: {e}", exc_info=True)
        # Garante que as variáveis globais sejam None em caso de falha
        db_client = None
        db_instance = None
        return None

# ==============================
# --- Função de Fechamento ---
# ==============================
async def close_mongo_connection():
    """
    Fecha a conexão com o MongoDB durante o encerramento da aplicação.

    Verifica se o cliente global `db_client` foi inicializado antes de tentar fechar.
    """
    global db_client
    logger.info("Tentando fechar conexão com MongoDB...")
    if db_client:
        db_client.close()
        logger.info("Conexão com MongoDB fechada.")
    else:
        logger.warning("Tentativa de fechar conexão com MongoDB, mas cliente não estava inicializado.")

# =============================
# --- Função de Acesso DB ---
# =============================
def get_database() -> AsyncIOMotorDatabase:
    """
    Retorna a instância global do banco de dados MongoDB.

    Função utilitária para ser usada como dependência FastAPI ou chamada
    diretamente por outras partes da aplicação que precisam acessar o DB.

    Raises:
        RuntimeError: Se a função for chamada antes de `connect_to_mongo`
                      ter inicializado `db_instance` com sucesso.

    Returns:
        A instância `AsyncIOMotorDatabase` global.
    """
    if db_instance is None:
        # Medida de segurança para evitar acesso antes da conexão
        logger.error("Tentativa de obter instância do DB antes da inicialização!")
        raise RuntimeError("A conexão com o banco de dados não foi inicializada.")
    return db_instance