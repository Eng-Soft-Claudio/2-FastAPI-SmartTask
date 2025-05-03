# app/models/user.py
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import Optional
import uuid
from datetime import datetime, timezone

class UserBase(BaseModel):
    """Campos base para um usuário."""
    email: EmailStr = Field(..., title="Endereço de E-mail", description="Deve ser um e-mail válido e único.")
    username: str = Field(..., title="Nome de Usuário", min_length=3, max_length=50, pattern="^[a-zA-Z0-9_]+$", description="Nome de usuário único (letras, números, underscore).")
    full_name: Optional[str] = Field(None, title="Nome Completo", max_length=100)
    disabled: bool = Field(default=False, title="Status Desativado", description="Indica se o usuário está desativado.")

class UserCreate(BaseModel):
    """Campos necessários para criar um novo usuário (recebido pela API)."""
    email: EmailStr = Field(..., title="Endereço de E-mail")
    username: str = Field(..., title="Nome de Usuário", min_length=3, max_length=50, pattern="^[a-zA-Z0-9_]+$")
    password: str = Field(..., title="Senha", min_length=8, description="Senha (será hasheada antes de salvar).")
    full_name: Optional[str] = Field(None, title="Nome Completo", max_length=100)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "email": "johndoe@example.com",
                    "username": "johndoe",
                    "password": "averysecurepassword",
                    "full_name": "John Doe"
                }
            ]
        }
    }

class UserUpdate(BaseModel):
    """Campos que podem ser atualizados para um usuário."""
    email: Optional[EmailStr] = Field(None, title="Endereço de E-mail")
    full_name: Optional[str] = Field(None, title="Nome Completo", max_length=100)
    disabled: Optional[bool] = Field(None, title="Status Desativado")
    # Não permitimos atualizar username ou senha por este modelo geralmente
    # Senha teria um endpoint/processo separado

class UserInDBBase(UserBase):
    """Modelo de usuário como armazenado no banco, incluindo ID e senha hasheada."""
    id: uuid.UUID = Field(..., title="ID Único do Usuário")
    hashed_password: str = Field(..., title="Senha Hasheada")
    created_at: datetime = Field(default_factory=datetime.now(timezone.utc), title="Data de Criação")
    updated_at: Optional[datetime] = Field(None, title="Data da Última Atualização")

    # Configuração Pydantic v2 para permitir criação a partir de atributos de objeto (ex: do MongoDB)
    model_config = ConfigDict(from_attributes=True)

# Modelo que será retornado pela API (não inclui senha hasheada)
class User(UserBase):
    """Modelo de usuário para respostas da API (sem senha)."""
    id: uuid.UUID = Field(..., title="ID Único do Usuário")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), title="Data de Criação")
    updated_at: Optional[datetime] = Field(None, title="Data da Última Atualização")

    model_config = ConfigDict(from_attributes=True)

# Modelo para representar o usuário armazenado completamente no DB (para uso interno)
class UserInDB(UserInDBBase):
   pass