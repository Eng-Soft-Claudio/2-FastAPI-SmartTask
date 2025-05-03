# app/routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError
from typing import Annotated
from app.db.mongodb_utils import get_database
from app.db import user_crud 
from app.models.user import User, UserCreate
from app.models.token import Token
from app.core.security import verify_password, create_access_token

router = APIRouter(
    tags=["Authentication"],
)

DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_database)]

@router.post(
    "/register",
    response_model=User, 
    status_code=status.HTTP_201_CREATED,
    summary="Registra um novo usuário",
    response_description="O usuário recém-registrado.",
)
async def register_user(
    db: DbDep,
    user_in: Annotated[UserCreate, Body(description="Dados do novo usuário")]):
    """
    Registra um novo usuário no sistema:
    - Verifica se o username ou email já existem.
    - Hasheia a senha.
    - Salva o usuário no banco de dados.
    - Retorna os dados do usuário criado (sem a senha).
    """
    existing_user = await user_crud.get_user_by_username(db, user_in.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Usuário '{user_in.username}' já existe.",
        )
    existing_email = await user_crud.get_user_by_email(db, user_in.email)
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"E-mail '{user_in.email}' já registrado.",
        )

    try:
        created_user_db = await user_crud.create_user(db=db, user_in=user_in)
        if created_user_db is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="Não foi possível criar o usuário.")
        return User.model_validate(created_user_db)
    except DuplicateKeyError:
         raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Usuário ou e-mail já registrado (conflito de índice único).",
         )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Ocorreu um erro inesperado durante o registro.")


@router.post(
    "/login/access-token",
    response_model=Token,
    summary="Obtém um token de acesso JWT",
    description="Autentica o usuário com username e senha (form data) e retorna um token JWT.",
)
async def login_for_access_token(
    db: DbDep,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
):
    """
    Endpoint de login padrão OAuth2:
    - Recebe `username` e `password` via form-data.
    - Busca o usuário pelo username.
    - Verifica se o usuário existe e se a senha está correta.
    - Verifica se o usuário não está desativado.
    - Cria e retorna um token de acesso JWT.
    """
    user = await user_crud.get_user_by_username(db, form_data.username)

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha incorretos.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.disabled:
         raise HTTPException(
             status_code=status.HTTP_400_BAD_REQUEST,
             detail="Usuário inativo."
         )

    access_token = create_access_token(
        subject=user.id,
        username=user.username
        )

    return Token(access_token=access_token, token_type="bearer")