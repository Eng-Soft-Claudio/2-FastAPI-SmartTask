# app/db/mongodb_utils.py
from typing import Optional
import motor.motor_asyncio
from app.core.config import settings 
import logging
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

# Variáveis globais para o cliente e banco de dados
db_client: motor.motor_asyncio.AsyncIOMotorClient | None = None
db_instance: motor.motor_asyncio.AsyncIOMotorDatabase | None = None

async def connect_to_mongo() -> Optional[AsyncIOMotorDatabase]:
    """
    Conecta-se ao MongoDB na inicialização da aplicação.
    """
    global db_client, db_instance

    try:

        db_client = motor.motor_asyncio.AsyncIOMotorClient(
            settings.MONGODB_URL,
            serverSelectionTimeoutMS=5000 
        )
        await db_client.admin.command('ping')

        db_instance = db_client[settings.DATABASE_NAME]

        return db_instance
    
    except Exception as e:
        logger.error(f"Não foi possível conectar ao MongoDB: {e}")
        db_client = None
        db_instance = None
        return None

async def close_mongo_connection():
    """
    Fecha a conexão com o MongoDB no encerramento da aplicação.
    """
    global db_client
    if db_client:
        db_client.close()
    else:
        logger.warning("Tentativa de fechar conexão com MongoDB, mas cliente não estava inicializado.")

def get_database() -> motor.motor_asyncio.AsyncIOMotorDatabase:
    """
    Retorna a instância do banco de dados MongoDB.
    Pode ser usada como uma dependência FastAPI ou chamada diretamente.
    """
    if db_instance is None:
        logger.error("Tentativa de obter instância do DB antes da inicialização!")
        raise RuntimeError("A conexão com o banco de dados não foi inicializada.")
    return db_instance
