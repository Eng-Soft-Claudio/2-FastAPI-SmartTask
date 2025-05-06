# app/core/security.py
from datetime import datetime, timedelta, timezone
from typing import Any, Union, Optional
from passlib.context import CryptContext
from jose import jwt, JWTError
from pydantic import ValidationError 
import logging
from app.core.config import settings 
from app.models.token import TokenPayload

# Logger
logger = logging.getLogger(__name__)

# ===================================================
# --- Configuração do Hashing de Senha ---
# ===================================================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = settings.JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica se a senha fornecida corresponde à senha hasheada."""
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except ValueError: # Pode ocorrer se o hash não for reconhecido
         return False


def get_password_hash(password: str) -> str:
    """Gera o hash de uma senha usando bcrypt."""
    return pwd_context.hash(password)

# ===================================================
# --- Funções JWT ---
# ===================================================

def create_access_token(subject: Union[str, Any],
                        username: str,
                        expires_delta: Optional[timedelta] = None
                        ) -> str:
    """
    Cria um novo token de acesso JWT.

    Args:
        subject: O identificador único do sujeito do token (ex: user ID ou username).
        expires_delta: Tempo de vida do token. Se None, usa o padrão das configurações.

    Returns:
        O token JWT codificado como string.
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    subject_str = str(subject)

    to_encode = {
        "exp": expire,
        "sub": subject_str, 
        "username": username 
    }


    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_token(token: str) -> Optional[TokenPayload]:
    """
    Decodifica um token JWT e valida seu conteúdo.
    Args:
        token: O token JWT string.
    Returns:
        Um objeto TokenPayload com os dados do token se válido, None caso contrário.
    """
    try:
        # Decodifica o token
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        token_data = TokenPayload.model_validate(payload)

        if token_data.exp is not None:
             if datetime.now(timezone.utc) > datetime.fromtimestamp(token_data.exp, tz=timezone.utc):
                 return None # Ou trate como inválido

        return token_data

    except (JWTError, ValidationError, KeyError) as e:
        logger.error(f"Erro ao decodificar/validar token: {e}", exc_info=True)
        return None