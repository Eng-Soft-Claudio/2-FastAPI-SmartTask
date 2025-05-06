# tests/test_core_dependencies.py
import pytest
import uuid
from fastapi import HTTPException, status
from unittest.mock import AsyncMock, MagicMock, patch
from app.core.dependencies import get_current_user, get_current_active_user, oauth2_scheme
from app.db import user_crud 
from app.models.user import UserInDB 
from app.models.token import TokenPayload
from datetime import datetime, timezone

pytestmark = pytest.mark.asyncio

# Mock para o DB Dependency (DbDep)
@pytest.fixture
def mock_db():
    return AsyncMock()

# Mock para o Token Dependency (TokenDep)
@pytest.fixture
def mock_valid_token_str():
    return "valid.test.token"

# ===================================================
# --- Testes para get_current_user ---
# ===================================================

async def test_get_current_user_success(mock_db, mock_valid_token_str):
    """Testa get_current_user com token e usuário válidos."""
    test_user_id = uuid.uuid4()
    test_username = "testuser"
    test_user = UserInDB(
        id=test_user_id,
        username=test_username,
        email="test@example.com",
        hashed_password="xxx",
        disabled=False,
        created_at=datetime.now(timezone.utc)
    )
    test_payload = TokenPayload(sub=test_user_id, username=test_username)

    # Mockar decode_token para retornar payload válido
    with patch("app.core.dependencies.decode_token", return_value=test_payload) as mock_decode:
        # Mockar get_user_by_id para retornar o usuário
        with patch("app.core.dependencies.user_crud.get_user_by_id", return_value=test_user) as mock_get_id:
            # Chama a dependência 
            user = await get_current_user(db=mock_db, token=mock_valid_token_str)

            mock_decode.assert_called_once_with(mock_valid_token_str)
            mock_get_id.assert_awaited_once_with(db=mock_db, user_id=test_user_id)
            assert user == test_user

async def test_get_current_user_invalid_token(mock_db, mock_valid_token_str):
    """Testa get_current_user quando decode_token falha (token inválido/expirado)."""
    # Mockar decode_token para retornar None
    with patch("app.core.dependencies.decode_token", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(db=mock_db, token=mock_valid_token_str)
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Não foi possível validar as credenciais" in exc_info.value.detail

async def test_get_current_user_user_not_found(mock_db, mock_valid_token_str):
    """Testa get_current_user quando o usuário do token não existe no DB."""
    test_user_id = uuid.uuid4()
    test_payload = TokenPayload(sub=test_user_id, username="ghost")

    # Mock decode_token para retornar payload válido
    with patch("app.core.dependencies.decode_token", return_value=test_payload):
         # Mock get_user_by_id para retornar None
        with patch("app.core.dependencies.user_crud.get_user_by_id", return_value=None) as mock_get_id:
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(db=mock_db, token=mock_valid_token_str)
            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "Não foi possível validar as credenciais" in exc_info.value.detail
            mock_get_id.assert_awaited_once_with(db=mock_db, user_id=test_user_id)

# ===================================================
# --- Testes para get_current_active_user ---
# ===================================================

async def test_get_current_active_user_disabled():
    """Testa get_current_active_user com um usuário desativado."""
    disabled_user = UserInDB(
        id=uuid.uuid4(),
        username="inactive",
        email="inactive@x.com",
        hashed_password="...",
        disabled=True,
        created_at=datetime.now(timezone.utc)
    )
    # Chama a função diretamente, passando o usuário desativado
    with pytest.raises(HTTPException) as exc_info:
        await get_current_active_user(current_user=disabled_user) 
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Usuário inativo" in exc_info.value.detail

async def test_get_current_active_user_active():
    """Testa get_current_active_user com um usuário ativo."""
    active_user = UserInDB(
        id=uuid.uuid4(),
        username="active",
        email="active@x.com",
        hashed_password="...",
        disabled=False,
        created_at=datetime.now(timezone.utc)
    )
    # Chama a função e verifica se retorna o mesmo usuário
    user = await get_current_active_user(current_user=active_user)
    assert user == active_user