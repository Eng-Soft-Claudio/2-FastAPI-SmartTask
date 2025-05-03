# app/core/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Annotated # Python 3.9+
import uuid

from app.db.mongodb_utils import get_database
from app.core.security import decode_token
from app.db import user_crud
from app.models.user import UserInDB, User # Import User para retorno

# Define o esquema OAuth2 para obter o token do header Authorization: Bearer <token>
# tokenUrl aponta para o nosso endpoint de login que gera o token
# O path relativo deve ser o correto APÓS o prefixo da API
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login/access-token") # Ajuste se seu prefixo/rota for diferente

# Tipos anotados para dependências (mais legível)
DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_database)]
TokenDep = Annotated[str, Depends(oauth2_scheme)]

async def get_current_user(
    db: DbDep,
    token: TokenDep # Obtém o token do header usando OAuth2PasswordBearer
) -> UserInDB: # Retorna o usuário completo do DB (incluindo senha hasheada)
               # Mude para 'User' se preferir retornar o modelo sem senha hasheada
    """
    Dependência para obter o usuário atual com base no token JWT:
    - Extrai e valida o token do header 'Authorization: Bearer <token>'.
    - Decodifica o token e obtém o ID do usuário ('sub').
    - Busca o usuário no banco de dados pelo ID.
    - Levanta exceção se o token for inválido, expirado ou o usuário não existir/estiver desativado.
    - Retorna o objeto do usuário encontrado.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não foi possível validar as credenciais",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Decodifica o token JWT
    token_payload = decode_token(token)

    if token_payload is None or token_payload.sub is None:
         # Se decode_token retornou None, o token é inválido ou expirou
        raise credentials_exception

    # Tenta converter o 'sub' (subject/ID do usuário) para UUID
    try:
        user_id = uuid.UUID(str(token_payload.sub)) # Garante que sub seja tratado como string
    except ValueError:
         # O 'sub' no token não é um UUID válido
         raise credentials_exception

    # Busca o usuário no banco de dados usando o ID do token
    user = await user_crud.get_user_by_id(db=db, user_id=user_id)
    if user is None:
         # Usuário referenciado no token não existe mais no DB
         raise credentials_exception

    # Opcional: Poderia retornar o modelo User (sem hash de senha) aqui se preferir
    # return User.model_validate(user)
    return user # Retorna UserInDB (útil se precisarmos da info completa internamente)


async def get_current_active_user(
     # Esta dependência *reutiliza* a anterior
    current_user: Annotated[UserInDB, Depends(get_current_user)]
) -> UserInDB: # Mude para User se get_current_user retornar User
    """
    Dependência que garante que o usuário obtido de get_current_user
    não está desativado.
    """
    if current_user.disabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuário inativo")
    # Se passou, retorna o mesmo usuário validado
    # Poderia retornar User aqui também: User.model_validate(current_user)
    return current_user

# --- Tipos Anotados para Injeção ---
# Define tipos curtos para usar nos endpoints protegidos
CurrentUser = Annotated[UserInDB, Depends(get_current_active_user)]
# Use este se preferir retornar o modelo User sem a senha hasheada:
# CurrentUser = Annotated[User, Depends(get_current_active_user)] # Se get_current_active_user retornar User