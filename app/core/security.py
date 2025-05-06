# app/core/security.py

# ========================
# --- Importações ---
# ========================
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Union, Optional
from passlib.context import CryptContext 
from jose import jwt, JWTError 
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
# Define o contexto do passlib para hashing de senhas.
# - schemes=["bcrypt"]: Usa bcrypt como o algoritmo padrão e preferido.
# - deprecated="auto": Automaticamente atualiza hashes antigos (se houver)
#   para bcrypt quando uma senha for verificada com sucesso (ex: durante o login).
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# =========================
# --- Constantes JWT ---
# =========================
# Algoritmo de assinatura JWT (lido das configurações)
ALGORITHM = settings.JWT_ALGORITHM
# Tempo de expiração padrão para tokens de acesso (lido das configurações)
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
        # passlib compara a senha com o hash, levando em conta o salt
        return pwd_context.verify(plain_password, hashed_password)
    except ValueError:
        # Ocorre se 'hashed_password' não for um formato reconhecido pelo pwd_context
        logger.warning("Tentativa de verificar senha com hash em formato inválido.")
        return False
    # Considerar capturar outras exceções potenciais do passlib se necessário

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
    # Define o tempo de expiração: usa o delta fornecido ou o padrão das settings
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    # Garante que o subject seja uma string para o payload JWT
    subject_str = str(subject)

    # Payload a ser codificado no token
    to_encode = {
        "exp": expire,     
        "sub": subject_str,
        "username": username 
        # Pode-se adicionar outros claims aqui, se necessário
    }

    # Codifica o payload usando a chave secreta e algoritmo das settings
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_token(token: str) -> Optional[TokenPayload]:
    """
    Decodifica e valida um token JWT.

    Verifica a assinatura, a expiração e a estrutura do payload usando o modelo Pydantic.

    Args:
        token: A string do token JWT recebida (ex: do header Authorization).

    Returns:
        Um objeto `TokenPayload` contendo os dados validados (`sub`, `username`, `exp`)
        se o token for válido e não expirado. Retorna `None` se a decodificação
        ou validação falhar por qualquer motivo (assinatura inválida, expirado,
        formato inválido, payload não conforma com `TokenPayload`).
    """
    try:
        # Tenta decodificar o token usando a chave secreta e o algoritmo esperado.
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[ALGORITHM] 
        )

        # Valida a estrutura e os tipos do payload usando o modelo Pydantic
        token_data = TokenPayload.model_validate(payload)

        # Verificação adicional explícita de expiração (redundante mas seguro)
        if token_data.exp is not None:
            if datetime.now(timezone.utc) > datetime.fromtimestamp(token_data.exp, tz=timezone.utc):
                logger.info("Token JWT expirado (verificação dupla).")
                return None
        return token_data

    # Captura erros específicos da biblioteca JWT (assinatura, formato)
    # Captura erros de validação do Pydantic (campos/tipos incorretos no payload)
    # Captura KeyError se campos esperados faltarem no payload (antes da validação Pydantic)
    except (JWTError, ValidationError, KeyError) as e:
        logger.error(f"Erro ao decodificar/validar token: {e}", exc_info=True)
        # Retorna None para indicar falha na validação/decodificação
        return None