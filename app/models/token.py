# app/models/token.py
"""
Este módulo define os modelos Pydantic relacionados à autenticação por token,
especificamente para a estrutura do token JWT retornado ao cliente e
para o payload contido dentro do token JWT.
"""

# ========================
# --- Importações ---
# ========================
import uuid
from typing import Optional

from pydantic import BaseModel, Field

# ========================
# --- Modelos Pydantic Token ---
# ========================
class Token(BaseModel):
    """
    Modelo de resposta para um token de acesso JWT.
    Este é o formato retornado ao cliente após uma autenticação bem-sucedida.
    """
    access_token: str = Field(..., title="Token de Acesso JWT")
    token_type: str = Field(default="bearer", title="Tipo do Token")

class TokenPayload(BaseModel):
    """
    Modelo para os dados (payload/claims) contidos dentro de um token JWT.
    Representa as informações decodificadas do token.
    """
    sub: uuid.UUID = Field(..., title="ID do Usuário (Subject)")
    username: str = Field(..., title="Nome de Usuário")
    exp: Optional[int] = Field(None, title="Timestamp de Expiração")