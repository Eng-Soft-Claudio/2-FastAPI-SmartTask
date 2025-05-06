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

# ================================
# --- Modelos Pydantic de User ---
# ================================

# --- Modelo Base ---

class UserBase(BaseModel):
    """
    Modelo base contendo os atributos comuns a todas as variações de usuário.
    Define os campos que podem ser esperados na maioria das representações de um usuário.
    """
    # Endereço de e-mail do usuário, deve ser único.
    email: EmailStr = Field(..., title="Endereço de E-mail", description="Deve ser um e-mail válido e único.")
    # Nome de usuário único, usado para login. Restrito a caracteres alfanuméricos e underscore.
    username: str = Field(
        ...,
        title="Nome de Usuário",
        min_length=3,
        max_length=50,
        pattern="^[a-zA-Z0-9_]+$",
        description="Nome de usuário único (letras, números, underscore)."
    )
    # Nome completo opcional do usuário.
    full_name: Optional[str] = Field(None, title="Nome Completo", max_length=100)
    # Indica se a conta do usuário está desativada. Por padrão, usuários são criados como ativos (False).
    disabled: bool = Field(default=False, title="Status Desativado", description="Indica se o usuário está desativado.")

# --- Modelo para Criação de Usuário ---

class UserCreate(BaseModel):
    """
    Modelo para os dados necessários ao criar um novo usuário.
    Este é o formato esperado no payload da API para registro de usuários.
    """
    # E-mail para o novo usuário.
    email: EmailStr = Field(..., title="Endereço de E-mail")
    # Nome de usuário para o novo usuário.
    username: str = Field(..., title="Nome de Usuário", min_length=3, max_length=50, pattern="^[a-zA-Z0-9_]+$")
    # Senha para o novo usuário. Será hasheada antes de ser armazenada.
    password: str = Field(..., title="Senha", min_length=8, description="Senha (será hasheada antes de salvar).")
    # Nome completo opcional para o novo usuário.
    full_name: Optional[str] = Field(None, title="Nome Completo", max_length=100)

    # Configurações do modelo Pydantic, incluindo exemplos para OpenAPI.
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
    # Novo endereço de e-mail (opcional).
    email: Optional[EmailStr] = Field(None, title="Endereço de E-mail")
    # Nova senha (opcional). Deve atender aos requisitos de segurança.
    password: Optional[str] = Field(None, title="Nova Senha", min_length=8, description="Nova senha (se fornecida).")
    # Novo nome completo (opcional).
    full_name: Optional[str] = Field(None, title="Nome Completo", max_length=100)
    # Novo status de desativação (opcional).
    disabled: Optional[bool] = Field(None, title="Status Desativado")

    # Configurações do modelo Pydantic, incluindo exemplos para OpenAPI.
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
    # ID único universal do usuário, gerado no momento da criação.
    id: uuid.UUID = Field(..., title="ID Único do Usuário")
    # Senha do usuário armazenada de forma segura (hasheada).
    hashed_password: str = Field(..., title="Senha Hasheada")
    # Data e hora (UTC) em que o usuário foi criado, definida automaticamente.
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), title="Data de Criação")
    # Data e hora (UTC) da última atualização do usuário. Nulo se nunca atualizado.
    updated_at: Optional[datetime] = Field(None, title="Data da Última Atualização")

    # Configuração Pydantic para permitir que o modelo seja instanciado a partir
    # de atributos de objetos (útil para mapear dados de ORMs/ODMs).
    model_config = ConfigDict(from_attributes=True)

class User(UserBase):
    """
    Modelo de usuário utilizado nas respostas da API.
    Projetado para expor dados seguros do usuário, omitindo informações sensíveis como a senha hasheada.
    Herda os campos base e adiciona o ID e timestamps.
    """
    # ID único universal do usuário.
    id: uuid.UUID = Field(..., title="ID Único do Usuário")
    # Data e hora (UTC) de criação do usuário.
    created_at: datetime
    # Data e hora (UTC) da última atualização do usuário.
    updated_at: Optional[datetime] = None 

    # Configuração Pydantic.
    model_config = ConfigDict(from_attributes=True)

class UserInDB(UserInDBBase):
    """
    Representação completa de um usuário como armazenado no banco de dados.
    Este modelo inclui todos os campos, inclusive a senha hasheada, e é tipicamente
    usado internamente pela aplicação (camada de CRUD) e não exposto diretamente pela API.
    """
    # Atualmente, não adiciona campos além de UserInDBBase,
    # mas serve como um tipo explícito para clareza semântica.
    pass