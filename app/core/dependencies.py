# app/core/dependencies.py

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

# ==========================
# --- Esquema OAuth2 ---
# ==========================
# Define o esquema OAuth2 para obter o token do header 'Authorization: Bearer <token>'.
# O tokenUrl aponta para o endpoint de login que gera o token.
# O path relativo deve ser o correto APÓS o prefixo da API (settings.API_V1_STR).
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login/access-token")

# ================================
# --- Tipos de Dependência ---
# ================================
# Tipos anotados para dependências, melhorando legibilidade nas rotas.
DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_database)]
TokenDep = Annotated[str, Depends(oauth2_scheme)]

# ==================================
# --- Dependência: Usuário Atual ---
# ==================================
async def get_current_user(
    db: DbDep,
    token: TokenDep
) -> UserInDB:
    """
    Dependência para obter o usuário atual com base no token JWT fornecido.

    Processo:
    1. Extrai e valida o token do header 'Authorization: Bearer <token>'.
    2. Decodifica o token usando `decode_token` e obtém o payload.
    3. Verifica se o payload é válido e contém o 'sub' (ID do usuário).
    4. Converte o 'sub' para um objeto UUID.
    5. Busca o usuário no banco de dados pelo ID extraído.
    6. Levanta HTTPException 401 se o token for inválido, expirado,
       o 'sub' não for UUID, ou o usuário não existir no banco de dados.
    7. Retorna o objeto `UserInDB` completo encontrado.

    Args:
        db: Instância do banco de dados injetada.
        token: Token JWT extraído do header pela dependência `oauth2_scheme`.

    Returns:
        O objeto `UserInDB` correspondente ao token, se válido e encontrado.

    Raises:
        HTTPException: Com status 401 se as credenciais não puderem ser validadas.
    """
    # Exceção padrão para falhas de autenticação
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não foi possível validar as credenciais",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Decodifica o token JWT via função em core.security
    token_payload = decode_token(token)

    # Verifica se a decodificação foi bem-sucedida e se temos o 'sub'
    if token_payload is None or token_payload.sub is None:
        raise credentials_exception

    # Tenta converter o 'sub' (ID do usuário) para UUID
    try:
        # Garante que sub seja tratado como string antes de converter
        user_id = uuid.UUID(str(token_payload.sub))
    except ValueError:
        # O 'sub' no token não é um UUID válido
        raise credentials_exception

    # Busca o usuário no banco de dados usando a função CRUD
    user = await user_crud.get_user_by_id(db=db, user_id=user_id)
    if user is None:
        # Usuário referenciado no token não existe mais no DB
        raise credentials_exception

    # Retorna o objeto UserInDB completo (inclui senha hasheada, útil internamente)
    # Para retornar o modelo User (sem senha) à API, a rota faria a conversão/validação.
    return user

# =========================================
# --- Dependência: Usuário Ativo Atual ---
# =========================================
async def get_current_active_user(
    current_user: Annotated[UserInDB, Depends(get_current_user)]
) -> UserInDB:
    """
    Dependência que reutiliza `get_current_user` e adicionalmente garante
    que o usuário obtido não está desativado (campo `disabled` é False).

    Args:
        current_user: O objeto `UserInDB` retornado pela dependência `get_current_user`.

    Returns:
        O mesmo objeto `UserInDB` se o usuário estiver ativo.

    Raises:
        HTTPException: Com status 400 se o usuário estiver desativado.
    """
    if current_user.disabled:
        # Levanta erro específico se o usuário estiver marcado como inativo
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuário inativo")

    # Se chegou aqui, o usuário está ativo; retorna o objeto recebido
    return current_user

# ==========================================
# --- Tipos Anotados para Uso em Rotas ---
# ==========================================
# Define tipos curtos e mais expressivos para usar como dependências
# nos endpoints protegidos, melhorando a leitura do código das rotas.

# Injeta um usuário ativo validado (UserInDB)
CurrentUser = Annotated[UserInDB, Depends(get_current_active_user)]
