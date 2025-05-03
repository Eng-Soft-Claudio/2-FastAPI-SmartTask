# app/models/token.py
from pydantic import BaseModel, Field
from typing import Optional
import uuid

class Token(BaseModel):
    """Modelo para a resposta do token JWT."""
    access_token: str = Field(..., title="Token de Acesso JWT")
    token_type: str = Field(default="bearer", title="Tipo do Token")

class TokenPayload(BaseModel):
    """Modelo para os dados contidos no payload do JWT."""
    sub: uuid.UUID = Field(..., title="ID do Usuário (Subject)")
    username: str = Field(..., title="Nome de Usuário")
    exp: Optional[int] = Field(None, title="Timestamp de Expiração")
