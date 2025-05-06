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

# ===============================
# --- Modelos Pydantic Token ---
# ===============================

class Token(BaseModel):
    """
    Modelo de resposta para um token de acesso JWT.
    Este é o formato retornado ao cliente após uma autenticação bem-sucedida.
    """
    # O token JWT em si, que o cliente usará para autenticar requisições subsequentes.
    access_token: str = Field(..., title="Token de Acesso JWT")
    # Indica o tipo de token; por padrão e comumente, "bearer".
    token_type: str = Field(default="bearer", title="Tipo do Token")

class TokenPayload(BaseModel):
    """
    Modelo para os dados (payload/claims) contidos dentro de um token JWT.
    Representa as informações decodificadas do token.
    """
    # O "subject" (assunto) do token, tipicamente o ID único do usuário.
    sub: uuid.UUID = Field(..., title="ID do Usuário (Subject)")
    # O nome de usuário associado ao token, pode ser usado para display ou identificação.
    username: str = Field(..., title="Nome de Usuário")
    # Opcional: timestamp Unix indicando o tempo de expiração do token (claim 'exp' padrão do JWT).
    # Geralmente gerenciado pela biblioteca de JWT durante a criação e validação do token.
    exp: Optional[int] = Field(None, title="Timestamp de Expiração")