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

# =====================================
# --- Configurações e Constantes ---
# =====================================

# Obter um logger para este módulo
logger = logging.getLogger(__name__)

# Nome da coleção no MongoDB para usuários
USERS_COLLECTION = "users"

# =========================================
# --- Funções Auxiliares (Internas) ---
# =========================================

def _get_users_collection(db: AsyncIOMotorDatabase) -> AsyncIOMotorCollection:
    """Retorna a coleção de usuários do banco de dados."""
def _get_users_collection(db: AsyncIOMotorDatabase) -> AsyncIOMotorCollection:
    return db[USERS_COLLECTION]

# =======================================
# --- Operações CRUD para Usuários ---
# =======================================

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
        # Remove o campo '_id' do MongoDB antes de validar com Pydantic
        user_dict.pop('_id', None)
        try:
            return UserInDB.model_validate(user_dict)
        except Exception as e:
            # Log da validação de dados vindo do DB.
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
        # Remove o campo '_id' do MongoDB antes de validar com Pydantic
        user_dict.pop('_id', None)
        try:
            return UserInDB.model_validate(user_dict)
        except Exception as e:
            # Log da validação de dados vindo do DB.
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
    # Para melhor performance e garantir unicidade, um índice no campo 'email' é altamente recomendado.
    user_dict = await collection.find_one({"email": email})
    if user_dict:
        # Remove o campo '_id' do MongoDB antes de validar com Pydantic
        user_dict.pop('_id', None)
        try:
            return UserInDB.model_validate(user_dict)
        except Exception as e:
            # Log da validação de dados vindo do DB.
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

    # Prepara os dados do usuário para inserção no banco, incluindo campos gerados
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

    # Valida os dados preparados com o modelo Pydantic UserInDB antes de tentar inserir
    # Isso ajuda a pegar erros de formatação ou tipo de dados antes da operação de DB.
    try:
        user_db_obj = UserInDB.model_validate(user_db_data)
    except Exception as validation_error:
        logger.error(f"Erro de validação Pydantic ao preparar dados para user_db_obj (username: {user_in.username}): {validation_error}", exc_info=True)
        return None

    # Converte o objeto Pydantic validado para um dicionário para inserção no MongoDB
    # 'mode="json"' garante que tipos como UUID e datetime sejam serializados corretamente.
    user_db_dict = user_db_obj.model_dump(mode="json")
    collection = _get_users_collection(db)

    try:
        insert_result = await collection.insert_one(user_db_dict)
        if not insert_result.acknowledged:
            logger.error(f"DB Insert User Acknowledged False for username {user_in.username}")
            return None
        # Retorna o objeto UserInDB completo e validado após a inserção bem-sucedida
        return user_db_obj
    except DuplicateKeyError:
        # Se um DuplicateKeyError ocorrer (e.g., username ou email já existem),
        # ele é relançado para ser tratado por uma camada superior (provavelmente o endpoint da API),
        # que pode retornar uma resposta HTTP 400/409 apropriada.
        logger.warning(f"Tentativa de criar usuário com username ou email duplicado: {user_in.username} / {user_in.email}")
        raise
    except Exception as e:
        # Captura outras exceções inesperadas durante a inserção.
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

    # Converte o modelo Pydantic para dicionário, excluindo campos não definidos (unset)
    # para que apenas os campos passados sejam atualizados.
    # 'exclude_unset=True' é crucial aqui.
    update_data = user_update.model_dump(exclude_unset=True)

    # Se a senha estiver sendo atualizada, hasheia a nova senha.
    if "password" in update_data and update_data["password"] is not None:
        update_data["hashed_password"] = get_password_hash(update_data.pop("password"))
    elif "password" in update_data and update_data["password"] is None:
        # Evitar que 'password: null' delete o hash_password. O model UserUpdate deve garantir
        # que o campo password seja uma string válida se presente.
        update_data.pop("password")


    # Se não houver dados para atualizar após processamento (ex: apenas 'password: null' foi passado e removido),
    # podemos retornar o usuário atual sem fazer uma chamada ao DB, ou simplesmente continuar e
    # atualizar apenas o 'updated_at'. 
    if not update_data and "hashed_password" not in update_data : 
        existing_user = await get_user_by_id(db, user_id)
        if existing_user:
            # Atualiza apenas o updated_at se nenhum outro campo for modificado
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
        return existing_user 


    # Garante que o campo 'updated_at' seja atualizado.
    update_data["updated_at"] = datetime.now(timezone.utc)

    try:
        # Executa a atualização e retorna o documento modificado
        updated_user_doc = await collection.find_one_and_update(
            {"id": str(user_id)},
            {"$set": update_data},
            return_document=True  
        )

        if updated_user_doc:
            # Remove o campo '_id' do MongoDB antes de validar com Pydantic
            updated_user_doc.pop('_id', None)
            try:
                return UserInDB.model_validate(updated_user_doc)
            except ValidationError as e: 
                logger.error(f"DB Validation error after updating user {user_id}: {e}")
                return None
        else:
            # O usuário não foi encontrado para atualização
            logger.warning(f"Attempt to update user not found: ID {user_id}")
            return None
    except DuplicateKeyError:
        # Tratar erro de chave duplicada (e.g., email ou username)
        logger.warning(f"DB Error: Attempt to update user {user_id} resulted in duplicate key for data: { {k: v for k, v in update_data.items() if k not in ['hashed_password', 'updated_at']} }")
        # Relança para ser tratado na camada de cima
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
        # Verifica se exatamente um documento foi deletado
        if delete_result.deleted_count == 1:
            logger.info(f"User {user_id} deleted successfully.")
            return True
        else:
            logger.warning(f"Attempt to delete user {user_id}, but user was not found or not deleted (deleted_count: {delete_result.deleted_count}).")
            return False
    except Exception as e:
        logger.exception(f"DB Error deleting user {user_id}: {e}")
        return False

# ===================================================
# --- Configuração de Índices do Banco de Dados ---
# ===================================================
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
        # Índice único para 'username' para buscas rápidas e unicidade
        await collection.create_index("username", unique=True, name="username_unique_idx")
        # Índice único para 'email' para buscas rápidas e unicidade
        await collection.create_index("email", unique=True, name="email_unique_idx")
        # Adicionado log com logger do módulo
        logger.info("Índices da coleção 'users' ('username', 'email') verificados/criados com sucesso.")
    except Exception as e:
        # Adicionado log com logger do módulo e exc_info=True
        logger.error(f"Erro ao criar índices para a coleção 'users': {e}", exc_info=True)