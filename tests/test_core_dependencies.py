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
from unittest.mock import AsyncMock, patch 
import pytest
from fastapi import HTTPException, status

# --- Módulos da Aplicação ---
# Import oauth2_scheme mesmo que não seja diretamente chamado nos testes,
# pois faz parte da assinatura de get_current_user que estamos testando indiretamente.
from app.core.dependencies import (get_current_active_user, get_current_user,
                                   oauth2_scheme)
from app.models.token import TokenPayload
from app.models.user import UserInDB

# ====================================
# --- Marcador Global de Teste ---
# ====================================
pytestmark = pytest.mark.asyncio

# ========================================
# --- Fixtures para Mocks Comuns ---
# ========================================

@pytest.fixture
def mock_db() -> AsyncMock:
    """
    Fixture que retorna um `AsyncMock` para simular a dependência do banco de dados (`DbDep`).
    Isso permite testar as funções de dependência sem uma conexão real com o banco.
    """
    print("  Fixture: Criando mock_db (AsyncMock)")
    return AsyncMock()

@pytest.fixture
def mock_valid_token_str() -> str:
    """
    Fixture que retorna uma string de token JWT mockada e válida.
    O conteúdo real do token não importa aqui, pois `decode_token` será mockado.
    """
    print("  Fixture: Fornecendo mock_valid_token_str")
    return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"

# ===================================================
# --- Testes para a dependência `get_current_user` ---
# ===================================================

async def test_get_current_user_success(
    mock_db: AsyncMock, # Mock da dependência do banco de dados.
    mock_valid_token_str: str # Mock da string do token.
):
    """
    Testa o cenário de sucesso para `get_current_user`.

    Verifica se:
    - `decode_token` é chamado corretamente com o token fornecido.
    - `user_crud.get_user_by_id` é chamado com o ID do usuário do payload do token.
    - A função retorna o objeto `UserInDB` esperado.
    """
    test_user_id = uuid.uuid4()
    test_username = "test_active_user"
    # Prepara um objeto UserInDB mockado que esperamos que seja retornado.
    expected_user_obj = UserInDB(
        id=test_user_id,
        username=test_username,
        email="testuser@example.com",
        hashed_password="fake_hashed_password",
        disabled=False,
        created_at=datetime.now(timezone.utc)
    )
    # Prepara um payload de token mockado.
    mock_token_payload = TokenPayload(sub=test_user_id, username=test_username)
    
    print(f"\nTeste: get_current_user com token válido e usuário existente (ID: {test_user_id}).")

    # --- Arrange: Mockar as funções dependentes ---
    # Mocka `decode_token` para retornar o payload mockado.
    # Mocka `user_crud.get_user_by_id` para retornar o usuário esperado.
    with patch("app.core.dependencies.decode_token", return_value=mock_token_payload) as mock_decode_jwt, \
         patch("app.core.dependencies.user_crud.get_user_by_id", return_value=expected_user_obj) as mock_get_user:
        
        print(f"  Chamando get_current_user com token: '{mock_valid_token_str[:20]}...'")
        # --- Act: Chamar a dependência `get_current_user` ---
        # A dependência `oauth2_scheme` é normalmente injetada pela FastAPI,
        # mas como estamos testando a função `get_current_user` diretamente,
        # o `token` que ela recebe é o resultado dessa dependência (a string do token).
        retrieved_user = await get_current_user(db=mock_db, token=mock_valid_token_str)

        # --- Assert: Verificar chamadas e resultado ---
        print(f"  Usuário recuperado: {retrieved_user.username if retrieved_user else 'None'}")
        mock_decode_jwt.assert_called_once_with(mock_valid_token_str)
        mock_get_user.assert_awaited_once_with(db=mock_db, user_id=test_user_id)
        assert retrieved_user == expected_user_obj, "Usuário retornado não é o esperado."
        print("  Sucesso: get_current_user retornou o usuário correto.")


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
    print("\nTeste: get_current_user com token JWT inválido/expirado.")

    # --- Arrange: Mockar `decode_token` para simular falha na decodificação ---
    with patch("app.core.dependencies.decode_token", return_value=None) as mock_decode_jwt:
        print(f"  Mockando decode_token para retornar None.")
        # --- Act & Assert: Chamar a dependência e verificar a exceção ---
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(db=mock_db, token=mock_valid_token_str)
        
        # Verifica os detalhes da exceção HTTP.
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED, "Status code não é 401."
        assert "Não foi possível validar as credenciais" in exc_info.value.detail, \
            "Mensagem de detalhe da exceção não é a esperada."
        mock_decode_jwt.assert_called_once_with(mock_valid_token_str)
        print("  Sucesso: HTTPException 401 levantada para token inválido/expirado.")


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
    test_user_id_not_in_db = uuid.uuid4()
    mock_token_payload = TokenPayload(sub=test_user_id_not_in_db, username="ghost_user")
    
    print(f"\nTeste: get_current_user com usuário (ID: {test_user_id_not_in_db}) não encontrado no DB.")

    # --- Arrange: Mockar `decode_token` para retornar um payload válido,
    #              e `user_crud.get_user_by_id` para retornar None (usuário não encontrado). ---
    with patch("app.core.dependencies.decode_token", return_value=mock_token_payload) as mock_decode_jwt, \
         patch("app.core.dependencies.user_crud.get_user_by_id", return_value=None) as mock_get_user:
        
        print(f"  Mockando user_crud.get_user_by_id para retornar None.")
        # --- Act & Assert: Chamar a dependência e verificar a exceção ---
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(db=mock_db, token=mock_valid_token_str)

        # Verifica os detalhes da exceção HTTP e as chamadas aos mocks.
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED, "Status code não é 401."
        assert "Não foi possível validar as credenciais" in exc_info.value.detail, \
            "Mensagem de detalhe da exceção não é a esperada para usuário não encontrado."
        mock_decode_jwt.assert_called_once_with(mock_valid_token_str)
        mock_get_user.assert_awaited_once_with(db=mock_db, user_id=test_user_id_not_in_db)
        print("  Sucesso: HTTPException 401 levantada para usuário não encontrado no DB.")

# =========================================================
# --- Testes para a dependência `get_current_active_user` ---
# =========================================================

async def test_get_current_active_user_when_user_is_disabled():
    """
    Testa `get_current_active_user` passando um objeto `UserInDB`
    que representa um usuário desativado (`disabled=True`).

    Verifica se:
    - Uma `HTTPException` com status 400 Bad Request é levantada.
    - A mensagem de detalhe da exceção indica "Usuário inativo".
    """
    # Cria um mock de usuário desativado.
    disabled_user_mock = UserInDB(
        id=uuid.uuid4(),
        username="inactive_user",
        email="inactive@example.com",
        hashed_password="fake_hashed_password",
        disabled=True, # Usuário está desativado.
        created_at=datetime.now(timezone.utc)
    )
    print(f"\nTeste: get_current_active_user com usuário desativado (Username: {disabled_user_mock.username}).")

    # --- Act & Assert: Chamar a função e verificar a exceção ---
    # `get_current_active_user` é uma função simples que opera diretamente
    # no objeto `current_user` que lhe é passado (que seria o resultado de `get_current_user`).
    with pytest.raises(HTTPException) as exc_info:
        # Note que aqui `current_user` é um parâmetro direto da função, não uma dependência FastAPI no mesmo sentido.
        # Se `get_current_active_user` fosse uma dependência FastAPI completa com `Depends(get_current_user)`,
        # o teste seria estruturado de forma diferente, mockando a dependência `get_current_user`.
        await get_current_active_user(current_user=disabled_user_mock) 
    
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST, "Status code não é 400."
    assert "Usuário inativo" in exc_info.value.detail, "Mensagem de detalhe da exceção não é 'Usuário inativo'."
    print("  Sucesso: HTTPException 400 levantada para usuário desativado.")


async def test_get_current_active_user_when_user_is_active():
    """
    Testa `get_current_active_user` passando um objeto `UserInDB`
    que representa um usuário ativo (`disabled=False`).

    Verifica se:
    - A função retorna o mesmo objeto de usuário que foi passado.
    - Nenhuma exceção é levantada.
    """
    # Cria um mock de usuário ativo.
    active_user_mock = UserInDB(
        id=uuid.uuid4(),
        username="active_user",
        email="active_user@example.com",
        hashed_password="fake_hashed_password",
        disabled=False, 
        created_at=datetime.now(timezone.utc)
    )
    print(f"\nTeste: get_current_active_user com usuário ativo (Username: {active_user_mock.username}).")

    # --- Act: Chamar a função ---
    returned_user = await get_current_active_user(current_user=active_user_mock)

    # --- Assert: Verificar o resultado ---
    assert returned_user == active_user_mock, "Usuário ativo retornado não é o mesmo que foi passado."
    print("  Sucesso: get_current_active_user retornou o usuário ativo corretamente.")