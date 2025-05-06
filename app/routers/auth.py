# app/routers/auth.py
"""
Este módulo define as rotas da API relacionadas à autenticação de usuários,
incluindo registro de novos usuários, login (obtenção de token de acesso JWT)
e recuperação de informações do usuário autenticado.
"""

# ========================
# --- Importações ---
# ========================
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm 
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

# --- Módulos da Aplicação ---
from app.core.dependencies import CurrentUser
from app.core.security import create_access_token, verify_password
from app.db import user_crud
from app.db.mongodb_utils import get_database
from app.models.token import Token
from app.models.user import User, UserCreate, UserUpdate

# ================================
# --- Configuração do Router ---
# ================================
router = APIRouter(
    # Prefixo para todas as rotas neste router pode ser adicionado aqui se desejado.
    # Ex: prefix="/auth",
    # Agrupa estas rotas sob "Authentication" na documentação OpenAPI.
    tags=["Authentication"], 
)

# =========================================
# --- Dependências Específicas do Roteador ---
# =========================================

# Dependência para obter a instância do banco de dados.
# Annotated melhora a legibilidade e o suporte do editor.
DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_database)]

# =====================
# --- Rotas da API ---
# =====================

@router.post(
    "/register",
    response_model=User, 
    status_code=status.HTTP_201_CREATED, 
    summary="Registra um novo usuário no sistema",
    response_description="Retorna os dados do usuário recém-registrado (sem a senha).",
)
async def register_user(
    db: DbDep,
    # `user_in` é o payload da requisição, validado pelo modelo UserCreate.
    user_in: Annotated[UserCreate, Body(description="Dados do novo usuário para registro.")]
):
    """
    Endpoint para registrar um novo usuário.

    Operações realizadas:
    1. Verifica se já existe um usuário com o mesmo `username`.
    2. Verifica se já existe um usuário com o mesmo `email`.
    3. Se não houver conflitos, tenta criar o usuário no banco de dados.
       A senha é hasheada pela função `user_crud.create_user`.
    4. Retorna o objeto `User` (sem a senha) em caso de sucesso.

    Exceções possíveis:
    - `HTTP 409 Conflict`: Se o `username` ou `email` já estiverem em uso.
    - `HTTP 500 Internal Server Error`: Se ocorrer um erro inesperado durante a criação.
    """
    # Verificação prévia da existência do nome de usuário.
    existing_user_by_username = await user_crud.get_user_by_username(db, user_in.username)
    if existing_user_by_username:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"O nome de usuário '{user_in.username}' já existe.",
        )

    # Verificação prévia da existência do e-mail.
    existing_user_by_email = await user_crud.get_user_by_email(db, user_in.email)
    if existing_user_by_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"O endereço de e-mail '{user_in.email}' já registrado.",
        )

    try:
        # Tenta criar o usuário no banco de dados.
        created_user_db_obj = await user_crud.create_user(db=db, user_in=user_in)
        if created_user_db_obj is None:
            # Se user_crud.create_user retornar None sem levantar exceção (caso não esperado, mas coberto).
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Não foi possível criar o usuário devido a um erro interno no servidor."
            )
        # Converte o objeto UserInDB (do banco) para o modelo User (resposta da API).
        return User.model_validate(created_user_db_obj)
    except DuplicateKeyError:
        # Esta exceção pode ocorrer se, apesar das verificações acima (race condition)
        # ou devido a outros índices únicos, uma chave duplicada for detectada pelo MongoDB.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflito: nome de usuário ou e-mail já existe (detectado pelo banco de dados).",
        )
    except Exception: # Captura genérica para outros erros inesperados.
        # Logar a exceção original 'e' é recomendado em um cenário de produção.
        # logger.exception("Erro inesperado durante o registro do usuário:")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ocorreu um erro inesperado durante o processo de registro.",
        )


@router.post(
    "/login/access-token",
    response_model=Token, 
    summary="Autentica o usuário e obtém um token de acesso JWT",
    description=(
        "Endpoint de login padrão que utiliza OAuth2PasswordRequestForm. "
        "O cliente deve enviar `username` e `password` como form data."
    ),
    response_description="Token de acesso JWT e tipo do token ('bearer')."
)
async def login_for_access_token(
    db: DbDep,
    # `form_data` injeta os dados do formulário (`username` e `password`).
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
):
    """
    Autentica um usuário e retorna um token de acesso.

    Passos da autenticação:
    1. Busca o usuário pelo `username` fornecido.
    2. Verifica se o usuário existe e se a senha fornecida corresponde à senha hasheada armazenada.
    3. Verifica se a conta do usuário não está desativada (`disabled`).
    4. Se todas as verificações passarem, um novo token de acesso JWT é gerado e retornado.

    Exceções possíveis:
    - `HTTP 401 Unauthorized`: Se o usuário não for encontrado ou a senha estiver incorreta.
    - `HTTP 400 Bad Request`: Se a conta do usuário estiver desativada.
    """
    # Busca o usuário no banco de dados pelo username.
    user = await user_crud.get_user_by_username(db, form_data.username)

    # Verifica se o usuário existe e se a senha está correta.
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nome de usuário ou senha incorretos.",
            headers={"WWW-Authenticate": "Bearer"}, 
        )

    # Verifica se o usuário está ativo.
    if user.disabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="A conta do usuário está inativa."
        )

    # Cria o token de acesso JWT.
    # O 'subject' do token é o ID do usuário.
    access_token = create_access_token(
        subject=user.id, 
        username=user.username
    )

    return Token(access_token=access_token, token_type="bearer")

@router.get(
    "/users/me",
    response_model=User, 
    summary="Obtém dados do usuário atualmente autenticado",
    description=(
        "Recupera e retorna os dados do usuário que está autenticado "
        "através do token JWT fornecido no cabeçalho de Autorização (Bearer Token)."
    ),
    response_description="Dados do usuário autenticado (sem a senha).",
)
async def read_users_me(
    # `CurrentUser` é uma dependência que valida o token JWT
    # e retorna o objeto User (ou UserInDB) correspondente.
    current_user: CurrentUser
) -> User:
    """
    Retorna as informações do usuário autenticado.

    A dependência `CurrentUser` é responsável por:
    - Extrair o token JWT do cabeçalho de autorização.
    - Validar o token.
    - Buscar o usuário correspondente no banco de dados.
    - Levantar uma exceção `HTTP 401 Unauthorized` se o token for inválido ou ausente.

    Este endpoint simplesmente retorna o usuário fornecido pela dependência.
    """
    # O tipo de `current_user` já é `User` (ou `UserInDB` que será validado por `User` como response_model).
    # FastAPI automaticamente validará `current_user` contra `response_model=User`.
    return current_user

@router.put(
    "/users/me",
    response_model=User,
    summary="Atualiza os dados do usuário atualmente autenticado",
    description=(
        "Permite que o usuário autenticado atualize seus próprios dados, "
        "como e-mail, nome completo ou senha."
    ),
    response_description="Dados do usuário atualizados (sem a senha).",
)
async def update_current_user(
    db: DbDep,
    user_update_payload: Annotated[UserUpdate, Body(description="Campos do usuário a serem atualizados.")],
    current_user: CurrentUser 
):
    """
    Permite ao usuário autenticado atualizar suas próprias informações.

    Campos que podem ser atualizados incluem: e-mail, senha, nome completo e status de desativação.
    Se o e-mail for atualizado, verifica-se a unicidade.
    A nova senha, se fornecida, será hasheada.

    Exceções possíveis:
    - `HTTP 401 Unauthorized`: Se o token for inválido.
    - `HTTP 404 Not Found`: Se, por algum motivo, o usuário não for encontrado para atualização.
    - `HTTP 409 Conflict`: Se a tentativa de atualizar o e-mail resultar em um e-mail já existente.
    - `HTTP 500 Internal Server Error`: Para outros erros inesperados.
    """
    try:
        # O user_id para atualização é o do usuário autenticado (current_user.id)
        updated_user_db_obj = await user_crud.update_user(
            db=db,
            user_id=current_user.id,
            user_update=user_update_payload
        )

        if updated_user_db_obj is None:
            # Isso pode ocorrer se user_crud.update_user não encontrar o usuário
            # (improvável se CurrentUser funcionou) ou se houver outro erro interno no CRUD.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="Não foi possível atualizar o usuário. Usuário não encontrado ou erro interno."
            )
        return User.model_validate(updated_user_db_obj)
    except DuplicateKeyError:
        # Tratado se a atualização do email resultar em um conflito.
        email_em_uso = user_update_payload.email if user_update_payload.email else "N/A"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Não foi possível atualizar: o e-mail '{email_em_uso}' já está em uso por outra conta.",
        )
    except Exception:
        # Em produção, logar a exceção original aqui seria ideal.
        # logger.exception(f"Erro inesperado ao atualizar usuário {current_user.id}:")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ocorreu um erro inesperado durante a atualização do usuário.",
        )


@router.delete(
    "/users/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deleta a conta do usuário atualmente autenticado",
    description="Permite que o usuário autenticado delete sua própria conta permanentemente.",
    response_description="Nenhum conteúdo é retornado em caso de sucesso.",
)
async def delete_current_user(
    db: DbDep,
    current_user: CurrentUser 
):
    """
    Permite ao usuário autenticado deletar sua própria conta.

    Esta operação é permanente e não pode ser desfeita.
    Retorna HTTP 204 (No Content) em caso de sucesso.

    Exceções possíveis:
    - `HTTP 401 Unauthorized`: Se o token for inválido.
    - `HTTP 404 Not Found`: Se o usuário não for encontrado para deleção (improvável).
    - `HTTP 500 Internal Server Error`: Para outros erros inesperados.
    """
    try:
        deleted_successfully = await user_crud.delete_user(
            db=db,
            user_id=current_user.id
        )
        if not deleted_successfully:
            # Se user_crud.delete_user retornar False, indica que o usuário não foi encontrado
            # ou a deleção falhou por outro motivo (count != 1).
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="Não foi possível deletar o usuário. Usuário não encontrado ou erro interno."
            )
        # Para status 204, não se deve retornar corpo, então o Response(status_code=...) é apropriado.
        # Alternativamente, FastAPI lida com isso se a função não retornar nada.
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except Exception:
        # Em produção, logar a exceção original aqui seria ideal.
        # logger.exception(f"Erro inesperado ao deletar usuário {current_user.id}:")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ocorreu um erro inesperado durante a deleção do usuário.",
        )