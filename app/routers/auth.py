# app/routers/auth.py
"""
Este módulo define as rotas da API relacionadas à autenticação de usuários,
incluindo registro, login (obtenção de token JWT) e gerenciamento
de informações do usuário autenticado (visualizar, atualizar, deletar).
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
from core.dependencies import CurrentUser, DbDep 
from core.security import create_access_token, verify_password
from db import user_crud
from models.token import Token
from models.user import User, UserCreate, UserUpdate

# ========================
# --- Configuração do Router ---
# ========================
router = APIRouter(
    tags=["Authentication"],
)

# ========================
# --- Rotas da API ---
# ========================

# --- Endpoint de Registro ---
@router.post(
    "/register",
    response_model=User,
    status_code=status.HTTP_201_CREATED,
    summary="Registra um novo usuário no sistema",
    response_description="Dados do usuário recém-registrado (sem senha).",
)
async def register_user(
    db: DbDep,
    user_in: Annotated[UserCreate, Body(description="Dados do novo usuário para registro.")]
):
    """
    Endpoint para registrar um novo usuário.

    Verifica duplicidade de username e email.
    Cria o usuário no banco, hasheando a senha.
    Retorna o usuário criado (sem a senha).
    """
    existing_user_by_username = await user_crud.get_user_by_username(db, user_in.username)
    if existing_user_by_username:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"O nome de usuário '{user_in.username}' já existe.",
        )

    existing_user_by_email = await user_crud.get_user_by_email(db, user_in.email)
    if existing_user_by_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"O endereço de e-mail '{user_in.email}' já registrado.",
        )

    try:
        created_user_db_obj = await user_crud.create_user(db=db, user_in=user_in)
        if created_user_db_obj is None:
            # Este cenário é menos provável se as validações anteriores e create_user funcionam
            # como esperado, a menos que create_user retorne None por um motivo não coberto
            # por DuplicateKeyError ou outra Exception específica.
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Não foi possível criar o usuário devido a um erro interno no servidor."
            )
        return User.model_validate(created_user_db_obj)
    except DuplicateKeyError: # pragma: no cover (Testado no CRUD, difícil simular aqui se as checagens prévias funcionam)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflito: nome de usuário ou e-mail já existe (detectado pelo banco de dados).",
        )
    except Exception: # Para outros erros inesperados durante o user_crud.create_user
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ocorreu um erro inesperado durante o processo de registro.",
        )

# --- Endpoint de Login ---
@router.post(
    "/login/access-token",
    response_model=Token,
    summary="Autentica o usuário e obtém um token de acesso JWT",
    description="Endpoint de login padrão OAuth2PasswordRequestForm. Envie 'username' e 'password' como form data.",
    response_description="Token de acesso JWT e tipo do token ('bearer')."
)
async def login_for_access_token(
    db: DbDep,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
):
    """
    Autentica um usuário e retorna um token de acesso.

    Verifica usuário, senha e se a conta está ativa.
    Gera e retorna um token JWT em caso de sucesso.
    """
    user = await user_crud.get_user_by_username(db, form_data.username)

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nome de usuário ou senha incorretos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.disabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A conta do usuário está inativa."
        )

    access_token = create_access_token(
        subject=user.id,
        username=user.username
    )
    return Token(access_token=access_token, token_type="bearer")

# --- Endpoint de Dados do Usuário Autenticado ---
@router.get(
    "/users/me",
    response_model=User,
    summary="Obtém dados do usuário atualmente autenticado",
    description="Retorna os dados do usuário autenticado via token JWT.",
    response_description="Dados do usuário autenticado (sem a senha)."
)
async def read_users_me(
    current_user: CurrentUser # CurrentUser já é o UserInDB ativo
) -> User:
    """
    Retorna as informações do usuário autenticado.
    A dependência `CurrentUser` lida com a validação e busca do usuário.
    """
    # current_user já é o objeto UserInDB validado e ativo.
    # O Pydantic cuidará da conversão para o response_model User.
    return current_user

# --- Endpoint de Atualização do Usuário Autenticado ---
@router.put(
    "/users/me",
    response_model=User,
    summary="Atualiza os dados do usuário atualmente autenticado",
    description="Permite ao usuário autenticado atualizar e-mail, nome completo ou senha.",
    response_description="Dados do usuário atualizados (sem a senha)."
)
async def update_current_user(
    db: DbDep,
    user_update_payload: Annotated[UserUpdate, Body(description="Campos do usuário a serem atualizados.")],
    current_user: CurrentUser
):
    """
    Permite ao usuário autenticado atualizar suas próprias informações.
    """
    try:
        updated_user_db_obj = await user_crud.update_user(
            db=db,
            user_id=current_user.id,
            user_update=user_update_payload
        )

        if updated_user_db_obj is None:
            # O user_crud.update_user retorna None se não encontra ou há erro de validação Pydantic após update
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, # Ou 500 se a causa for erro de validação
                detail="Não foi possível atualizar o usuário. Usuário não encontrado ou erro interno."
            )
        return User.model_validate(updated_user_db_obj)
    except DuplicateKeyError:
        email_em_uso = user_update_payload.email if user_update_payload.email else "N/A"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Não foi possível atualizar: o e-mail '{email_em_uso}' já está em uso por outra conta.",
        )
    except Exception: # Para outros erros inesperados vindos do CRUD (que não sejam DuplicateKeyError)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ocorreu um erro inesperado durante a atualização do usuário.",
        )

# --- Endpoint de Deleção do Usuário Autenticado ---
@router.delete(
    "/users/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deleta a conta do usuário atualmente autenticado",
    description="Permite ao usuário autenticado deletar sua própria conta permanentemente.",
    response_description="Nenhum conteúdo é retornado em caso de sucesso."
)
async def delete_current_user(
    db: DbDep,
    current_user: CurrentUser
):
    """
    Permite ao usuário autenticado deletar sua própria conta.
    """
    try:
        deleted_successfully = await user_crud.delete_user(
            db=db,
            user_id=current_user.id
        )
        if not deleted_successfully:
            # Se delete_user retorna False, significa que não encontrou o usuário para deletar
            # (o que seria estranho aqui, já que current_user existe) ou falhou.
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, # HTTP_404_NOT_FOUND pode ser considerado.
                detail="Não foi possível deletar o usuário. Erro interno ou usuário não encontrado."
            )
        return Response(status_code=status.HTTP_204_NO_CONTENT) # Resposta HTTP 204

    except Exception: # Para outros erros inesperados vindos do CRUD
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ocorreu um erro inesperado durante a deleção do usuário.",
        )