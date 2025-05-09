# app/core/dependencies.py
"""
Define as dependências reutilizáveis para a aplicação FastAPI,
especialmente aquelas relacionadas à autenticação e acesso ao banco de dados.
"""

# ========================
# --- Importações ---
# ========================
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Annotated
import uuid

# --- Módulos da Aplicação ---
from app.db.mongodb_utils import get_database
from app.core.security import decode_token
from app.db import user_crud
from app.models.user import UserInDB

# ========================
# --- Esquema OAuth2 ---
# ========================
# Define o esquema OAuth2 para obter o token do header 'Authorization: Bearer <token>'.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login/access-token")

# ========================
# --- Tipos de Dependência ---
# ========================
DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_database)]
TokenDep = Annotated[str, Depends(oauth2_scheme)]

# ========================
# --- Dependência: Usuário Atual ---
# ========================
async def get_current_user(
    db: DbDep,
    token: TokenDep
) -> UserInDB:
    """
    Dependência para obter o usuário atual com base no token JWT fornecido.

    Processo:
    1. Extrai e valida o token do header.
    2. Decodifica o token e obtém o payload ('sub' como ID do usuário).
    3. Converte 'sub' para UUID e busca o usuário no banco de dados.
    4. Levanta HTTPException 401 se a validação falhar.

    Args:
        db: Instância do banco de dados.
        token: Token JWT do header.

    Returns:
        O objeto UserInDB correspondente ao token.

    Raises:
        HTTPException: Status 401 se as credenciais não puderem ser validadas.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não foi possível validar as credenciais",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token_payload = decode_token(token)

    if token_payload is None or token_payload.sub is None:
        raise credentials_exception

    try:
        user_id = uuid.UUID(str(token_payload.sub))
    except ValueError:
        raise credentials_exception

    user = await user_crud.get_user_by_id(db=db, user_id=user_id)
    if user is None:
        raise credentials_exception

    return user

# ========================
# --- Dependência: Usuário Ativo Atual ---
# ========================
async def get_current_active_user(
    current_user: Annotated[UserInDB, Depends(get_current_user)]
) -> UserInDB:
    """
    Dependência que reutiliza `get_current_user` e garante que o usuário não está desativado.

    Args:
        current_user: Usuário retornado por `get_current_user`.

    Returns:
        O objeto UserInDB se o usuário estiver ativo.

    Raises:
        HTTPException: Status 400 se o usuário estiver desativado.
    """
    if current_user.disabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuário inativo")
    return current_user

# ========================
# --- Tipos Anotados para Rotas ---
# ========================
# Injeta um usuário ativo validado (UserInDB) nos endpoints.
CurrentUser = Annotated[UserInDB, Depends(get_current_active_user)]