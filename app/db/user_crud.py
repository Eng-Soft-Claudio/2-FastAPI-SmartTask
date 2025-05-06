# app/db/user_crud.py
import logging
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorCollection
from typing import Optional, List
import uuid
from datetime import datetime, timezone
from pymongo.errors import DuplicateKeyError
from app.models.user import UserCreate, UserInDB, UserUpdate
from app.core.security import get_password_hash
from motor.motor_asyncio import AsyncIOMotorDatabase

# Logger
logger = logging.getLogger(__name__)

# Nome da coleção de usuários
USERS_COLLECTION = "users"

# ==================================================
# --- Funções CRUD para Usuários ---
# ==================================================


async def get_user_by_id(db: AsyncIOMotorDatabase, user_id: uuid.UUID) -> Optional[UserInDB]:
    """Busca um usuário pelo seu ID (UUID)."""
    user_dict = await db[USERS_COLLECTION].find_one({"id": str(user_id)})
    if user_dict:
        user_dict.pop('_id', None) 
        try:
             return UserInDB.model_validate(user_dict)
        except Exception as e:
             logger.error(f"DB Validation error get_user_by_id {user_id}: {e}") 
             return None
    return None

async def get_user_by_username(db: AsyncIOMotorDatabase, username: str) -> Optional[UserInDB]:
    """Busca um usuário pelo seu nome de usuário."""
    # Index no 'username' é recomendado para performance
    user_dict = await db[USERS_COLLECTION].find_one({"username": username})
    if user_dict:
         user_dict.pop('_id', None)
         try:
            return UserInDB.model_validate(user_dict)
         except Exception as e:
            logger.error(f"DB Validation error get_user_by_username {username}: {e}")
            return None
    return None

async def get_user_by_email(db: AsyncIOMotorDatabase, email: str) -> Optional[UserInDB]:
    """Busca um usuário pelo seu e-mail."""
     # Index no 'email' é recomendado para performance e unicidade
    user_dict = await db[USERS_COLLECTION].find_one({"email": email})
    if user_dict:
        user_dict.pop('_id', None)
        try:
            return UserInDB.model_validate(user_dict)
        except Exception as e:
            logger.error(f"DB Validation error get_user_by_email {email}: {e}")
            return None
    return None

async def create_user(db: AsyncIOMotorDatabase, user_in: UserCreate) -> Optional[UserInDB]:
    """Cria um novo usuário no banco de dados."""
    hashed_password = get_password_hash(user_in.password)

    user_db_data = {
        "id": uuid.uuid4(),
        "username": user_in.username,
        "email": user_in.email,
        "hashed_password": hashed_password,
        "full_name": user_in.full_name,
        "disabled": False, 
        "created_at": datetime.now(timezone.utc),
        "updated_at": None
    }
    # Tenta validar antes de inserir (boa prática)
    try:
        user_db_obj = UserInDB.model_validate(user_db_data)
    except Exception as validation_error:
        logger.error(f"Erro de validação Pydantic ao criar user_db_obj: {validation_error}")
        return None

    # Converte para dicionário para inserir no Mongo
    user_db_dict = user_db_obj.model_dump(mode="json")

    try:
        insert_result = await db[USERS_COLLECTION].insert_one(user_db_dict)
        if not insert_result.acknowledged:
            logger.error(f"DB Insert User Acknowledged False for username {user_in.username}")
            return None
        # Retorna o objeto UserInDB validado
        return user_db_obj
    except DuplicateKeyError:
        raise 
    except Exception as e:
        logger.exception(f"Erro inesperado ao inserir usuário {user_in.username} no DB: {e}")
        return None

# Adicionar funções de update e delete se necessário
# async def update_user(...)
# async def delete_user(...)

# ==================================================
# --- Configuração de Índices MongoDB ---
# ==================================================
async def create_user_indexes(db: AsyncIOMotorDatabase):
    """Cria índices únicos para username e email se não existirem."""
    collection = db[USERS_COLLECTION]
    try:
        await collection.create_index("username", unique=True, name="username_unique_idx")
        await collection.create_index("email", unique=True, name="email_unique_idx")
        logging.info("Índices de usuário ('username', 'email') verificados/criados.")
    except Exception as e:
        logging.error(f"Erro ao criar índices de usuário: {e}")