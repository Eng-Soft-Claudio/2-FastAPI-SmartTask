# app/db/user_crud.py
"""
Módulo contendo as funções CRUD (Create, Read, Update, Delete)
para interagir com a coleção de usuários no MongoDB.
Inclui também funções para criação de índices.
"""

# ========================
# --- Importações ---
# ========================
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorCollection
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError

# --- Módulos da Aplicação ---
from app.models.user import UserCreate, UserInDB, UserUpdate
from app.core.security import get_password_hash

# ========================
# --- Configurações e Constantes ---
# ========================
logger = logging.getLogger(__name__)
USERS_COLLECTION = "users"

# ========================
# --- Funções Auxiliares (Internas) ---
# ========================
def _get_users_collection(db: AsyncIOMotorDatabase) -> AsyncIOMotorCollection:
    """Retorna a coleção de usuários do banco de dados."""
    return db[USERS_COLLECTION]

# ========================
# --- Operações CRUD para Usuários ---
# ========================
async def get_user_by_id(db: AsyncIOMotorDatabase, user_id: uuid.UUID) -> Optional[UserInDB]:
    """
    Busca um usuário pelo seu ID (UUID).

    Args:
        db: Instância da conexão com o banco de dados.
        user_id: O ID do usuário a ser buscado.

    Returns:
        Um objeto UserInDB se o usuário for encontrado e válido, None caso contrário.
    """
    collection = _get_users_collection(db)
    user_dict = await collection.find_one({"id": str(user_id)})
    if user_dict:
        user_dict.pop('_id', None)
        try:
            return UserInDB.model_validate(user_dict)
        except Exception as e:
            logger.error(f"DB Validation error get_user_by_id {user_id}: {e}")
            return None
    return None

async def get_user_by_username(db: AsyncIOMotorDatabase, username: str) -> Optional[UserInDB]:
    """
    Busca um usuário pelo seu nome de usuário.

    Args:
        db: Instância da conexão com o banco de dados.
        username: O nome de usuário a ser buscado.

    Returns:
        Um objeto UserInDB se o usuário for encontrado e válido, None caso contrário.
    """
    collection = _get_users_collection(db)
    user_dict = await collection.find_one({"username": username})
    if user_dict:
        user_dict.pop('_id', None)
        try:
            return UserInDB.model_validate(user_dict)
        except Exception as e:
            logger.error(f"DB Validation error get_user_by_username {username}: {e}")
            return None
    return None

async def get_user_by_email(db: AsyncIOMotorDatabase, email: str) -> Optional[UserInDB]:
    """
    Busca um usuário pelo seu endereço de e-mail.

    Args:
        db: Instância da conexão com o banco de dados.
        email: O endereço de e-mail a ser buscado.

    Returns:
        Um objeto UserInDB se o usuário for encontrado e válido, None caso contrário.
    """
    collection = _get_users_collection(db)
    user_dict = await collection.find_one({"email": email})
    if user_dict:
        user_dict.pop('_id', None)
        try:
            return UserInDB.model_validate(user_dict)
        except Exception as e:
            logger.error(f"DB Validation error get_user_by_email {email}: {e}")
            return None
    return None

async def create_user(db: AsyncIOMotorDatabase, user_in: UserCreate) -> Optional[UserInDB]:
    """
    Cria um novo usuário no banco de dados.

    Gera um UUID para o usuário, hasheia a senha e define campos padrão
    como 'disabled', 'created_at' e 'updated_at'.

    Args:
        db: Instância da conexão com o banco de dados.
        user_in: Objeto UserCreate com os dados do usuário a ser criado.

    Returns:
        Um objeto UserInDB representando o usuário criado se sucesso, None em caso de erro.
        Pode levantar DuplicateKeyError se username ou email já existirem e houver
        índices de unicidade configurados.
    """
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

    try:
        user_db_obj = UserInDB.model_validate(user_db_data)
    except Exception as validation_error:
        logger.error(f"Erro de validação Pydantic ao preparar dados para user_db_obj (username: {user_in.username}): {validation_error}", exc_info=True)
        return None

    user_db_dict = user_db_obj.model_dump(mode="json")
    collection = _get_users_collection(db)

    try:
        insert_result = await collection.insert_one(user_db_dict)
        if not insert_result.acknowledged: # pragma: no cover
            logger.error(f"DB Insert User Acknowledged False for username {user_in.username}")
            return None
        return user_db_obj
    except DuplicateKeyError:
        logger.warning(f"Tentativa de criar usuário com username ou email duplicado: {user_in.username} / {user_in.email}")
        raise
    except Exception as e:
        logger.exception(f"Erro inesperado ao inserir usuário {user_in.username} no DB: {e}")
        return None

async def update_user(db: AsyncIOMotorDatabase, user_id: uuid.UUID, user_update: UserUpdate) -> Optional[UserInDB]:
    """
    Atualiza os dados de um usuário existente.

    Apenas os campos fornecidos no objeto `user_update` serão alterados.
    O campo `updated_at` é automaticamente atualizado. Se a senha for
    alterada, ela será hasheada.

    Args:
        db: Instância da conexão com o banco de dados.
        user_id: O ID do usuário a ser atualizado.
        user_update: Objeto UserUpdate contendo os dados a serem atualizados.

    Returns:
        O objeto UserInDB atualizado se sucesso, None se o usuário não for encontrado ou erro.
        Pode levantar DuplicateKeyError se a atualização tentar definir um username/email
        que já exista e pertença a outro usuário.
    """
    collection = _get_users_collection(db)
    update_data = user_update.model_dump(exclude_unset=True)

    if "password" in update_data:
        if update_data["password"] is not None:
            update_data["hashed_password"] = get_password_hash(update_data.pop("password"))
        elif "password" in update_data and update_data["password"] is None: # Este elif é redundante com a condição externa.
            update_data.pop("password") # Evita 'password: null' se for passado explicitamente como None

    if not update_data and "hashed_password" not in update_data :
        existing_user = await get_user_by_id(db, user_id)
        if existing_user:
            try:
                updated_doc = await collection.find_one_and_update(
                    {"id": str(user_id)},
                    {"$set": {"updated_at": datetime.now(timezone.utc)}},
                    return_document=True
                )
                if updated_doc:
                    updated_doc.pop('_id', None)
                    return UserInDB.model_validate(updated_doc)
                return None
            except Exception as e:
                logger.exception(f"DB Error updating user (only updated_at) {user_id}: {e}")
                return None
        return existing_user # Retorna o usuário existente se nada mais for atualizado

    update_data["updated_at"] = datetime.now(timezone.utc)

    try:
        updated_user_doc = await collection.find_one_and_update(
            {"id": str(user_id)},
            {"$set": update_data},
            return_document=True
        )

        if updated_user_doc:
            updated_user_doc.pop('_id', None)
            try:
                return UserInDB.model_validate(updated_user_doc)
            except ValidationError as e:
                logger.error(f"DB Validation error after updating user {user_id}: {e}")
                return None
        else:
            logger.warning(f"Attempt to update user not found: ID {user_id}")
            return None
    except DuplicateKeyError:
        logger.warning(f"DB Error: Attempt to update user {user_id} resulted in duplicate key for data: { {k: v for k, v in update_data.items() if k not in ['hashed_password', 'updated_at']} }")
        raise
    except Exception as e:
        logger.exception(f"DB Error updating user {user_id}: {e}")
        return None

async def delete_user(db: AsyncIOMotorDatabase, user_id: uuid.UUID) -> bool:
    """
    Deleta um usuário do banco de dados pelo seu ID.

    Args:
        db: Instância da conexão com o banco de dados.
        user_id: O ID do usuário a ser deletado.

    Returns:
        True se o usuário foi deletado com sucesso (1 documento afetado), False caso contrário.
    """
    collection = _get_users_collection(db)
    try:
        delete_result = await collection.delete_one({"id": str(user_id)})
        if delete_result.deleted_count == 1:
            logger.info(f"User {user_id} deleted successfully.")
            return True
        else:
            logger.warning(f"Attempt to delete user {user_id}, but user was not found or not deleted (deleted_count: {delete_result.deleted_count}).")
            return False
    except Exception as e:
        logger.exception(f"DB Error deleting user {user_id}: {e}")
        return False

# ========================
# --- Configuração de Índices do Banco de Dados ---
# ========================
async def create_user_indexes(db: AsyncIOMotorDatabase):
    """
    Cria os índices necessários na coleção de usuários para otimizar consultas
    e garantir unicidade de campos como username e email.

    Os índices são criados apenas se ainda não existirem.
    Esta função é tipicamente chamada durante a inicialização da aplicação.

    Args:
        db: Instância da conexão com o banco de dados.
    """
    collection = _get_users_collection(db)
    try:
        await collection.create_index("username", unique=True, name="username_unique_idx")
        await collection.create_index("email", unique=True, name="email_unique_idx")
        logger.info("Índices da coleção 'users' ('username', 'email') verificados/criados com sucesso.")
    except Exception as e:
        logger.error(f"Erro ao criar índices para a coleção 'users': {e}", exc_info=True)