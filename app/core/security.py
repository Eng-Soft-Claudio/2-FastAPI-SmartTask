# app/core/security.py
from datetime import datetime, timedelta, timezone
from typing import Any, Union, Optional
from passlib.context import CryptContext
from jose import jwt, JWTError
from pydantic import ValidationError # Para erros de validação de token

from app.core.config import settings # Importa configurações (SECRET_KEY, etc.)
from app.models.token import TokenPayload # Modelo para dados do payload

# --- Configuração do Hashing de Senha ---
# Define o contexto do passlib, especificando os esquemas de hash permitidos
# 'bcrypt' será o padrão para novas senhas. Outros são para senhas legadas (se houver)
# 'deprecated="auto"' significa que senhas com esquemas antigos serão automaticamente atualizadas para bcrypt no login
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

# --- Funções JWT ---

def create_access_token(subject: Union[str, Any],username: str, expires_delta: Optional[timedelta] = None) -> str:
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

    # Garante que o subject (ID do usuário) seja uma string para o JWT
    # Embora Any seja aceito, geralmente é um ID (UUID, int, str)
    subject_str = str(subject)

    to_encode = {
        "exp": expire,
        "sub": subject_str, # User ID
        "username": username # Username
    }

    # Adicione outros dados ao payload se necessário (cuidado com o tamanho do token)
    # to_encode.update({"username": username_do_subject})

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

        # Extrai os dados esperados (subject/user_id)
        # subject = payload.get("sub") # 'sub' é o id do usuário (UUID string)
        # username = payload.get("username") # Se incluímos o username no token

        # if subject is None: # or username is None:
        #     return None

        # Valida os dados do payload com o modelo Pydantic
        # Isso garante que os tipos e campos esperados estejam presentes
        token_data = TokenPayload.model_validate(payload)

        # Verifica se o token expirou (embora jwt.decode geralmente faça isso)
        if token_data.exp is not None:
             if datetime.now(timezone.utc) > datetime.fromtimestamp(token_data.exp, tz=timezone.utc):
                 # Poderia levantar uma exceção específica de expiração aqui
                 return None # Ou trate como inválido

        # Aqui poderíamos converter o 'sub' (string UUID) de volta para UUID se necessário
        # try:
        #     token_data.sub = uuid.UUID(token_data.sub)
        # except ValueError:
        #     return None # ID inválido no token

        return token_data

    except (JWTError, ValidationError, KeyError) as e:
        # Logar o erro `e` aqui seria útil para depuração
        print(f"Erro ao decodificar token: {e}") # Log de erro simples
        return None