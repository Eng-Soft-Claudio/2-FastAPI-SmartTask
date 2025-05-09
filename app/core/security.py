# app/core/security.py

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
from app.core.config import settings 
from app.models.token import TokenPayload 

# ===============================
# --- Configuração do Logger ---
# ===============================
logger = logging.getLogger(__name__)

# ==========================================
# --- Configuração Hashing de Senha ---
# ==========================================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# =========================
# --- Constantes JWT ---
# =========================
ALGORITHM = settings.JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

# ================================
# --- Funções de Senha ---
# ================================
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifica se uma senha em texto plano corresponde a um hash armazenado.

    Usa o contexto do passlib (`pwd_context`) para comparar a senha
    com o hash de forma segura.

    Args:
        plain_password: A senha fornecida pelo usuário.
        hashed_password: O hash da senha armazenado no banco de dados.

    Returns:
        True se a senha corresponder ao hash, False caso contrário (incluindo
        se o formato do hash for inválido).
    """
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except ValueError:
        logger.warning("Tentativa de verificar senha com hash em formato inválido.")
        return False

def get_password_hash(password: str) -> str:
    """
    Gera um hash seguro (bcrypt) para uma senha fornecida.

    Args:
        password: A senha em texto plano a ser hasheada.

    Returns:
        A string do hash bcrypt gerado (incluindo salt e metadados).
    """
    return pwd_context.hash(password)

# =========================
# --- Funções JWT ---
# =========================

def create_access_token(
    subject: Union[str, Any], 
    username: str,
    expires_delta: Optional[timedelta] = None 
) -> str:
    """
    Cria um novo token de acesso JWT, codificando 'subject' (ID do usuário)
    e 'username' no payload, com um tempo de expiração definido.

    Args:
        subject: O identificador único do usuário (convertido para string).
                 Normalmente o ID do usuário (ex: UUID).
        username: O nome de usuário, incluído no payload.
        expires_delta: Duração opcional para a validade do token.
                       Se None, usa o padrão `ACCESS_TOKEN_EXPIRE_MINUTES`.

    Returns:
        O token JWT codificado como uma string.
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
    Decodifica e valida um token JWT.

    Verifica a assinatura, a expiração e a estrutura do payload usando o modelo Pydantic.
    A verificação de expiração padrão do jwt.decode é desabilitada para que
    a lógica de verificação dupla de expiração seja testada e executada.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"verify_exp": False}  
        )
        token_data = TokenPayload.model_validate(payload) 
        if token_data.exp is not None:
            token_expiration_time = datetime.fromtimestamp(token_data.exp, tz=timezone.utc)
            if datetime.now(timezone.utc) > token_expiration_time:
                logger.info("Token JWT expirado (verificação dupla).") 
                return None
        else:
            pass
        return token_data
    except ExpiredSignatureError: 
        logger.warning("Token JWT detectado como expirado pela biblioteca JOSE antes da verificação dupla.") 
        return None 
    except (JWTError, ValidationError, KeyError) as e: 
        logger.error(f"Erro ao decodificar/validar token: {e}", exc_info=True)
        return None