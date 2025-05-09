# tests/test_core_dependencies.py
"""
Este módulo contém testes unitários para as dependências de segurança
definidas em `app.core.dependencies`.

As dependências testadas são:
- `get_current_user`: Responsável por decodificar o token JWT, validar o payload
  e buscar o usuário correspondente no banco de dados.
- `get_current_active_user`: Uma dependência que consome o resultado de
  `get_current_user` e verifica se o usuário não está desativado.

Os testes utilizam mocks para isolar as dependências de chamadas reais
ao banco de dados ou funções de decodificação de token.
"""

# ========================
# --- Importações ---
# ========================
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import HTTPException, status

# --- Módulos da Aplicação ---
from app.core.dependencies import (get_current_active_user, get_current_user,
                                   oauth2_scheme) # oauth2_scheme não usado diretamente nos testes, mas mantido
from app.models.token import TokenPayload
from app.models.user import UserInDB

# ========================
# --- Marcador Global de Teste ---
# ========================
pytestmark = pytest.mark.asyncio

# ========================
# --- Fixtures para Mocks Comuns ---
# ========================
@pytest.fixture
def mock_db() -> AsyncMock:
    """
    Fixture que retorna um `AsyncMock` para simular a dependência do banco de dados (`DbDep`).
    """
    return AsyncMock()

@pytest.fixture
def mock_valid_token_str() -> str:
    """
    Fixture que retorna uma string de token JWT mockada e válida.
    """
    return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"

# ========================
# --- Testes para a dependência `get_current_user` ---
# ========================
async def test_get_current_user_success(
    mock_db: AsyncMock,
    mock_valid_token_str: str
):
    """
    Testa o cenário de sucesso para `get_current_user`.

    Verifica se:
    - `decode_token` é chamado corretamente com o token fornecido.
    - `user_crud.get_user_by_id` é chamado com o ID do usuário do payload do token.
    - A função retorna o objeto `UserInDB` esperado.
    """
    # --- Arrange ---
    test_user_id = uuid.uuid4()
    test_username = "test_active_user"
    expected_user_obj = UserInDB(
        id=test_user_id,
        username=test_username,
        email="testuser@example.com",
        hashed_password="fake_hashed_password",
        disabled=False,
        created_at=datetime.now(timezone.utc)
    )
    mock_token_payload = TokenPayload(sub=test_user_id, username=test_username)

    with patch("app.core.dependencies.decode_token", return_value=mock_token_payload) as mock_decode_jwt, \
         patch("app.core.dependencies.user_crud.get_user_by_id", return_value=expected_user_obj) as mock_get_user:

        # --- Act ---
        retrieved_user = await get_current_user(db=mock_db, token=mock_valid_token_str)

        # --- Assert ---
        mock_decode_jwt.assert_called_once_with(mock_valid_token_str)
        mock_get_user.assert_awaited_once_with(db=mock_db, user_id=test_user_id)
        assert retrieved_user == expected_user_obj, "Usuário retornado não é o esperado."


async def test_get_current_user_invalid_or_expired_token(
    mock_db: AsyncMock,
    mock_valid_token_str: str
):
    """
    Testa `get_current_user` quando `decode_token` falha (retorna None),
    simulando um token JWT inválido, malformado ou expirado.

    Verifica se:
    - Uma `HTTPException` com status 401 é levantada.
    - A mensagem de detalhe da exceção é a esperada.
    """
    # --- Arrange ---
    with patch("app.core.dependencies.decode_token", return_value=None) as mock_decode_jwt:

        # --- Act & Assert ---
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(db=mock_db, token=mock_valid_token_str)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED, "Status code não é 401."
        assert "Não foi possível validar as credenciais" in exc_info.value.detail, \
            "Mensagem de detalhe da exceção não é a esperada."
        mock_decode_jwt.assert_called_once_with(mock_valid_token_str)

async def test_get_current_user_user_not_found_in_db(
    mock_db: AsyncMock,
    mock_valid_token_str: str
):
    """
    Testa `get_current_user` quando o token é válido e decodificado com sucesso,
    mas o ID de usuário (sub) contido no payload do token não corresponde
    a nenhum usuário no banco de dados.

    Verifica se:
    - Uma `HTTPException` com status 401 é levantada.
    - A mensagem de detalhe da exceção é a esperada.
    - `user_crud.get_user_by_id` é chamado.
    """
    # --- Arrange ---
    test_user_id_not_in_db = uuid.uuid4()
    mock_token_payload = TokenPayload(sub=test_user_id_not_in_db, username="ghost_user")

    with patch("app.core.dependencies.decode_token", return_value=mock_token_payload) as mock_decode_jwt, \
         patch("app.core.dependencies.user_crud.get_user_by_id", return_value=None) as mock_get_user:

        # --- Act & Assert ---
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(db=mock_db, token=mock_valid_token_str)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED, "Status code não é 401."
        assert "Não foi possível validar as credenciais" in exc_info.value.detail, \
            "Mensagem de detalhe da exceção não é a esperada para usuário não encontrado."
        mock_decode_jwt.assert_called_once_with(mock_valid_token_str)
        mock_get_user.assert_awaited_once_with(db=mock_db, user_id=test_user_id_not_in_db)

# ========================
# --- Testes para a dependência `get_current_active_user` ---
# ========================
async def test_get_current_active_user_when_user_is_disabled():
    """
    Testa `get_current_active_user` passando um objeto `UserInDB`
    que representa um usuário desativado (`disabled=True`).

    Verifica se:
    - Uma `HTTPException` com status 400 Bad Request é levantada.
    - A mensagem de detalhe da exceção indica "Usuário inativo".
    """
    # --- Arrange ---
    disabled_user_mock = UserInDB(
        id=uuid.uuid4(),
        username="inactive_user",
        email="inactive@example.com",
        hashed_password="fake_hashed_password",
        disabled=True,
        created_at=datetime.now(timezone.utc)
    )

    # --- Act & Assert ---
    with pytest.raises(HTTPException) as exc_info:
        await get_current_active_user(current_user=disabled_user_mock)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST, "Status code não é 400."
    assert "Usuário inativo" in exc_info.value.detail, "Mensagem de detalhe da exceção não é 'Usuário inativo'."


async def test_get_current_active_user_when_user_is_active():
    """
    Testa `get_current_active_user` passando um objeto `UserInDB`
    que representa um usuário ativo (`disabled=False`).

    Verifica se:
    - A função retorna o mesmo objeto de usuário que foi passado.
    - Nenhuma exceção é levantada.
    """
    # --- Arrange ---
    active_user_mock = UserInDB(
        id=uuid.uuid4(),
        username="active_user",
        email="active_user@example.com",
        hashed_password="fake_hashed_password",
        disabled=False,
        created_at=datetime.now(timezone.utc)
    )

    # --- Act ---
    returned_user = await get_current_active_user(current_user=active_user_mock)

    # --- Assert ---
    assert returned_user == active_user_mock, "Usuário ativo retornado não é o mesmo que foi passado."


async def test_get_current_user_invalid_sub_uuid_format(mock_db, mock_valid_token_str, mocker): # type: ignore
    """
    Testa get_current_user quando o 'sub' no token não é um UUID válido.
    """
    # --- Arrange ---
    invalid_sub_str = "not-a-uuid-at-all"
    # No seu código original, mock_payload_dict não era usado, mas sim mock_token_payload_obj
    mock_token_payload_obj = MagicMock()
    mock_token_payload_obj.sub = invalid_sub_str # O atributo 'sub' tem a string inválida

    mock_decode = mocker.patch("app.core.dependencies.decode_token", return_value=mock_token_payload_obj)
    mock_get_user = mocker.patch("app.core.dependencies.user_crud.get_user_by_id", new_callable=AsyncMock)

    # --- Act & Assert ---
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(db=mock_db, token=mock_valid_token_str)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Não foi possível validar as credenciais" in exc_info.value.detail

    mock_decode.assert_called_once_with(mock_valid_token_str)
    mock_get_user.assert_not_called()