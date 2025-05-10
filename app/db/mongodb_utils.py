# app/db/mongodb_utils.py
"""
Este módulo gerencia a conexão com o banco de dados MongoDB.
Inclui funções para conectar, fechar a conexão e obter a instância do banco de dados.
Utiliza a biblioteca Motor para interações assíncronas com o MongoDB.
"""

# ========================
# --- Importações ---
# ========================
import logging
from typing import Optional
import motor.motor_asyncio
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase 

# --- Módulos da Aplicação ---
from app.core.config import settings

# ========================
# --- Configuração do Logger ---
# ========================
logger = logging.getLogger(__name__)

# ========================
# --- Variáveis Globais de Conexão ---
# ========================
# Estas variáveis mantêm o estado da conexão MongoDB para a aplicação.
db_client: Optional[AsyncIOMotorClient] = None
db_instance: Optional[AsyncIOMotorDatabase] = None

# ========================
# --- Função de Conexão ---
# ========================
async def connect_to_mongo() -> Optional[AsyncIOMotorDatabase]:
    """
    Estabelece a conexão com o MongoDB.

    Cria um cliente AsyncIOMotorClient, verifica a conexão com um comando 'ping',
    e define as variáveis globais `db_client` e `db_instance`.

    Returns:
        A instância AsyncIOMotorDatabase se a conexão for bem-sucedida, None caso contrário.
    """
    global db_client, db_instance
    logger.info("Tentando conectar ao MongoDB...")
    try:
        db_client = motor.motor_asyncio.AsyncIOMotorClient(
            settings.MONGODB_URL,
            serverSelectionTimeoutMS=5000 # Timeout para seleção do servidor
        )
        # Verifica a conexão
        await db_client.admin.command('ping')
        logger.info("Comando ping para MongoDB bem-sucedido.")

        db_instance = db_client[settings.DATABASE_NAME]
        logger.info(f"Conectado com sucesso ao banco de dados: {settings.DATABASE_NAME}")
        return db_instance

    except Exception as e:
        logger.error(f"Não foi possível conectar ao MongoDB: {e}", exc_info=True)
        db_client = None
        db_instance = None
        return None

# ========================
# --- Função de Fechamento de Conexão ---
# ========================
async def close_mongo_connection():
    """
    Fecha a conexão com o MongoDB.
    Verifica se o cliente `db_client` foi inicializado antes de tentar fechar.
    """
    global db_client # Indica que estamos referenciando a variável global
    logger.info("Tentando fechar conexão com MongoDB...")
    if db_client:
        db_client.close()
        logger.info("Conexão com MongoDB fechada.")
        # Opcionalmente, resetar db_client e db_instance para None após fechar:
        # db_client = None
        # db_instance = None
    else:
        logger.warning("Tentativa de fechar conexão com MongoDB, mas cliente não estava inicializado.")

# ========================
# --- Função de Acesso ao DB ---
# ========================
def get_database() -> AsyncIOMotorDatabase:
    """
    Retorna a instância global do banco de dados MongoDB.

    Usada como dependência FastAPI ou chamada por outras partes da aplicação.

    Raises:
        RuntimeError: Se chamada antes de `connect_to_mongo` inicializar `db_instance`.

    Returns:
        A instância AsyncIOMotorDatabase.
    """
    if db_instance is None:
        # Este log de erro é importante para diagnóstico
        logger.error("Tentativa de obter instância do DB antes da inicialização!")
        raise RuntimeError("A conexão com o banco de dados não foi inicializada.")
    return db_instance

# ========================
# --- Função de Acesso ao DB ---
# ========================
async def check_mongo_connection():
    """
    Verifica a conectividade com o banco de dados MongoDB.

    Tenta realizar uma operação simples de "ping" no MongoDB para garantir que
    a conexão com o banco de dados está ativa e funcionando corretamente.

    Retorna:
        bool: Retorna True se a conexão com o MongoDB for bem-sucedida, 
              caso contrário, retorna False.

    Exceções:
        Caso ocorra algum erro na conexão ou no comando, retorna False.
    """
    try:
        # Tente uma consulta simples ao MongoDB
        db = await connect_to_mongo()
        await db.command("ping")
        return True
    except Exception as e:
        return False