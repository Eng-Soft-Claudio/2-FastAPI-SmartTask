# app/models/user.py
"""
Este módulo define os modelos Pydantic para a entidade Usuário (User).
Inclui modelos para criação, atualização, e diferentes representações
de dados do usuário, como a forma como são armazenados no banco de dados
e como são retornados nas respostas da API.
"""

# ========================
# --- Importações ---
# ========================
import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, ConfigDict

# ========================
# --- Modelos Pydantic de User ---
# ========================

# --- Modelo Base ---
class UserBase(BaseModel):
    """
    Modelo base contendo os atributos comuns a todas as variações de usuário.
    Define os campos que podem ser esperados na maioria das representações de um usuário.
    """
    email: EmailStr = Field(..., title="Endereço de E-mail", description="Deve ser um e-mail válido e único.")
    username: str = Field(
        ...,
        title="Nome de Usuário",
        min_length=3,
        max_length=50,
        pattern="^[a-zA-Z0-9_]+$",
        description="Nome de usuário único (letras, números, underscore)."
    )
    full_name: Optional[str] = Field(None, title="Nome Completo", max_length=100)
    disabled: bool = Field(default=False, title="Status Desativado", description="Indica se o usuário está desativado.")

# --- Modelo para Criação de Usuário ---
class UserCreate(BaseModel):
    """
    Modelo para os dados necessários ao criar um novo usuário.
    Este é o formato esperado no payload da API para registro de usuários.
    """
    email: EmailStr = Field(..., title="Endereço de E-mail")
    username: str = Field(..., title="Nome de Usuário", min_length=3, max_length=50, pattern="^[a-zA-Z0-9_]+$")
    password: str = Field(..., title="Senha", min_length=8, description="Senha (será hasheada antes de salvar).")
    full_name: Optional[str] = Field(None, title="Nome Completo", max_length=100)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "email": "userTest@example.com",
                    "username": "userTest",
                    "password": "averysecurepassword",
                    "full_name": "User Test"
                }
            ]
        }
    }

# --- Modelo para Atualização de Usuário ---
class UserUpdate(BaseModel):
    """
    Modelo para os dados que podem ser atualizados em um usuário existente.
    Todos os campos são opcionais, permitindo atualizações parciais.
    """
    email: Optional[EmailStr] = Field(None, title="Endereço de E-mail")
    password: Optional[str] = Field(None, title="Nova Senha", min_length=8, description="Nova senha (se fornecida).")
    full_name: Optional[str] = Field(None, title="Nome Completo", max_length=100)
    disabled: Optional[bool] = Field(None, title="Status Desativado")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "full_name": "User Test Updated Name",
                    "email": "usertest.updated@example.com",
                    "disabled": False
                },
                {
                    "password": "mynewverysecurepassword123"
                }
            ]
        }
    }

# --- Modelos para Representação no Banco de Dados e Respostas da API ---
class UserInDBBase(UserBase):
    """
    Modelo base para usuários como são armazenados e recuperados do banco de dados.
    Inclui campos gerenciados pelo sistema como ID, senha hasheada e timestamps.
    """
    id: uuid.UUID = Field(..., title="ID Único do Usuário")
    hashed_password: str = Field(..., title="Senha Hasheada")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), title="Data de Criação")
    updated_at: Optional[datetime] = Field(None, title="Data da Última Atualização")

    model_config = ConfigDict(from_attributes=True)

class User(UserBase):
    """
    Modelo de usuário utilizado nas respostas da API.
    Projetado para expor dados seguros do usuário, omitindo a senha hasheada.
    """
    id: uuid.UUID = Field(..., title="ID Único do Usuário")
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class UserInDB(UserInDBBase):
    """
    Representação completa de um usuário como armazenado no banco de dados.
    Inclui todos os campos (inclusive senha hasheada) e é usado internamente.
    """
    # Atualmente não adiciona campos além de UserInDBBase, mas serve para clareza.
    pass