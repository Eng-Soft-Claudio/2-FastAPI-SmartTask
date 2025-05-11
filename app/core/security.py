# app/core/security.py
"""
Módulo responsável pelas funcionalidades de segurança da aplicação,
incluindo hashing de senhas e gerenciamento de tokens JWT (JSON Web Token)
para autenticação e autorização.
"""

# ========================
# --- Importações ---
# ========================
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Union, Optional
from passlib.context import CryptContext
from jose import ExpiredSignatureError, jwt, JWTError
from pydantic import ValidationError

# --- Módulos da Aplicação ---
from core.config import settings
from models.token import TokenPayload

# ========================
# --- Configuração do Logger ---
# ========================
logger = logging.getLogger(__name__)

# ========================
# --- Configuração Hashing de Senha ---
# ========================
# Contexto Passlib para hashing e verificação de senhas usando bcrypt.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ========================
# --- Constantes JWT ---
# ========================
ALGORITHM = settings.JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

# ========================
# --- Funções de Senha ---
# ========================
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifica se uma senha em texto plano corresponde a um hash armazenado.

    Args:
        plain_password: A senha fornecida pelo usuário (texto plano).
        hashed_password: O hash da senha armazenado.

    Returns:
        True se a senha corresponder ao hash, False caso contrário.
    """
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except ValueError:
        # Ocorre se o formato do hash for inválido para o passlib
        logger.warning("Tentativa de verificar senha com hash em formato inválido.")
        return False

def get_password_hash(password: str) -> str:
    """
    Gera um hash seguro (bcrypt) para uma senha fornecida.

    Args:
        password: A senha em texto plano a ser hasheada.

    Returns:
        A string do hash bcrypt gerado.
    """
    return pwd_context.hash(password)

# ========================
# --- Funções JWT ---
# ========================
def create_access_token(
    subject: Union[str, Any],
    username: str,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Cria um novo token de acesso JWT.

    Args:
        subject: Identificador único do usuário (normalmente ID).
        username: Nome de usuário.
        expires_delta: Duração opcional para a validade do token.
                       Se None, usa o padrão `ACCESS_TOKEN_EXPIRE_MINUTES`.

    Returns:
        O token JWT codificado como uma string.
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    subject_str = str(subject) # Garante que 'sub' seja string no payload

    to_encode = {
        "exp": expire,
        "sub": subject_str,
        "username": username
    }
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_token(token: str) -> Optional[TokenPayload]:
    """
    Decodifica e valida um token JWT.

    Verifica assinatura, expiração e estrutura do payload (via Pydantic).
    A verificação de expiração padrão do `jwt.decode` é desabilitada
    para que a lógica de verificação dupla de expiração seja executada.

    Args:
        token: A string do token JWT.

    Returns:
        Objeto TokenPayload se o token for válido e não expirado, None caso contrário.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"verify_exp": False} # Desabilita verif. de expiração da lib JWT
        )
        # Valida o payload contra o modelo Pydantic TokenPayload
        token_data = TokenPayload.model_validate(payload)

        # Verificação dupla da expiração
        if token_data.exp is not None:
            token_expiration_time = datetime.fromtimestamp(token_data.exp, tz=timezone.utc)
            if datetime.now(timezone.utc) > token_expiration_time:
                logger.info("Token JWT expirado (verificação dupla).")
                return None
        else:
            # Se 'exp' é opcional no TokenPayload e está ausente
            pass # Tratar como válido neste ponto, se permitido pelo modelo.
                 # Se 'exp' for obrigatório no TokenPayload, model_validate já falharia.
        return token_data
    except ExpiredSignatureError:
        # Este bloco seria alcançado se options={"verify_exp": True} fosse usado
        # e a própria lib jose pegasse a expiração, ou outro erro inesperado da lib.
        logger.warning("Token JWT detectado como expirado pela biblioteca JOSE antes da verificação dupla.")
        return None
    except (JWTError, ValidationError, KeyError) as e:
        # Captura erros de assinatura/formato JWT, erros de validação Pydantic do payload,
        # ou ausência de chaves esperadas se a validação Pydantic não for suficiente.
        logger.error(f"Erro ao decodificar/validar token: {e}", exc_info=True)
        return None